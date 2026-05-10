from pydantic import BaseModel

class RegimeStatusDTO(BaseModel):
    regime_id: int
    regime_name: str
    is_crisis: bool
    decay_value: float
    last_friday: str
    prob_crisis: float
