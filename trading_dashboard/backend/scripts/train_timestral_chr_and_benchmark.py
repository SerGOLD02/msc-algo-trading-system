#!/usr/bin/env python3
"""
train_timestral_chr_and_benchmark.py

1. Crea il dataset storico combinato: Timestral-209M (t1, t5, t20) + Chronos (distribuzioni median/width).
2. Esegue l'ottimizzazione degli iperparametri di XGBoost con Optuna (50 trial, 5-fold Stratified CV)
   sul training set (2006-2018).
3. Salva XGB_TIMESTRAL_CHR_OPTUNA_MODEL.pkl e aggiorna OPTUNA_BEST_HYPERPARAMS_TFM3_TIMESTRAL.json.
4. Scarica e calcola il benchmark globale VWCE ad accumulazione (VWRA.L / VT in USD, allineato alla valuta del portafoglio).
5. Esegue il backtest comparativo completo su:
   - Training Set (2006-2018)
   - Validation Set (2019-2022)
   - Test Set OOS (2023-2025)
   - 2026 YTD (Live)
6. Aggiorna TABELLA_COMPARATIVA_MODELLI_NATIVI.csv e mock-data.ts.
"""

import os
import sys
import json
import time
import joblib
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import xgboost as xgb
import optuna
from sklearn.model_selection import StratifiedKFold, cross_val_score

warnings.filterwarnings('ignore')
optuna.logging.set_verbosity(optuna.logging.WARNING)

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent.parent if BACKEND_DIR.name == "backend" and BACKEND_DIR.parent.name == "trading_dashboard" else BACKEND_DIR.parent
DATASET_DIR = REPO_ROOT / "TESI DATI PULITI" / "Dataset"

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))

from database.connection import SessionLocal
from modules.backtest.service import (
    _get_all_prices, _get_fridays,
    _crisis_basket_return, _compute_decay,
    _weekly_ret_with_tpsl, _weekly_ret
)
from modules.features.service import compute_log_ratios, compute_ml_features
from modules.hmm.service import compute_hmm_features, run_hmm_inference
from modules.inference.service import load_inference_cache
from modules.timesfm3.service import load_timesfm3_inference_cache
from modules.timestral.service import load_timestral_inference_cache
from modules.meta_labeler.service import _load_lgb_model
from modules.hrp.service import compute_blended_weights
from config import (
    RATIOS, CRISIS_STATE_IDX, DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
    DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA, DEFAULT_K_UP, DEFAULT_K_DOWN
)
from modules.backtest.schemas import BacktestParams
from fastapi.encoders import jsonable_encoder


def main():
    print("=" * 80)
    print("FASE 1: CREAZIONE DATASET IBRIDO TIMESTRAL + CHRONOS")
    print("=" * 80)

    path_ds = DATASET_DIR / "DATASET_INFERENCE_READY.parquet"
    path_hmm = DATASET_DIR / "HMM_REGIMES.parquet"
    path_lbl = DATASET_DIR / "TRIPLE_BARRIER_LABELS_OPTIMAL.parquet"
    path_excel = DATASET_DIR / "DATI BLOOMBERG COMPLETI.xlsx"

    path_tfm25 = DATASET_DIR / "INFERENZE_FULL_DATASET_O2TFM.parquet"
    path_tfm30 = DATASET_DIR / "INFERENZE_FULL_DATASET_TFM3.parquet"
    path_tstr  = DATASET_DIR / "INFERENZE_FULL_DATASET_TIMESTRAL.parquet"
    path_tstr_chr = DATASET_DIR / "INFERENZE_FULL_DATASET_TIMESTRAL_CHR.parquet"

    df_ds_hist = pd.read_parquet(path_ds)
    df_hmm_hist = pd.read_parquet(path_hmm)
    df_lbl = pd.read_parquet(path_lbl)

    df_inf_tfm25 = pd.read_parquet(path_tfm25)
    df_inf_tfm30 = pd.read_parquet(path_tfm30)
    df_inf_tstr  = pd.read_parquet(path_tstr)

    # Crea dataset ibrido: t1, t5, t20 da Timestral; CHR_Median_t5, CHR_Width_t5 da Chronos (df_inf_tfm30)
    df_inf_tstr_chr = df_inf_tstr.copy()
    # Mappa Chronos median e width da df_inf_tfm30
    df_chr_map = df_inf_tfm30.set_index(["Date", "Ratio"])[["CHR_Median_t5", "CHR_Width_t5"]]
    df_inf_tstr_chr = df_inf_tstr_chr.set_index(["Date", "Ratio"])
    df_inf_tstr_chr["CHR_Median_t5"] = df_chr_map["CHR_Median_t5"]
    df_inf_tstr_chr["CHR_Width_t5"] = df_chr_map["CHR_Width_t5"]
    df_inf_tstr_chr = df_inf_tstr_chr.reset_index()

    df_inf_tstr_chr.to_parquet(path_tstr_chr)
    print(f"Dataset ibrido salvato: {path_tstr_chr} (Shape: {df_inf_tstr_chr.shape})")

    # Prepara feature per addestramento Optuna
    df_ml_cols = [c for c in df_ds_hist.columns if c.startswith("ML_FEAT_")]
    fm_feat_cols = ["TFM_t1", "TFM_t5", "TFM_t20", "CHR_Median_t5", "CHR_Width_t5"]
    all_meta_cols = df_ml_cols + fm_feat_cols

    df_inf_copy = df_inf_tstr_chr.copy()
    df_inf_copy["Date"] = pd.to_datetime(df_inf_copy["Date"])

    df_ds_reset = df_ds_hist[df_ml_cols].reset_index()
    if "Date" not in df_ds_reset.columns:
        df_ds_reset = df_ds_reset.rename(columns={df_ds_reset.columns[0]: "Date"})
    df_ds_reset["Date"] = pd.to_datetime(df_ds_reset["Date"])

    df_lbl_reset = df_lbl.reset_index() if isinstance(df_lbl.index, pd.MultiIndex) else df_lbl.copy()
    if "Date" not in df_lbl_reset.columns:
        df_lbl_reset = df_lbl_reset.rename(columns={df_lbl_reset.columns[0]: "Date"})
    df_lbl_reset["Date"] = pd.to_datetime(df_lbl_reset["Date"])

    df_m = pd.merge(df_inf_copy, df_ds_reset, on="Date", how="inner")
    df_m = pd.merge(df_m, df_lbl_reset, on=["Date", "Ratio"], how="inner")

    train_mask = df_m["Date"] < pd.Timestamp("2019-01-01")
    X_train = df_m.loc[train_mask, all_meta_cols]
    y_train = df_m.loc[train_mask, "Label"]

    print(f"Training set: {X_train.shape[0]} campioni x {X_train.shape[1]} feature. Target balance: {y_train.mean():.3f}")

    print("\n" + "=" * 80)
    print("FASE 2: OTTIMIZZAZIONE IPERPARAMETRI OPTUNA (50 TRIALS)")
    print("=" * 80)

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
    # Enqueue baseline
    study.enqueue_trial({
        'n_estimators': 168, 'max_depth': 3, 'learning_rate': 0.049,
        'subsample': 1.0, 'colsample_bytree': 1.0, 'min_child_weight': 1,
        'gamma': 0.0, 'reg_alpha': 1e-8, 'reg_lambda': 1.0
    })

    t0 = time.time()
    study.optimize(objective, n_trials=50)
    print(f"[Timestral + CHR + XGBoost] Optuna completato in {time.time() - t0:.1f}s.")
    print(f"Miglior ROC-AUC: {study.best_value:.5f}")
    print(f"Migliori Parametri: {study.best_params}")

    best_p = study.best_params.copy()
    best_p.update({'random_state': 42, 'eval_metric': 'logloss'})
    xgb_timestral_chr_optuna = xgb.XGBClassifier(**best_p)
    xgb_timestral_chr_optuna.fit(X_train, y_train)

    # Salva il modello serializzato
    model_save_path = DATASET_DIR / "XGB_TIMESTRAL_CHR_OPTUNA_MODEL.pkl"
    joblib.dump(xgb_timestral_chr_optuna, model_save_path)
    print(f"Modello salvato: {model_save_path}")

    # Aggiorna il file JSON degli iperparametri
    json_path = DATASET_DIR / "OPTUNA_BEST_HYPERPARAMS_TFM3_TIMESTRAL.json"
    hyper_dict = {}
    if json_path.exists():
        with open(json_path, 'r') as f:
            hyper_dict = json.load(f)
    hyper_dict["timestral_chr_xgb_optuna"] = best_p
    with open(json_path, 'w') as f:
        json.dump(hyper_dict, f, indent=2)
    print(f"File iperparametri aggiornato: {json_path}")

    print("\n" + "=" * 80)
    print("FASE 3: BENCHMARK VWCE AD ACCUMULAZIONE (USD, MATCHING PORTFOLIO)")
    print("=" * 80)

    # Scarica prezzi settimanali per VWRA.L (USD Acc) e VT (USD World proxy)
    print("Download prezzi VWRA.L e VT da Yahoo Finance...")
    df_vwra = yf.download("VWRA.L", start="2019-01-01", progress=False, auto_adjust=True)
    df_vt = yf.download("VT", start="2006-01-01", progress=False, auto_adjust=True)

    vwra_close = df_vwra["Close"].squeeze().dropna()
    vt_close = df_vt["Close"].squeeze().dropna()

    print(f"VWRA.L punti: {len(vwra_close)}, VT punti: {len(vt_close)}")

    print("\n" + "=" * 80)
    print("FASE 4: BACKTEST COMPARATIVO TUTTI I PERIODI E TUTTI I MODELLI")
    print("=" * 80)

    # Carica altri modelli
    lgb_model = _load_lgb_model()
    xgb_tfm3_optuna = joblib.load(DATASET_DIR / "XGB_TFM3_OPTUNA_MODEL.pkl")
    xgb_timestral_optuna = joblib.load(DATASET_DIR / "XGB_TIMESTRAL_OPTUNA_MODEL.pkl")

    # Baseline XGBoost
    df_inf_tfm25_c = df_inf_tfm25.copy()
    df_inf_tfm25_c["Date"] = pd.to_datetime(df_inf_tfm25_c["Date"])
    df_m_b = pd.merge(df_inf_tfm25_c, df_ds_reset, on="Date", how="inner")
    df_m_b = pd.merge(df_m_b, df_lbl_reset, on=["Date", "Ratio"], how="inner")
    xgb_baseline = xgb.XGBClassifier(n_estimators=168, max_depth=3, learning_rate=0.049, random_state=42, eval_metric='logloss')
    xgb_baseline.fit(df_m_b.loc[train_mask, all_meta_cols], df_m_b.loc[train_mask, "Label"])

    # Carica Bloomberg Excel per prezzi storici
    df_excel = pd.read_excel(path_excel, sheet_name="Sheet1", skiprows=[1, 2])
    df_excel = df_excel.rename(columns={"Unnamed: 0": "Date"})
    df_excel["Date"] = pd.to_datetime(df_excel["Date"])
    df_excel = df_excel.set_index("Date")
    for col in df_excel.columns:
        df_excel[col] = pd.to_numeric(df_excel[col], errors="coerce")

    bbg_to_yf = {
        'SPY US Equity': 'SPY', 'TLT US Equity': 'TLT', 'GLD US Equity': 'GLD',
        'UUP US Equity': 'UUP', 'FXE US Equity': 'FXE', 'LQD US Equity': 'LQD',
        'IEF US Equity': 'IEF', 'SHY US Equity': 'SHY', 'XLF US Equity': 'XLF',
        'XLU US Equity': 'XLU', 'QQQ US Equity': 'QQQ', 'IWM US Equity': 'IWM',
        'MDY US Equity': 'MDY', 'DIA US Equity': 'DIA', 'XLY US Equity': 'XLY',
        'XLP US Equity': 'XLP', 'XLK US Equity': 'XLK', 'XLE US Equity': 'XLE',
        'XLV US Equity': 'XLV', 'XLI US Equity': 'XLI', 'XLB US Equity': 'XLB',
        'EEM US Equity': 'EEM', 'EFA US Equity': 'EFA', 'SLV US Equity': 'SLV',
        'SOXX US Equity': 'SOXX', 'VNQ US Equity': 'VNQ', 'SH US Equity': 'SH',
        'PSQ US Equity': 'PSQ', 'RWM US Equity': 'RWM', 'VIXY US Equity': 'VIXY'
    }
    prices_hist = {
        yf_col: pd.DataFrame({"Close": df_excel[bbg_col], "High": df_excel[bbg_col], "Low": df_excel[bbg_col], "Volume": 1000000})
        for bbg_col, yf_col in bbg_to_yf.items() if bbg_col in df_excel.columns
    }

    def build_inf_dict(df_inf):
        res = {}
        for _, row in df_inf.iterrows():
            res[(str(row['Date']), str(row['Ratio']))] = {
                "tfm_t1": float(row['TFM_t1']),
                "tfm_t5": float(row['TFM_t5']),
                "tfm_t20": float(row['TFM_t20']),
                "chr_median_t5": float(row['CHR_Median_t5']),
                "chr_width_t5": float(row['CHR_Width_t5']),
            }
        return res

    inf_dict_tfm25   = build_inf_dict(df_inf_tfm25)
    inf_dict_tfm30   = build_inf_dict(df_inf_tfm30)
    inf_dict_tstr    = build_inf_dict(df_inf_tstr)
    inf_dict_tstr_chr = build_inf_dict(df_inf_tstr_chr)

    # Dati 2026 Live da SQLite
    db = SessionLocal()
    prices_db = _get_all_prices(db)
    fridays_db = _get_fridays(db)
    log_ratios_db = compute_log_ratios(prices_db)
    ml_features_db = compute_ml_features(prices_db, log_ratios_db)
    hmm_feat_db = compute_hmm_features(prices_db, fridays_db)
    regimes_db = run_hmm_inference(hmm_feat_db)
    params_bt = BacktestParams(
        bet_quality=DEFAULT_BET_QUALITY, hrp_alpha=DEFAULT_HRP_ALPHA,
        k_sigmoid=DEFAULT_K_SIGMOID, c_soglia=DEFAULT_C_SOGLIA,
        k_up=DEFAULT_K_UP, k_down=DEFAULT_K_DOWN,
    )
    decay_db = _compute_decay(prices_db, fridays_db, params_bt)
    tfm25_live_cache = load_inference_cache(db)
    tfm30_live_cache = load_timesfm3_inference_cache(db)
    tstr_live_cache  = load_timestral_inference_cache(db)
    db.close()

    # Live cache ibrido per 2026: t1, t5, t20 da Timestral; chr da Chronos (tfm30_live_cache)
    tstr_chr_live_cache = {}
    for k, t_val in tstr_live_cache.items():
        chr_val = tfm30_live_cache.get(k, {})
        tstr_chr_live_cache[k] = {
            "tfm_t1": t_val.get("tfm_t1", 0.0),
            "tfm_t5": t_val.get("tfm_t5", 0.0),
            "tfm_t20": t_val.get("tfm_t20", 0.0),
            "chr_median_t5": chr_val.get("chr_median_t5", t_val.get("chr_median_t5", 0.0)),
            "chr_width_t5": chr_val.get("chr_width_t5", t_val.get("chr_width_t5", 0.0)),
        }

    def simulate_period(start_date, end_date, model_obj, inf_dict, is_live_2026=False, live_cache=None):
        if is_live_2026:
            sub_fridays = fridays_db[fridays_db >= pd.Timestamp(start_date)]
            pr_source = prices_db
            reg_source = regimes_db
            decay_source = decay_db
            ml_source = ml_features_db
            lr_source = log_ratios_db
        else:
            log_r_hist = compute_log_ratios(prices_hist)
            start_dt = pd.Timestamp(start_date)
            end_dt = pd.Timestamp(end_date)
            sub_fridays = log_r_hist.index[(log_r_hist.index >= start_dt) & (log_r_hist.index <= end_dt)]
            sub_fridays = sub_fridays[sub_fridays.dayofweek == 4]
            pr_source = prices_hist
            reg_source = df_hmm_hist
            decay_source = None
            ml_source = df_ds_hist
            lr_source = log_r_hist

        port_value = 1.0
        results = []

        for i in range(len(sub_fridays) - 1):
            friday = sub_fridays[i]
            next_friday = sub_fridays[i + 1]
            fri_str = str(friday.date())

            regime = 0
            if "Regime_Final" in reg_source.columns and friday in reg_source.index:
                regime = int(reg_source.loc[friday, "Regime_Final"])

            decay_val = 1.0
            if decay_source is not None:
                decay_val = float(decay_source.get(friday, 1.0))

            is_crisis = (regime == CRISIS_STATE_IDX)

            if is_crisis:
                week_ret = _crisis_basket_return(pr_source, friday, next_friday)
            else:
                active_trades = []
                batch_rows = []
                batch_meta = []

                if friday in ml_source.index:
                    row_ml = ml_source.loc[friday]
                    base_feats = {}
                    for col in df_ml_cols:
                        raw = col.replace("ML_FEAT_", "")
                        if raw in row_ml.index:
                            base_feats[col] = float(row_ml[raw])
                        elif col in row_ml.index:
                            base_feats[col] = float(row_ml[col])
                        else:
                            base_feats[col] = 0.0

                    for ratio_id, (num, den) in RATIOS.items():
                        if ratio_id not in lr_source.columns:
                            continue
                        cur_ratio = lr_source.loc[friday, ratio_id]

                        if is_live_2026:
                            key = (fri_str, ratio_id)
                            if key not in live_cache:
                                continue
                            inf = live_cache[key]
                        else:
                            key = (fri_str, ratio_id)
                            if key not in inf_dict:
                                matches = [k for k in inf_dict.keys() if k[0] == fri_str and k[1].startswith(ratio_id)]
                                if not matches:
                                    continue
                                key = matches[0]
                            inf = inf_dict[key]

                        tfm_t5 = inf.get("tfm_t5")
                        if tfm_t5 is None or np.isnan(tfm_t5):
                            continue
                        long_tick = num if tfm_t5 > cur_ratio else den

                        feats = base_feats.copy()
                        feats["TFM_t1"] = inf.get("tfm_t1", 0.0) or 0.0
                        feats["TFM_t5"] = inf.get("tfm_t5", 0.0) or 0.0
                        feats["TFM_t20"] = inf.get("tfm_t20", 0.0) or 0.0
                        feats["CHR_Median_t5"] = inf.get("chr_median_t5", 0.0) or 0.0
                        feats["CHR_Width_t5"] = inf.get("chr_width_t5", 0.0) or 0.0

                        batch_rows.append(feats)
                        batch_meta.append({"long_ticker": long_tick})

                if not batch_rows:
                    week_ret = 0.0
                else:
                    df_b = pd.DataFrame(batch_rows)[all_meta_cols]
                    if hasattr(model_obj, "predict_proba"):
                        probs = model_obj.predict_proba(df_b)[:, 1]
                    else:
                        probs = model_obj.predict(df_b)

                    for idx, prob in enumerate(probs):
                        if prob >= 0.50:
                            active_trades.append({"long_ticker": batch_meta[idx]["long_ticker"], "bet_quality": float(prob)})

                    if not active_trades:
                        week_ret = 0.0
                    else:
                        active_tickers = list({t["long_ticker"] for t in active_trades})
                        window_rets = pd.DataFrame({
                            t: pr_source[t]["Close"]
                                 .reindex(sub_fridays[sub_fridays <= friday][-53:])
                                 .pct_change()
                            for t in active_tickers if t in pr_source
                        }).dropna()

                        weights = compute_blended_weights(window_rets, active_tickers, DEFAULT_HRP_ALPHA)
                        ticker_sigma = window_rets.std().to_dict() if window_rets.shape[0] >= 4 else {}

                        port_ret = 0.0
                        for t in active_trades:
                            tick = t["long_ticker"]
                            w = weights.get(tick, 0)
                            sigma = ticker_sigma.get(tick, 0.0)
                            if sigma > 0:
                                ret = _weekly_ret_with_tpsl(pr_source, tick, friday, next_friday, DEFAULT_K_UP, DEFAULT_K_DOWN, sigma)
                            else:
                                ret = _weekly_ret(pr_source, tick, friday, next_friday)
                            port_ret += w * ret

                        week_ret = port_ret * decay_val

            port_value *= (1 + week_ret)
            results.append({"date": fri_str, "ret": week_ret, "val": port_value})

        vals = [1.0] + [r["val"] for r in results]
        rets = pd.Series([r["ret"] for r in results])
        n = len(rets)
        tot_ret = vals[-1] - 1.0
        cagr = (vals[-1] ** (52.0 / n)) - 1.0 if n > 0 and vals[-1] > 0 else 0.0
        cummax = pd.Series(vals).cummax()
        max_dd = ((pd.Series(vals) - cummax) / cummax).min()
        sharpe = (rets.mean() * 52) / (rets.std() * np.sqrt(52)) if rets.std() > 0 else 0.0
        calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0
        win_rate = (rets > 0).mean() if n > 0 else 0.0

        series_display = [{"date": str(sub_fridays[0].date()), "value": 1.0}]
        for r in results:
            series_display.append({"date": r["date"], "value": round(r["val"], 6)})

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

    # Funzione per calcolare benchmark (SPY o VWCE)
    def compute_benchmark_period(start_date, end_date, tick_name, is_live_2026=False):
        if is_live_2026:
            sub_fridays = fridays_db[fridays_db >= pd.Timestamp(start_date)]
            pr_source = prices_db
        else:
            log_r_hist = compute_log_ratios(prices_hist)
            start_dt = pd.Timestamp(start_date)
            end_dt = pd.Timestamp(end_date)
            sub_fridays = log_r_hist.index[(log_r_hist.index >= start_dt) & (log_r_hist.index <= end_dt)]
            sub_fridays = sub_fridays[sub_fridays.dayofweek == 4]
            pr_source = prices_hist

        rets = []
        vals = [1.0]
        cur_val = 1.0

        for i in range(len(sub_fridays) - 1):
            f1 = sub_fridays[i]
            f2 = sub_fridays[i + 1]

            if tick_name == "SPY":
                if is_live_2026:
                    c1 = pr_source["SPY"]["Close"].get(f1)
                    c2 = pr_source["SPY"]["Close"].get(f2)
                else:
                    c1 = pr_source["SPY"]["Close"].get(f1)
                    c2 = pr_source["SPY"]["Close"].get(f2)
                r = (c2 / c1 - 1.0) if (c1 and c2 and c1 > 0) else 0.0
            elif tick_name == "VWCE":
                # Se f2 >= 2019-07-26 usa VWRA.L; altrimenti VT
                if f2 in vwra_close.index and f1 in vwra_close.index:
                    c1 = vwra_close.loc[f1]
                    c2 = vwra_close.loc[f2]
                    r = float(c2 / c1 - 1.0)
                else:
                    c1 = vt_close.asof(f1)
                    c2 = vt_close.asof(f2)
                    r = float(c2 / c1 - 1.0) if (c1 and c2 and c1 > 0) else 0.0

            cur_val *= (1 + r)
            rets.append(r)
            vals.append(cur_val)

        s_rets = pd.Series(rets)
        n = len(s_rets)
        tot_ret = vals[-1] - 1.0
        cagr = (vals[-1] ** (52.0 / n)) - 1.0 if n > 0 and vals[-1] > 0 else 0.0
        cummax = pd.Series(vals).cummax()
        max_dd = ((pd.Series(vals) - cummax) / cummax).min()
        sharpe = (s_rets.mean() * 52) / (s_rets.std() * np.sqrt(52)) if s_rets.std() > 0 else 0.0
        calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0
        win_rate = (s_rets > 0).mean() if n > 0 else 0.0

        series_display = [{"date": str(sub_fridays[0].date()), "value": 1.0}]
        for idx_r, r_val in enumerate(vals[1:]):
            series_display.append({"date": str(sub_fridays[idx_r + 1].date()), "value": round(r_val, 6)})

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

    periods = [
        ("Training Set (2006-2018)", "2006-04-07", "2018-12-28", False),
        ("Validation Set (2019-2022)", "2019-01-04", "2022-12-30", False),
        ("Test Set OOS (2023-2025)", "2023-01-06", "2025-12-26", False),
        ("2026 YTD (Live)", "2026-01-02", "2026-10-23", True),
    ]

    # Nomi compatti esatti richiesti dall'utente:
    # 1. TFM 2.5 + CHR + LGB (Algoritmo Tesi)
    # 2. TFM 2.5 + CHR + XGB (Base)
    # 3. TFM 3.0 + CHR + XGB (Opt)
    # 4. Timestral + XGB (Opt)
    # 5. Timestral + CHR + XGB (Opt)
    # 6. S&P 500
    # 7. VWCE (Acc)
    setups = [
        ("TFM 2.5 + CHR + LGB", lgb_model, inf_dict_tfm25, tfm25_live_cache),
        ("TFM 2.5 + CHR + XGB (Base)", xgb_baseline, inf_dict_tfm25, tfm25_live_cache),
        ("TFM 3.0 + CHR + XGB (Opt)", xgb_tfm3_optuna, inf_dict_tfm30, tfm30_live_cache),
        ("Timestral + XGB (Opt)", xgb_timestral_optuna, inf_dict_tstr, tstr_live_cache),
        ("Timestral + CHR + XGB (Opt)", xgb_timestral_chr_optuna, inf_dict_tstr_chr, tstr_chr_live_cache),
    ]

    benchmarks = [
        ("S&P 500", "SPY"),
        ("VWCE (Acc)", "VWCE")
    ]

    table_rows = []
    series_2026 = {}
    full_history_series = {}

    for p_name, s_date, e_date, is_live in periods:
        print(f"\nSimulazione: {p_name} ({s_date} -> {e_date})...")
        for s_name, model_obj, inf_d, live_c in setups:
            m = simulate_period(s_date, e_date, model_obj, inf_d, is_live_2026=is_live, live_cache=live_c)
            table_rows.append({
                "Periodo": p_name,
                "Setup": s_name,
                "CAGR (%)": m["CAGR (%)"],
                "Total Return (%)": m["Total Return (%)"],
                "Sharpe": m["Sharpe"],
                "MaxDD (%)": m["MaxDD (%)"],
                "Calmar": m["Calmar"],
                "Win Rate (%)": m["Win Rate (%)"],
                "N Weeks": m["N Weeks"]
            })
            if is_live:
                series_2026[s_name] = m

        for b_name, tick in benchmarks:
            m_b = compute_benchmark_period(s_date, e_date, tick, is_live_2026=is_live)
            table_rows.append({
                "Periodo": p_name,
                "Setup": b_name,
                "CAGR (%)": m_b["CAGR (%)"],
                "Total Return (%)": m_b["Total Return (%)"],
                "Sharpe": m_b["Sharpe"],
                "MaxDD (%)": m_b["MaxDD (%)"],
                "Calmar": m_b["Calmar"],
                "Win Rate (%)": m_b["Win Rate (%)"],
                "N Weeks": m_b["N Weeks"]
            })
            if is_live:
                series_2026[b_name] = m_b

    df_out = pd.DataFrame(table_rows)
    print("\n" + "=" * 115)
    print("TABELLA COMPARATIVA PERFORMANCE COMPLETA (TUTTI I PERIODI)")
    print("=" * 115)
    print(df_out.to_string(index=False))
    print("=" * 115)

    csv_path = DATASET_DIR / "TABELLA_COMPARATIVA_MODELLI_NATIVI.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"Risultati salvati in: {csv_path}")

    # Aggiorna mock-data.ts
    mock_file = REPO_ROOT / "trading_dashboard" / "frontend" / "src" / "app" / "core" / "utils" / "mock-data.ts"
    with open(mock_file, 'r', encoding='utf-8') as f:
        content = f.read()
    prefix = "// Automatically generated mock data from SQLite database\nexport const MOCK_DATA: any = "
    data = json.loads(content[len(prefix):].rstrip(';\n'))

    data["tfm25XgbBaseBacktest"] = jsonable_encoder(series_2026["TFM 2.5 + CHR + XGB (Base)"])
    data["tfm3XgbOptunaBacktest"] = jsonable_encoder(series_2026["TFM 3.0 + CHR + XGB (Opt)"])
    data["timestralXgbOptunaBacktest"] = jsonable_encoder(series_2026["Timestral + XGB (Opt)"])
    data["timestralChrXgbOptunaBacktest"] = jsonable_encoder(series_2026["Timestral + CHR + XGB (Opt)"])
    data["vwceBacktest"] = jsonable_encoder(series_2026["VWCE (Acc)"])

    # Aggiorna anche all'interno di defaultBacktest la serie VWCE se presente
    if "defaultBacktest" in data:
        data["defaultBacktest"]["vwce_series"] = series_2026["VWCE (Acc)"]["series"]
        data["defaultBacktest"]["vwce_cagr"] = series_2026["VWCE (Acc)"]["CAGR (%)"]
        data["defaultBacktest"]["vwce_sharpe"] = series_2026["VWCE (Acc)"]["Sharpe"]
        data["defaultBacktest"]["vwce_max_drawdown"] = series_2026["VWCE (Acc)"]["MaxDD (%)"]
        data["defaultBacktest"]["vwce_calmar"] = series_2026["VWCE (Acc)"]["Calmar"]
        data["defaultBacktest"]["vwce_total_return"] = series_2026["VWCE (Acc)"]["Total Return (%)"]

    with open(mock_file, 'w', encoding='utf-8') as f:
        f.write(prefix)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write(";\n")
    print(f"mock-data.ts aggiornato con successo: {mock_file}")


if __name__ == "__main__":
    main()
