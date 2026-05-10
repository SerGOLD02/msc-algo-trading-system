from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from database.connection import get_db
from modules.backtest.service import get_or_compute_backtest
from modules.backtest.schemas import BacktestParams, BacktestResponseDTO

router = APIRouter()

@router.post("/compute", response_model=BacktestResponseDTO)
def compute_backtest(
    params: BacktestParams,
    background_tasks: BackgroundTasks,
    start_date: str | None = Query(None, description="YYYY-MM-DD override"),
    db: Session = Depends(get_db)
):
    """
    Restituisce il backtest per i parametri dati.
    Se già in cache lo restituisce immediatamente.
    Se non in cache lo calcola (può richiedere 10-30 secondi).
    """
    if start_date:
        params.start_date = start_date
    return get_or_compute_backtest(params, db)


@router.get("/default", response_model=BacktestResponseDTO)
def default_backtest(
    start_date: str | None = Query(None, description="YYYY-MM-DD override"),
    db: Session = Depends(get_db)
):
    """
    Restituisce sempre il backtest con i parametri originali della tesi.
    """
    from config import (DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
                        DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA,
                        DEFAULT_K_UP, DEFAULT_K_DOWN)
    params = BacktestParams(
        bet_quality=DEFAULT_BET_QUALITY,
        hrp_alpha=DEFAULT_HRP_ALPHA,
        k_sigmoid=DEFAULT_K_SIGMOID,
        c_soglia=DEFAULT_C_SOGLIA,
        k_up=DEFAULT_K_UP,
        k_down=DEFAULT_K_DOWN,
        start_date=start_date,
    )
    return get_or_compute_backtest(params, db)
