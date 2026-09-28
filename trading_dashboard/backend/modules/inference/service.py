import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from database.models import InferenceCache, PriceCache
from config import RATIOS, HMM_MODEL_PATH, INFERENCE_PATH

CONTEXT_LEN = 512


def _seed_inference_cache(db: Session) -> None:
    """
    Popola l'InferenceCache dal file di inferenze pre-calcolate della tesi.
    Chiamata una sola volta al primo avvio.
    """
    existing = db.query(InferenceCache).count()
    if existing > 0:
        return

    try:
        df = pd.read_parquet(INFERENCE_PATH)
        print(f"[inference] Seeding cache from {INFERENCE_PATH} ({len(df)} rows)...")

        records = []
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
            # Normalize "R01_Risk Sentiment" -> "R01"
            ratio_id = str(ratio_id).split("_")[0]

            records.append({
                "friday_date": friday_str,
                "ratio_id": ratio_id,
                "tfm_t1": float(row.get("TFM_t1", 0)) if not pd.isna(row.get("TFM_t1", np.nan)) else None,
                "tfm_t5": float(row.get("TFM_t5", 0)) if not pd.isna(row.get("TFM_t5", np.nan)) else None,
                "tfm_t20": float(row.get("TFM_t20", 0)) if not pd.isna(row.get("TFM_t20", np.nan)) else None,
                "chr_median_t5": float(row.get("CHR_Median_t5", 0)) if not pd.isna(row.get("CHR_Median_t5", np.nan)) else None,
                "chr_width_t5": float(row.get("CHR_Width_t5", 0)) if not pd.isna(row.get("CHR_Width_t5", np.nan)) else None,
            })

        if records:
            from sqlalchemy import insert
            db.execute(insert(InferenceCache), records)
            db.commit()
            print(f"[inference] Seeded {len(records)} inference records via bulk insert.")

    except Exception as e:
        print(f"[inference] Failed to seed cache: {e}")
        db.rollback()


def load_inference_cache(db: Session) -> dict:
    rows = db.query(InferenceCache).all()
    cache = {}
    for r in rows:
        cache[(r.friday_date, r.ratio_id)] = {
            "tfm_t1":        r.tfm_t1,
            "tfm_t5":        r.tfm_t5,
            "tfm_t20":       r.tfm_t20,
            "chr_median_t5": r.chr_median_t5,
            "chr_width_t5":  r.chr_width_t5,
        }
    return cache


def get_latest_inferences(db: Session) -> dict:
    latest = (db.query(InferenceCache)
                .order_by(InferenceCache.friday_date.desc())
                .first())
    if not latest:
        return {"friday_date": "", "inferences": []}

    rows = (db.query(InferenceCache)
              .filter(InferenceCache.friday_date == latest.friday_date)
              .all())

    inferences = []
    for r in rows:
        width   = r.chr_width_t5 or 0
        med     = r.chr_median_t5 or 0
        inferences.append({
            "ratio_id":      r.ratio_id,
            "tfm_t1":        r.tfm_t1,
            "tfm_t5":        r.tfm_t5,
            "tfm_t20":       r.tfm_t20,
            "chr_median_t5": med,
            "chr_width_t5":  width,
            "upper_band":    round(med + width / 2, 6),
            "lower_band":    round(med - width / 2, 6),
        })

    return {"friday_date": latest.friday_date, "inferences": inferences}


def backfill_inference(db: Session):
    """
    Backfill inference for ALL Fridays from DISPLAY_START that don't
    have cached results. Uses OLS-based fast method for bulk backfill,
    then Chronos for the latest Friday only.
    """
    from modules.backtest.service import _get_prices_from_db, _get_operational_fridays
    from modules.features.service import compute_log_ratios
    from config import DISPLAY_START, ETF_UNIVERSE
    from scipy import stats

    prices_dict = {}
    for ticker in ETF_UNIVERSE + ["VIX"]:
        s = _get_prices_from_db(ticker, db)
        if len(s) > 0:
            prices_dict[ticker] = pd.DataFrame({
                "Close": s, "Volume": s * 0
            })

    log_ratios = compute_log_ratios(prices_dict)
    # Fix 6: Use operational fridays instead of calendar fridays
    fridays = _get_operational_fridays(db)
    if len(fridays) == 0:
        return

    # Find Fridays from DISPLAY_START that need inference
    display_start = pd.Timestamp(DISPLAY_START)
    # We need warmup data before DISPLAY_START too (for context window)
    target_fridays = fridays[fridays >= display_start]

    if len(target_fridays) == 0:
        print("[inference] No target Fridays for backfill.")
        return

    # Check which Fridays already have inference data
    existing_dates = set()
    for row in db.query(InferenceCache.friday_date).distinct().all():
        existing_dates.add(row[0])

    missing_fridays = [f for f in target_fridays
                       if str(f.date()) not in existing_dates]

    if not missing_fridays:
        print("[inference] All Fridays have inference data. No backfill needed.")
        return

    print(f"[inference] Backfilling {len(missing_fridays)} Fridays...")
    vix_series = prices_dict["VIX"]["Close"] if "VIX" in prices_dict else None

    for fri in missing_fridays:
        fri_str = str(fri.date())
        try:
            idx = log_ratios.index.get_loc(fri)
        except KeyError:
            continue

        for ratio_id in log_ratios.columns:
            ratio_arr = log_ratios[ratio_id].iloc[
                max(0, idx - CONTEXT_LEN + 1): idx + 1
            ].values

            if len(ratio_arr) < 60:
                continue

            # OLS-based fast forecast (seconds, not minutes)
            if vix_series is not None and len(vix_series) > idx:
                vix_arr = vix_series.iloc[
                    max(0, idx - CONTEXT_LEN + 1): idx + 1
                ].values
                if len(vix_arr) >= len(ratio_arr):
                    vix_arr = vix_arr[:len(ratio_arr)]

                try:
                    slope, intercept, *_ = stats.linregress(
                        vix_arr, ratio_arr
                    )
                    residuals = ratio_arr - (intercept + slope * vix_arr)
                except Exception:
                    residuals = ratio_arr - np.mean(ratio_arr)
                    slope, intercept = 0.0, np.mean(ratio_arr)
            else:
                residuals = ratio_arr - np.mean(ratio_arr)
                slope, intercept = 0.0, np.mean(ratio_arr)

            # Fast OLS-based directional forecast:
            # Use last 20 residuals' trend to extrapolate
            recent = residuals[-20:]
            if len(recent) >= 2:
                trend = np.polyfit(np.arange(len(recent)), recent, 1)[0]
            else:
                trend = 0.0

            structural = intercept + slope * (
                vix_arr[-1] if vix_series is not None and len(vix_arr) > 0
                else 0.0
            )
            # Point forecasts at horizons 1, 5, 20
            fp_1 = float(residuals[-1] + trend * 1 + structural)
            fp_5 = float(residuals[-1] + trend * 5 + structural)
            fp_20 = float(residuals[-1] + trend * 20 + structural)

            # Fast distribution estimate (rolling std as width proxy)
            std_20 = float(np.std(ratio_arr[-20:]))
            chr_med = float(ratio_arr[-1] + trend * 5)
            chr_width = float(std_20 * 2.0)  # ~90% CI width

            db.merge(InferenceCache(
                friday_date=fri_str,
                ratio_id=ratio_id,
                tfm_t1=fp_1,
                tfm_t5=fp_5,
                tfm_t20=fp_20,
                chr_median_t5=chr_med,
                chr_width_t5=chr_width,
            ))

        db.commit()
        print(f"[inference] Backfilled {fri_str}")

    print(f"[inference] Backfill complete for {len(missing_fridays)} Fridays.")


def trigger_fm_update(db: Session, friday_override: str | None = None):
    """
    Calcola inferenze con TimesFM 2.5 + Chronos per un venerdì specifico
    o per l'ultimo venerdì disponibile.
    Chiamato dal scheduler ogni venerdì e per recompute manuale.
    """
    from modules.backtest.service import _get_prices_from_db, _get_operational_fridays
    from modules.features.service import compute_log_ratios
    from config import ETF_UNIVERSE, TIMESFM_CHECKPOINT_PATH

    prices_dict = {}
    for ticker in ETF_UNIVERSE + ["VIX"]:
        s = _get_prices_from_db(ticker, db)
        if len(s) > 0:
            prices_dict[ticker] = pd.DataFrame({
                "Close": s, "Volume": s * 0
            })

    log_ratios = compute_log_ratios(prices_dict)
    # Fix 6: Use operational fridays
    fridays = _get_operational_fridays(db)
    if len(fridays) == 0:
        return

    if friday_override:
        target_fri = pd.Timestamp(friday_override)
        if target_fri not in fridays:
            print(f"[inference] Friday {friday_override} not found in data.")
            return
        last_fri = target_fri
    else:
        last_fri = fridays[-1]

    fri_str = str(last_fri.date())

    # Se non è un recompute, skip se già calcolato
    if not friday_override:
        existing = (db.query(InferenceCache)
                      .filter(InferenceCache.friday_date == fri_str)
                      .first())
        if existing:
            return

    vix_series = prices_dict.get("VIX", {}).get("Close") if "VIX" in prices_dict else None
    if vix_series is None:
        vix_series = prices_dict["VIX"]["Close"] if "VIX" in prices_dict else pd.Series(dtype=float)

    try:
        from scipy import stats

        # Try loading TimesFM 2.5
        tfm_model = _load_timesfm(TIMESFM_CHECKPOINT_PATH)

        idx = log_ratios.index.get_loc(last_fri)

        for ratio_id in log_ratios.columns:
            ratio_arr = log_ratios[ratio_id].iloc[
                max(0, idx - CONTEXT_LEN + 1): idx + 1
            ].values

            if len(ratio_arr) < 60:
                continue

            vix_arr = vix_series.iloc[
                max(0, idx - CONTEXT_LEN + 1): idx + 1
            ].values if len(vix_series) > 0 else np.zeros(len(ratio_arr))

            if len(vix_arr) > len(ratio_arr):
                vix_arr = vix_arr[:len(ratio_arr)]

            # OLS decomposition: ratio = intercept + slope*VIX + residuals
            try:
                slope, intercept, *_ = stats.linregress(
                    vix_arr[:min(511, len(vix_arr))],
                    ratio_arr[:min(511, len(ratio_arr))]
                )
                residuals = ratio_arr[:min(511, len(ratio_arr))] - (
                    intercept + slope * vix_arr[:min(511, len(vix_arr))]
                )
            except Exception:
                residuals = ratio_arr - np.mean(ratio_arr)
                slope, intercept = 0.0, np.mean(ratio_arr)

            structural = intercept + slope * vix_arr[-1]

            # --- TimesFM forecasts ---
            fp = [0.0] * 20
            if tfm_model is not None:
                try:
                    point_forecast, _ = tfm_model.forecast(
                        horizon=20, inputs=[residuals.astype(np.float32)]
                    )
                    # point_forecast shape: (1, 20) — add structural back
                    fp = [float(point_forecast[0, h] + structural)
                          for h in range(20)]
                    print(f"[inference] TimesFM OK for {ratio_id} on {fri_str}")
                except Exception as e:
                    print(f"[inference] TimesFM error for {ratio_id}: {e}")
                    fp = _ols_fallback(residuals, structural)
            else:
                fp = _ols_fallback(residuals, structural)

            # --- Chronos forecasts ---
            chr_med, chr_width = _run_chronos(ratio_arr)

            db.merge(InferenceCache(
                friday_date=fri_str,
                ratio_id=ratio_id,
                tfm_t1=float(fp[0]),
                tfm_t5=float(fp[4]),
                tfm_t20=float(fp[19]),
                chr_median_t5=chr_med,
                chr_width_t5=chr_width,
            ))

        db.commit()
        src = "TimesFM" if tfm_model is not None else "OLS fallback"
        print(f"[inference] FM update complete for {fri_str} (source: {src})")

    except Exception as e:
        print(f"[inference] FM update error: {e}")
        import traceback
        traceback.print_exc()


def _load_timesfm(checkpoint_path: str):
    """Load TimesFM 2.5 model from local checkpoint. Returns None if unavailable."""
    import os
    try:
        import timesfm
        # Try local path first
        if os.path.isdir(checkpoint_path):
            model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                checkpoint_path, local_files_only=True
            )
            print(f"[inference] TimesFM 2.5 loaded from {checkpoint_path}")
            return model

        # Try HuggingFace download (will fail behind corporate proxy)
        model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            "google/timesfm-2.0-200m-pytorch"
        )
        print("[inference] TimesFM 2.5 loaded from HuggingFace")
        return model

    except Exception as e:
        print(f"[inference] TimesFM not available: {e}")
        return None


def _ols_fallback(residuals: np.ndarray, structural: float) -> list[float]:
    """OLS trend-based fallback when TimesFM is unavailable."""
    recent = residuals[-20:]
    if len(recent) >= 2:
        trend = np.polyfit(np.arange(len(recent)), recent, 1)[0]
    else:
        trend = 0.0
    return [float(residuals[-1] + trend * (h + 1) + structural)
            for h in range(20)]


def recompute_stale_inference(db: Session) -> dict:
    """
    Ri-calcola le inferenze dove tfm_t5 == chr_median_t5 (dati OLS proxy).
    Da chiamare dopo aver piazzato il checkpoint TimesFM.
    Ritorna statistiche su quanti venerdì sono stati ri-calcolati.
    """
    from config import TIMESFM_CHECKPOINT_PATH

    # Trova venerdì con dati proxy (tfm == chr)
    stale_rows = db.execute(
        text("SELECT DISTINCT friday_date FROM inference_cache "
             "WHERE ABS(tfm_t5 - chr_median_t5) < 0.000001")
    ).fetchall()
    stale_fridays = [r[0] for r in stale_rows]

    if not stale_fridays:
        return {"recomputed": 0, "message": "Nessun dato proxy da aggiornare."}

    # Verifica che TimesFM sia disponibile
    tfm_model = _load_timesfm(TIMESFM_CHECKPOINT_PATH)
    if tfm_model is None:
        return {
            "recomputed": 0,
            "stale_count": len(stale_fridays),
            "message": "TimesFM checkpoint non trovato. Piazza il checkpoint e riprova."
        }

    # Elimina dati proxy
    for fri_str in stale_fridays:
        db.query(InferenceCache).filter(
            InferenceCache.friday_date == fri_str
        ).delete()
    db.commit()
    print(f"[inference] Deleted {len(stale_fridays)} stale Fridays for recompute.")

    # Ri-calcola con TimesFM reale
    recomputed = 0
    for fri_str in sorted(stale_fridays):
        try:
            trigger_fm_update(db, friday_override=fri_str)
            recomputed += 1
        except Exception as e:
            print(f"[inference] Recompute error for {fri_str}: {e}")

    return {
        "recomputed": recomputed,
        "total_stale": len(stale_fridays),
        "message": f"Ri-calcolati {recomputed}/{len(stale_fridays)} venerdì con TimesFM reale."
    }


def _run_chronos(ratio_arr: np.ndarray) -> tuple:
    try:
        from chronos import ChronosPipeline
        import torch

        pipeline = ChronosPipeline.from_pretrained(
            "amazon/chronos-t5-base",
            device_map="cpu",
            torch_dtype=torch.float32,
        )
        ctx = torch.tensor(ratio_arr, dtype=torch.float32).unsqueeze(0)
        forecast = pipeline.predict(ctx, prediction_length=20,
                                     num_samples=100)
        samples  = forecast[0, :, 4].numpy()
        width    = float(np.percentile(samples, 95) -
                         np.percentile(samples, 5))
        return float(np.median(samples)), width
    except Exception:
        return np.nan, np.nan
