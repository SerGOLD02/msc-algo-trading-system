"""
modules/timestral/service.py

Gestione del modello Timestral (mistralai/Timestral-209M) per la generazione
delle inferenze direzionali e delle bande predittive di incertezza.
"""

import os
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from config import RATIOS, ETF_UNIVERSE, DISPLAY_START
from database.models import TimestralInferenceCache

TIMESTRAL_CHECKPOINT = "mistralai/Timestral-209M"
CONTEXT_LEN = 512


def _load_timestral_forecaster():
    """Carica il modello TimestralForecaster da HuggingFace (cache locale)."""
    os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
    from timestral import TimestralForecaster
    print(f"[timestral] Loading checkpoint: {TIMESTRAL_CHECKPOINT}...")
    forecaster = TimestralForecaster.from_pretrained(
        TIMESTRAL_CHECKPOINT,
        device="cpu",
    )
    print("[timestral] Model loaded.")
    return forecaster


def backfill_timestral_inference(db: Session) -> None:
    """
    Backfill inferenze Timestral per tutti i venerdì dal DISPLAY_START
    che non hanno ancora dati nella tabella timestral_inference_cache.
    """
    from modules.backtest.service import _get_prices_from_db, _get_operational_fridays
    from modules.features.service import compute_log_ratios

    # Controlla quali venerdì sono già presenti
    existing_dates = set(
        row[0] for row in db.query(TimestralInferenceCache.friday_date).distinct().all()
    )

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
        print("[timestral] No operational Fridays found.")
        return

    display_start = pd.Timestamp(DISPLAY_START)
    target_fridays = fridays[fridays >= display_start]
    missing_fridays = [f for f in target_fridays if str(f.date()) not in existing_dates]

    if not missing_fridays:
        print("[timestral] All Fridays already have Timestral inference. No backfill needed.")
        return

    print(f"[timestral] Backfilling {len(missing_fridays)} Fridays with Timestral...")
    forecaster = _load_timestral_forecaster()
    ratio_cols = [r for r in RATIOS.keys() if r in log_ratios.columns]

    for fri in missing_fridays:
        fri_str = str(fri.date())
        if fri not in log_ratios.index:
            continue
        row_loc = log_ratios.index.get_loc(fri)

        sub_df = log_ratios[ratio_cols].iloc[max(0, row_loc - CONTEXT_LEN + 1): row_loc + 1]
        clean_vals = sub_df.values.T.astype(np.float32)
        if np.isnan(clean_vals).any():
            clean_vals = np.nan_to_num(clean_vals, nan=0.0)

        try:
            res = forecaster.forecast(context=clean_vals, prediction_length=20)
        except Exception as e:
            print(f"[timestral] Error forecasting on {fri_str}: {e}")
            continue

        records = []
        for i, ratio_id in enumerate(ratio_cols):
            t1 = float(res.median[i, 0, 0])
            t5 = float(res.median[i, 0, 4])
            t20 = float(res.median[i, 0, 19])
            q05 = float(res.quantiles[i, 0, 4, 1])
            q95 = float(res.quantiles[i, 0, 4, 19])
            width = max(0.0001, q95 - q05)

            records.append(TimestralInferenceCache(
                friday_date=fri_str,
                ratio_id=ratio_id,
                tstral_t1=t1,
                tstral_t5=t5,
                tstral_t20=t20,
                chr_median_t5=t5,
                chr_width_t5=width,
            ))

        if records:
            for r in records:
                db.merge(r)
            db.commit()
            print(f"[timestral] Backfilled {fri_str} ({len(records)} ratios)")

    print(f"[timestral] Backfill complete for {len(missing_fridays)} Fridays.")


def load_timestral_inference_cache(db: Session) -> dict:
    """Carica tutte le inferenze Timestral dal DB in un dizionario (date, ratio_id) -> dict."""
    rows = db.query(TimestralInferenceCache).all()
    cache = {}
    for r in rows:
        cache[(r.friday_date, r.ratio_id)] = {
            "tfm_t1":        r.tstral_t1,
            "tfm_t5":        r.tstral_t5,
            "tfm_t20":       r.tstral_t20,
            "chr_median_t5": r.chr_median_t5,
            "chr_width_t5":  r.chr_width_t5,
        }
    return cache


def seed_timestral_from_parquet(db: Session, parquet_path: str) -> None:
    """Inizializza la tabella timestral_inference_cache dal file precalcolato."""
    if not os.path.exists(parquet_path):
        print(f"[timestral] Parquet file not found: {parquet_path}")
        return

    df = pd.read_parquet(parquet_path)
    print(f"[timestral] Seeding {len(df)} records from {parquet_path}...")

    # Create table if not exists
    from database.connection import engine, Base
    Base.metadata.create_all(bind=engine)

    records = []
    for _, row in df.iterrows():
        records.append(TimestralInferenceCache(
            friday_date=str(row["friday_date"]),
            ratio_id=str(row["ratio_id"]),
            tstral_t1=float(row["tfm_t1"]),
            tstral_t5=float(row["tfm_t5"]),
            tstral_t20=float(row["tfm_t20"]),
            chr_median_t5=float(row["chr_median_t5"]),
            chr_width_t5=float(row["chr_width_t5"]),
        ))

    for r in records:
        db.merge(r)
    db.commit()
    print(f"[timestral] Successfully seeded {len(records)} records into timestral_inference_cache.")
