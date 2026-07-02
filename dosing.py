"""
도징 알고리즘 엔진 — 순수 계산 모듈, 하드웨어 무관.

운용 방식: 순차 폐루프(closed-loop) 2단계
  1단계 (pH):  B액으로 목표 pH 도달  →  compute_ph_dose()
      · A액은 pH에 거의 영향을 주지 않으므로(a_ph_A≈0) pH는 B액 단독으로 조정.
      · B액은 pH를 낮추는 방향(a_ph_B<0)으로만 작용.
  ── B액 투입 → 교반 → 재측정 ──
  2단계 (EC):  재측정한 EC로 남은 EC 차이만 A액으로 채움  →  compute_ec_dose()
      · B가 올린 EC는 이미 재측정값에 반영돼 있으므로 A액만 계산.
      · 이 방식은 B의 EC 계수(a_ec_B) 오차에 영향받지 않는다(측정이 흡수).

과거의 A·B 동시 1회 해법(compute_dose)은 6개 계수가 모두 정확해야 했으나,
순차 폐루프는 각 단계가 1변수 문제라 계수 의존을 크게 줄인다.

모델(계수 도출용, derive_coefficients):
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

_PH_TOL = 0.1  # pH 측정 오차 폭 — 이보다 큰 pH 이탈만 조정 대상


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


# ── 공개 API ───────────────────────────────────────────────────────

def compute_ph_dose(
    current_ph: float,
    target_ph: float,
    volume_l: float,
    coeffs: DoseCoeffs,
    constraints: DoseConstraints,
    calibration_pending: bool = False,
) -> DoseResult:
    """
    1단계 — 목표 pH 도달을 위한 B액 투입량(mL) 계산.

    A액은 pH에 거의 영향을 주지 않으므로 pH는 B액 단독으로 조정한다.
    B액은 pH를 낮추는 방향(a_ph_B<0)으로만 작용하므로, pH를 올려야 하는
    경우(현재<목표)에는 양액으로 불가하며 pH-up(염기) 별도 조치가 필요하다.

    투입 순서상 B가 먼저 들어가므로 이 단계에서 A는 0 → 상호작용항 없음(1변수).
    반환 후 반드시 B액 투입·교반·재측정 → compute_ec_dose()로 A액을 계산할 것.
    """
    notes: List[str] = []
    d_ph = target_ph - current_ph
    c = coeffs

    # pH 데드밴드 — 측정 오차 폭 이내면 조정 불필요
    if abs(d_ph) <= _PH_TOL:
        return DoseResult(
            a_ml=0.0, b_ml=0.0, status="SKIP",
            message=f"pH 차이 {d_ph:+.2f} — 허용 오차 이내, B액 불필요",
            notes=notes, calibration_pending=calibration_pending,
        )

    # pH를 올려야 하는 경우 — 양액으로 상향 불가
    if d_ph > 0:
        return DoseResult(
            a_ml=0.0, b_ml=0.0, status="SKIP",
            message=(f"현재 pH {current_ph:.2f} < 목표 {target_ph:.2f} "
                     "— 양액 투입으로 pH를 올릴 수 없음"),
            notes=["pH-up(염기) 별도 조치 필요"],
            calibration_pending=calibration_pending,
        )

    # B가 pH를 낮출 수 있어야 함 (a_ph_B<0). 계수 이상 방어.
    if c.a_ph_B >= 0:
        return DoseResult(
            a_ml=0.0, b_ml=0.0, status="SKIP",
            message="B액 pH 계수 이상(a_ph_B≥0) — 도징 계산 불가",
            notes=["계수 재점검 필요"],
            calibration_pending=calibration_pending,
        )

    xB = d_ph / c.a_ph_B          # d_ph<0, a_ph_B<0 → xB>0
    b_ml = xB * volume_l

    capped = False
    if b_ml > constraints.max_b_ml:
        b_ml = constraints.max_b_ml
        capped = True
        notes.append(f"B액 {constraints.max_b_ml:.0f}mL 상한 — 나머지는 다음 사이클에 처리")

    if b_ml > constraints.extrapolation_warn_ml:
        notes.append("투입량이 실험 측정 범위를 초과합니다 — 투입 후 재측정 권장")

    if calibration_pending:
        notes.append("계수 미보정(placeholder) — 실험 완료 후 정밀도 확보됩니다")

    notes.append("B액 투입·교반 후 재측정하여 EC 단계(A액)를 진행하세요")

    b_ml = round(b_ml, 1) + 0.0  # -0.0 정규화
    status = "CAPPED" if capped else "OK"
    suffix = " — 상한 적용, 분할 투입 필요" if capped else ""
    return DoseResult(
        a_ml=0.0, b_ml=b_ml, status=status,
        message=(f"B액 {b_ml:.1f}mL 투입 권장 "
                 f"(탱크 {volume_l:.0f}L, pH {current_ph:.2f}→{target_ph:.2f}){suffix}"),
        notes=notes, calibration_pending=calibration_pending,
    )


def compute_ec_dose(
    current_ec: float,
    target_ec: float,
    volume_l: float,
    coeffs: DoseCoeffs,
    constraints: DoseConstraints,
    calibration_pending: bool = False,
    b_ml_dosed: float = 0.0,
) -> DoseResult:
    """
    2단계 — (B액 투입·재측정 후) 목표 EC 도달을 위한 A액 투입량(mL) 계산.

    B가 올린 EC는 이미 current_ec(재측정값)에 반영돼 있으므로 남은 EC 차이만
    A액으로 채운다. 이 방식은 B의 EC 계수(a_ec_B) 오차에 영향받지 않는다.

    b_ml_dosed : 1단계에서 실제 투입한 B액(mL). 상호작용항(c_ec)이 있을 때
                 A액의 유효 EC 기울기를 (a_ec_A + c_ec·xB)로 보정한다.
                 c_ec=0(기본) 또는 0이면 무영향.
    """
    notes: List[str] = []
    d_ec = target_ec - current_ec
    c = coeffs

    # EC 데드밴드
    if abs(d_ec) <= constraints.ec_deadband:
        return DoseResult(
            a_ml=0.0, b_ml=0.0, status="SKIP",
            message=f"EC 차이 {d_ec:+.2f} mS/cm — 데드밴드 이내, A액 불필요",
            notes=notes, calibration_pending=calibration_pending,
        )

    # EC가 목표보다 높음 — 양액으로 낮출 수 없음
    if d_ec < 0:
        return DoseResult(
            a_ml=0.0, b_ml=0.0, status="SKIP",
            message=(f"EC {current_ec:.2f} > 목표 {target_ec:.2f} mS/cm "
                     "— 양액 투입으로 낮출 수 없음, 희석 필요"),
            notes=notes, calibration_pending=calibration_pending,
        )

    xB = (b_ml_dosed / volume_l) if volume_l else 0.0
    slope = c.a_ec_A + c.c_ec * xB     # A액 유효 EC 기울기 (상호작용 보정)
    if slope <= 0:
        return DoseResult(
            a_ml=0.0, b_ml=0.0, status="SKIP",
            message="A액 EC 유효 기울기 ≤ 0 — 도징 계산 불가",
            notes=["계수 재점검 필요"],
            calibration_pending=calibration_pending,
        )

    a_ml = (d_ec / slope) * volume_l

    capped = False
    if a_ml > constraints.max_a_ml:
        a_ml = constraints.max_a_ml
        capped = True
        notes.append(f"A액 {constraints.max_a_ml:.0f}mL 상한 — 나머지는 다음 사이클에 처리")

    if a_ml > constraints.extrapolation_warn_ml:
        notes.append("투입량이 실험 측정 범위를 초과합니다 — 투입 후 재측정 권장")

    if calibration_pending:
        notes.append("계수 미보정(placeholder) — 실험 완료 후 정밀도 확보됩니다")

    a_ml = round(a_ml, 1) + 0.0  # -0.0 정규화
    status = "CAPPED" if capped else "OK"
    suffix = " — 상한 적용, 분할 투입 필요" if capped else ""
    return DoseResult(
        a_ml=a_ml, b_ml=0.0, status=status,
        message=(f"A액 {a_ml:.1f}mL 투입 권장 "
                 f"(탱크 {volume_l:.0f}L, EC {current_ec:.2f}→{target_ec:.2f}){suffix}"),
        notes=notes, calibration_pending=calibration_pending,
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

    print("=" * 60)
    print("순차 폐루프 시뮬레이션 (1단계 pH → 재측정 → 2단계 EC)")
    print("=" * 60)

    # 시나리오: 현재 EC 1.50 / pH 6.8 → 목표 EC 2.0 / pH 6.5
    ec0, ph0, tec, tph = 1.50, 6.8, 2.0, 6.5

    # 1단계 — B액으로 pH 조정
    r1 = compute_ph_dose(ph0, tph, TANK_VOLUME_L, c, con, CALIBRATION_PENDING)
    print(f"[1단계 pH] {r1.status}: {r1.message}")
    for n in r1.notes:
        print(f"  ⚠  {n}")

    # B 투입 후 재측정 시뮬레이션: B가 EC를 a_ec_B·xB 만큼 올린다고 가정
    xB = r1.b_ml / TANK_VOLUME_L
    ec_after_b = ec0 + c.a_ec_B * xB
    print(f"  → B 투입 후 예상 재측정 EC ≈ {ec_after_b:.2f} mS/cm")

    # 2단계 — 재측정 EC로 A액 계산
    r2 = compute_ec_dose(ec_after_b, tec, TANK_VOLUME_L, c, con,
                         CALIBRATION_PENDING, b_ml_dosed=r1.b_ml)
    print(f"[2단계 EC] {r2.status}: {r2.message}")
    for n in r2.notes:
        print(f"  ⚠  {n}")
    print("=" * 60)

    # 개별 엣지 케이스
    edge = [
        ("pH 이미 목표",   6.5, tph, "ph"),
        ("pH 올려야 함",   5.0, tph, "ph"),
        ("EC 데드밴드",    1.92, tec, "ec"),
        ("EC 초과",        2.80, tec, "ec"),
    ]
    for label, cur, tgt, kind in edge:
        if kind == "ph":
            r = compute_ph_dose(cur, tgt, TANK_VOLUME_L, c, con)
        else:
            r = compute_ec_dose(cur, tgt, TANK_VOLUME_L, c, con)
        print(f"[{label}] {r.status}: {r.message}")
    print("=" * 60)
