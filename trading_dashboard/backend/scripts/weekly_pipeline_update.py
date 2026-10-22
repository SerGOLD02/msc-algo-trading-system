#!/usr/bin/env python3
"""
weekly_pipeline_update.py
Script di aggiornamento settimanale automatico (utilizzato sia localmente che in GitHub Actions CI/CD).

Fasi:
1. Scarica i prezzi aggiornati da Yahoo Finance e aggiorna PriceCache nel database SQLite.
2. Esegue il backfill delle inferenze mancanti per tutti i nuovi venerdì (Chronos, TimesFM 2.5, TimesFM 3.0).
3. Ricalcola i backtest di sistema (Pipeline originale LGBM e TimesFM 3.0 LGBM).
4. Allena ed esegue i modelli XGBoost (TimesFM 3.0 Optuna ed TimesFM 2.5 Baseline).
5. Estrae tutti i widget analitici e serializza l'intero stato in `mock-data.ts`.
"""

import sys
import os
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import yfinance as yf
from sqlalchemy import text

# Setup paths dynamically
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
REPO_ROOT   = BACKEND_DIR.parent.parent if BACKEND_DIR.name == "backend" and BACKEND_DIR.parent.name == "trading_dashboard" else BACKEND_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))

from database.connection import SessionLocal
from database.models import PriceCache, InferenceCache, TimesFM3InferenceCache, TimesFM3BacktestResult, BacktestResult
from config import (
    ETF_UNIVERSE, RATIOS, DISPLAY_START, CRISIS_STATE_IDX,
    DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
    DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA, DEFAULT_K_UP, DEFAULT_K_DOWN,
    DRIVE_PATH
)

from modules.backtest.service import (
    _get_all_prices, _get_fridays, _get_operational_fridays,
    _crisis_basket_return, _compute_decay,
    _weekly_ret_with_tpsl, _weekly_ret, _normal_week_return,
    get_or_compute_backtest
)
from modules.backtest.schemas import BacktestParams
from modules.features.service import compute_log_ratios, compute_ml_features
from modules.hmm.service import compute_hmm_features, run_hmm_inference, get_current_regime
from modules.inference.service import backfill_inference, load_inference_cache
from modules.timesfm3.service import (
    backfill_timesfm3_inference, load_timesfm3_inference_cache,
    compute_and_save_timesfm3_backtest, get_timesfm3_backtest_from_db
)
from modules.hrp.service import compute_blended_weights
from modules.market_data.service import get_market_snapshot
from modules.signals.service import get_weekly_signals, get_available_fridays
from modules.analytics.service import (
    get_decay_history, get_correlation_heatmap, get_drawdown,
    get_chronos_bands, get_yearly_breakdown, get_operational_status,
    get_etf_performance, get_regime_stats, get_weekly_decomposition
)
from fastapi.encoders import jsonable_encoder

import xgboost as xgb


def update_prices_from_yfinance(db):
    """Scarica da YFinance i prezzi recenti e aggiorna PriceCache."""
    tickers = list(dict.fromkeys(
        ETF_UNIVERSE + ["^VIX", "DX-Y.NYB", "GC=F", "SI=F",
                         "^TNX", "^IRX", "FXE"]
    ))
    
    last_date = db.execute(text("SELECT MAX(date) FROM price_cache")).fetchone()[0]
    start_date = "2026-09-01" if not last_date else str((pd.Timestamp(last_date) - pd.Timedelta(days=14)).date())
    print(f"[1/5] Updating prices from YFinance since {start_date}...")
    
    try:
        raw = yf.download(
            tickers=tickers,
            start=start_date,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True
        )
    except Exception as e:
        print(f"YFinance download error: {e}")
        raw = None

    updated, inserted = 0, 0
    for ticker in tickers:
        clean_ticker = ticker.replace("^", "").replace("=F", "").replace("-Y.NYB", "")
        if ticker == "DX-Y.NYB": clean_ticker = "DXY"
        elif ticker == "GC=F": clean_ticker = "GC"
        elif ticker == "SI=F": clean_ticker = "SI"
        elif ticker == "^VIX": clean_ticker = "VIX"
        elif ticker == "^TNX": clean_ticker = "TNX"
        elif ticker == "^IRX": clean_ticker = "IRX"

        df = None
        if raw is not None and not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker in raw.columns.get_level_values(0):
                    df = raw[ticker].dropna(subset=["Close"])
            else:
                df = raw.dropna(subset=["Close"])

        # Fallback individual download se il batch ha saltato questo ticker
        if df is None or len(df) == 0:
            try:
                df = yf.download(ticker, start=start_date, auto_adjust=True, progress=False)
                if df is not None and not df.empty:
                    df = df.dropna(subset=["Close"])
            except Exception:
                df = None

        if df is None or len(df) == 0:
            continue

        for idx_date, row in df.iterrows():
            date_str = str(idx_date.date())
            close_val = float(row["Close"])
            if np.isnan(close_val):
                continue

            existing = db.query(PriceCache).filter_by(ticker=clean_ticker, date=date_str).first()
            if existing:
                existing.close = close_val
                existing.open = float(row.get("Open", close_val))
                existing.high = float(row.get("High", close_val))
                existing.low = float(row.get("Low", close_val))
                existing.volume = float(row.get("Volume", 0))
                updated += 1
            else:
                db.add(PriceCache(
                    ticker=clean_ticker,
                    date=date_str,
                    open=float(row.get("Open", close_val)),
                    high=float(row.get("High", close_val)),
                    low=float(row.get("Low", close_val)),
                    close=close_val,
                    volume=float(row.get("Volume", 0)),
                ))
                inserted += 1

    db.commit()
    max_date = db.execute(text("SELECT MAX(date) FROM price_cache")).fetchone()[0]
    print(f"Prices updated: {updated} updated, {inserted} inserted. Latest date in DB: {max_date}")


def train_xgb_models():
    """Allena i modelli XGBoost (Optuna Tuned e Baseline)."""
    dataset_dir = DRIVE_PATH
    path_infer  = os.path.join(dataset_dir, "INFERENZE_FULL_DATASET_O2TFM.parquet")
    path_ds     = os.path.join(dataset_dir, "DATASET_INFERENCE_READY.parquet")
    path_labels = os.path.join(dataset_dir, "TRIPLE_BARRIER_LABELS_OPTIMAL.parquet")

    df_infer_hist = pd.read_parquet(path_infer)
    df_ds_hist    = pd.read_parquet(path_ds)
    df_labels_hist = pd.read_parquet(path_labels)

    if not isinstance(df_ds_hist.index, pd.DatetimeIndex):
        if "Date" in df_ds_hist.columns:
            df_ds_hist["Date"] = pd.to_datetime(df_ds_hist["Date"])
            df_ds_hist = df_ds_hist.set_index("Date")

    df_ml_cols = [c for c in df_ds_hist.columns if c.startswith("ML_FEAT_")]

    df_infer_sub = df_infer_hist.copy()
    df_infer_sub["Date"] = pd.to_datetime(df_infer_sub["Date"])

    df_ds_reset = df_ds_hist[df_ml_cols].reset_index()
    if "Date" not in df_ds_reset.columns:
        df_ds_reset = df_ds_reset.rename(columns={df_ds_reset.columns[0]: "Date"})
    df_ds_reset["Date"] = pd.to_datetime(df_ds_reset["Date"])

    df_lbl_reset = df_labels_hist.reset_index()
    df_lbl_reset["Date"] = pd.to_datetime(df_lbl_reset["Date"])

    df_model = pd.merge(df_infer_sub, df_ds_reset, on="Date", how="inner")
    df_model = pd.merge(df_model, df_lbl_reset, on=["Date", "Ratio"], how="inner")

    train_mask = df_model["Date"] < pd.Timestamp("2019-01-01")
    fm_feat_cols = ["TFM_t1", "TFM_t5", "TFM_t20", "CHR_Median_t5", "CHR_Width_t5"]
    all_meta_cols = df_ml_cols + [c for c in fm_feat_cols if c in df_model.columns]

    X_train_meta = df_model.loc[train_mask, all_meta_cols]
    y_train_meta = df_model.loc[train_mask, "Label"]

    # XGBoost Optuna tuned model
    xgb_optuna_tfm3 = xgb.XGBClassifier(
        n_estimators=210, max_depth=7, learning_rate=0.01166,
        subsample=0.9972, colsample_bytree=0.5960, min_child_weight=2,
        gamma=4.991, reg_alpha=2.882, reg_lambda=1.824e-06,
        random_state=42, eval_metric='logloss'
    )
    xgb_optuna_tfm3.fit(X_train_meta, y_train_meta)

    # XGBoost Baseline model
    xgb_baseline = xgb.XGBClassifier(
        n_estimators=168, max_depth=3, learning_rate=0.049,
        random_state=42, eval_metric='logloss'
    )
    xgb_baseline.fit(X_train_meta, y_train_meta)

    return xgb_optuna_tfm3, xgb_baseline, df_ml_cols, all_meta_cols


def generate_xgb_series(db, model_obj, cache_source, df_ml_cols, all_meta_cols):
    """Simula il backtest settimanale per un dato modello XGBoost."""
    prices_db = _get_all_prices(db)
    fridays_db = _get_fridays(db)
    log_ratios_db = compute_log_ratios(prices_db)
    ml_features_db = compute_ml_features(prices_db, log_ratios_db)
    hmm_feat_db = compute_hmm_features(prices_db, fridays_db)
    regimes_db = run_hmm_inference(hmm_feat_db)

    params = BacktestParams(
        bet_quality=DEFAULT_BET_QUALITY, hrp_alpha=DEFAULT_HRP_ALPHA,
        k_sigmoid=DEFAULT_K_SIGMOID, c_soglia=DEFAULT_C_SOGLIA,
        k_up=DEFAULT_K_UP, k_down=DEFAULT_K_DOWN,
    )
    decay_db = _compute_decay(prices_db, fridays_db, params)

    sub_fridays = fridays_db[fridays_db >= pd.Timestamp(DISPLAY_START)]
    ops_fridays = _get_operational_fridays(db)

    results = []
    port_value = 1.0

    for i in range(len(sub_fridays) - 1):
        friday = sub_fridays[i]
        next_friday = sub_fridays[i + 1]

        if friday not in regimes_db.index:
            continue

        regime = int(regimes_db.loc[friday, "Regime_Final"])
        decay_val = float(decay_db.get(friday, 1.0))
        is_crisis = (regime == CRISIS_STATE_IDX)

        if is_crisis:
            week_ret = _crisis_basket_return(prices_db, friday, next_friday)
            n_trades = 4
        else:
            active_trades = []
            batch_rows = []
            batch_meta = []

            if friday in ml_features_db.index:
                row_feat = ml_features_db.loc[friday]
                base_features = {}
                for col in df_ml_cols:
                    raw_col = col.replace("ML_FEAT_", "")
                    if raw_col in row_feat.index:
                        base_features[col] = float(row_feat[raw_col])
                    elif col in row_feat.index:
                        base_features[col] = float(row_feat[col])
                    else:
                        base_features[col] = 0.0

                for ratio_id, (num, den) in RATIOS.items():
                    if ratio_id not in log_ratios_db.columns or friday not in log_ratios_db.index:
                        continue
                    cur_ratio = log_ratios_db.loc[friday, ratio_id]
                    key = (str(friday.date()), ratio_id)
                    if key not in cache_source:
                        continue
                    inferences = cache_source[key]
                    tfm_t5 = inferences.get("tfm_t5")
                    if tfm_t5 is None or np.isnan(tfm_t5):
                        continue
                    long_tick = num if tfm_t5 > cur_ratio else den

                    features = base_features.copy()
                    features["TFM_t1"] = inferences.get("tfm_t1", 0.0) or 0.0
                    features["TFM_t5"] = inferences.get("tfm_t5", 0.0) or 0.0
                    features["TFM_t20"] = inferences.get("tfm_t20", 0.0) or 0.0
                    features["CHR_Median_t5"] = inferences.get("chr_median_t5", 0.0) or 0.0
                    features["CHR_Width_t5"] = inferences.get("chr_width_t5", 0.0) or 0.0

                    batch_rows.append(features)
                    batch_meta.append({"long_ticker": long_tick})

            if batch_rows:
                df_batch = pd.DataFrame(batch_rows)[all_meta_cols]
                probs = model_obj.predict_proba(df_batch)[:, 1]
                for idx, prob in enumerate(probs):
                    if prob >= 0.50:
                        active_trades.append({"long_ticker": batch_meta[idx]["long_ticker"], "bet_quality": float(prob)})

            if not active_trades:
                week_ret = 0.0
                n_trades = 0
            else:
                n_trades = len(active_trades)
                active_tickers = list({t["long_ticker"] for t in active_trades})
                window_rets = pd.DataFrame({
                    t: prices_db[t]["Close"]
                         .reindex(fridays_db[fridays_db <= friday][-53:])
                         .pct_change()
                    for t in active_tickers if t in prices_db
                }).dropna()

                weights = compute_blended_weights(window_rets, active_tickers, params.hrp_alpha)
                ticker_sigma = window_rets.std().to_dict() if window_rets.shape[0] >= 4 else {}

                port_ret = 0.0
                for t in active_trades:
                    tick = t["long_ticker"]
                    w = weights.get(tick, 0)
                    sigma = ticker_sigma.get(tick, 0.0)
                    if sigma > 0:
                        ret = _weekly_ret_with_tpsl(prices_db, tick, friday, next_friday, params.k_up, params.k_down, sigma)
                    else:
                        ret = _weekly_ret(prices_db, tick, friday, next_friday)
                    port_ret += w * ret

                week_ret = port_ret * decay_val

        port_value *= (1 + week_ret)
        results.append({
            "friday_date": str(friday.date()),
            "portfolio_value": round(port_value, 6),
            "weekly_return": round(week_ret, 6),
            "regime": regime,
            "decay_value": round(decay_val, 4),
            "n_trades": n_trades,
            "is_crisis": is_crisis
        })

    display_series = [{"date": results[0]["friday_date"], "value": 1.0}]
    for row in results:
        entry_dt = pd.Timestamp(row["friday_date"])
        next_fris = ops_fridays[ops_fridays > entry_dt]
        if len(next_fris) > 0:
            exit_date = str(next_fris[0].date())
            display_series.append({"date": exit_date, "value": row["portfolio_value"]})

    vals = [p["value"] for p in display_series]
    rets = pd.Series([row["weekly_return"] for row in results])
    n = len(rets)
    tot_ret = vals[-1] - 1.0
    cagr = (vals[-1] ** (52.0 / n)) - 1.0 if n > 0 else 0.0
    sharpe = (rets.mean() * 52) / (rets.std() * np.sqrt(52)) if rets.std() > 0 else 0.0
    cummax = pd.Series(vals).cummax()
    max_dd = ((pd.Series(vals) - cummax) / cummax).min()
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0

    return {
        "series": display_series,
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "calmar": round(calmar, 4),
        "total_return": round(tot_ret, 4)
    }


def main():
    print("=== STARTING WEEKLY PIPELINE UPDATE ===")
    db = SessionLocal()

    try:
        # Step 1: Prezzi YFinance
        update_prices_from_yfinance(db)

        # Step 2: Inferenze Foundation Models
        print("[2/5] Checking and backfilling inferences (Chronos, TimesFM 2.5, TimesFM 3.0)...")
        backfill_inference(db)
        backfill_timesfm3_inference(db)

        # Step 3: Backtest di sistema
        print("[3/5] Computing Default LGBM and TimesFM 3.0 backtests...")
        compute_and_save_timesfm3_backtest(db)
        
        # Svuota cache backtest di default per forzare ricalcolo all'ultima data
        db.execute(text("DELETE FROM backtest_results"))
        db.commit()

        params = BacktestParams(
            bet_quality=DEFAULT_BET_QUALITY, hrp_alpha=DEFAULT_HRP_ALPHA,
            k_sigmoid=DEFAULT_K_SIGMOID, c_soglia=DEFAULT_C_SOGLIA,
            k_up=DEFAULT_K_UP, k_down=DEFAULT_K_DOWN, start_date=None,
        )
        default_backtest = jsonable_encoder(get_or_compute_backtest(params, db))
        timesfm3_backtest = jsonable_encoder(get_timesfm3_backtest_from_db(db))

        # Step 4: Addestramento ed esecuzione XGBoost
        print("[4/5] Training and evaluating XGBoost models...")
        xgb_optuna_tfm3, xgb_baseline, df_ml_cols, all_meta_cols = train_xgb_models()

        tfm25_cache = load_inference_cache(db)
        tfm30_cache = load_timesfm3_inference_cache(db)

        tfm3_xgb_optuna = jsonable_encoder(generate_xgb_series(db, xgb_optuna_tfm3, tfm30_cache, df_ml_cols, all_meta_cols))
        tfm25_xgb_base = jsonable_encoder(generate_xgb_series(db, xgb_baseline, tfm25_cache, df_ml_cols, all_meta_cols))

        # Step 5: Generazione Mock Data completo per il frontend
        print("[5/5] Extracting dashboard widgets and serializing mock-data.ts...")
        current_regime = jsonable_encoder(get_current_regime(db))
        market_snapshot = jsonable_encoder(get_market_snapshot(db))
        decay_history = jsonable_encoder(get_decay_history(db))
        drawdown = jsonable_encoder(get_drawdown(db))
        yearly_breakdown = jsonable_encoder(get_yearly_breakdown(db))
        operational_status = jsonable_encoder(get_operational_status(db))
        etf_performance = jsonable_encoder(get_etf_performance(db, None))
        regime_stats = jsonable_encoder(get_regime_stats(db, None))
        weekly_decomposition = jsonable_encoder(get_weekly_decomposition(db))

        fridays = get_available_fridays(db)
        weekly_signals = {}
        chronos_bands = {}
        for friday in fridays:
            weekly_signals[friday] = jsonable_encoder(get_weekly_signals(db, friday, DEFAULT_BET_QUALITY))
            chronos_bands[friday] = jsonable_encoder(get_chronos_bands(db, friday))

        correlation_heatmap = {}
        for window in ["1w", "1m", "3m", "6m", "52w"]:
            correlation_heatmap[window] = jsonable_encoder(get_correlation_heatmap(db, window, "alphabetical"))

        mock_data = {
            "defaultBacktest": default_backtest,
            "timesfm3Backtest": timesfm3_backtest,
            "tfm3XgbOptunaBacktest": tfm3_xgb_optuna,
            "tfm25XgbBaseBacktest": tfm25_xgb_base,
            "currentRegime": current_regime,
            "marketSnapshot": market_snapshot,
            "weeklySignals": weekly_signals,
            "chronosBands": chronos_bands,
            "decayHistory": decay_history,
            "correlationHeatmap": correlation_heatmap,
            "drawdown": drawdown,
            "yearlyBreakdown": yearly_breakdown,
            "etfPerformance": etf_performance,
            "regimeStats": regime_stats,
            "weeklyDecomposition": weekly_decomposition,
            "operationalStatus": operational_status
        }

        output_path = REPO_ROOT / "trading_dashboard" / "frontend" / "src" / "app" / "core" / "utils" / "mock-data.ts"
        print(f"Writing updated mock data to: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("// Automatically generated mock data from SQLite database\n")
            f.write("export const MOCK_DATA: any = ")
            json.dump(mock_data, f, indent=2, ensure_ascii=False)
            f.write(";\n")

        print("=== PIPELINE UPDATE COMPLETED SUCCESSFULLY ===")

    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
