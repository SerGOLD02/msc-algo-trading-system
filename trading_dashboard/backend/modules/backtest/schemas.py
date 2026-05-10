from pydantic import BaseModel
from typing import Optional

class BacktestParams(BaseModel):
    bet_quality: float = 0.50
    hrp_alpha:   float = 0.50
    k_sigmoid:   float = 10.0
    c_soglia:    float = 0.50
    k_up:        float = 1.25
    k_down:      float = 1.50
    start_date:  str | None = None

class WeeklyPoint(BaseModel):
    date:             str
    portfolio_value:  float
    weekly_return:    float
    regime:           int
    decay_value:      float
    n_trades:         int
    is_crisis:        bool

class BacktestResponseDTO(BaseModel):
    params_hash:   str
    is_default:    bool
    series:        list[WeeklyPoint]
    cagr:          float
    sharpe:        float
    max_drawdown:  float
    calmar:        float
    total_return:  float
    n_crisis_weeks: int
    n_normal_weeks: int
    spy_series:    list[dict]
    spy_cagr:      float = 0.0
    spy_sharpe:    float = 0.0
    spy_max_drawdown: float = 0.0
    spy_calmar:    float = 0.0
    spy_total_return: float = 0.0
