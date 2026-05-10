"""
Segnale della Settimana: assembla i segnali per un dato venerdì.
Per ogni ratio: direzione (TFM), bet quality (LGB/fallback), stato.
"""
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from database.models import InferenceCache, PriceCache, BacktestResult
from config import (RATIOS, DISPLAY_START, DEFAULT_BET_QUALITY,
                    CRISIS_STATE_IDX)


def get_available_fridays(db: Session) -> list[str]:
    from modules.backtest.service import _get_operational_fridays
    
    # Fix 6: available fridays based on operational days with data
    fridays = _get_operational_fridays(db)
    
    # Filter only those that have inference data cached
    inf_dates = (db.query(InferenceCache.friday_date)
                   .distinct()
                   .all())
    inf_dates_set = {r[0] for r in inf_dates}
    
    available = [str(f.date()) for f in fridays if str(f.date()) in inf_dates_set]
    available = sorted(available, reverse=True)
    
    # Also filter by DISPLAY_START
    available = [f for f in available if f >= DISPLAY_START]
    
    return available


def get_weekly_signals(db: Session, friday: str | None = None,
                       threshold: float = DEFAULT_BET_QUALITY) -> dict:
    available = get_available_fridays(db)
    if not available:
        return {
            "friday_date": "", "available_fridays": [],
            "regime_id": 0, "regime_name": "N/D",
            "is_crisis": False, "n_active": 0, "n_filtered": 0,
            "signals": []
        }

    if friday is None or friday not in available:
        friday = available[0]

    # Load inferences for this Friday
    inf_rows = (db.query(InferenceCache)
                  .filter(InferenceCache.friday_date == friday)
                  .all())
    inf_map = {}
    for r in inf_rows:
        inf_map[r.ratio_id] = {
            "tfm_t5": r.tfm_t5,
            "chr_median_t5": r.chr_median_t5,
            "chr_width_t5": r.chr_width_t5,
        }

    # Get current ratio values from prices
    ratio_values = _get_ratio_values(db, friday)

    # Get regime for this Friday from backtest results
    regime_id, regime_name, is_crisis = _get_regime_for_friday(db, friday)

    signals = []
    n_active = 0
    n_filtered = 0

    for ratio_id, (num, den) in RATIOS.items():
        inf = inf_map.get(ratio_id)
        cur_ratio = ratio_values.get(ratio_id)

        if inf is None or cur_ratio is None:
            signals.append({
                "ratio_id": ratio_id,
                "numerator": num,
                "denominator": den,
                "direction": "N/A",
                "long_ticker": "",
                "short_ticker": "",
                "bet_quality": 0.0,
                "is_active": False,
                "status": "no_data",
                "tfm_t5": None,
                "tfm_projection": None,
                "current_ratio": cur_ratio,
                "chr_median_t5": None,
                "chr_width_t5": None,
            })
            continue

        tfm_t5 = inf["tfm_t5"]
        if tfm_t5 is None or np.isnan(tfm_t5):
            signals.append({
                "ratio_id": ratio_id,
                "numerator": num,
                "denominator": den,
                "direction": "N/A",
                "long_ticker": "",
                "short_ticker": "",
                "bet_quality": 0.0,
                "is_active": False,
                "status": "no_data",
                "tfm_t5": None,
                "tfm_projection": None,
                "current_ratio": cur_ratio,
                "chr_median_t5": inf.get("chr_median_t5"),
                "chr_width_t5": inf.get("chr_width_t5"),
            })
            continue

        # Direction: TFM_t5 > current → long numerator
        if tfm_t5 > cur_ratio:
            direction = "LONG_NUM"
            long_tick = num
            short_tick = den
        else:
            direction = "LONG_DEN"
            long_tick = den
            short_tick = num

        # Bet quality (fallback: Chronos width-based)
        chr_width = inf.get("chr_width_t5")
        if chr_width is not None and not np.isnan(chr_width):
            bq = max(0.0, min(1.0, 1.0 - abs(chr_width)))
        else:
            bq = 0.55

        # Fix 4: Proper state mapping logic
        if is_crisis:
            is_active = False
            status = "crisis"
        elif bq < threshold:
            is_active = False
            status = "filtrato"
        else:
            is_active = True
            status = "attivo"
            
        if is_active:
            n_active += 1
        else:
            n_filtered += 1

        # TFM projection direction
        tfm_proj = None
        if abs(tfm_t5 - cur_ratio) > 1e-8:
            tfm_proj = "BULLISH" if tfm_t5 > cur_ratio else "BEARISH"

        signals.append({
            "ratio_id": ratio_id,
            "numerator": num,
            "denominator": den,
            "direction": direction,
            "long_ticker": long_tick,
            "short_ticker": short_tick,
            "bet_quality": round(bq, 4),
            "is_active": is_active,
            "status": status,
            "tfm_t5": round(tfm_t5, 6),
            "tfm_projection": tfm_proj,
            "current_ratio": round(cur_ratio, 6),
            "chr_median_t5": round(inf.get("chr_median_t5") or 0, 6),
            "chr_width_t5": round(inf.get("chr_width_t5") or 0, 6),
        })

    # Sort by bet_quality descending
    signals.sort(key=lambda s: s["bet_quality"], reverse=True)

    # Compute realized returns for past Fridays (Task 1.4 + Fix 4)
    # If the selected Friday is the very last one, we don't have realized returns yet
    if friday != available[0]:
        next_fri = _get_next_friday(friday, available)
        if next_fri:
            for sig in signals:
                if sig["is_active"] and sig["long_ticker"]:
                    sig["realized_return"] = _compute_realized_return(
                        db, sig["long_ticker"], friday, next_fri)
                else:
                    sig["realized_return"] = None
        else:
            for sig in signals:
                sig["realized_return"] = None
    else:
        for sig in signals:
            sig["realized_return"] = None

    return {
        "friday_date": friday,
        "available_fridays": available,
        "regime_id": regime_id,
        "regime_name": regime_name,
        "is_crisis": is_crisis,
        "n_active": n_active,
        "n_filtered": n_filtered,
        "signals": signals,
    }


def _get_ratio_values(db: Session, friday: str) -> dict:
    """Get log-ratio values for a specific Friday."""
    ratio_vals = {}
    for ratio_id, (num, den) in RATIOS.items():
        p_num = (db.query(PriceCache)
                   .filter(PriceCache.ticker == num,
                           PriceCache.date == friday)
                   .first())
        p_den = (db.query(PriceCache)
                   .filter(PriceCache.ticker == den,
                           PriceCache.date == friday)
                   .first())
        if p_num and p_den and p_den.close > 0 and p_num.close > 0:
            ratio_vals[ratio_id] = float(
                np.log(p_num.close) - np.log(p_den.close)
            )
    return ratio_vals


def _get_regime_for_friday(db: Session, friday: str) -> tuple:
    from modules.hmm.service import REGIME_NAMES
    bt = (db.query(BacktestResult)
            .filter(BacktestResult.friday_date == friday)
            .first())
    if bt:
        regime_id = bt.regime or 0
        return (
            regime_id,
            REGIME_NAMES.get(regime_id, f"Stato {regime_id}"),
            bt.is_crisis or False
        )

    # Fallback: use nearest prior backtest result
    prev = (db.query(BacktestResult)
              .filter(BacktestResult.friday_date < friday)
              .order_by(BacktestResult.friday_date.desc())
              .first())
    if prev:
        regime_id = prev.regime or 0
        return (
            regime_id,
            REGIME_NAMES.get(regime_id, f"Stato {regime_id}"),
            prev.is_crisis or False
        )

    return (0, "N/D", False)


def _compute_realized_return(db: Session, ticker: str,
                              entry_friday: str, exit_friday: str):
    """Compute simple return for a ticker between two Fridays."""
    p0 = (db.query(PriceCache)
             .filter(PriceCache.ticker == ticker,
                     PriceCache.date == entry_friday)
             .first())
    p1 = (db.query(PriceCache)
             .filter(PriceCache.ticker == ticker,
                     PriceCache.date == exit_friday)
             .first())
    if p0 and p1 and p0.close and p0.close > 0:
        return round((p1.close - p0.close) / p0.close, 6)
    return None


def _get_next_friday(friday: str, available_fridays: list[str]):
    """Get the next Friday after the given one (available is sorted desc)."""
    try:
        idx = available_fridays.index(friday)
    except ValueError:
        return None
    if idx > 0:
        return available_fridays[idx - 1]
    return None
