"""
Analytics service: decay history, correlation heatmap, drawdown, chronos bands.
"""
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from database.models import (BacktestResult, PriceCache, InferenceCache)
from config import (RATIOS, ETF_UNIVERSE, DISPLAY_START,
                    DEFAULT_BET_QUALITY, CRISIS_STATE_IDX,
                    DEFAULT_HRP_ALPHA, DEFAULT_K_SIGMOID,
                    DEFAULT_C_SOGLIA, DEFAULT_K_UP, DEFAULT_K_DOWN)


REGIME_NAMES = {
    0: "Growth",
    1: "Moderate Growth",
    2: "Consolidation",
    3: "Stress",
    4: "Crisis"
}


def get_operational_status(db: Session) -> dict:
    """Returns at-a-glance operational status for the header."""
    from modules.backtest.service import params_to_hash
    from modules.backtest.schemas import BacktestParams
    
    # Create default params object
    default_params = BacktestParams(
        bet_quality=DEFAULT_BET_QUALITY,
        hrp_alpha=DEFAULT_HRP_ALPHA,
        k_sigmoid=DEFAULT_K_SIGMOID,
        c_soglia=DEFAULT_C_SOGLIA,
        k_up=DEFAULT_K_UP,
        k_down=DEFAULT_K_DOWN
    )
    default_hash = params_to_hash(default_params)
    
    # Get the most recent Friday's data with default params
    row = (db.query(BacktestResult)
             .filter(BacktestResult.params_hash == default_hash)
             .order_by(BacktestResult.friday_date.desc())
             .first())
    
    if not row:
        return {
            "n_active_trades": 0,
            "regime_name": "N/D",
            "regime_id": 0,
            "is_crisis": False,
            "decay_value": 1.0,
            "last_friday": ""
        }
    
    regime_id = row.regime or 0
    return {
        "n_active_trades": row.n_trades or 0,
        "regime_name": REGIME_NAMES.get(regime_id, f"Stato {regime_id}"),
        "regime_id": regime_id,
        "is_crisis": bool(row.is_crisis),
        "decay_value": round(row.decay_value or 1.0, 4),
        "last_friday": row.friday_date or "",
    }


def get_decay_history(db: Session) -> dict:
    """
    Returns sigmoid decay + rolling correlation for each Friday
    in the backtest period.
    """
    rows = (db.query(BacktestResult)
              .filter(BacktestResult.friday_date >= DISPLAY_START)
              .order_by(BacktestResult.friday_date.asc())
              .all())

    if not rows:
        return {"series": []}

    # Compute rolling correlation from prices
    corr_map = _compute_rolling_correlation(db)

    seen = set()
    series = []
    for r in rows:
        if r.friday_date in seen:
            continue
        seen.add(r.friday_date)
        avg_corr = corr_map.get(r.friday_date, 0.0)
        series.append({
            "date": r.friday_date,
            "decay_value": round(r.decay_value or 1.0, 4),
            "avg_correlation": round(avg_corr, 4),
            "regime": r.regime or 0,
        })

    return {"series": series}


def _compute_rolling_correlation(db: Session) -> dict:
    """Compute 8-week rolling average pairwise correlation."""
    from modules.backtest.service import _get_operational_fridays
    
    tradable = [t for t in ETF_UNIVERSE
                if t not in ("SH", "PSQ", "RWM", "VIXY", "FXE")]

    prices = {}
    for ticker in tradable:
        rows = (db.query(PriceCache.date, PriceCache.close)
                  .filter(PriceCache.ticker == ticker)
                  .order_by(PriceCache.date.asc())
                  .all())
        if rows:
            prices[ticker] = pd.Series(
                {r.date: r.close for r in rows}, dtype=float
            )

    if len(prices) < 5:
        return {}

    closes = pd.DataFrame(prices)
    closes.index = pd.to_datetime(closes.index)
    closes.sort_index(inplace=True)

    # Fix 6: Use operational fridays
    fridays = _get_operational_fridays(db)
    weekly = closes.reindex(fridays, method="ffill")
    rets = weekly.pct_change().dropna()

    corr_map = {}
    for i in range(8, len(rets)):
        window = rets.iloc[i - 8:i]
        corr = window.corr()
        n = corr.shape[0]
        vals = [corr.iloc[r, c]
                for r in range(n)
                for c in range(r + 1, n)
                if not np.isnan(corr.iloc[r, c])]
        avg = float(np.mean(vals)) if vals else 0.0
        fri_str = str(rets.index[i].date())
        corr_map[fri_str] = avg

    return corr_map


WINDOW_DAYS = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "52w": 260,
}


def get_correlation_heatmap(db: Session, window: str = "52w",
                            ordering: str = "alphabetical") -> dict:
    """Returns 26x26 correlation matrix for tradable ETFs."""
    n_days = WINDOW_DAYS.get(window, 260)

    tradable = [t for t in ETF_UNIVERSE
                if t not in ("FXE",)][:26]

    prices = {}
    for ticker in tradable:
        rows = (db.query(PriceCache.date, PriceCache.close)
                  .filter(PriceCache.ticker == ticker)
                  .order_by(PriceCache.date.asc())
                  .all())
        if rows:
            prices[ticker] = pd.Series(
                {r.date: r.close for r in rows}, dtype=float
            )

    if len(prices) < 5:
        return {"tickers": [], "matrix": [], "as_of_date": "", "window": window,
                "avg_correlation": 0.0, "max_correlation": 0.0, "n_high_pairs": 0}

    closes = pd.DataFrame(prices)
    closes.index = pd.to_datetime(closes.index)
    closes.sort_index(inplace=True)

    rets = closes.pct_change().dropna()
    rets = rets.iloc[-n_days:] if len(rets) > n_days else rets

    corr = rets.corr()

    # Apply hierarchical ordering if requested
    if ordering == "hierarchical" and corr.shape[0] >= 3:
        try:
            from scipy.cluster.hierarchy import linkage, leaves_list
            from scipy.spatial.distance import squareform

            dist = 1 - corr.fillna(0).values
            np.fill_diagonal(dist, 0)
            dist = (dist + dist.T) / 2  # ensure symmetry
            dist = np.clip(dist, 0, None)  # no negative distances

            condensed = squareform(dist, checks=False)
            Z = linkage(condensed, method='ward')
            order = leaves_list(Z)

            ordered_cols = [corr.columns[i] for i in order]
            corr = corr.loc[ordered_cols, ordered_cols]
        except Exception as e:
            print(f"[analytics] Hierarchical ordering failed: {e}")

    tickers = list(corr.columns)
    matrix = corr.fillna(0).values.tolist()

    as_of = str(closes.index[-1].date()) if len(closes) > 0 else ""

    # Compute KPIs from upper triangle
    n_tickers = len(tickers)
    upper_vals = []
    for i in range(n_tickers):
        for j in range(i + 1, n_tickers):
            v = corr.iloc[i, j]
            if not np.isnan(v):
                upper_vals.append(v)
    
    avg_corr = float(np.mean(upper_vals)) if upper_vals else 0.0
    max_corr = float(max(abs(v) for v in upper_vals)) if upper_vals else 0.0
    n_high = sum(1 for v in upper_vals if abs(v) > 0.80)

    return {
        "tickers": tickers,
        "matrix": [[round(v, 4) for v in row] for row in matrix],
        "as_of_date": as_of,
        "window": window,
        "avg_correlation": round(avg_corr, 4),
        "max_correlation": round(max_corr, 4),
        "n_high_pairs": n_high,
    }


def get_drawdown(db: Session) -> dict:
    """Compute drawdown from ATH for normal, crisis, and combined modes."""
    rows = (db.query(BacktestResult)
              .filter(BacktestResult.friday_date >= DISPLAY_START)
              .order_by(BacktestResult.friday_date.asc())
              .all())

    if not rows:
        empty = {
            "current_drawdown_pct": 0.0, "max_drawdown_pct": 0.0,
            "days_since_peak": 0, "peak_date": "", "peak_value": 1.0,
            "current_value": 1.0
        }
        return {
            "normal": empty, "crisis": empty,
            "combined": empty, "as_of_date": "", "history": []
        }

    # Deduplicate by friday_date (take first params_hash)
    seen = {}
    for r in rows:
        if r.friday_date not in seen:
            seen[r.friday_date] = r

    sorted_rows = sorted(seen.values(), key=lambda r: r.friday_date)

    combined_dd = _compute_dd_from_rows(sorted_rows)
    
    # Compute drawdown history for the combined series
    history = []
    if sorted_rows:
        peak_val = sorted_rows[0].portfolio_value
        for r in sorted_rows:
            if r.portfolio_value > peak_val:
                peak_val = r.portfolio_value
            dd_pct = ((r.portfolio_value - peak_val) / peak_val) * 100 if peak_val > 0 else 0.0
            history.append({"date": r.friday_date, "drawdown_pct": round(dd_pct, 2)})
    
    normal_rows = [r for r in sorted_rows if not r.is_crisis]
    crisis_rows = [r for r in sorted_rows if r.is_crisis]

    normal_dd = _compute_dd_from_rows(normal_rows) if normal_rows else {
        "current_drawdown_pct": 0.0, "max_drawdown_pct": 0.0,
        "days_since_peak": 0, "peak_date": "", "peak_value": 1.0,
        "current_value": 1.0
    }
    crisis_dd = _compute_dd_from_rows(crisis_rows) if crisis_rows else {
        "current_drawdown_pct": 0.0, "max_drawdown_pct": 0.0,
        "days_since_peak": 0, "peak_date": "", "peak_value": 1.0,
        "current_value": 1.0
    }

    return {
        "normal": normal_dd,
        "crisis": crisis_dd,
        "combined": combined_dd,
        "as_of_date": sorted_rows[-1].friday_date if sorted_rows else "",
        "history": history,
    }


def _compute_dd_from_rows(rows) -> dict:
    if not rows:
        return {
            "current_drawdown_pct": 0.0, "max_drawdown_pct": 0.0,
            "days_since_peak": 0, "peak_date": "", "peak_value": 1.0,
            "current_value": 1.0
        }

    values = [r.portfolio_value for r in rows]
    dates = [r.friday_date for r in rows]

    peak_val = values[0]
    peak_date = dates[0]
    max_dd = 0.0

    for i, v in enumerate(values):
        if v > peak_val:
            peak_val = v
            peak_date = dates[i]
        dd = (v - peak_val) / peak_val
        if dd < max_dd:
            max_dd = dd

    current_val = values[-1]
    current_dd = (current_val - peak_val) / peak_val if peak_val > 0 else 0.0

    # Days since peak
    from datetime import datetime
    try:
        peak_dt = datetime.strptime(peak_date, "%Y-%m-%d")
        last_dt = datetime.strptime(dates[-1], "%Y-%m-%d")
        days_since = (last_dt - peak_dt).days
    except Exception:
        days_since = 0

    return {
        "current_drawdown_pct": round(current_dd * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "days_since_peak": days_since,
        "peak_date": peak_date,
        "peak_value": round(peak_val, 6),
        "current_value": round(current_val, 6),
    }


def get_chronos_bands(db: Session, friday: str | None = None) -> dict:
    """
    Returns Chronos confidence bands for all ratios on a specific Friday.
    Uses normal approximation: band = median ± 1.645 * (width/2).
    """
    from modules.signals.service import get_available_fridays
    
    # Fix 6: available_fridays now derived from operational ones
    available_fridays = get_available_fridays(db)

    if friday is None:
        if available_fridays:
            friday = available_fridays[0]
        else:
            return {"friday_date": "", "available_fridays": [], "bands": []}

    inf_rows = (db.query(InferenceCache)
                  .filter(InferenceCache.friday_date == friday)
                  .all())

    if not inf_rows:
        return {"friday_date": friday, "available_fridays": available_fridays, "bands": []}

    # Get current ratio values
    ratio_values = {}
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
            ratio_values[ratio_id] = float(
                np.log(p_num.close) - np.log(p_den.close)
            )

    bands = []
    for r in inf_rows:
        ratio_id = r.ratio_id
        if ratio_id not in RATIOS:
            continue
        num, den = RATIOS[ratio_id]

        median = r.chr_median_t5 or 0.0
        width = r.chr_width_t5 or 0.0
        sigma = abs(width) / 2.0
        upper = median + 1.645 * sigma
        lower = median - 1.645 * sigma

        cur_val = ratio_values.get(ratio_id, 0.0)
        tfm_t5 = r.tfm_t5  # None if not available

        # Direction
        tfm_val = tfm_t5 if tfm_t5 is not None else 0.0
        if tfm_val > cur_val:
            direction = "LONG_NUM"
        else:
            direction = "LONG_DEN"

        # Active?
        bq = max(0.0, min(1.0, 1.0 - abs(width)))
        is_active = bq >= DEFAULT_BET_QUALITY

        # TFM projection: BULLISH if tfm_t5 > current, BEARISH if <
        tfm_projection = None
        if tfm_t5 is not None and cur_val != 0.0:
            if abs(tfm_t5 - cur_val) > 1e-8:
                tfm_projection = "BULLISH" if tfm_t5 > cur_val else "BEARISH"

        bands.append({
            "ratio_id": ratio_id,
            "numerator": num,
            "denominator": den,
            "current_value": round(cur_val, 6),
            "median": round(median, 6),
            "upper_95": round(upper, 6),
            "lower_5": round(lower, 6),
            "tfm_t5": round(tfm_t5, 6) if tfm_t5 is not None else None,
            "tfm_projection": tfm_projection,
            "direction": direction,
            "is_active": is_active,
        })

    bands.sort(key=lambda b: b["ratio_id"])

    return {"friday_date": friday, "available_fridays": available_fridays, "bands": bands}


def get_yearly_breakdown(db: Session) -> dict:
    """Compute per-year performance breakdown."""
    from modules.backtest.service import params_to_hash
    from modules.backtest.schemas import BacktestParams
    from config import (DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
                        DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA,
                        DEFAULT_K_UP, DEFAULT_K_DOWN)
    
    default_params = BacktestParams(
        bet_quality=DEFAULT_BET_QUALITY, hrp_alpha=DEFAULT_HRP_ALPHA,
        k_sigmoid=DEFAULT_K_SIGMOID, c_soglia=DEFAULT_C_SOGLIA,
        k_up=DEFAULT_K_UP, k_down=DEFAULT_K_DOWN
    )
    default_hash = params_to_hash(default_params)
    
    rows = (db.query(BacktestResult)
              .filter(BacktestResult.params_hash == default_hash)
              .order_by(BacktestResult.friday_date.asc())
              .all())
    
    if not rows:
        return {"years": []}
    
    # Group by year
    from collections import defaultdict
    by_year = defaultdict(list)
    for r in rows:
        year = int(r.friday_date[:4])
        by_year[year].append(r)
    
    # Get SPY prices
    spy_rows = (db.query(PriceCache)
                  .filter(PriceCache.ticker == "SPY")
                  .order_by(PriceCache.date.asc())
                  .all())
    spy_prices = {r.date: r.close for r in spy_rows}
    
    years_data = []
    for year in sorted(by_year.keys()):
        year_rows = by_year[year]
        if len(year_rows) < 2:
            continue
        
        # Normalize portfolio values to start at 1.0
        base_val = year_rows[0].portfolio_value
        if base_val <= 0:
            continue
        norm_values = [r.portfolio_value / base_val for r in year_rows]
        weekly_rets = pd.Series([r.weekly_return for r in year_rows])
        
        n = len(norm_values)
        pv = pd.Series(norm_values)
        tot_ret = pv.iloc[-1] - 1
        cagr = (1 + tot_ret) ** (52 / n) - 1 if n > 1 else 0
        sharpe = (weekly_rets.mean() * 52) / (weekly_rets.std() * np.sqrt(52)) if weekly_rets.std() > 0 else 0
        running_max = pv.cummax()
        max_dd = ((pv - running_max) / running_max).min()
        
        # SPY for same dates
        spy_vals = []
        for r in year_rows:
            if r.friday_date in spy_prices:
                spy_vals.append(spy_prices[r.friday_date])
        
        spy_cagr = spy_sharpe = spy_max_dd = spy_tot_ret = 0.0
        if len(spy_vals) >= 2:
            spy_base = spy_vals[0]
            spy_norm = pd.Series([v / spy_base for v in spy_vals])
            spy_tot_ret = spy_norm.iloc[-1] - 1
            spy_cagr = (1 + spy_tot_ret) ** (52 / len(spy_norm)) - 1 if len(spy_norm) > 1 else 0
            spy_wr = spy_norm.pct_change().dropna()
            spy_sharpe = (spy_wr.mean() * 52) / (spy_wr.std() * np.sqrt(52)) if spy_wr.std() > 0 else 0
            spy_running = spy_norm.cummax()
            spy_max_dd = ((spy_norm - spy_running) / spy_running).min()
        
        years_data.append({
            "year": year,
            "cagr": round(float(cagr), 4),
            "sharpe": round(float(sharpe), 4),
            "max_drawdown": round(float(max_dd), 4),
            "total_return": round(float(tot_ret), 4),
            "n_weeks": n,
            "spy_cagr": round(float(spy_cagr), 4),
            "spy_sharpe": round(float(spy_sharpe), 4),
            "spy_max_drawdown": round(float(spy_max_dd), 4),
            "spy_total_return": round(float(spy_tot_ret), 4),
        })
    
    return {"years": years_data}


# ────────────────────────────────────────────────────────────
# Task 1.2: Per-ETF performance
# ────────────────────────────────────────────────────────────

def get_etf_performance(db: Session, start_date: str | None = None) -> dict:
    """
    For each ETF, compute algo cumulative return (when it was signalled),
    buy-and-hold return, alpha, and trade count.
    """
    from modules.signals.service import get_weekly_signals, get_available_fridays

    effective_start = start_date or DISPLAY_START

    # Fix 6: available_fridays derived from operational ones
    all_fridays = get_available_fridays(db)
    fridays_in_range = sorted(
        [f for f in all_fridays if f >= effective_start]
    )

    if len(fridays_in_range) < 2:
        return {"start_date": effective_start, "end_date": "", "etfs": []}

    # Accumulate per-ticker returns
    from collections import defaultdict
    ticker_returns = defaultdict(list)  # ticker -> list of weekly returns

    for i in range(len(fridays_in_range) - 1):
        fri = fridays_in_range[i]
        next_fri = fridays_in_range[i + 1]

        sigs = get_weekly_signals(db, fri)
        for s in sigs.get("signals", []):
            if not s.get("is_active") or not s.get("long_ticker"):
                continue
            tick = s["long_ticker"]
            p0 = (db.query(PriceCache)
                     .filter(PriceCache.ticker == tick,
                             PriceCache.date == fri)
                     .first())
            p1 = (db.query(PriceCache)
                     .filter(PriceCache.ticker == tick,
                             PriceCache.date == next_fri)
                     .first())
            if p0 and p1 and p0.close and p0.close > 0:
                ret = (p1.close - p0.close) / p0.close
                ticker_returns[tick].append(ret)

    # B&H for each ETF
    first_fri = fridays_in_range[0]
    last_fri = fridays_in_range[-1]

    etfs = []
    all_tickers = sorted(set(
        list(ticker_returns.keys()) + ETF_UNIVERSE
    ))

    for tick in all_tickers:
        rets = ticker_returns.get(tick, [])
        if rets:
            cum = 1.0
            for r in rets:
                cum *= (1 + r)
            algo_ret = round(cum - 1, 6)
        else:
            algo_ret = 0.0

        # B&H
        p_start = (db.query(PriceCache)
                     .filter(PriceCache.ticker == tick,
                             PriceCache.date >= first_fri)
                     .order_by(PriceCache.date.asc())
                     .first())
        p_end = (db.query(PriceCache)
                   .filter(PriceCache.ticker == tick,
                           PriceCache.date <= last_fri)
                   .order_by(PriceCache.date.desc())
                   .first())
        if p_start and p_end and p_start.close and p_start.close > 0:
            bh_ret = round((p_end.close - p_start.close) / p_start.close, 6)
        else:
            bh_ret = 0.0

        n_trades = len(rets)
        alpha = round(algo_ret - bh_ret, 6) if n_trades > 0 else 0.0

        if n_trades > 0 or tick in ETF_UNIVERSE:
            etfs.append({
                "ticker": tick,
                "algo_return": algo_ret,
                "bh_return": bh_ret,
                "alpha": alpha,
                "n_trades": n_trades,
            })

    etfs.sort(key=lambda x: x["alpha"], reverse=True)

    return {
        "start_date": effective_start,
        "end_date": last_fri,
        "etfs": etfs,
    }


# ────────────────────────────────────────────────────────────
# Task 1.3: HMM Regime stats
# ────────────────────────────────────────────────────────────

def get_regime_stats(db: Session, start_date: str | None = None) -> dict:
    effective_start = start_date or DISPLAY_START
    rows = (db.query(BacktestResult)
              .filter(BacktestResult.friday_date >= effective_start)
              .all())

    # Deduplicate by friday_date (first params_hash encountered)
    seen = {}
    for r in rows:
        if r.friday_date not in seen:
            seen[r.friday_date] = r
    deduped = list(seen.values())

    from collections import defaultdict
    regime_data = defaultdict(list)
    for r in deduped:
        regime_data[r.regime].append(r)

    stats = []
    for regime_id in range(5):
        rrows = regime_data.get(regime_id, [])
        if not rrows:
            stats.append({
                "regime_id": regime_id,
                "regime_name": REGIME_NAMES.get(regime_id, f"Stato {regime_id}"),
                "n_weeks": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "total_trades": 0,
            })
            continue
        returns = [r.weekly_return for r in rrows
                   if r.weekly_return is not None]
        win_rate = (sum(1 for r in returns if r > 0) / len(returns)
                    if returns else 0.0)
        avg_ret = sum(returns) / len(returns) if returns else 0.0
        total_trades = sum(r.n_trades or 0 for r in rrows)
        stats.append({
            "regime_id": regime_id,
            "regime_name": REGIME_NAMES.get(regime_id, f"Stato {regime_id}"),
            "n_weeks": len(rrows),
            "win_rate": round(win_rate, 4),
            "avg_return": round(avg_ret, 6),
            "total_trades": total_trades,
        })

    return {"start_date": effective_start, "regimes": stats}


# ────────────────────────────────────────────────────────────
# Task 1.5: Weekly decomposition
# ────────────────────────────────────────────────────────────

def get_weekly_decomposition(db: Session) -> dict:
    """Per-ticker breakdown of the last completed week's return."""
    from modules.signals.service import (get_available_fridays,
                                          get_weekly_signals)
    from modules.backtest.service import (
        _get_all_prices, _get_fridays, _weekly_ret, _weekly_ret_with_tpsl_details
    )

    available = get_available_fridays(db)
    if len(available) < 2:
        return {"friday_date": "", "next_friday": "",
                "contributions": [], "total_return": 0.0}

    last_friday = available[0]
    prev_friday = available[1]

    sigs_data = get_weekly_signals(db, prev_friday)
    active_trades = [
        s for s in sigs_data.get("signals", [])
        if s.get("is_active") and s.get("long_ticker")
    ]

    if not active_trades:
        return {"friday_date": prev_friday, "next_friday": last_friday,
                "contributions": [], "total_return": 0.0}

    n = len(active_trades)
    weight = 1.0 / n

    # For TP/SL trigger logic we need prices and sigma
    prices = _get_all_prices(db)
    fridays = _get_fridays(db)

    contributions = []
    total = 0.0
    for s in active_trades:
        ticker = s["long_ticker"]
        
        # Logic to find sigma for this ticker
        ticker_sigma = 0.0
        if ticker in prices:
            try:
                window_rets = prices[ticker]["Close"].reindex(fridays[fridays <= pd.Timestamp(prev_friday)][-53:]).pct_change().dropna()
                if len(window_rets) >= 4:
                    ticker_sigma = float(window_rets.std())
            except Exception:
                pass
        
        # Use helper from backtest service to find return and trigger_state
        if ticker_sigma > 0:
            ret, trigger = _weekly_ret_with_tpsl_details(
                prices, ticker, pd.Timestamp(prev_friday), pd.Timestamp(last_friday),
                DEFAULT_K_UP, DEFAULT_K_DOWN, ticker_sigma
            )
        else:
            ret = _weekly_ret(prices, ticker, pd.Timestamp(prev_friday), pd.Timestamp(last_friday))
            trigger = "hold"
            
        contribution = weight * ret
        total += contribution
        contributions.append({
            "ticker": ticker,
            "weight": round(weight, 4),
            "return_pct": round(ret, 6),
            "contribution": round(contribution, 6),
            "trigger_state": trigger
        })

    contributions.sort(key=lambda x: x["contribution"], reverse=True)

    return {
        "friday_date": prev_friday,
        "next_friday": last_friday,
        "contributions": contributions,
        "total_return": round(total, 6),
    }
