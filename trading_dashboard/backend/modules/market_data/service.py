import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from database.models import PriceCache, Metadata
from config import ETF_UNIVERSE, DISPLAY_START, WARMUP_START

ET = ZoneInfo("America/New_York")

INDEX_MAP = {
    "S&P 500":     "SPY",
    "Nasdaq 100":  "QQQ",
    "Russell 2000":"IWM",
    "Treasury 20Y":"TLT",
    "Oro":         "GLD",
    "VIX":         "^VIX",
}


def is_market_open() -> bool:
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        return False
    market_open  = now_et.replace(hour=9,  minute=30, second=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0)
    return market_open <= now_et <= market_close


def get_next_friday_close_et() -> datetime:
    """
    Restituisce il prossimo venerdì alle 16:00 ET.
    Se siamo venerdì prima delle 16:00 ET, restituisce oggi alle 16:00.
    """
    from datetime import timedelta
    now_et = datetime.now(ET)
    days_ahead = (4 - now_et.weekday()) % 7
    if days_ahead == 0 and now_et.hour >= 16:
        days_ahead = 7
    next_fri = now_et + timedelta(days=days_ahead)
    next_fri = next_fri.replace(hour=16, minute=0, second=0, microsecond=0)
    return next_fri


def seconds_to_next_friday_close() -> int:
    now_et  = datetime.now(ET)
    target  = get_next_friday_close_et()
    delta   = target - now_et
    return max(0, int(delta.total_seconds()))


def refresh_prices(db: Session, initial: bool = False) -> None:
    """
    Scarica prezzi aggiornati da YFinance e li salva in PriceCache.
    initial=True scarica da WARMUP_START (primo avvio);
    initial=False scarica solo gli ultimi 2 giorni (refresh periodico).
    """
    tickers = list(dict.fromkeys(
        ETF_UNIVERSE + ["^VIX", "DX-Y.NYB", "GC=F", "SI=F",
                         "^TNX", "^IRX", "FXE"]
    ))

    period = None
    start_date = None
    if initial:
        start_date = WARMUP_START
        print(f"[market_data] Initial download from {WARMUP_START}...")
    else:
        period = "5d"

    try:
        kwargs = dict(
            tickers=tickers,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
        if start_date:
            kwargs["start"] = start_date
        else:
            kwargs["period"] = period

        raw = yf.download(**kwargs)
    except Exception as e:
        print(f"[market_data] YFinance download error: {e}")
        return

    if raw is None or raw.empty:
        print("[market_data] YFinance returned empty data")
        return

    count = 0
    for ticker in tickers:
        clean_ticker = ticker.replace("^", "").replace("=F", "").\
            replace("-Y.NYB", "")
        # Mapping ticker speciali
        if ticker == "DX-Y.NYB":
            clean_ticker = "DXY"
        elif ticker == "GC=F":
            clean_ticker = "GC"
        elif ticker == "SI=F":
            clean_ticker = "SI"
        elif ticker == "^VIX":
            clean_ticker = "VIX"
        elif ticker == "^TNX":
            clean_ticker = "TNX"
        elif ticker == "^IRX":
            clean_ticker = "IRX"

        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker in raw.columns.get_level_values(0):
                    df = raw[ticker].dropna(subset=["Close"])
                else:
                    continue
            else:
                # Single ticker case
                df = raw.dropna(subset=["Close"])

            if len(df) == 0:
                continue

            for idx_date, row in df.iterrows():
                date_str = str(idx_date.date())
                close_val = float(row["Close"])
                if np.isnan(close_val):
                    continue

                existing = db.query(PriceCache).filter_by(
                    ticker=clean_ticker, date=date_str
                ).first()

                if existing:
                    existing.close = close_val
                    existing.open = float(row.get("Open", close_val))
                    existing.high = float(row.get("High", close_val))
                    existing.low = float(row.get("Low", close_val))
                    existing.volume = float(row.get("Volume", 0))
                else:
                    db.add(PriceCache(
                        ticker=clean_ticker,
                        date=date_str,
                        close=close_val,
                        open=float(row.get("Open", close_val)),
                        high=float(row.get("High", close_val)),
                        low=float(row.get("Low", close_val)),
                        volume=float(row.get("Volume", 0)),
                    ))
                count += 1

        except Exception as e:
            print(f"[market_data] Error processing {ticker}: {e}")
            db.rollback()
            continue

    try:
        db.commit()
    except Exception as e:
        print(f"[market_data] Commit error: {e}")
        db.rollback()

    db.merge(Metadata(key="last_price_update",
                       value=datetime.now().isoformat()))
    db.commit()
    print(f"[market_data] Saved {count} price records")


def _compute_returns(db: Session, ticker: str, last_price: float) -> dict:
    """Compute 1D, 1W, 1M, 1Y and YTD returns from PriceCache."""
    from datetime import date, timedelta

    today = date.today()
    # Get all prices for this ticker ordered by date desc (for efficiency)
    all_prices = (db.query(PriceCache.date, PriceCache.close)
                    .filter(PriceCache.ticker == ticker)
                    .order_by(PriceCache.date.desc())
                    .all())

    if not all_prices:
        return {"change_1d_pct": 0.0, "change_1w_pct": 0.0,
                "change_1m_pct": 0.0, "change_1y_pct": 0.0,
                "change_ytd_pct": 0.0}

    # Build a date->close lookup
    price_map = {row.date: row.close for row in all_prices}
    dates_sorted = sorted(price_map.keys(), reverse=True)

    def _find_price_near(target_str: str) -> float | None:
        """Find the closest price on or before target date."""
        for d in dates_sorted:
            if d <= target_str:
                return price_map[d]
        return None

    # 1D: previous trading day
    prev_1d = price_map.get(dates_sorted[1]) if len(dates_sorted) > 1 else None
    chg_1d = ((last_price - prev_1d) / prev_1d * 100) if prev_1d else 0.0

    # 1W: ~5 trading days ago
    target_1w = (today - timedelta(days=7)).isoformat()
    p_1w = _find_price_near(target_1w)
    chg_1w = ((last_price - p_1w) / p_1w * 100) if p_1w else 0.0

    # 1M: ~22 trading days ago
    target_1m = (today - timedelta(days=30)).isoformat()
    p_1m = _find_price_near(target_1m)
    chg_1m = ((last_price - p_1m) / p_1m * 100) if p_1m else 0.0

    # 1Y: ~252 trading days ago
    target_1y = (today - timedelta(days=365)).isoformat()
    p_1y = _find_price_near(target_1y)
    chg_1y = ((last_price - p_1y) / p_1y * 100) if p_1y else 0.0

    # YTD: from Jan 1 of current year
    ytd_start = f"{today.year}-01-01"
    p_ytd = _find_price_near(ytd_start)
    # If no price found before/on Jan 1, try first available in this year
    if p_ytd is None:
        for d in sorted(price_map.keys()):
            if d >= ytd_start:
                p_ytd = price_map[d]
                break
    chg_ytd = ((last_price - p_ytd) / p_ytd * 100) if p_ytd else 0.0

    return {
        "change_1d_pct": round(chg_1d, 2),
        "change_1w_pct": round(chg_1w, 2),
        "change_1m_pct": round(chg_1m, 2),
        "change_1y_pct": round(chg_1y, 2),
        "change_ytd_pct": round(chg_ytd, 2),
    }


def get_market_snapshot(db: Session) -> dict:
    """
    Costruisce lo snapshot di mercato per il frontend.
    Legge da PriceCache per i valori attuali.
    Calcola change_1d e change_ytd.
    """
    indices = []
    for name, ticker in INDEX_MAP.items():
        clean = ticker.replace("^", "")
        rows = (db.query(PriceCache)
                  .filter(PriceCache.ticker == clean)
                  .order_by(PriceCache.date.desc())
                  .limit(1).all())

        if len(rows) == 0:
            continue

        last_price = rows[0].close
        returns = _compute_returns(db, clean, last_price)

        indices.append({
            "name": name, "ticker": ticker,
            "last_price": round(last_price, 2),
            **returns,
        })

    assets = []
    for ticker in ETF_UNIVERSE:
        rows = (db.query(PriceCache)
                  .filter(PriceCache.ticker == ticker)
                  .order_by(PriceCache.date.desc())
                  .limit(1).all())
        if len(rows) == 0:
            continue

        last_price = rows[0].close
        returns = _compute_returns(db, ticker, last_price)

        assets.append({
            "ticker": ticker,
            "last_price": round(last_price, 2),
            **returns,
            "volume": float(rows[0].volume or 0),
            "is_etf": True,
        })

    last_meta = db.query(Metadata).filter_by(
        key="last_price_update"
    ).first()

    return {
        "indices": indices,
        "assets":  assets,
        "last_updated": last_meta.value if last_meta else "",
        "market_open": is_market_open(),
        "next_friday": get_next_friday_close_et().strftime("%Y-%m-%d"),
        "seconds_to_friday_close": seconds_to_next_friday_close(),
    }
