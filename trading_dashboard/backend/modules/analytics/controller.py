from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database.connection import get_db
from modules.analytics.service import (
    get_decay_history, get_correlation_heatmap,
    get_drawdown, get_chronos_bands, get_yearly_breakdown,
    get_operational_status, get_etf_performance,
    get_regime_stats, get_weekly_decomposition
)
from modules.analytics.schemas import (
    DecayHistoryResponse, CorrelationHeatmapResponse,
    DrawdownResponse, ChronosBandsResponse, YearlyBreakdownResponse,
    OperationalStatusResponse, EtfPerformanceResponse,
    RegimeStatsResponse, WeeklyDecompositionResponse
)

router = APIRouter()


@router.get("/decay-history", response_model=DecayHistoryResponse)
def decay_history(db: Session = Depends(get_db)):
    return get_decay_history(db)


@router.get("/correlation-heatmap", response_model=CorrelationHeatmapResponse)
def correlation_heatmap(
    window: str = Query("52w", description="Window: 1w, 1m, 3m, 6m, 52w"),
    ordering: str = Query("alphabetical",
                          description="alphabetical or hierarchical"),
    db: Session = Depends(get_db)
):
    return get_correlation_heatmap(db, window, ordering)


@router.get("/drawdown", response_model=DrawdownResponse)
def drawdown(db: Session = Depends(get_db)):
    return get_drawdown(db)


@router.get("/chronos-bands", response_model=ChronosBandsResponse)
def chronos_bands(
    friday: str | None = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return get_chronos_bands(db, friday)


@router.get("/yearly-breakdown", response_model=YearlyBreakdownResponse)
def yearly_breakdown(db: Session = Depends(get_db)):
    return get_yearly_breakdown(db)


@router.get("/operational-status", response_model=OperationalStatusResponse)
def operational_status(db: Session = Depends(get_db)):
    return get_operational_status(db)


@router.get("/etf-performance", response_model=EtfPerformanceResponse)
def etf_performance(
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return get_etf_performance(db, start_date)


@router.get("/regime-stats", response_model=RegimeStatsResponse)
def regime_stats(
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return get_regime_stats(db, start_date)


@router.get("/weekly-decomposition", response_model=WeeklyDecompositionResponse)
def weekly_decomposition(db: Session = Depends(get_db)):
    return get_weekly_decomposition(db)
