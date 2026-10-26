#!/usr/bin/env python3
"""
evaluate_all_final_setups.py

Valuta tutti i setup con i rispettivi modelli riaddestrati nativamente sui dataset storici:
1. Algoritmo (TFM 2.5 + LightGBM Ufficiale)
2. TFM 3.0 + XGBoost (Optuna Nativo 50 Trials)
3. Timestral All-In-One + XGBoost (Optuna Nativo 50 Trials)
4. TFM 2.5 + XGBoost (Baseline)
5. S&P 500 (Buy & Hold)

Calcola le metriche su:
- Training (2006-2018)
- Validation (2019-2022)
- Test OOS (2023-2025)
- 2026 YTD
"""

import os
import sys
import json
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent.parent if BACKEND_DIR.name == "backend" and BACKEND_DIR.parent.name == "trading_dashboard" else BACKEND_DIR.parent
DATASET_DIR = REPO_ROOT / "TESI DATI PULITI" / "Dataset"

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))

from database.connection import SessionLocal
from modules.backtest.service import (
    _get_all_prices, _get_fridays, _get_operational_fridays,
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

# 1. Carica dataset storici
PATH_DS = DATASET_DIR / "DATASET_INFERENCE_READY.parquet"
PATH_HMM = DATASET_DIR / "HMM_REGIMES.parquet"
PATH_EXCEL = DATASET_DIR / "DATI BLOOMBERG COMPLETI.xlsx"

PATH_INFER_TFM25 = DATASET_DIR / "INFERENZE_FULL_DATASET_O2TFM.parquet"
PATH_INFER_TFM30 = DATASET_DIR / "INFERENZE_FULL_DATASET_TFM3.parquet"
PATH_INFER_TSTR  = DATASET_DIR / "INFERENZE_FULL_DATASET_TIMESTRAL.parquet"

df_ds_hist = pd.read_parquet(PATH_DS)
df_hmm_hist = pd.read_parquet(PATH_HMM)

df_inf_tfm25 = pd.read_parquet(PATH_INFER_TFM25)
df_inf_tfm30 = pd.read_parquet(PATH_INFER_TFM30)
df_inf_tstr  = pd.read_parquet(PATH_INFER_TSTR)

df_excel = pd.read_excel(PATH_EXCEL, sheet_name="Sheet1", skiprows=[1, 2])
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
prices_hist = {yf_col: pd.DataFrame({"Close": df_excel[bbg_col], "High": df_excel[bbg_col], "Low": df_excel[bbg_col], "Volume": 1000000}) for bbg_col, yf_col in bbg_to_yf.items() if bbg_col in df_excel.columns}

df_ml_cols = [c for c in df_ds_hist.columns if c.startswith("ML_FEAT_")]
fm_feat_cols = ["TFM_t1", "TFM_t5", "TFM_t20", "CHR_Median_t5", "CHR_Width_t5"]
all_meta_cols = df_ml_cols + fm_feat_cols

# 2. Carica modelli
lgb_model = _load_lgb_model()
xgb_tfm3_optuna = joblib.load(DATASET_DIR / "XGB_TFM3_OPTUNA_MODEL.pkl")
xgb_timestral_optuna = joblib.load(DATASET_DIR / "XGB_TIMESTRAL_OPTUNA_MODEL.pkl")

# Modello baseline XGB
import xgboost as xgb
df_lbl = pd.read_parquet(DATASET_DIR / "TRIPLE_BARRIER_LABELS_OPTIMAL.parquet")
df_inf_copy = df_inf_tfm25.copy()
df_inf_copy["Date"] = pd.to_datetime(df_inf_copy["Date"])
df_ds_reset = df_ds_hist[df_ml_cols].reset_index()
if "Date" not in df_ds_reset.columns: df_ds_reset = df_ds_reset.rename(columns={df_ds_reset.columns[0]: "Date"})
df_ds_reset["Date"] = pd.to_datetime(df_ds_reset["Date"])
df_lbl_reset = df_lbl.reset_index() if isinstance(df_lbl.index, pd.MultiIndex) else df_lbl.copy()
if "Date" not in df_lbl_reset.columns: df_lbl_reset = df_lbl_reset.rename(columns={df_lbl_reset.columns[0]: "Date"})
df_lbl_reset["Date"] = pd.to_datetime(df_lbl_reset["Date"])
df_m = pd.merge(df_inf_copy, df_ds_reset, on="Date", how="inner")
df_m = pd.merge(df_m, df_lbl_reset, on=["Date", "Ratio"], how="inner")
train_m = df_m["Date"] < pd.Timestamp("2019-01-01")
xgb_baseline = xgb.XGBClassifier(n_estimators=168, max_depth=3, learning_rate=0.049, random_state=42, eval_metric='logloss')
xgb_baseline.fit(df_m.loc[train_m, all_meta_cols], df_m.loc[train_m, "Label"])


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

inf_dict_tfm25 = build_inf_dict(df_inf_tfm25)
inf_dict_tfm30 = build_inf_dict(df_inf_tfm30)
inf_dict_tstr  = build_inf_dict(df_inf_tstr)

# Prepara DB per 2026 YTD
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
                    if raw in row_ml.index: base_feats[col] = float(row_ml[raw])
                    elif col in row_ml.index: base_feats[col] = float(row_ml[col])
                    else: base_feats[col] = 0.0

                for ratio_id, (num, den) in RATIOS.items():
                    if ratio_id not in lr_source.columns: continue
                    cur_ratio = lr_source.loc[friday, ratio_id]

                    if is_live_2026:
                        key = (fri_str, ratio_id)
                        if key not in live_cache: continue
                        inf = live_cache[key]
                    else:
                        key = (fri_str, ratio_id)
                        if key not in inf_dict:
                            matches = [k for k in inf_dict.keys() if k[0] == fri_str and k[1].startswith(ratio_id)]
                            if not matches: continue
                            key = matches[0]
                        inf = inf_dict[key]

                    tfm_t5 = inf.get("tfm_t5")
                    if tfm_t5 is None or np.isnan(tfm_t5): continue
                    long_tick = num if tfm_t5 > cur_ratio else den

                    feats = base_feats.copy()
                    feats["TFM_t1"] = inf.get("tfm_t1", 0.0) or 0.0
                    feats["TFM_t5"] = inf.get("tfm_t5", 0.0) or 0.0
                    feats["TFM_t20"] = inf.get("tfm_t20", 0.0) or 0.0
                    feats["CHR_Median_t5"] = inf.get("chr_median_t5", 0.0) or 0.0
                    feats["CHR_Width_t5"] = inf.get("chr_width_t5", 0.0) or 0.0

                    batch_rows.append(feats)
                    batch_meta.append({"long_ticker": long_tick})

            if batch_rows:
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


def main():
    periods = [
        ("Training Set (2006-2018)", "2006-04-07", "2018-12-28", False),
        ("Validation Set (2019-2022)", "2019-01-04", "2022-12-30", False),
        ("Test Set OOS (2023-2025)", "2023-01-06", "2025-12-26", False),
        ("2026 YTD (Live)", "2026-01-02", "2026-10-23", True),
    ]

    setups = [
        ("Algoritmo (TFM 2.5 + LightGBM)", lgb_model, inf_dict_tfm25, tfm25_live_cache),
        ("TFM 3.0 + XGBoost (Optuna Nativo)", xgb_tfm3_optuna, inf_dict_tfm30, tfm30_live_cache),
        ("Timestral + XGBoost (Optuna Nativo)", xgb_timestral_optuna, inf_dict_tstr, tstr_live_cache),
        ("TFM 2.5 + XGBoost (Baseline)", xgb_baseline, inf_dict_tfm25, tfm25_live_cache),
    ]

    table_rows = []
    series_2026 = {}

    for p_name, s_date, e_date, is_live in periods:
        print(f"\nEvaluating: {p_name}...")
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

    df_out = pd.DataFrame(table_rows)
    print("\n" + "="*110)
    print("TABELLA COMPARATIVA PERFORMANCE COMPLETA (TUTTI I PERIODI)")
    print("="*110)
    print(df_out.to_string(index=False))
    print("="*110)

    csv_path = DATASET_DIR / "TABELLA_COMPARATIVA_MODELLI_NATIVI.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"Risultati salvati in: {csv_path}")

    # Aggiorna mock-data.ts con le nuove serie live
    import json
    from fastapi.encoders import jsonable_encoder
    mock_file = REPO_ROOT / "trading_dashboard" / "frontend" / "src" / "app" / "core" / "utils" / "mock-data.ts"
    
    with open(mock_file, 'r', encoding='utf-8') as f:
        content = f.read()
    prefix = "// Automatically generated mock data from SQLite database\nexport const MOCK_DATA: any = "
    data = json.loads(content[len(prefix):].rstrip(';\n'))

    data["tfm3XgbOptunaBacktest"] = jsonable_encoder(series_2026["TFM 3.0 + XGBoost (Optuna Nativo)"])
    data["timestralXgbOptunaBacktest"] = jsonable_encoder(series_2026["Timestral + XGBoost (Optuna Nativo)"])
    data["timestralXgbBaseBacktest"] = jsonable_encoder(series_2026["Timestral + XGBoost (Optuna Nativo)"])
    data["tfm25XgbBaseBacktest"] = jsonable_encoder(series_2026["TFM 2.5 + XGBoost (Baseline)"])

    with open(mock_file, 'w', encoding='utf-8') as f:
        f.write(prefix)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write(";\n")
    print(f"Aggiornato con successo: {mock_file}")


if __name__ == "__main__":
    main()
