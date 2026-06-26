"""
도징 알고리즘 엔진 — 순수 계산 모듈, 하드웨어 무관.

운용 가정:
  투입 순서: A액 먼저 투입 → 충분히 교반 → B액 추가 투입
  이는 실험 3(A+B 혼합) 측정 절차와 동일하므로 계수가 그대로 적용됩니다.

모델:
  ΔEC = a_ec_A·xA + a_ec_B·xB + c_ec·(xA·xB)
  ΔpH = a_ph_A·xA + a_ph_B·xB + c_ph·(xA·xB)
  xA = A(mL) / V(L),  xB = B(mL) / V(L)

계수 출처:
  a_ec_A, a_ph_A  ← 실험 1 (A 단독)
  a_ec_B, a_ph_B  ← 실험 2 (B 단독)
  c_ec,   c_ph    ← 실험 3 (A+B 혼합, 기본값 0 = 선형 모드)
"""

from dataclasses import dataclass, field
from typing import List

from config import DoseCoeffs

_NEWTON_MAX_ITER = 8
_NEWTON_TOL = 1e-6
_DET_EPS = 1e-9


@dataclass
class DoseConstraints:
    ec_deadband:          float = 0.15
    max_a_ml:             float = 20.0
    max_b_ml:             float = 20.0
    extrapolation_warn_ml: float = 25.0


@dataclass
class DoseResult:
    a_ml:               float
    b_ml:               float
    status:             str
    message:            str
    notes:              List[str] = field(default_factory=list)
    calibration_pending: bool = False


# ── 내부 풀이 함수 ─────────────────────────────────────────────────

def _linear_solve(a_ec_A, a_ph_A, a_ec_B, a_ph_B, d_ec, d_ph):
    """2×2 선형 연립 닫힌형 풀이. singular이면 None 반환."""
    det = a_ec_A * a_ph_B - a_ec_B * a_ph_A
    if abs(det) < _DET_EPS:
        return None
    xA = (d_ec * a_ph_B - d_ph * a_ec_B) / det
    xB = (a_ec_A * d_ph - a_ph_A * d_ec) / det
    return xA, xB


def _newton_solve(coeffs: DoseCoeffs, d_ec: float, d_ph: float,
                  x0A: float, x0B: float):
    """
    이중선형 연립방정식 Newton 반복 풀이.
    c_ec=c_ph=0이면 1회 후 잔차=0으로 즉시 종료 (선형 해 그대로).
    """
    c = coeffs
    xA, xB = x0A, x0B

    for _ in range(_NEWTON_MAX_ITER):
        f1 = c.a_ec_A*xA + c.a_ec_B*xB + c.c_ec*xA*xB - d_ec
        f2 = c.a_ph_A*xA + c.a_ph_B*xB + c.c_ph*xA*xB - d_ph

        if abs(f1) < _NEWTON_TOL and abs(f2) < _NEWTON_TOL:
            break

        # 야코비안 J = [[j11, j12], [j21, j22]]
        j11 = c.a_ec_A + c.c_ec * xB
        j12 = c.a_ec_B + c.c_ec * xA
        j21 = c.a_ph_A + c.c_ph * xB
        j22 = c.a_ph_B + c.c_ph * xA
        det = j11 * j22 - j12 * j21

        if abs(det) < _DET_EPS:
            break  # 특이 행렬 → 현재 해 그대로 반환

        # Newton step: [xA, xB] -= J^{-1} F
        xA -= (j22 * f1 - j12 * f2) / det
        xB -= (j11 * f2 - j21 * f1) / det

    return xA, xB


# ── 공개 API ───────────────────────────────────────────────────────

def compute_dose(
    current_ec: float,
    current_ph: float,
    target_ec: float,
    target_ph: float,
    volume_l: float,
    coeffs: DoseCoeffs,
    constraints: DoseConstraints,
    calibration_pending: bool = False,
) -> DoseResult:
    """
    현재 EC·pH와 목표값을 받아 A·B 투입량(mL)을 역산합니다.

    Parameters
    ----------
    current_ec, current_ph : 현재 센서 측정값
    target_ec, target_ph   : 목표값
    volume_l               : 운용 탱크 용량 (L)
    coeffs                 : 응답 계수 (실험 1·2·3에서 도출)
    constraints            : 물리 제약 설정
    calibration_pending    : True면 계수가 placeholder임을 결과에 표시
    """
    notes: List[str] = []
    d_ec = target_ec - current_ec
    d_ph = target_ph - current_ph

    # ── 1. 데드밴드 / EC 초과 체크 ───────────────────────────────
    if abs(d_ec) <= constraints.ec_deadband:
        return DoseResult(
            a_ml=0.0, b_ml=0.0,
            status="SKIP",
            message=f"EC 차이 {d_ec:+.2f} mS/cm — 데드밴드 이내, 도징 불필요",
            notes=notes,
            calibration_pending=calibration_pending,
        )

    if d_ec < 0:
        return DoseResult(
            a_ml=0.0, b_ml=0.0,
            status="SKIP",
            message=(f"EC {current_ec:.2f} > 목표 {target_ec:.2f} mS/cm "
                     "— 양액 투입으로 낮출 수 없음, 희석 필요"),
            notes=notes,
            calibration_pending=calibration_pending,
        )

    # ── 2. 선형 초기해 → Newton 보정 ─────────────────────────────
    c = coeffs
    lin = _linear_solve(c.a_ec_A, c.a_ph_A, c.a_ec_B, c.a_ph_B, d_ec, d_ph)

    if lin is None:
        # A·B의 pH 기울기 비율 동일 → EC 기준 균등 분배
        half = d_ec / ((c.a_ec_A + c.a_ec_B) or _DET_EPS) / 2
        xA, xB = half, half
        notes.append("A·B pH 응답이 유사해 EC 기준 균등 분배 적용")
        status_base = "CLAMPED"
    else:
        xA, xB = _newton_solve(coeffs, d_ec, d_ph, *lin)
        status_base = "OK"

    # ── 3. 음수 클램프 (EC 우선 단독 재산출) ─────────────────────
    clamped = False

    if xA < 0 and xB < 0:
        # 이 경우는 d_ec>0인데 둘 다 음수 → 이론상 불가, 안전망
        return DoseResult(
            a_ml=0.0, b_ml=0.0,
            status="SKIP",
            message="계수 이상 또는 상충 조건 — 도징 계산 불가",
            notes=["A·B 모두 음수 해: 계수 재점검 필요"],
            calibration_pending=calibration_pending,
        )

    if xA < 0:
        xA = 0.0
        xB = d_ec / (c.a_ec_B or _DET_EPS)
        clamped = True
        notes.append("A액 0 클램프 — EC 기준 B액만으로 조정 (pH 방향이 B 단독 적합)")

    elif xB < 0:
        xB = 0.0
        xA = d_ec / (c.a_ec_A or _DET_EPS)
        clamped = True
        notes.append("B액 0 클램프 — EC 기준 A액만으로 조정 (pH 방향이 A 단독 적합)")

    a_ml = xA * volume_l
    b_ml = xB * volume_l

    # ── 4. 상한 캡 ───────────────────────────────────────────────
    capped = False
    if a_ml > constraints.max_a_ml:
        a_ml = constraints.max_a_ml
        capped = True
        notes.append(f"A액 {constraints.max_a_ml:.0f}mL 상한 — 나머지는 다음 사이클에 처리")
    if b_ml > constraints.max_b_ml:
        b_ml = constraints.max_b_ml
        capped = True
        notes.append(f"B액 {constraints.max_b_ml:.0f}mL 상한 — 나머지는 다음 사이클에 처리")

    # ── 5. 외삽 경고 ─────────────────────────────────────────────
    if a_ml > constraints.extrapolation_warn_ml or b_ml > constraints.extrapolation_warn_ml:
        notes.append("투입량이 실험 측정 범위를 초과합니다 — 투입 후 재측정 권장")

    # ── 6. 캘리브레이션 경고 ─────────────────────────────────────
    if calibration_pending:
        notes.append("계수 미보정(placeholder) — 실험 완료 후 정밀도 확보됩니다")

    # ── 7. 상태·메시지 조합 ──────────────────────────────────────
    if capped:
        status = "CAPPED"
        suffix = " — 상한 적용, 분할 투입 필요"
    elif clamped:
        status = "CLAMPED"
        suffix = ""
    else:
        status = status_base
        suffix = ""

    message = (f"A액 {a_ml:.1f}mL + B액 {b_ml:.1f}mL 투입 권장"
               f" (탱크 {volume_l:.0f}L 기준){suffix}")

    return DoseResult(
        a_ml=round(a_ml, 1),
        b_ml=round(b_ml, 1),
        status=status,
        message=message,
        notes=notes,
        calibration_pending=calibration_pending,
    )


def derive_coefficients(
    *,
    exp1_baseline_ec: float, exp1_baseline_ph: float,
    exp1_std_ec: float,      exp1_std_ph: float,
    exp2_baseline_ec: float, exp2_baseline_ph: float,
    exp2_std_ec: float,      exp2_std_ph: float,
    exp3_baseline_ec: float, exp3_baseline_ph: float,
    exp3_std_ec: float,      exp3_std_ph: float,
    dose_density_ml_per_l: float = 1.25,
) -> DoseCoeffs:
    """
    실험 1·2·3의 측정값으로 6개 응답 계수를 계산합니다.

    Parameters
    ----------
    exp1_* : 실험 1 (A 단독) 베이스라인·표준 1배 EC/pH
    exp2_* : 실험 2 (B 단독) 베이스라인·표준 1배 EC/pH
    exp3_* : 실험 3 (A+B 혼합) 베이스라인·표준 1배 EC/pH
    dose_density_ml_per_l : 표준 1배 도징밀도 (기본: 5mL / 4L = 1.25 mL/L)

    Usage (실험 후)
    ---------------
    coeffs = derive_coefficients(
        exp1_baseline_ec=0.31, exp1_baseline_ph=7.1,
        exp1_std_ec=1.40,      exp1_std_ph=7.3,
        exp2_baseline_ec=0.30, exp2_baseline_ph=7.0,
        exp2_std_ec=1.38,      exp2_std_ph=6.6,
        exp3_baseline_ec=0.30, exp3_baseline_ph=7.0,
        exp3_std_ec=2.05,      exp3_std_ph=6.8,
    )
    # → config.py의 DEFAULT_COEFFS를 이 값으로 교체
    """
    d = dose_density_ml_per_l

    a_ec_A = (exp1_std_ec - exp1_baseline_ec) / d
    a_ph_A = (exp1_std_ph - exp1_baseline_ph) / d
    a_ec_B = (exp2_std_ec - exp2_baseline_ec) / d
    a_ph_B = (exp2_std_ph - exp2_baseline_ph) / d

    # 혼합 비선형 보정: 실측 - 선형 예측 차이를 xA*xB로 나눔
    d_ec_3 = exp3_std_ec - exp3_baseline_ec
    d_ph_3 = exp3_std_ph - exp3_baseline_ph
    c_ec = (d_ec_3 - (a_ec_A + a_ec_B) * d) / (d * d)
    c_ph = (d_ph_3 - (a_ph_A + a_ph_B) * d) / (d * d)

    return DoseCoeffs(
        a_ec_A=round(a_ec_A, 4),
        a_ph_A=round(a_ph_A, 4),
        a_ec_B=round(a_ec_B, 4),
        a_ph_B=round(a_ph_B, 4),
        c_ec=round(c_ec, 4),
        c_ph=round(c_ph, 4),
    )


if __name__ == "__main__":
    from config import DEFAULT_COEFFS, TANK_VOLUME_L, CALIBRATION_PENDING

    c = DEFAULT_COEFFS
    con = DoseConstraints()

    cases = [
        ("정상 도징",   1.50, 6.8, 2.0, 6.5),
        ("pH만 낮음",   2.05, 7.2, 2.0, 6.5),
        ("데드밴드",    1.92, 6.5, 2.0, 6.5),
        ("EC 초과",     2.80, 6.5, 2.0, 6.5),
    ]

    print("=" * 60)
    for label, ec, ph, tec, tph in cases:
        r = compute_dose(ec, ph, tec, tph, TANK_VOLUME_L, c, con, CALIBRATION_PENDING)
        print(f"[{label}] {r.status}")
        print(f"  {r.message}")
        for n in r.notes:
            print(f"  ⚠  {n}")
    print("=" * 60)

    # 왕복 검증 (상호작용항 포함)
    coeffs_full = DoseCoeffs(
        a_ec_A=0.72, a_ph_A=0.20,
        a_ec_B=0.72, a_ph_B=-0.28,
        c_ec=-0.05,  c_ph=0.02,
    )
    r = compute_dose(1.2, 7.0, 2.0, 6.5, 20.0, coeffs_full, con)
    xA, xB = r.a_ml / 20.0, r.b_ml / 20.0
    dEC = coeffs_full.a_ec_A*xA + coeffs_full.a_ec_B*xB + coeffs_full.c_ec*xA*xB
    dpH = coeffs_full.a_ph_A*xA + coeffs_full.a_ph_B*xB + coeffs_full.c_ph*xA*xB
    print(f"[왕복검증] A={r.a_ml}mL B={r.b_ml}mL")
    print(f"  ΔEC 재현: {dEC:.4f}  (목표 0.8000)")
    print(f"  ΔpH 재현: {dpH:.4f}  (목표 -0.5000)")
