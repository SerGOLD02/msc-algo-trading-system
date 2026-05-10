from pydantic import BaseModel
from typing import List

class IndexSummaryDTO(BaseModel):
    name: str
    ticker: str
    last_price: float
    change_1d_pct: float
    change_1w_pct: float
    change_1m_pct: float
    change_1y_pct: float
    change_ytd_pct: float

class AssetPriceDTO(BaseModel):
    ticker: str
    last_price: float
    change_1d_pct: float
    change_1w_pct: float
    change_1m_pct: float
    change_1y_pct: float
    change_ytd_pct: float
    volume: float
    is_etf: bool

class MarketSnapshotDTO(BaseModel):
    indices: List[IndexSummaryDTO]
    assets: List[AssetPriceDTO]
    last_updated: str
    market_open: bool
    next_friday: str
    seconds_to_friday_close: int
