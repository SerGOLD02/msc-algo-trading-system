"""
EODHD API service: fetches macro data (Treasury 2Y, CPI, Consumer Sentiment).
Rate limit: 20 calls/day. Schedule: 4 calls/day at 09:00, 15:30, 18:00 IT.
"""
import requests
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from database.models import MacroCache, PriceCache
from config import EODHD_API_KEY, EODHD_BASE_URL, MOVE_PROXY_SCALE


def _upsert_macro(db: Session, indicator: str, dt: str,
                  value: float, source: str):
    """Insert or update a macro cache record."""
    existing = (db.query(MacroCache)
                  .filter(MacroCache.indicator == indicator,
                          MacroCache.date == dt)
                  .first())
    if existing:
        existing.value = value
        existing.source = source
    else:
        db.add(MacroCache(
            indicator=indicator, date=dt,
            value=value, source=source
        ))


def _eodhd_get(endpoint: str, params: dict = None) -> dict | list | None:
    """Execute a single EODHD API call."""
    if not EODHD_API_KEY:
        print("[EODHD] No API key configured")
        return None

    url = f"{EODHD_BASE_URL}/{endpoint}"
    default_params = {"api_token": EODHD_API_KEY, "fmt": "json"}
    if params:
        default_params.update(params)

    try:
        r = requests.get(url, params=default_params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[EODHD] API error for {endpoint}: {e}")
        return None


def fetch_treasury_2y(db: Session) -> None:
    """Fetch US 2-Year Treasury yield from EODHD."""
    last_date = _get_last_cached_date(db, "USGG2YR")
    from_date = last_date or "2023-01-01"

    data = _eodhd_get(f"eod/US2Y.INDX", {"from": from_date})
    if not data:
        # Fallback: try bond endpoint
        data = _eodhd_get(f"eod/US02Y.BOND", {"from": from_date})

    if data and isinstance(data, list):
        count = 0
        for row in data:
            if "date" in row and "close" in row and row["close"]:
                _upsert_macro(db, "USGG2YR", row["date"],
                              float(row["close"]), "eodhd")
                count += 1
        db.commit()
        if count > 0:
            print(f"[EODHD] Stored {count} USGG2YR records")


def fetch_cpi_yoy(db: Session) -> None:
    """Fetch CPI YoY inflation from EODHD macro indicators."""
    data = _eodhd_get("macro-indicator/USA", {"indicator": "inflation_consumer_prices_annual"})

    if data and isinstance(data, list):
        count = 0
        for row in data:
            if "Date" in row and "Value" in row and row["Value"] is not None:
                _upsert_macro(db, "CPI_YOY", row["Date"][:10],
                              float(row["Value"]), "eodhd")
                count += 1
        db.commit()
        if count > 0:
            print(f"[EODHD] Stored {count} CPI_YOY records")


def fetch_consumer_sentiment(db: Session) -> None:
    """Fetch Consumer Confidence/Sentiment from EODHD."""
    data = _eodhd_get("macro-indicator/USA", {"indicator": "consumer_confidence_index"})

    if data and isinstance(data, list):
        count = 0
        for row in data:
            if "Date" in row and "Value" in row and row["Value"] is not None:
                _upsert_macro(db, "CONSSENT", row["Date"][:10],
                              float(row["Value"]), "eodhd")
                count += 1
        db.commit()
        if count > 0:
            print(f"[EODHD] Stored {count} CONSSENT records")


def compute_move_proxy(db: Session) -> None:
    """
    Compute MOVE index proxy from TLT 20-day realized volatility.
    MOVE = TLT daily returns std(20) * sqrt(252) * MOVE_PROXY_SCALE
    """
    rows = (db.query(PriceCache)
              .filter(PriceCache.ticker == "TLT")
              .order_by(PriceCache.date.asc())
              .all())

    if len(rows) < 30:
        return

    dates = [r.date for r in rows]
    closes = pd.Series([r.close for r in rows], index=pd.Index(dates))
    returns = closes.pct_change().dropna()

    # 20-day rolling realized vol, annualized
    rvol_20 = returns.rolling(20).std() * np.sqrt(252) * MOVE_PROXY_SCALE
    rvol_20 = rvol_20.dropna()

    count = 0
    for dt, val in rvol_20.items():
        if not np.isnan(val):
            _upsert_macro(db, "MOVE", str(dt),
                          round(float(val), 4), "proxy")
            count += 1

    db.commit()
    if count > 0:
        print(f"[EODHD] Computed {count} MOVE proxy records")


def refresh_all_macro(db: Session) -> None:
    """
    Refresh all macro data. Called 4x/day by scheduler.
    Uses 3 EODHD API calls per refresh (within 20/day limit).
    """
    print(f"[EODHD] Macro refresh at {datetime.now().isoformat()}")
    fetch_treasury_2y(db)
    fetch_cpi_yoy(db)
    fetch_consumer_sentiment(db)
    compute_move_proxy(db)


def get_macro_series(db: Session, indicator: str,
                     from_date: str = None) -> pd.Series:
    """Get macro indicator time series from cache."""
    query = db.query(MacroCache).filter(MacroCache.indicator == indicator)
    if from_date:
        query = query.filter(MacroCache.date >= from_date)
    rows = query.order_by(MacroCache.date.asc()).all()

    if not rows:
        return pd.Series(dtype=float)

    return pd.Series(
        {r.date: r.value for r in rows},
        dtype=float
    )


def _get_last_cached_date(db: Session, indicator: str) -> str | None:
    """Get the most recent cached date for an indicator."""
    row = (db.query(MacroCache)
             .filter(MacroCache.indicator == indicator)
             .order_by(MacroCache.date.desc())
             .first())
    return row.date if row else None
