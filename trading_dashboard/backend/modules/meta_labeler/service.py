"""
Meta-labeler: calcolo Bet Quality via LightGBM.
Carica il modello pre-addestrato dal Drive.
Se il modello non è disponibile, usa un fallback basato su Chronos width.
"""
import json
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from config import (LGB_MODEL_PATH, LGB_PARAMS_PATH,
                    DATASET_PATH, TRIPLE_BARRIER_PATH)

_lgb_model = None
_model_loaded = False
_feature_columns: list[str] | None = None


def _get_feature_columns() -> list[str]:
    """
    Carica l'ordine esatto delle feature dal dataset di riferimento.
    """
    global _feature_columns
    if _feature_columns is None:
        try:
            df = pd.read_parquet(DATASET_PATH, columns=None)
            # Le colonne ML_FEAT_* sono quelle usate dal modello
            _feature_columns = [c for c in df.columns
                                if c.startswith("ML_FEAT_")]
            print(f"[meta_labeler] Feature columns loaded: {len(_feature_columns)}")
        except Exception as e:
            print(f"[meta_labeler] Cannot load feature columns: {e}")
            _feature_columns = []
    return _feature_columns


def _load_lgb_model():
    """
    Carica il modello LightGBM. Se non esiste il file pre-addestrato,
    tenta di ricostruirlo dai dati di training disponibili.
    """
    global _lgb_model, _model_loaded

    if _model_loaded:
        return _lgb_model

    _model_loaded = True

    # Tentativo 1: caricare modello salvato
    pkl_path = LGB_MODEL_PATH.with_suffix(".pkl")
    for candidate in [LGB_MODEL_PATH, pkl_path,
                      LGB_MODEL_PATH.parent / "LGB_FINAL_MODEL.txt"]:
        if candidate.exists():
            try:
                if str(candidate).endswith(".pkl"):
                    _lgb_model = joblib.load(candidate)
                else:
                    import lightgbm as lgb
                    _lgb_model = lgb.Booster(model_file=str(candidate))
                print(f"[meta_labeler] Model loaded from {candidate}")
                return _lgb_model
            except Exception as e:
                print(f"[meta_labeler] Failed to load {candidate}: {e}")

    # Tentativo 2: ricostruire da dati disponibili (one-time)
    if LGB_PARAMS_PATH.exists() and DATASET_PATH.exists() and TRIPLE_BARRIER_PATH.exists():
        try:
            _lgb_model = _build_lgb_model()
            return _lgb_model
        except Exception as e:
            print(f"[meta_labeler] Failed to build model: {e}")

    print("[meta_labeler] WARNING: LGB model not available. Using fallback bet quality.")
    return None


def _build_lgb_model():
    """
    Ricostruisce il modello LGB dai file di training disponibili.
    Questo è un recovery di un artefatto mancante, non un retraining.
    """
    import lightgbm as lgb

    print("[meta_labeler] Building LGB model from training data...")

    with open(LGB_PARAMS_PATH, "r") as f:
        best_params = json.load(f)

    dataset = pd.read_parquet(DATASET_PATH)
    labels = pd.read_parquet(TRIPLE_BARRIER_PATH)

    feat_cols = [c for c in dataset.columns if c.startswith("ML_FEAT_")]
    # Aggiungere colonne di inferenza se presenti
    for extra in ["TFM_t1", "TFM_t5", "TFM_t20", "CHR_Median_t5", "CHR_Width_t5"]:
        if extra in dataset.columns:
            feat_cols.append(extra)

    # Merge features e labels
    common_idx = dataset.index.intersection(labels.index)
    X = dataset.loc[common_idx, feat_cols].dropna()
    y = labels.loc[X.index]

    if isinstance(y, pd.DataFrame):
        y = y.iloc[:, 0]

    # Train period: 2006-2018
    train_mask = X.index < "2019-01-01"
    X_train = X[train_mask]
    y_train = y[train_mask]

    if len(X_train) < 100:
        raise ValueError(f"Not enough training data: {len(X_train)} rows")

    model = lgb.LGBMClassifier(
        **best_params,
        random_state=42,
        verbose=-1
    )
    model.fit(X_train, y_train)

    # Salva per uso futuro
    save_path = LGB_MODEL_PATH.with_suffix(".pkl")
    joblib.dump(model, save_path)
    print(f"[meta_labeler] Model built and saved to {save_path}")

    return model


def compute_bet_quality(ml_features_row: pd.Series,
                        inferences: dict,
                        ratio_id: str,
                        threshold: float) -> tuple[float, bool]:
    """
    Calcola Bet Quality per un singolo trade.

    Args:
        ml_features_row: riga del DataFrame ML features (index=feature names)
        inferences: dict con tfm_t1, tfm_t5, tfm_t20, chr_median_t5, chr_width_t5
        ratio_id: es. "R01"
        threshold: soglia di ammissione (default 0.50)

    Returns:
        (bet_quality_score, is_admitted)
    """
    model = _load_lgb_model()

    if model is None:
        # Fallback: usa Chronos width come proxy di confidence
        # Width piccolo = alta confidenza nel segnale
        chr_width = inferences.get("chr_width_t5")
        if chr_width is not None and not np.isnan(chr_width):
            bq = max(0.0, min(1.0, 1.0 - abs(chr_width)))
        else:
            bq = 0.55  # default moderato
        return bq, bq >= threshold

    feat_cols = _get_feature_columns()
    if not feat_cols:
        return 0.55, True

    # Costruisci feature vector nell'ordine esatto del training
    features = {}
    for col in feat_cols:
        if col in ml_features_row.index:
            features[col] = ml_features_row[col]
        else:
            features[col] = 0.0

    # Aggiungi colonne di inferenza
    for key, col_name in [("tfm_t1", "TFM_t1"), ("tfm_t5", "TFM_t5"),
                          ("tfm_t20", "TFM_t20"),
                          ("chr_median_t5", "CHR_Median_t5"),
                          ("chr_width_t5", "CHR_Width_t5")]:
        val = inferences.get(key)
        features[col_name] = val if val is not None and not np.isnan(val) else 0.0

    X = pd.DataFrame([features])

    try:
        if hasattr(model, "predict_proba"):
            bq = float(model.predict_proba(X)[0, 1])
        else:
            # lightgbm Booster
            bq = float(model.predict(X)[0])
    except Exception:
        bq = 0.55

    return bq, bq >= threshold
