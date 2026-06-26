from fastapi import APIRouter

from config import (
    DEFAULT_COEFFS, TANK_VOLUME_L, CALIBRATION_PENDING,
    EC_DEADBAND, MAX_DOSE_A_ML, MAX_DOSE_B_ML, EXTRAPOLATION_WARN_ML,
    DEFAULT_TARGET_EC, DEFAULT_TARGET_PH,
)
from dosing import compute_dose, DoseConstraints
from models import DoseRequest, DoseResponse

router = APIRouter(prefix="/api/control", tags=["control"])

_DUMMY_EC = 1.5
_DUMMY_PH = 6.8


@router.post("/dose", response_model=DoseResponse)
async def dose(req: DoseRequest = None):
    """
    현재 센서값·목표값을 받아 A·B 도징량(mL)을 계산합니다.

    request body (모두 optional):
      ec, ph           : 현재 센서 측정값 (없으면 더미값 사용)
      target_ec, target_ph : 목표값 (없으면 기본값 사용)

    Phase 2 완료 후: DB에서 최신 센서·목표값을 직접 읽도록 교체 예정.
    실제 펌프 구동은 TODO 주석 위치에 추가.
    """
    if req is None:
        req = DoseRequest()

    ec       = req.ec        if req.ec        is not None else _DUMMY_EC
    ph       = req.ph        if req.ph        is not None else _DUMMY_PH
    tgt_ec   = req.target_ec if req.target_ec is not None else DEFAULT_TARGET_EC
    tgt_ph   = req.target_ph if req.target_ph is not None else DEFAULT_TARGET_PH

    constraints = DoseConstraints(
        ec_deadband=EC_DEADBAND,
        max_a_ml=MAX_DOSE_A_ML,
        max_b_ml=MAX_DOSE_B_ML,
        extrapolation_warn_ml=EXTRAPOLATION_WARN_ML,
    )

    result = compute_dose(
        current_ec=ec, current_ph=ph,
        target_ec=tgt_ec, target_ph=tgt_ph,
        volume_l=TANK_VOLUME_L,
        coeffs=DEFAULT_COEFFS,
        constraints=constraints,
        calibration_pending=CALIBRATION_PENDING,
    )

    # TODO (Phase 4): 펌프 구동
    # if result.status not in ("SKIP",):
    #     await pump_controller.dose(a_ml=result.a_ml, b_ml=result.b_ml)

    return DoseResponse(
        a_ml=result.a_ml,
        b_ml=result.b_ml,
        status=result.status,
        message=result.message,
        notes=result.notes,
        calibration_pending=result.calibration_pending,
    )
