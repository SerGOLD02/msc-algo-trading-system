import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DRIVE_PATH = Path(os.getenv("DRIVE_BASE_PATH", "/app/models"))

# Percorsi modelli
LGB_MODEL_PATH      = DRIVE_PATH / os.getenv("MODEL_LGB", "LGB_FINAL_MODEL")
HMM_MODEL_PATH      = DRIVE_PATH / os.getenv("MODEL_HMM", "HMM_MODEL.pkl")
HRP_WEIGHTS_PATH    = DRIVE_PATH / os.getenv("HRP_WEIGHTS", "HRP_WEIGHTS.parquet")
SIGMOID_DECAY_PATH  = DRIVE_PATH / os.getenv("SIGMOID_DECAY", "SIGMOID_DECAY.parquet")
INFERENCE_PATH      = DRIVE_PATH / os.getenv("INFERENCE_FULL", "INFERENZE_FULL_DATASET_O2TFM.parquet")
DATASET_PATH        = DRIVE_PATH / os.getenv("DATASET_INFERENCE", "DATASET_INFERENCE_READY.parquet")
HMM_REGIMES_PATH    = DRIVE_PATH / "HMM_REGIMES.parquet"
LGB_PARAMS_PATH     = DRIVE_PATH / "BEST_PARAMS_LGB.json"
TRIPLE_BARRIER_PATH = DRIVE_PATH / "TRIPLE_BARRIER_LABELS_OPTIMAL.parquet"


# Database
SQLITE_PATH = os.getenv("SQLITE_PATH", "backend/database/trading.db")
DATABASE_URL = f"sqlite:///{SQLITE_PATH}"

# Parametri sistema (fissi, mai riallenati)
DEFAULT_BET_QUALITY = 0.50
DEFAULT_HRP_ALPHA   = 0.50
DEFAULT_K_SIGMOID   = 10.0
DEFAULT_C_SOGLIA    = 0.50
DEFAULT_K_UP        = 1.25
DEFAULT_K_DOWN      = 1.50
CRISIS_STATE_IDX    = 4

# Universo
ETF_UNIVERSE = [
    "SPY","QQQ","IWM","MDY","DIA","EFA","EEM",
    "XLB","XLE","XLF","XLI","XLK","XLP","XLU",
    "XLV","XLY","IYR","VNQ","SOXX",
    "TLT","IEF","SHY","LQD",
    "SH","PSQ","RWM","VIXY","UUP","GLD","SLV","FXE"
]

RATIOS = {
    "R01": ("SPY","TLT"),  "R02": ("GLD","TLT"),
    "R03": ("GLD","SPY"),  "R04": ("UUP","FXE"),
    "R05": ("LQD","IEF"),  "R06": ("TLT","SHY"),
    "R07": ("XLF","XLU"),  "R08": ("QQQ","SPY"),
    "R09": ("IWM","SPY"),  "R10": ("MDY","SPY"),
    "R11": ("DIA","QQQ"),  "R12": ("XLY","XLP"),
    "R13": ("XLK","XLE"),  "R14": ("XLV","SPY"),
    "R15": ("XLI","SPY"),  "R16": ("XLE","XLB"),
    "R17": ("EEM","EFA"),  "R18": ("GLD","SLV"),
    "R19": ("SOXX","SPY"), "R20": ("VNQ","IEF"),
}

CRISIS_BASKET = {"SH":0.05,"PSQ":0.05,"RWM":0.05,"VIXY":0.05}

# Scheduler
PRICES_REFRESH_MINUTES = int(os.getenv("PRICES_REFRESH_MINUTES", 2))
NYSE_CLOSE_HOUR_ET     = int(os.getenv("NYSE_CLOSE_HOUR_ET", 16))
NYSE_CLOSE_MINUTE_ET   = int(os.getenv("NYSE_CLOSE_MINUTE_ET", 0))

# Warmup e display
WARMUP_START   = "2023-06-01"
DISPLAY_START  = "2026-01-02"  # Primo venerdì operativo 2026

# EODHD API
EODHD_API_KEY  = os.getenv("EODHD_API_KEY", "")
EODHD_BASE_URL = os.getenv("EODHD_BASE_URL", "https://eodhd.com/api")

# Macro data mapping: feature_name -> (source, ticker/indicator)
MACRO_YFINANCE = {
    "VIX": "^VIX",
    "USGG10YR": "^TNX",
    "US0003M": "^IRX",
    "DXY": "DX-Y.NYB",
}

MACRO_EODHD = {
    "USGG2YR": ("eod", "US2Y.INDX"),
    "CPI_YOY": ("macro-indicator", "USA", "inflation_consumer_prices_annual"),
    "CONSSENT": ("macro-indicator", "USA", "consumer_confidence_index"),
}

# MOVE index proxy: TLT 20-day realized vol * scaling factor
MOVE_PROXY_SCALE = 100.0

# TimesFM checkpoint (locale dopo download manuale)
TIMESFM_CHECKPOINT_PATH = os.getenv(
    "TIMESFM_CHECKPOINT_PATH",
    os.path.expanduser("~/.cache/timesfm/google--timesfm-2.0-200m-pytorch")
)

# API Backend
BACKEND_PORT   = 8000
