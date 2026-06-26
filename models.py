from pydantic import BaseModel
from typing import List, Optional


class DoseRequest(BaseModel):
    ec:        Optional[float] = None
    ph:        Optional[float] = None
    target_ec: Optional[float] = None
    target_ph: Optional[float] = None


class TargetSettings(BaseModel):
    ec: float
    ph: float


class DoseResponse(BaseModel):
    a_ml:               float
    b_ml:               float
    status:             str         # OK | SKIP | CLAMPED | CAPPED
    message:            str
    notes:              List[str] = []
    calibration_pending: bool = False
