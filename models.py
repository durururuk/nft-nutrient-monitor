from pydantic import BaseModel
from typing import List, Optional


class DoseRequest(BaseModel):
    ec:         Optional[float] = None
    ph:         Optional[float] = None
    target_ec:  Optional[float] = None
    target_ph:  Optional[float] = None
    b_ml_dosed: Optional[float] = None  # EC 단계에서 1단계 B 투입량(상호작용 보정용)


class TargetSettings(BaseModel):
    ec: float
    ph: float


class DoseResponse(BaseModel):
    a_ml:               float
    b_ml:               float
    status:             str         # OK | SKIP | CAPPED
    message:            str
    phase:              str = ""    # ph | ec — 순차 폐루프 단계
    notes:              List[str] = []
    calibration_pending: bool = False
