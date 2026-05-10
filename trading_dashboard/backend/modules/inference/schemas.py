from pydantic import BaseModel
from typing import List, Optional

class InferenceDTO(BaseModel):
    ratio_id: str
    tfm_t1: Optional[float] = None
    tfm_t5: Optional[float] = None
    tfm_t20: Optional[float] = None
    chr_median_t5: Optional[float] = None
    chr_width_t5: Optional[float] = None
    upper_band: Optional[float] = None
    lower_band: Optional[float] = None

class InferenceResponseDTO(BaseModel):
    friday_date: str
    inferences: List[InferenceDTO]
