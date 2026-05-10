from pathlib import Path

# Base path to the thesis data
BASE_PATH = Path("data_tesi")

# File mappings (Treat these files strictly as read-only per GEMINI.md security protocol)
LGB_MODEL = BASE_PATH / "LGB_FINAL_MODEL"
HMM_MODEL = BASE_PATH / "HMM_MODEL.pkl"
INFERENCE_DATA = BASE_PATH / "INFERENZE_FULL_DATASET_O2TFM.parquet"
