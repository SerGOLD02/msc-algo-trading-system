from pydantic import BaseModel
from typing import List, Optional

class RatioSignalDTO(BaseModel):
    ratio_id: str
    numerator: str
    denominator: str
    direction: str
    long_ticker: str
    short_ticker: str
    bet_quality: float
    is_active: bool
    status: str
    tfm_t5: Optional[float] = None
    tfm_projection: Optional[str] = None
    current_ratio: Optional[float] = None
    chr_median_t5: Optional[float] = None
    chr_width_t5: Optional[float] = None
    realized_return: Optional[float] = None

class WeeklySignalResponse(BaseModel):
    friday_date: str
    available_fridays: List[str]
    regime_id: int
    regime_name: str
    is_crisis: bool
    n_active: int
    n_filtered: int
    signals: List[RatioSignalDTO]
