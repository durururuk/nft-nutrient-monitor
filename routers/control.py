from fastapi import APIRouter

from config import (
    DEFAULT_COEFFS, TANK_VOLUME_L, CALIBRATION_PENDING,
    EC_DEADBAND, MAX_DOSE_A_ML, MAX_DOSE_B_ML, EXTRAPOLATION_WARN_ML,
    DEFAULT_TARGET_EC, DEFAULT_TARGET_PH,
)
from dosing import compute_ph_dose, compute_ec_dose, DoseConstraints
from models import DoseRequest, DoseResponse

router = APIRouter(prefix="/api/control", tags=["control"])

_DUMMY_EC = 1.5
_DUMMY_PH = 6.8


def _constraints() -> DoseConstraints:
    return DoseConstraints(
        ec_deadband=EC_DEADBAND,
        max_a_ml=MAX_DOSE_A_ML,
        max_b_ml=MAX_DOSE_B_ML,
        extrapolation_warn_ml=EXTRAPOLATION_WARN_ML,
    )


@router.post("/dose/ph", response_model=DoseResponse)
async def dose_ph(req: DoseRequest = None):
    """
    1단계 — 목표 pH 도달을 위한 B액 도징량 계산.

    A액은 pH에 거의 영향이 없으므로 pH는 B액 단독으로 조정한다.
    이 응답의 B액을 투입·교반한 뒤 반드시 재측정하여 /dose/ec 를 호출할 것.

    request body (모두 optional):
      ph        : 현재 pH (없으면 더미값)
      target_ph : 목표 pH (없으면 기본값)
    """
    if req is None:
        req = DoseRequest()

    ph     = req.ph        if req.ph        is not None else _DUMMY_PH
    tgt_ph = req.target_ph if req.target_ph is not None else DEFAULT_TARGET_PH

    result = compute_ph_dose(
        current_ph=ph, target_ph=tgt_ph,
        volume_l=TANK_VOLUME_L,
        coeffs=DEFAULT_COEFFS,
        constraints=_constraints(),
        calibration_pending=CALIBRATION_PENDING,
    )

    # TODO (Phase 4): 펌프 구동 — if result.status != "SKIP": await pump.dose_b(result.b_ml)

    return DoseResponse(
        a_ml=result.a_ml, b_ml=result.b_ml,
        status=result.status, message=result.message, phase="ph",
        notes=result.notes, calibration_pending=result.calibration_pending,
    )


@router.post("/dose/ec", response_model=DoseResponse)
async def dose_ec(req: DoseRequest = None):
    """
    2단계 — (B액 투입·재측정 후) 목표 EC 도달을 위한 A액 도징량 계산.

    B가 올린 EC는 이미 재측정 EC(req.ec)에 반영돼 있으므로 남은 차이만 A액으로 채운다.

    request body (모두 optional):
      ec         : 재측정 EC (없으면 더미값)
      target_ec  : 목표 EC (없으면 기본값)
      b_ml_dosed : 1단계에서 투입한 B액(mL) — 상호작용 보정용(c_ec≠0일 때)
    """
    if req is None:
        req = DoseRequest()

    ec     = req.ec         if req.ec         is not None else _DUMMY_EC
    tgt_ec = req.target_ec  if req.target_ec  is not None else DEFAULT_TARGET_EC
    b_ml   = req.b_ml_dosed if req.b_ml_dosed is not None else 0.0

    result = compute_ec_dose(
        current_ec=ec, target_ec=tgt_ec,
        volume_l=TANK_VOLUME_L,
        coeffs=DEFAULT_COEFFS,
        constraints=_constraints(),
        calibration_pending=CALIBRATION_PENDING,
        b_ml_dosed=b_ml,
    )

    # TODO (Phase 4): 펌프 구동 — if result.status != "SKIP": await pump.dose_a(result.a_ml)

    return DoseResponse(
        a_ml=result.a_ml, b_ml=result.b_ml,
        status=result.status, message=result.message, phase="ec",
        notes=result.notes, calibration_pending=result.calibration_pending,
    )
