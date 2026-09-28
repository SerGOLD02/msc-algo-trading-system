"""
modules/timesfm3/service.py

Backtest engine usando inferenze TimesFM 3.0 (google/timesfm-2.5-200m-pytorch).
La pipeline ML (HMM -> LightGBM -> HRP -> TP/SL -> Decay) è identica
al backtest standard. Solo il segnale direzionale (tfm_t5) proviene da
TimesFM 3.0 invece che dall'OLS.

Autore: generato automaticamente per la tesi di laurea.
Licenza modello: timesfm-non-commercial-license-v1.0 (solo uso accademico).
"""

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from config import (
    RATIOS, ETF_UNIVERSE, DISPLAY_START, CRISIS_STATE_IDX,
    DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
    DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA, DEFAULT_K_UP, DEFAULT_K_DOWN
)
from database.models import (
    TimesFM3InferenceCache, TimesFM3BacktestResult, PriceCache
)

TIMESFM3_CHECKPOINT = "google/timesfm-2.5-200m-pytorch"
CONTEXT_LEN = 512


# ---------------------------------------------------------------------------
# Inferenze TimesFM 3.0
# ---------------------------------------------------------------------------

def _load_timesfm3_forecaster():
    """Carica il modello TimesFM3Forecaster da HuggingFace (usa cache locale)."""
    from timesfm import TimesFM3Forecaster
    print(f"[timesfm3] Loading checkpoint: {TIMESFM3_CHECKPOINT}...")
    forecaster = TimesFM3Forecaster.from_pretrained(
        TIMESFM3_CHECKPOINT,
        device="cpu",
    )
    print("[timesfm3] Model loaded.")
    return forecaster


def backfill_timesfm3_inference(db: Session) -> None:
    """
    Backfill inferenze TimesFM 3.0 per tutti i venerdì dal DISPLAY_START
    che non hanno ancora dati nella tabella timesfm3_inference_cache.
    """
    from modules.backtest.service import _get_prices_from_db, _get_operational_fridays
    from modules.features.service import compute_log_ratios

    # Controlla quali venerdì sono già presenti
    existing_dates = set(
        row[0] for row in db.query(TimesFM3InferenceCache.friday_date).distinct().all()
    )

    # Calcola log-ratio su tutti i ticker
    prices_dict = {}
    for ticker in ETF_UNIVERSE + ["VIX"]:
        s = _get_prices_from_db(ticker, db)
        if len(s) > 0:
            prices_dict[ticker] = pd.DataFrame({
                "Close": s, "Volume": s * 0
            })

    log_ratios = compute_log_ratios(prices_dict)
    fridays = _get_operational_fridays(db)

    if len(fridays) == 0:
        print("[timesfm3] No operational Fridays found.")
        return

    display_start = pd.Timestamp(DISPLAY_START)
    target_fridays = fridays[fridays >= display_start]
    missing_fridays = [f for f in target_fridays if str(f.date()) not in existing_dates]

    if not missing_fridays:
        print("[timesfm3] All Fridays already have TimesFM 3.0 inference. No backfill needed.")
        return

    print(f"[timesfm3] Backfilling {len(missing_fridays)} Fridays with TimesFM 3.0...")

    # Carica il modello una sola volta
    forecaster = _load_timesfm3_forecaster()

    for fri in missing_fridays:
        fri_str = str(fri.date())
        try:
            idx = log_ratios.index.get_loc(fri)
        except KeyError:
            print(f"[timesfm3] Warning: {fri_str} not found in log_ratios. Skipping.")
            continue

        records = []
        for ratio_id in log_ratios.columns:
            ratio_arr = log_ratios[ratio_id].iloc[
                max(0, idx - CONTEXT_LEN + 1): idx + 1
            ].values.astype(np.float32)

            if len(ratio_arr) < 60:
                continue

            # Rimuovi NaN se presenti
            ratio_arr = np.nan_to_num(ratio_arr, nan=float(np.nanmean(ratio_arr)))

            try:
                outputs = list(forecaster.predict_batch(
                    [ratio_arr],
                    horizon=20,
                    return_quantiles=True,
                    use_symmetric_averaging=True,
                ))
                if not outputs:
                    continue

                out = outputs[0]
                forecast = out.forecast  # shape: (20,)

                fp_t1  = float(forecast[0])
                fp_t5  = float(forecast[4])
                fp_t20 = float(forecast[19])

            except Exception as e:
                print(f"[timesfm3] Error forecasting {ratio_id} on {fri_str}: {e}")
                continue

            records.append(TimesFM3InferenceCache(
                friday_date=fri_str,
                ratio_id=ratio_id,
                tfm3_t1=fp_t1,
                tfm3_t5=fp_t5,
                tfm3_t20=fp_t20,
            ))

        if records:
            for r in records:
                db.merge(r)
            db.commit()
            print(f"[timesfm3] Backfilled {fri_str} ({len(records)} ratios)")
        else:
            print(f"[timesfm3] Warning: No records computed for {fri_str}")

    print(f"[timesfm3] Backfill complete for {len(missing_fridays)} Fridays.")


# ---------------------------------------------------------------------------
# Carica inferenze TimesFM3 dal DB
# ---------------------------------------------------------------------------

def load_timesfm3_inference_cache(db: Session) -> dict:
    """Carica tutte le inferenze TimesFM3 dal DB in un dizionario (date, ratio_id) -> dict."""
    rows = db.query(TimesFM3InferenceCache).all()
    cache = {}
    for r in rows:
        cache[(r.friday_date, r.ratio_id)] = {
            "tfm_t1":  r.tfm3_t1,
            "tfm_t5":  r.tfm3_t5,
            "tfm_t20": r.tfm3_t20,
            # Compatibilità con il resto della pipeline che usa chr_median_t5/chr_width_t5
            "chr_median_t5": r.tfm3_t5,
            "chr_width_t5":  abs(r.tfm3_t5 - r.tfm3_t1) * 2 if r.tfm3_t1 else 0.0,
        }
    return cache


# ---------------------------------------------------------------------------
# Compute backtest TimesFM3
# ---------------------------------------------------------------------------

def compute_and_save_timesfm3_backtest(db: Session) -> dict:
    """
    Esegue il backtest completo usando le inferenze TimesFM 3.0.
    Riutilizza tutta la pipeline ML standard (HMM, LightGBM, HRP, TP/SL, Decay).
    """
    from modules.backtest.service import (
        _get_all_prices, _get_fridays, _get_operational_fridays,
        _crisis_basket_return, _normal_week_return, _compute_metrics,
        _build_display_series, _get_spy_series, _compute_spy_metrics
    )
    from modules.features.service import (
        compute_log_ratios, compute_ml_features
    )
    from modules.hmm.service import (
        compute_hmm_features, run_hmm_inference
    )
    from modules.backtest.schemas import BacktestParams

    # Parametri default identici al backtest standard
    params = BacktestParams(
        bet_quality=DEFAULT_BET_QUALITY,
        hrp_alpha=DEFAULT_HRP_ALPHA,
        k_sigmoid=DEFAULT_K_SIGMOID,
        c_soglia=DEFAULT_C_SOGLIA,
        k_up=DEFAULT_K_UP,
        k_down=DEFAULT_K_DOWN,
        start_date=None,
    )

    effective_start = DISPLAY_START
    prices  = _get_all_prices(db)
    fridays = _get_fridays(db)

    if len(fridays) == 0:
        return {}

    log_ratios  = compute_log_ratios(prices)
    ml_features = compute_ml_features(prices, log_ratios)
    hmm_feat    = compute_hmm_features(prices, fridays)
    regimes     = run_hmm_inference(hmm_feat)
    
    # Ricalcola decay (identico al backtest standard)
    from modules.backtest.service import _compute_decay
    decay = _compute_decay(prices, fridays, params)

    # Usa la cache TimesFM3 invece di quella OLS
    inf_cache = load_timesfm3_inference_cache(db)

    if not inf_cache:
        print("[timesfm3] No inference data found. Run backfill_timesfm3_inference first.")
        return {}

    display_fridays = fridays[fridays >= pd.Timestamp(effective_start)]

    results    = []
    port_value = 1.0

    for i, friday in enumerate(display_fridays[:-1]):
        next_friday = display_fridays[i + 1]
        friday_str  = str(friday.date())

        if friday not in regimes.index:
            continue

        regime    = int(regimes.loc[friday, "Regime_Final"])
        decay_val = float(decay.get(friday, 1.0))
        is_crisis = (regime == CRISIS_STATE_IDX)

        if is_crisis:
            week_ret = _crisis_basket_return(prices, friday, next_friday)
            n_trades = 4
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

    if not results:
        return {}

    # Calcola metriche aggregate
    series = pd.Series([r["weekly_return"] for r in results])
    cagr, sharpe, max_dd, calmar, tot_ret = _compute_metrics(
        [r["portfolio_value"] for r in results], series
    )

    # Salva nel DB (sovrascrive tutto: semplicissimo dato che non abbiamo params_hash)
    db.query(TimesFM3BacktestResult).delete()
    for r in results:
        db.add(TimesFM3BacktestResult(
            friday_date=r["friday_date"],
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
    print(f"[timesfm3] Backtest saved. Points: {len(results)}. Latest: {results[-1]['friday_date']}")

    # Costruisci risposta nel formato identico al backtest standard
    rows_from_db = (db.query(TimesFM3BacktestResult)
                      .order_by(TimesFM3BacktestResult.friday_date.asc())
                      .all())

    # Build display series (shift al venerdì di uscita)
    all_ops_fridays = _get_operational_fridays(db)

    display = []
    display.append({
        "date": rows_from_db[0].friday_date,
        "value": 1.0,
    })
    for row in rows_from_db:
        entry_dt = pd.Timestamp(row.friday_date)
        next_fris = all_ops_fridays[all_ops_fridays > entry_dt]
        if len(next_fris) > 0:
            exit_date = str(next_fris[0].date())
        else:
            continue
        display.append({
            "date": exit_date,
            "value": round(row.portfolio_value, 6),
        })

    last_row = rows_from_db[-1]
    return {
        "series":       display,
        "cagr":         last_row.cagr,
        "sharpe":       last_row.sharpe,
        "max_drawdown": last_row.max_drawdown,
        "calmar":       last_row.calmar,
        "total_return": last_row.total_return,
    }


def get_timesfm3_backtest_from_db(db: Session) -> dict:
    """
    Restituisce i risultati del backtest TimesFM3 già calcolati dal DB.
    Se non ci sono dati, ritorna un dict vuoto.
    """
    from modules.backtest.service import _get_operational_fridays

    rows = (db.query(TimesFM3BacktestResult)
              .order_by(TimesFM3BacktestResult.friday_date.asc())
              .all())

    if not rows:
        return {"series": [], "cagr": 0, "sharpe": 0,
                "max_drawdown": 0, "calmar": 0, "total_return": 0}

    all_ops_fridays = _get_operational_fridays(db)

    display = []
    display.append({"date": rows[0].friday_date, "value": 1.0})
    for row in rows:
        entry_dt = pd.Timestamp(row.friday_date)
        next_fris = all_ops_fridays[all_ops_fridays > entry_dt]
        if len(next_fris) > 0:
            exit_date = str(next_fris[0].date())
        else:
            continue
        display.append({"date": exit_date, "value": round(row.portfolio_value, 6)})

    last_row = rows[-1]
    return {
        "series":       display,
        "cagr":         last_row.cagr or 0,
        "sharpe":       last_row.sharpe or 0,
        "max_drawdown": last_row.max_drawdown or 0,
        "calmar":       last_row.calmar or 0,
        "total_return": last_row.total_return or 0,
    }
