import os, pathlib

# Fix SSL for corporate proxy: use exported Windows certificates
_cert_file = pathlib.Path(__file__).resolve().parents[1] / "cacert_windows.pem"
if not _cert_file.exists():
    _cert_file = pathlib.Path(r"C:\Users\KV936JT\OneDrive - EY\Desktop\tesi_trading_dashboard\cacert_windows.pem")
if _cert_file.exists():
    os.environ.setdefault("CURL_CA_BUNDLE", str(_cert_file))
    os.environ.setdefault("REQUESTS_CA_BUNDLE", str(_cert_file))
    os.environ.setdefault("SSL_CERT_FILE", str(_cert_file))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database.connection import init_db
from modules.scheduler.service import start_scheduler, stop_scheduler
from modules.market_data.controller import router as market_router
from modules.backtest.controller import router as backtest_router
from modules.hmm.controller import router as hmm_router
from modules.inference.controller import router as inference_router
from modules.signals.controller import router as signals_router
from modules.analytics.controller import router as analytics_router
from config import BACKEND_PORT
from modules.signals.live_engine import get_lgb_model, load_foundation_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[STARTUP] Caricamento modelli...")
    get_lgb_model()
    load_foundation_models()
    init_db()
    # Seed inference cache from pre-computed data
    from database.connection import SessionLocal
    db = SessionLocal()
    try:
        from modules.inference.service import _seed_inference_cache
        _seed_inference_cache(db)
    except Exception as e:
        print(f"[startup] Inference seed error: {e}")
    finally:
        db.close()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="Trading Dashboard API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router registration
app.include_router(market_router,   prefix="/api/market",   tags=["Market Data"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["Backtest"])
app.include_router(hmm_router,      prefix="/api/hmm",      tags=["HMM Regimes"])
app.include_router(inference_router,prefix="/api/inference",tags=["FM Inference"])
app.include_router(signals_router,  prefix="/api/signals",  tags=["Signals"])
app.include_router(analytics_router,prefix="/api/analytics",tags=["Analytics"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0",
                port=BACKEND_PORT, reload=False)
    




@app.get("/health")
def health_check():
    return {"status": "ok"}
