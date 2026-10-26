#!/usr/bin/env python3
"""
generate_historical_datasets.py

Script per:
1. Generare le inferenze storiche complete (2006-2025, 996 venerdì x 20 ratio) con Timestral-209M.
   - Fornisce t1, t5, t20 e stima probabilistica interna (CHR_Median_t5, CHR_Width_t5).
2. Generare le inferenze storiche complete (2006-2025, 996 venerdì x 20 ratio) con TimesFM 3.0.
   - Fornisce t1, t5, t20 da TimesFM 3.0, accoppiato con le distribuzioni Chronos della tesi.
3. Eseguire l'ottimizzazione degli iperparametri di XGBoost con Optuna (50 trial ciascuno)
   in 5-fold Stratified Cross-Validation sul training set (2006-2018).
4. Valutare e confrontare i backtest completi su:
   - Train (2006-2018)
   - Validation (2019-2022)
   - Test OOS (2023-2025)
   - 2026 YTD
5. Aggiornare le serie storiche per il frontend della dashboard.
"""

import sys
import os
import time
import math
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import optuna
import xgboost as xgb
from sklearn.model_selection import StratifiedKFold, cross_val_score

warnings.filterwarnings('ignore')
optuna.logging.set_verbosity(optuna.logging.WARNING)

# Suppress HF warnings
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

# Percorsi principali
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent.parent if BACKEND_DIR.name == "backend" and BACKEND_DIR.parent.name == "trading_dashboard" else BACKEND_DIR.parent
DATASET_DIR = REPO_ROOT / "TESI DATI PULITI" / "Dataset"

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))

from database.connection import SessionLocal
from database.models import PriceCache, TimestralInferenceCache, TimesFM3InferenceCache
from modules.backtest.service import (
    _get_all_prices, _get_fridays, _get_operational_fridays,
    _crisis_basket_return, _compute_decay,
    _weekly_ret_with_tpsl, _weekly_ret
)
from modules.features.service import compute_log_ratios, compute_ml_features
from modules.hmm.service import compute_hmm_features, run_hmm_inference
from modules.hrp.service import compute_blended_weights
from config import (
    RATIOS, CRISIS_STATE_IDX, DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
    DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA, DEFAULT_K_UP, DEFAULT_K_DOWN
)
from modules.backtest.schemas import BacktestParams

CONTEXT_LEN = 512
HORIZON_MAX = 20

PATH_DS_PARQUET = DATASET_DIR / "DATASET_INFERENCE_READY.parquet"
PATH_O2_PARQUET = DATASET_DIR / "INFERENZE_FULL_DATASET_O2TFM.parquet"
PATH_LABELS_PARQUET = DATASET_DIR / "TRIPLE_BARRIER_LABELS_OPTIMAL.parquet"
PATH_HMM_PARQUET = DATASET_DIR / "HMM_REGIMES.parquet"
PATH_PRICES_EXCEL = DATASET_DIR / "DATI BLOOMBERG COMPLETI.xlsx"

PATH_TIMESTRAL_PARQUET = DATASET_DIR / "INFERENZE_FULL_DATASET_TIMESTRAL.parquet"
PATH_TIMESTRAL_CKPT    = DATASET_DIR / "INFERENZE_CHECKPOINT_TIMESTRAL.parquet"

PATH_TFM3_PARQUET = DATASET_DIR / "INFERENZE_FULL_DATASET_TFM3.parquet"
PATH_TFM3_CKPT    = DATASET_DIR / "INFERENZE_CHECKPOINT_TFM3.parquet"


# ==============================================================================
# FASE 1: GENERAZIONE INFERENZE STORICHE TIMESTRAL-209M (2006-2025)
# ==============================================================================
def generate_timestral_historical(df_ds, target_dates, ratio_cols):
    if PATH_TIMESTRAL_PARQUET.exists():
        print(f"[TIMESTRAL] Dataset storico già presente in: {PATH_TIMESTRAL_PARQUET}")
        df_existing = pd.read_parquet(PATH_TIMESTRAL_PARQUET)
        if len(df_existing) == len(target_dates) * len(ratio_cols):
            print(f"[TIMESTRAL] Record completi ({len(df_existing)} righe). Saltando generazione.")
            return df_existing

    print("\n" + "="*80)
    print("[FASE 1/4] GENERAZIONE INFERENZE STORICHE TIMESTRAL-209M (Mistral AI)")
    print("="*80)

    from timestral import TimestralForecaster
    t0_load = time.time()
    print("[TIMESTRAL] Caricamento modello mistralai/Timestral-209M su CPU...")
    forecaster = TimestralForecaster.from_pretrained("mistralai/Timestral-209M", device="cpu")
    print(f"[TIMESTRAL] Modello caricato in {time.time() - t0_load:.2f}s")

    records = []
    processed_dates = set()
    if PATH_TIMESTRAL_CKPT.exists():
        df_ckpt = pd.read_parquet(PATH_TIMESTRAL_CKPT)
        records = df_ckpt.to_dict('records')
        processed_dates = set(df_ckpt['Date'].unique())
        print(f"[TIMESTRAL] Ripristino da checkpoint: {len(processed_dates)} venerdì già completati.")

    dates_to_do = [d for d in target_dates if str(pd.Timestamp(d).date()) not in processed_dates]
    print(f"[TIMESTRAL] Venerdì da processare: {len(dates_to_do)} / {len(target_dates)}")

    t0_all = time.time()
    for idx_loop, d in enumerate(dates_to_do):
        dt = pd.Timestamp(d)
        str_d = str(dt.date())

        if dt not in df_ds.index:
            continue
        row_loc = df_ds.index.get_loc(dt)
        if row_loc < CONTEXT_LEN - 1:
            continue

        sub_slice = df_ds[ratio_cols].iloc[row_loc - CONTEXT_LEN + 1 : row_loc + 1]
        clean_vals = sub_slice.values.T.astype(np.float32)
        if np.isnan(clean_vals).any():
            clean_vals = np.nan_to_num(clean_vals, nan=0.0)

        # Batch forecast (20 ratios, 512 context) -> horizon=20
        res = forecaster.forecast(context=clean_vals, prediction_length=20)

        for i, ratio_id in enumerate(ratio_cols):
            t1 = float(res.median[i, 0, 0])
            t5 = float(res.median[i, 0, 4])
            t20 = float(res.median[i, 0, 19])
            q05 = float(res.quantiles[i, 0, 4, 1])
            q95 = float(res.quantiles[i, 0, 4, 19])
            width = max(0.0001, q95 - q05)

            records.append({
                'Date': str_d,
                'Ratio': ratio_id,
                'TFM_t1': t1,
                'TFM_t5': t5,
                'TFM_t20': t20,
                'CHR_Median_t5': t5,
                'CHR_Width_t5': width,
            })

        if (idx_loop + 1) % 25 == 0 or (idx_loop + 1) == len(dates_to_do):
            elapsed = time.time() - t0_all
            pace = elapsed / (idx_loop + 1)
            remaining_sec = pace * (len(dates_to_do) - (idx_loop + 1))
            print(f"[TIMESTRAL] Processati {idx_loop + 1}/{len(dates_to_do)} venerdì ({str_d}) - Passo: {pace:.2f}s/venerdì - Rimanente: {remaining_sec/60:.1f} min")
            pd.DataFrame(records).to_parquet(PATH_TIMESTRAL_CKPT, index=False)

    df_out = pd.DataFrame(records)
    df_out.to_parquet(PATH_TIMESTRAL_PARQUET, index=False)
    if PATH_TIMESTRAL_CKPT.exists():
        os.remove(PATH_TIMESTRAL_CKPT)
    print(f"[TIMESTRAL] Salvate con successo {len(df_out)} inferenze in: {PATH_TIMESTRAL_PARQUET}")
    return df_out


# ==============================================================================
# FASE 2: GENERAZIONE INFERENZE STORICHE TIMESFM 3.0 (2006-2025)
# ==============================================================================
def generate_timesfm3_historical(df_ds, target_dates, ratio_cols, df_chronos_ref):
    if PATH_TFM3_PARQUET.exists():
        print(f"[TIMESFM 3.0] Dataset storico già presente in: {PATH_TFM3_PARQUET}")
        df_existing = pd.read_parquet(PATH_TFM3_PARQUET)
        if len(df_existing) == len(target_dates) * len(ratio_cols):
            print(f"[TIMESFM 3.0] Record completi ({len(df_existing)} righe). Saltando generazione.")
            return df_existing

    print("\n" + "="*80)
    print("[FASE 2/4] GENERAZIONE INFERENZE STORICHE TIMESFM 3.0 (Google)")
    print("="*80)

    from timesfm import TimesFM3Forecaster
    t0_load = time.time()
    print("[TIMESFM 3.0] Caricamento modello google/timesfm-3.0-pytorch su CPU...")
    forecaster = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch", device="cpu")
    print(f"[TIMESFM 3.0] Modello caricato in {time.time() - t0_load:.2f}s")

    # Mappa Chronos dalla tesi (Date, Ratio) -> (CHR_Median_t5, CHR_Width_t5)
    chr_map = {}
    for _, row in df_chronos_ref.iterrows():
        chr_map[(str(row['Date']), str(row['Ratio']))] = (
            float(row['CHR_Median_t5']), float(row['CHR_Width_t5'])
        )

    records = []
    processed_dates = set()
    if PATH_TFM3_CKPT.exists():
        df_ckpt = pd.read_parquet(PATH_TFM3_CKPT)
        records = df_ckpt.to_dict('records')
        processed_dates = set(df_ckpt['Date'].unique())
        print(f"[TIMESFM 3.0] Ripristino da checkpoint: {len(processed_dates)} venerdì già completati.")

    dates_to_do = [d for d in target_dates if str(pd.Timestamp(d).date()) not in processed_dates]
    print(f"[TIMESFM 3.0] Venerdì da processare: {len(dates_to_do)} / {len(target_dates)}")

    t0_all = time.time()
    for idx_loop, d in enumerate(dates_to_do):
        dt = pd.Timestamp(d)
        str_d = str(dt.date())

        if dt not in df_ds.index:
            continue
        row_loc = df_ds.index.get_loc(dt)
        if row_loc < CONTEXT_LEN - 1:
            continue

        contexts = []
        for r_name in ratio_cols:
            arr = df_ds[r_name].iloc[row_loc - CONTEXT_LEN + 1 : row_loc + 1].values.astype(np.float32)
            if np.isnan(arr).any():
                arr = np.nan_to_num(arr, nan=0.0)
            contexts.append(arr)

        outputs = list(forecaster.predict_batch(
            contexts=contexts,
            horizon=20,
            return_quantiles=False,
            use_symmetric_averaging=True
        ))

        for i, ratio_id in enumerate(ratio_cols):
            fc = outputs[i].forecast
            t1 = float(fc[0])
            t5 = float(fc[4])
            t20 = float(fc[19])

            chr_med, chr_w = chr_map.get((str_d, ratio_id), (t5, 0.05))

            records.append({
                'Date': str_d,
                'Ratio': ratio_id,
                'TFM_t1': t1,
                'TFM_t5': t5,
                'TFM_t20': t20,
                'CHR_Median_t5': chr_med,
                'CHR_Width_t5': chr_w,
            })

        if (idx_loop + 1) % 25 == 0 or (idx_loop + 1) == len(dates_to_do):
            elapsed = time.time() - t0_all
            pace = elapsed / (idx_loop + 1)
            remaining_sec = pace * (len(dates_to_do) - (idx_loop + 1))
            print(f"[TIMESFM 3.0] Processati {idx_loop + 1}/{len(dates_to_do)} venerdì ({str_d}) - Passo: {pace:.2f}s/venerdì - Rimanente: {remaining_sec/60:.1f} min")
            pd.DataFrame(records).to_parquet(PATH_TFM3_CKPT, index=False)

    df_out = pd.DataFrame(records)
    df_out.to_parquet(PATH_TFM3_PARQUET, index=False)
    if PATH_TFM3_CKPT.exists():
        os.remove(PATH_TFM3_CKPT)
    print(f"[TIMESFM 3.0] Salvate con successo {len(df_out)} inferenze in: {PATH_TFM3_PARQUET}")
    return df_out


# ==============================================================================
# FASE 3: OTTIMIZZAZIONE OPTUNA (50 TRIALS) PER CIASCUN MODELLO
# ==============================================================================
def optimize_optuna_for_dataset(df_infer, df_ds, df_labels, name_tag, n_trials=50):
    print("\n" + "="*80)
    print(f"[FASE 3] OTTIMIZZAZIONE OPTUNA (50 TRIALS) PER: {name_tag}")
    print("="*80)

    df_ml_cols = [c for c in df_ds.columns if c.startswith("ML_FEAT_")]

    df_infer_sub = df_infer.copy()
    df_infer_sub["Date"] = pd.to_datetime(df_infer_sub["Date"])

    df_ds_reset = df_ds[df_ml_cols].reset_index()
    if "Date" not in df_ds_reset.columns:
        df_ds_reset = df_ds_reset.rename(columns={df_ds_reset.columns[0]: "Date"})
    df_ds_reset["Date"] = pd.to_datetime(df_ds_reset["Date"])

    df_lbl_reset = df_labels.reset_index() if isinstance(df_labels.index, pd.MultiIndex) else df_labels.copy()
    if "Date" not in df_lbl_reset.columns:
        df_lbl_reset = df_lbl_reset.rename(columns={df_lbl_reset.columns[0]: "Date"})
    df_lbl_reset["Date"] = pd.to_datetime(df_lbl_reset["Date"])

    # Normalizza ratio column se necessario (es. R01 vs R01_Risk Sentiment)
    df_model = pd.merge(df_infer_sub, df_ds_reset, on="Date", how="inner")
    df_model = pd.merge(df_model, df_lbl_reset, on=["Date", "Ratio"], how="inner")

    train_mask = df_model["Date"] < pd.Timestamp("2019-01-01")
    fm_feat_cols = ["TFM_t1", "TFM_t5", "TFM_t20", "CHR_Median_t5", "CHR_Width_t5"]
    all_meta_cols = df_ml_cols + fm_feat_cols

    X_train = df_model.loc[train_mask, all_meta_cols]
    y_train = df_model.loc[train_mask, "Label"]

    print(f"[{name_tag}] Dataset Training (2006-2018): {len(X_train)} righe, {len(all_meta_cols)} features.")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 80, 350, step=10),
            'max_depth': trial.suggest_int('max_depth', 2, 7),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.15, log=True),
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'gamma': trial.suggest_float('gamma', 0.0, 5.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
            'random_state': 42,
            'eval_metric': 'logloss'
        }
        clf = xgb.XGBClassifier(**params)
        scores = cross_val_score(clf, X_train, y_train, cv=cv, scoring='roc_auc', n_jobs=-1)
        return scores.mean()

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    # Enqueue baseline come trial 0
    study.enqueue_trial({
        'n_estimators': 168, 'max_depth': 3, 'learning_rate': 0.049,
        'subsample': 1.0, 'colsample_bytree': 1.0, 'min_child_weight': 1,
        'gamma': 0.0, 'reg_alpha': 1e-8, 'reg_lambda': 1.0
    })

    t0 = time.time()
    study.optimize(objective, n_trials=n_trials)
    print(f"[{name_tag}] Optuna completato in {time.time() - t0:.1f}s. Best ROC-AUC: {study.best_value:.5f}")
    print(f"[{name_tag}] Best Parameters: {study.best_params}")

    best_p = study.best_params
    best_p.update({'random_state': 42, 'eval_metric': 'logloss'})
    best_model = xgb.XGBClassifier(**best_p)
    best_model.fit(X_train, y_train)

    return best_model, best_p, all_meta_cols, df_ml_cols


# ==============================================================================
# FASE 4: BACKTEST COMPARATIVO STORICO & LIVE 2026
# ==============================================================================
def evaluate_setup_simulation(model_obj, inf_dict, df_ds_hist, df_hmm_hist, prices_dict, fridays_list, all_meta_cols, df_ml_cols):
    results = []
    port_value = 1.0

    for i in range(len(fridays_list) - 1):
        friday = fridays_list[i]
        next_friday = fridays_list[i + 1]
        fri_str = str(friday.date())

        regime = 0
        if "Regime_Final" in df_hmm_hist.columns and friday in df_hmm_hist.index:
            regime = int(df_hmm_hist.loc[friday, "Regime_Final"])

        is_crisis = (regime == CRISIS_STATE_IDX)

        if is_crisis:
            week_ret = _crisis_basket_return(prices_dict, friday, next_friday)
            n_trades = 4
        else:
            active_trades = []
            batch_rows = []
            batch_meta = []

            if friday in df_ds_hist.index:
                row_ds = df_ds_hist.loc[friday]
                base_features = {col: float(row_ds[col]) if col in row_ds else 0.0 for col in df_ml_cols}

                for ratio_id, (num, den) in RATIOS.items():
                    key = (fri_str, ratio_id)
                    if key not in inf_dict:
                        # Prova con prefisso RXX
                        matches = [k for k in inf_dict.keys() if k[0] == fri_str and k[1].startswith(ratio_id)]
                        if not matches:
                            continue
                        key = matches[0]

                    inf = inf_dict[key]
                    tfm_t5 = inf.get("tfm_t5")
                    if tfm_t5 is None or np.isnan(tfm_t5):
                        continue

                    # Direzione
                    cur_ratio = row_ds.get(ratio_id, 0.0)
                    long_tick = num if tfm_t5 > cur_ratio else den

                    feats = base_features.copy()
                    feats["TFM_t1"] = inf.get("tfm_t1", 0.0) or 0.0
                    feats["TFM_t5"] = inf.get("tfm_t5", 0.0) or 0.0
                    feats["TFM_t20"] = inf.get("tfm_t20", 0.0) or 0.0
                    feats["CHR_Median_t5"] = inf.get("chr_median_t5", 0.0) or 0.0
                    feats["CHR_Width_t5"] = inf.get("chr_width_t5", 0.0) or 0.0

                    batch_rows.append(feats)
                    batch_meta.append({"long_ticker": long_tick})

            if batch_rows:
                df_batch = pd.DataFrame(batch_rows)[all_meta_cols]
                probs = model_obj.predict_proba(df_batch)[:, 1]
                for idx_p, prob in enumerate(probs):
                    if prob >= 0.50:
                        active_trades.append({"long_ticker": batch_meta[idx_p]["long_ticker"], "bet_quality": float(prob)})

            if not active_trades:
                week_ret = 0.0
                n_trades = 0
            else:
                n_trades = len(active_trades)
                active_tickers = list({t["long_ticker"] for t in active_trades})
                window_rets = pd.DataFrame({
                    t: prices_dict[t]["Close"]
                         .reindex(fridays_list[fridays_list <= friday][-53:])
                         .pct_change()
                    for t in active_tickers if t in prices_dict
                }).dropna()

                weights = compute_blended_weights(window_rets, active_tickers, DEFAULT_HRP_ALPHA)
                ticker_sigma = window_rets.std().to_dict() if window_rets.shape[0] >= 4 else {}

                port_ret = 0.0
                for t in active_trades:
                    tick = t["long_ticker"]
                    w = weights.get(tick, 0)
                    sigma = ticker_sigma.get(tick, 0.0)
                    if sigma > 0:
                        ret = _weekly_ret_with_tpsl(prices_dict, tick, friday, next_friday, DEFAULT_K_UP, DEFAULT_K_DOWN, sigma)
                    else:
                        ret = _weekly_ret(prices_dict, tick, friday, next_friday)
                    port_ret += w * ret

                week_ret = port_ret

        port_value *= (1 + week_ret)
        results.append({
            "date": fri_str,
            "weekly_return": week_ret,
            "portfolio_value": port_value,
            "n_trades": n_trades
        })

    vals = [1.0] + [r["portfolio_value"] for r in results]
    rets = pd.Series([r["weekly_return"] for r in results])
    n = len(rets)
    tot_ret = (vals[-1] - 1.0)
    cagr = (vals[-1] ** (52.0 / n)) - 1.0 if n > 0 and vals[-1] > 0 else 0.0
    cummax = pd.Series(vals).cummax()
    max_dd = ((pd.Series(vals) - cummax) / cummax).min()
    sharpe = (rets.mean() * 52) / (rets.std() * np.sqrt(52)) if rets.std() > 0 else 0.0
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0
    win_rate = (rets > 0).mean() if n > 0 else 0.0

    series_display = [{"date": str(fridays_list[0].date()), "value": 1.0}]
    for r in results:
        series_display.append({"date": r["date"], "value": round(r["portfolio_value"], 6)})

    return {
        "series": series_display,
        "CAGR (%)": round(cagr * 100, 2),
        "Total Return (%)": round(tot_ret * 100, 2),
        "Sharpe": round(sharpe, 2),
        "MaxDD (%)": round(max_dd * 100, 2),
        "Calmar": round(calmar, 2),
        "Win Rate (%)": round(win_rate * 100, 2),
        "N Weeks": n
    }


def main():
    print("=== INIZIALIZZAZIONE PIPELINE STORICA FOUNDATION MODELS ===")
    
    # 1. Carica dataset Bloomberg e Parquet
    df_ds = pd.read_parquet(PATH_DS_PARQUET)
    df_o2 = pd.read_parquet(PATH_O2_PARQUET)
    df_lbl = pd.read_parquet(PATH_LABELS_PARQUET)
    
    target_dates = sorted(df_o2['Date'].unique())
    ratio_cols = [
        'R01_Risk Sentiment', 'R02_Real Rates Hedge', 'R03_Safe Haven Pivot',
        'R04_Currency War', 'R05_Credit Stress', 'R06_Yield Curve',
        'R07_Rate Bets', 'R08_Tech Alpha', 'R09_Small Cap Health',
        'R10_Mid Cap Cycle', 'R11_Value Rotation', 'R12_Consumer Cycle',
        'R13_New/Old Economy', 'R14_Defensive Rotation', 'R15_Industrial Momentum',
        'R16_Commodity Infl Pulse', 'R17_Global Risk', 'R18_Industrial Cycle',
        'R19_Semiconductor Cycle', 'R20_Real Estate vs Rates'
    ]

    print(f"Venerdì storici di mercato: {len(target_dates)} (dal {target_dates[0]} al {target_dates[-1]})")
    print(f"Ratio analizzati: {len(ratio_cols)}")

    # 2. Genera o carica dataset Timestral storico
    df_timestral_hist = generate_timestral_historical(df_ds, target_dates, ratio_cols)

    # 3. Genera o carica dataset TimesFM 3.0 storico
    df_tfm3_hist = generate_timesfm3_historical(df_ds, target_dates, ratio_cols, df_o2)

    # 4. Ottimizza Optuna per Timestral e per TimesFM 3.0
    xgb_tfm3_optuna, p_tfm3, cols_tfm3, ml_cols = optimize_optuna_for_dataset(
        df_tfm3_hist, df_ds, df_lbl, name_tag="TimesFM 3.0 + Chronos + XGBoost"
    )

    xgb_timestral_optuna, p_tstral, cols_tstral, _ = optimize_optuna_for_dataset(
        df_timestral_hist, df_ds, df_lbl, name_tag="Timestral All-In-One + XGBoost"
    )

    print("\n" + "="*80)
    print("CONFRONTO IPERPARAMETRI OTTIMIZZATI CON OPTUNA:")
    print("="*80)
    print("Parametri TimesFM 3.0 + XGBoost (Optuna):")
    for k, v in p_tfm3.items(): print(f"  {k}: {v}")
    print("\nParametri Timestral-209M + XGBoost (Optuna):")
    for k, v in p_tstral.items(): print(f"  {k}: {v}")
    print("="*80)

    # Salva i parametri ottimali e i modelli su disco
    p_path = DATASET_DIR / "OPTUNA_BEST_HYPERPARAMS_TFM3_TIMESTRAL.json"
    import json
    import joblib
    with open(p_path, 'w') as f:
        json.dump({
            "timesfm3_xgb_optuna": p_tfm3,
            "timestral_xgb_optuna": p_tstral
        }, f, indent=2)
    print(f"Iperparametri salvati in: {p_path}")

    joblib.dump(xgb_tfm3_optuna, DATASET_DIR / "XGB_TFM3_OPTUNA_MODEL.pkl")
    joblib.dump(xgb_timestral_optuna, DATASET_DIR / "XGB_TIMESTRAL_OPTUNA_MODEL.pkl")
    print(f"Modelli serializzati in: {DATASET_DIR}")

    print("\n=== GENERAZIONE E TRAINING COMPLETATI CON SUCCESSO ===")


if __name__ == "__main__":
    main()
