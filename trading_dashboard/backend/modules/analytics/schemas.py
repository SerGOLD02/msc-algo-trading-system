from pydantic import BaseModel
from typing import List, Optional

class DecayPoint(BaseModel):
    date: str
    decay_value: float
    avg_correlation: float
    regime: int

class DecayHistoryResponse(BaseModel):
    series: List[DecayPoint]

class CorrelationHeatmapResponse(BaseModel):
    tickers: List[str]
    matrix: List[List[float]]
    as_of_date: str
    window: str
    avg_correlation: float
    max_correlation: float
    n_high_pairs: int

class DrawdownInfo(BaseModel):
    current_drawdown_pct: float
    max_drawdown_pct: float
    days_since_peak: int
    peak_date: str
    peak_value: float
    current_value: float

class DrawdownHistoryPoint(BaseModel):
    date: str
    drawdown_pct: float

class DrawdownResponse(BaseModel):
    normal: DrawdownInfo
    crisis: DrawdownInfo
    combined: DrawdownInfo
    as_of_date: str
    history: List[DrawdownHistoryPoint]

class ChronosBand(BaseModel):
    ratio_id: str
    numerator: str
    denominator: str
    current_value: float
    median: float
    upper_95: float
    lower_5: float
    tfm_t5: Optional[float] = None
    tfm_projection: Optional[str] = None
    direction: str
    is_active: bool

class ChronosBandsResponse(BaseModel):
    friday_date: str
    available_fridays: List[str]
    bands: List[ChronosBand]

class YearlyMetrics(BaseModel):
    year: int
    cagr: float
    sharpe: float
    max_drawdown: float
    total_return: float
    n_weeks: int
    spy_cagr: float
    spy_sharpe: float
    spy_max_drawdown: float
    spy_total_return: float

class YearlyBreakdownResponse(BaseModel):
    years: List[YearlyMetrics]

class OperationalStatusResponse(BaseModel):
    n_active_trades: int
    regime_name: str
    regime_id: int
    is_crisis: bool
    decay_value: float
    last_friday: str

class EtfPerformanceItem(BaseModel):
    ticker: str
    algo_return: float
    bh_return: float
    alpha: float
    n_trades: int

class EtfPerformanceResponse(BaseModel):
    start_date: str
    end_date: str
    etfs: List[EtfPerformanceItem]

class RegimeStatItem(BaseModel):
    regime_id: int
    regime_name: str
    n_weeks: int
    win_rate: float
    avg_return: float
    total_trades: int

class RegimeStatsResponse(BaseModel):
    start_date: str
    regimes: List[RegimeStatItem]

class ContributionItem(BaseModel):
    ticker: str
    weight: float
    return_pct: float
    contribution: float
    trigger_state: Optional[str] = "hold" # Fix 3: Added trigger_state

class WeeklyDecompositionResponse(BaseModel):
    friday_date: str
    next_friday: str
    contributions: List[ContributionItem]
    total_return: float
