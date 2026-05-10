import hashlib
import json
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from database.models import BacktestResult, SystemParams, PriceCache, InferenceCache
from modules.backtest.schemas import BacktestParams
from config import (RATIOS, CRISIS_BASKET, DISPLAY_START, WARMUP_START,
                    CRISIS_STATE_IDX, DEFAULT_BET_QUALITY,
                    DEFAULT_HRP_ALPHA, DEFAULT_K_SIGMOID,
                    DEFAULT_C_SOGLIA, DEFAULT_K_UP, DEFAULT_K_DOWN)


def params_to_hash(params: BacktestParams) -> str:
    d = params.model_dump()
    # Include start_date in hash so different periods get different cache
    d["start_date"] = d.get("start_date") or DISPLAY_START
    key = json.dumps(d, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def is_default_params(params: BacktestParams) -> bool:
    return (
        params.bet_quality == DEFAULT_BET_QUALITY and
        params.hrp_alpha   == DEFAULT_HRP_ALPHA   and
        params.k_sigmoid   == DEFAULT_K_SIGMOID   and
        params.c_soglia    == DEFAULT_C_SOGLIA     and
        params.k_up        == DEFAULT_K_UP         and
        params.k_down      == DEFAULT_K_DOWN
    )


def _get_operational_fridays(db: Session) -> pd.DatetimeIndex:
    """
    Returns only the Fridays where the market was actually open (SPY has data).
    Replicates the logic from the thesis notebook: festival/closed fridays are skipped.
    """
    rows = (db.query(PriceCache.date, PriceCache.volume)
              .filter(PriceCache.ticker == "SPY")
              .order_by(PriceCache.date.asc())
              .all())
    if not rows:
        return pd.DatetimeIndex([])
    
    df = pd.DataFrame(rows, columns=["date", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    
    # Filter for Fridays
    fridays = df[df.index.dayofweek == 4]
    
    # Filter for days with trading volume (market open)
    # If volume is missing or 0, we consider it closed
    operational = fridays[fridays["volume"] > 0]
    
    return operational.index


def get_or_compute_backtest(params: BacktestParams,
                              db: Session) -> dict:
    """
    Se il backtest con questi parametri è già in DB lo restituisce.
    Altrimenti lo calcola, lo salva e lo restituisce.
    """
    effective_start = params.start_date or DISPLAY_START

    # For historical periods, ensure we have prices and inferences
    if effective_start < "2024-01-01":
        _ensure_historical_prices(effective_start, db)
        _load_historical_inferences(db)

    params_hash = params_to_hash(params)

    cached = (db.query(BacktestResult)
                .filter(BacktestResult.params_hash == params_hash)
                .order_by(BacktestResult.friday_date.asc())
                .all())

    if cached:
        return _rows_to_response(cached, params_hash,
                                  is_default_params(params), db,
                                  effective_start)

    # Calcola e salva
    result = _compute_backtest(params, db)
    _save_backtest(result, params, params_hash, db)
    return _rows_to_response(
        db.query(BacktestResult)
          .filter(BacktestResult.params_hash == params_hash)
          .order_by(BacktestResult.friday_date.asc())
          .all(),
        params_hash, is_default_params(params), db,
        effective_start
    )


def _get_prices_from_db(ticker: str, db: Session) -> pd.Series:
    rows = (db.query(PriceCache)
              .filter(PriceCache.ticker == ticker)
              .order_by(PriceCache.date.asc())
              .all())
    if not rows:
        return pd.Series(dtype=float)
    idx  = pd.to_datetime([r.date for r in rows])
    vals = [r.close for r in rows]
    return pd.Series(vals, index=idx, name=ticker)


def _get_all_prices(db: Session) -> dict:
    from config import ETF_UNIVERSE
    all_tickers = list(set(ETF_UNIVERSE + ["VIX", "FXE"]))
    prices = {}
    for ticker in all_tickers:
        rows = (db.query(PriceCache)
                  .filter(PriceCache.ticker == ticker)
                  .order_by(PriceCache.date.asc())
                  .all())
        if not rows:
            continue
        idx = pd.to_datetime([r.date for r in rows])
        prices[ticker] = pd.DataFrame({
            "Close": [r.close for r in rows],
            "High":  [r.high if r.high else r.close for r in rows],
            "Low":   [r.low if r.low else r.close for r in rows],
        }, index=idx)
    return prices


def _get_fridays(db: Session) -> pd.DatetimeIndex:
    return _get_operational_fridays(db)


def _ensure_historical_prices(start_date: str, db: Session):
    """
    If start_date is before what we have in PriceCache, download
    from yfinance for all tickers back to start_date.
    """
    from config import ETF_UNIVERSE

    earliest = (db.query(PriceCache.date)
                  .order_by(PriceCache.date.asc())
                  .first())
    if earliest and earliest[0] <= start_date:
        return  # already have data far enough back

    all_tickers = list(set(ETF_UNIVERSE + ["FXE"]))
    print(f"[backtest] Downloading historical prices from {start_date}...")

    try:
        import yfinance as yf
        data = yf.download(
            all_tickers, start=start_date, auto_adjust=True,
            progress=False, threads=True
        )
        if data.empty:
            print("[backtest] No historical data returned from yfinance.")
            return

        # yf.download with multiple tickers returns MultiIndex columns
        if isinstance(data.columns, pd.MultiIndex):
            close_df = data["Close"] if "Close" in data.columns.get_level_values(0) else None
            high_df = data.get("High") if hasattr(data, "get") else data["High"] if "High" in data.columns.get_level_values(0) else None
            low_df = data.get("Low") if hasattr(data, "get") else data["Low"] if "Low" in data.columns.get_level_values(0) else None
            vol_df = data.get("Volume") if hasattr(data, "get") else data["Volume"] if "Volume" in data.columns.get_level_values(0) else None
        else:
            # Single ticker fallback
            close_df = data[["Close"]].rename(columns={"Close": all_tickers[0]})
            high_df = data[["High"]].rename(columns={"High": all_tickers[0]}) if "High" in data.columns else None
            low_df = data[["Low"]].rename(columns={"Low": all_tickers[0]}) if "Low" in data.columns else None
            vol_df = data[["Volume"]].rename(columns={"Volume": all_tickers[0]}) if "Volume" in data.columns else None

        if close_df is None:
            return

        count = 0
        for ticker in all_tickers:
            if ticker not in close_df.columns:
                continue
            ts = close_df[ticker].dropna()
            for dt, close_val in ts.items():
                date_str = str(dt.date()) if hasattr(dt, "date") else str(dt)[:10]
                high_val = float(high_df[ticker].get(dt, close_val)) if high_df is not None and ticker in high_df.columns else None
                low_val = float(low_df[ticker].get(dt, close_val)) if low_df is not None and ticker in low_df.columns else None
                vol_val = float(vol_df[ticker].get(dt, 0)) if vol_df is not None and ticker in vol_df.columns else None

                existing = (db.query(PriceCache)
                              .filter(PriceCache.ticker == ticker,
                                      PriceCache.date == date_str)
                              .first())
                if existing:
                    continue

                db.add(PriceCache(
                    ticker=ticker,
                    date=date_str,
                    open=float(close_val),
                    high=high_val,
                    low=low_val,
                    close=float(close_val),
                    volume=vol_val,
                ))
                count += 1

        db.commit()
        print(f"[backtest] Inserted {count} historical price rows.")
    except Exception as e:
        print(f"[backtest] Historical price download error: {e}")
        db.rollback()


def _load_historical_inferences(db: Session):
    """
    If InferenceCache lacks data before DISPLAY_START, load from the
    historical parquet file on Drive (read-only).
    """
    from config import INFERENCE_PATH

    # Check if we already have pre-DISPLAY_START data
    pre_display = (db.query(InferenceCache)
                     .filter(InferenceCache.friday_date < DISPLAY_START)
                     .first())
    if pre_display:
        return  # already loaded

    try:
        df = pd.read_parquet(INFERENCE_PATH)
        print(f"[backtest] Loading historical inferences from Drive ({len(df)} rows)...")

        count = 0
        for _, row in df.iterrows():
            date_val = row.get("Date")
            if date_val is None:
                continue
            if isinstance(date_val, pd.Timestamp):
                friday_str = str(date_val.date())
            else:
                friday_str = str(date_val)

            ratio_id = row.get("Ratio", "")
            if not ratio_id:
                continue
            ratio_id = str(ratio_id).split("_")[0]

            # Only insert if not already present
            existing = (db.query(InferenceCache)
                          .filter(InferenceCache.friday_date == friday_str,
                                  InferenceCache.ratio_id == ratio_id)
                          .first())
            if existing:
                continue

            db.add(InferenceCache(
                friday_date=friday_str,
                ratio_id=str(ratio_id),
                tfm_t1=float(row.get("TFM_t1", 0)) if not pd.isna(row.get("TFM_t1", np.nan)) else None,
                tfm_t5=float(row.get("TFM_t5", 0)) if not pd.isna(row.get("TFM_t5", np.nan)) else None,
                tfm_t20=float(row.get("TFM_t20", 0)) if not pd.isna(row.get("TFM_t20", np.nan)) else None,
                chr_median_t5=float(row.get("CHR_Median_t5", 0)) if not pd.isna(row.get("CHR_Median_t5", np.nan)) else None,
                chr_width_t5=float(row.get("CHR_Width_t5", 0)) if not pd.isna(row.get("CHR_Width_t5", np.nan)) else None,
            ))
            count += 1

        db.commit()
        print(f"[backtest] Loaded {count} historical inference rows.")
    except Exception as e:
        print(f"[backtest] Historical inference load error: {e}")
        db.rollback()


def _compute_backtest(params: BacktestParams, db: Session) -> list:
    """
    Esegue il backtest completo con i params dati.
    Usa params.start_date o DISPLAY_START come inizio.
    """
    from modules.features.service import (compute_log_ratios,
                                           compute_ml_features)
    from modules.hmm.service import (compute_hmm_features,
                                      run_hmm_inference)
    from modules.inference.service import load_inference_cache

    effective_start = params.start_date or DISPLAY_START

    prices  = _get_all_prices(db)
    fridays = _get_fridays(db)

    if len(fridays) == 0:
        return []

    log_ratios   = compute_log_ratios(prices)
    ml_features  = compute_ml_features(prices, log_ratios)
    hmm_feat     = compute_hmm_features(prices, fridays)
    regimes      = run_hmm_inference(hmm_feat)
    decay        = _compute_decay(prices, fridays, params)
    inf_cache    = load_inference_cache(db)

    display_fridays = fridays[fridays >= pd.Timestamp(effective_start)]

    results      = []
    port_value   = 1.0

    for i, friday in enumerate(display_fridays[:-1]):
        next_friday = display_fridays[i + 1]
        friday_str  = str(friday.date())

        if friday not in regimes.index:
            continue

        regime    = int(regimes.loc[friday, "Regime_Final"])
        decay_val = float(decay.get(friday, 1.0))
        is_crisis = (regime == CRISIS_STATE_IDX)

        if is_crisis:
            week_ret = _crisis_basket_return(
                prices, friday, next_friday
            )
            n_trades = len(CRISIS_BASKET)
        else:
            week_ret, n_trades = _normal_week_return(
                prices, log_ratios, ml_features,
                regimes, inf_cache, friday, next_friday,
                fridays, params, decay_val
            )

        port_value *= (1 + week_ret)

        results.append({
            "friday_date":     friday_str,
            "portfolio_value": round(port_value, 6),
            "weekly_return":   round(week_ret, 6),
            "regime":          regime,
            "decay_value":     round(decay_val, 4),
            "n_trades":        n_trades,
            "is_crisis":       is_crisis,
        })

    return results


def _crisis_basket_return(prices, entry, exit_) -> float:
    ret = 0.0
    for ticker, w in CRISIS_BASKET.items():
        if ticker in prices:
            try:
                p0 = prices[ticker]["Close"].loc[entry]
                p1 = prices[ticker]["Close"].loc[exit_]
                ret += w * (p1 - p0) / p0
            except KeyError:
                pass
    return ret


def _normal_week_return(prices, log_ratios, ml_features,
                         regimes, inf_cache, friday,
                         next_friday, fridays, params,
                         decay_val) -> tuple:
    from modules.meta_labeler.service import compute_bet_quality
    from modules.hrp.service import compute_blended_weights

    active_trades = []

    for ratio_id, (num, den) in RATIOS.items():
        if ratio_id not in log_ratios.columns:
            continue
        if friday not in log_ratios.index:
            continue

        key = (str(friday.date()), ratio_id)
        if key not in inf_cache:
            continue

        inferences = inf_cache[key]
        tfm_t5     = inferences.get("tfm_t5")
        if tfm_t5 is None or np.isnan(tfm_t5):
            continue

        cur_ratio  = log_ratios.loc[friday, ratio_id]
        long_tick  = num if tfm_t5 > cur_ratio else den

        if friday not in ml_features.index:
            continue

        bq, admitted = compute_bet_quality(
            ml_features.loc[friday],
            inferences, ratio_id,
            params.bet_quality
        )

        if admitted:
            active_trades.append({
                "long_ticker": long_tick,
                "bet_quality": bq
            })

    if not active_trades:
        return 0.0, 0

    active_tickers = list({t["long_ticker"] for t in active_trades})
    window_rets    = pd.DataFrame({
        t: prices[t]["Close"]
             .reindex(fridays[fridays <= friday][-53:])
             .pct_change()
        for t in active_tickers if t in prices
    }).dropna()

    weights = compute_blended_weights(
        window_rets, active_tickers, params.hrp_alpha
    )

    # Compute per-ticker weekly sigma for TP/SL levels
    ticker_sigma = {}
    if window_rets.shape[0] >= 4:
        ticker_sigma = window_rets.std().to_dict()

    port_ret = 0.0
    for t in active_trades:
        tick = t["long_ticker"]
        w = weights.get(tick, 0)
        sigma = ticker_sigma.get(tick, 0.0)
        if sigma > 0 and params.k_up > 0 and params.k_down > 0:
            ret = _weekly_ret_with_tpsl(
                prices, tick, friday, next_friday,
                params.k_up, params.k_down, sigma
            )
        else:
            ret = _weekly_ret(prices, tick, friday, next_friday)
        port_ret += w * ret

    return port_ret * decay_val, len(active_trades)


def _weekly_ret(prices, ticker, entry, exit_) -> float:
    try:
        p0 = prices[ticker]["Close"].loc[entry]
        p1 = prices[ticker]["Close"].loc[exit_]
        return (p1 - p0) / p0
    except (KeyError, ZeroDivisionError):
        return 0.0


def _weekly_ret_with_tpsl(prices, ticker, entry, exit_,
                          k_up, k_down, weekly_sigma) -> float:
    """Wrapper that returns only the simple return."""
    ret, _ = _weekly_ret_with_tpsl_details(prices, ticker, entry, exit_, k_up, k_down, weekly_sigma)
    return ret


def _weekly_ret_with_tpsl_details(prices, ticker, entry, exit_,
                                 k_up, k_down, weekly_sigma) -> tuple:
    """
    Rendimento settimanale con Take Profit / Stop Loss intra-settimanale.
    TP = entry * (1 + k_up * sigma), SL = entry * (1 - k_down * sigma).
    Controlla giorno per giorno High/Low tra entry e exit.
    Returns: (return_val, trigger_state) where trigger_state is 'tp', 'sl', or 'hold'
    """
    try:
        p0 = prices[ticker]["Close"].loc[entry]
    except KeyError:
        return 0.0, "hold"

    if p0 == 0 or weekly_sigma <= 0:
        return _weekly_ret(prices, ticker, entry, exit_), "hold"

    tp_level = p0 * (1 + k_up * weekly_sigma)
    sl_level = p0 * (1 - k_down * weekly_sigma)

    df = prices[ticker]
    mask = (df.index > entry) & (df.index <= exit_)
    intra_days = df.loc[mask]

    for _, row in intra_days.iterrows():
        day_high = row.get("High", row["Close"])
        day_low  = row.get("Low", row["Close"])

        # Stop Loss hit first (conservative: assume SL triggers before TP on same day)
        if day_low <= sl_level:
            return (sl_level - p0) / p0, "sl"
        # Take Profit hit
        if day_high >= tp_level:
            return (tp_level - p0) / p0, "tp"

    # No TP/SL triggered → hold to end of week
    try:
        p1 = prices[ticker]["Close"].loc[exit_]
        return (p1 - p0) / p0, "hold"
    except KeyError:
        return 0.0, "hold"


def _compute_decay(prices, fridays, params) -> pd.Series:
    from config import ETF_UNIVERSE
    closes = pd.DataFrame({
        t: prices[t]["Close"]
        for t in ETF_UNIVERSE if t in prices
    }).reindex(fridays, method="ffill")

    weekly_rets = closes.pct_change()
    decay = {}

    for i, friday in enumerate(fridays):
        if i < 8:
            decay[friday] = 1.0
            continue
        window = weekly_rets.iloc[i-8:i]
        corr   = window.corr()
        n      = corr.shape[0]
        vals   = [corr.iloc[r, c]
                  for r in range(n)
                  for c in range(r+1, n)
                  if not np.isnan(corr.iloc[r, c])]
        avg_c  = np.mean(vals) if vals else 0.0
        decay[friday] = 1.0 / (
            1.0 + np.exp(params.k_sigmoid * (avg_c - params.c_soglia))
        )

    return pd.Series(decay)


def _save_backtest(rows: list, params: BacktestParams,
                    params_hash: str, db: Session):
    # Salva params
    if not db.get(SystemParams, params_hash):
        db.add(SystemParams(
            params_hash=params_hash,
            bet_quality=params.bet_quality,
            hrp_alpha=params.hrp_alpha,
            k_sigmoid=params.k_sigmoid,
            c_soglia=params.c_soglia,
            k_up=params.k_up,
            k_down=params.k_down,
            is_default=is_default_params(params)
        ))

    series = pd.Series([r["weekly_return"] for r in rows])
    cagr, sharpe, max_dd, calmar, tot_ret = _compute_metrics(
        [r["portfolio_value"] for r in rows], series
    )

    for r in rows:
        db.merge(BacktestResult(
            friday_date=r["friday_date"],
            params_hash=params_hash,
            portfolio_value=r["portfolio_value"],
            weekly_return=r["weekly_return"],
            regime=r["regime"],
            decay_value=r["decay_value"],
            n_trades=r["n_trades"],
            is_crisis=r["is_crisis"],
            cagr=cagr,
            sharpe=sharpe,
            max_drawdown=max_dd,
            calmar=calmar,
            total_return=tot_ret,
        ))
    db.commit()


def _compute_metrics(portfolio_values, weekly_returns):
    pv      = pd.Series(portfolio_values)
    wr      = weekly_returns
    n       = len(pv)
    tot_ret = pv.iloc[-1] - 1 if n > 0 else 0
    cagr    = (1 + tot_ret) ** (52 / n) - 1 if n > 1 else 0
    sharpe  = (wr.mean() * 52) / (wr.std() * np.sqrt(52)) \
              if wr.std() > 0 else 0
    running = pv.cummax()
    dd      = ((pv - running) / running).min()
    calmar  = cagr / abs(dd) if dd != 0 else 0
    return round(cagr,4), round(sharpe,4), round(dd,4), \
           round(calmar,4), round(tot_ret,4)


def _build_display_series(rows, db: Session):
    """
    Fix 7: Re-models the series for the frontend.
    Adds a baseline point (1.0) and shifts realized returns to the exit Friday.
    """
    if not rows:
        return []
    
    # Operational fridays for date shifting
    all_fridays = _get_operational_fridays(db)
    
    display = []
    
    # 1. First point: Baseline 1.0 on the start date
    display.append({
        "date": rows[0].friday_date,
        "portfolio_value": 1.0,
        "weekly_return": 0.0,
        "regime": rows[0].regime,
        "decay_value": rows[0].decay_value,
        "n_trades": 0,
        "is_crisis": rows[0].is_crisis
    })
    
    # 2. Subsequent points: Values shifted to exit dates
    for row in rows:
        entry_dt = pd.Timestamp(row.friday_date)
        # Find next operational Friday (exit date)
        next_fris = all_fridays[all_fridays > entry_dt]
        if len(next_fris) > 0:
            exit_date = str(next_fris[0].date())
        else:
            # Fallback if we don't have the next Friday yet (e.g. today is Friday)
            continue 

        display.append({
            "date": exit_date,
            "portfolio_value": row.portfolio_value,
            "weekly_return": row.weekly_return,
            "regime": row.regime,
            "decay_value": row.decay_value,
            "n_trades": row.n_trades,
            "is_crisis": row.is_crisis
        })
        
    return display


def _rows_to_response(rows, params_hash, is_default, db,
                      effective_start=None) -> dict:
    if not rows:
        return {
            "params_hash": params_hash,
            "is_default": is_default,
            "series": [], "cagr": 0, "sharpe": 0,
            "max_drawdown": 0, "calmar": 0,
            "total_return": 0, "n_crisis_weeks": 0,
            "n_normal_weeks": 0, "spy_series": [],
            "spy_cagr": 0, "spy_sharpe": 0,
            "spy_max_drawdown": 0, "spy_calmar": 0,
            "spy_total_return": 0,
        }

    # Fix 7: Use re-modeled series for visual coherence
    series = _build_display_series(rows, db)
    display_dates = [point["date"] for point in series]

    start = effective_start or DISPLAY_START
    # Fix 7: Align SPY series to the exact same display grid
    spy_series = _get_spy_series(db, rows, start, display_dates=display_dates)
    spy_cagr, spy_sharpe, spy_max_dd, spy_calmar, spy_tot_ret = _compute_spy_metrics(spy_series)

    return {
        "params_hash":    params_hash,
        "is_default":     is_default,
        "series":         series,
        "cagr":           rows[-1].cagr,
        "sharpe":         rows[-1].sharpe,
        "max_drawdown":   rows[-1].max_drawdown,
        "calmar":         rows[-1].calmar,
        "total_return":   rows[-1].total_return,
        "n_crisis_weeks": sum(1 for r in rows if r.is_crisis),
        "n_normal_weeks": sum(1 for r in rows if not r.is_crisis),
        "spy_series":     spy_series,
        "spy_cagr":       spy_cagr,
        "spy_sharpe":     spy_sharpe,
        "spy_max_drawdown": spy_max_dd,
        "spy_calmar":     spy_calmar,
        "spy_total_return": spy_tot_ret,
    }


def _get_spy_series(db: Session, backtest_rows=None,
                    effective_start=None, display_dates=None) -> list:
    """
    Fix 7: Align SPY benchmark to the same temporal grid as the algorithm.
    """
    start = effective_start or DISPLAY_START
    rows = (db.query(PriceCache)
              .filter(PriceCache.ticker == "SPY")
              .order_by(PriceCache.date.asc())
              .all())
    if not rows:
        return []
        
    prices = {r.date: r.close for r in rows}
    
    # If display_dates is provided, follow it exactly
    if display_dates:
        # Base value on the first display date
        first_date = display_dates[0]
        base = prices.get(first_date)
        if not base:
            # Fallback to nearest price if exact start missing
            base_row = (db.query(PriceCache)
                          .filter(PriceCache.ticker == "SPY", PriceCache.date <= first_date)
                          .order_by(PriceCache.date.desc()).first())
            base = base_row.close if base_row else 1.0
            
        series = []
        for dt in display_dates:
            p = prices.get(dt)
            if not p:
                # Forward fill if date missing
                p_row = (db.query(PriceCache)
                           .filter(PriceCache.ticker == "SPY", PriceCache.date <= dt)
                           .order_by(PriceCache.date.desc()).first())
                p = p_row.close if p_row else base
            series.append({"date": dt, "value": round(p / base, 6)})
        return series

    # Fallback to operational fridays if no display grid
    operational = _get_operational_fridays(db)
    operational = operational[operational >= pd.Timestamp(start)]
    
    if len(operational) == 0:
        return []
        
    first_price_row = (db.query(PriceCache)
                         .filter(PriceCache.ticker == "SPY", PriceCache.date == str(operational[0].date()))
                         .first())
    base = first_price_row.close if first_price_row else 1.0
    
    series = []
    for dt in operational:
        date_str = str(dt.date())
        p = prices.get(date_str, base)
        series.append({"date": date_str, "value": round(p / base, 6)})
        
    return series


def _compute_spy_metrics(spy_series: list) -> tuple:
    """Compute CAGR, Sharpe, MaxDD, Calmar, TotalReturn for SPY B&H."""
    if len(spy_series) < 2:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    values = [s["value"] for s in spy_series]
    pv = pd.Series(values)
    
    # Fix 7: Compute returns correctly from the re-aligned series
    wr = pv.pct_change().dropna()
    n_periods = len(wr)
    
    tot_ret = pv.iloc[-1] - 1
    cagr = (1 + tot_ret) ** (52 / n_periods) - 1 if n_periods > 0 else 0
    sharpe = (wr.mean() * 52) / (wr.std() * np.sqrt(52)) if wr.std() > 0 else 0

    running_max = pv.cummax()
    dd = ((pv - running_max) / running_max).min()

    calmar = cagr / abs(dd) if dd != 0 else 0

    return (round(cagr, 4), round(sharpe, 4), round(dd, 4),
            round(calmar, 4), round(tot_ret, 4))
