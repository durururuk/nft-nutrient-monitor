from dataclasses import dataclass

# ── 탱크 설정 ──────────────────────────────────────────────────────
TANK_VOLUME_L: float = 50.0  # TODO: 운용 탱크 실측 후 교체

# ── 도징 계수 ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class DoseCoeffs:
    """
    응답 계수 정의 (단위: 해당 물성 변화량 per mL/L).

    실험 출처:
      a_ec_A, a_ph_A  ← 실험 1 (A액 단독)
      a_ec_B, a_ph_B  ← 실험 2 (B액 단독)
      c_ec, c_ph      ← 실험 3 (A+B 혼합, 기본값 0 = 실험 전 선형 모드)
    """
    a_ec_A: float  # A액 1 mL/L당 EC 상승량 (mS/cm per mL/L)
    a_ph_A: float  # A액 1 mL/L당 pH 변화량 (+: 상승)
    a_ec_B: float  # B액 1 mL/L당 EC 상승량
    a_ph_B: float  # B액 1 mL/L당 pH 변화량 (-: 하강)
    c_ec: float = 0.0  # A·B 혼합 시 EC 비선형 보정
    c_ph: float = 0.0  # A·B 혼합 시 pH 비선형 보정


# placeholder — 실험 1·2·3 완료 후 derive_coefficients()로 교체
DEFAULT_COEFFS = DoseCoeffs(
    a_ec_A=0.72,   # (2.1-0.3)/5mL * 4L/2 로 추정, 실험 후 교체 필요
    a_ph_A=0.20,
    a_ec_B=0.72,
    a_ph_B=-0.28,
    c_ec=0.0,      # 실험 3 전: 0 유지 (선형 모드)
    c_ph=0.0,
)

CALIBRATION_PENDING: bool = True  # 실험 계수 반영 후 False로 변경

# ── 도징 제약 ──────────────────────────────────────────────────────
EC_DEADBAND: float = 0.15        # EC 차이 이 이내면 도징 안 함 (mS/cm)
MAX_DOSE_A_ML: float = 20.0      # 1회 최대 A액 투입량 (mL)
MAX_DOSE_B_ML: float = 20.0      # 1회 최대 B액 투입량 (mL)
EXTRAPOLATION_WARN_ML: float = 25.0  # 이 이상이면 실험 범위 외 경고 (mL)

# ── 센서 정상 범위 (상추 기준) ────────────────────────────────────
SENSOR_RANGE = {
    "ec":   {"min": 0.5,  "max": 3.5},
    "ph":   {"min": 5.5,  "max": 7.5},
    "temp": {"min": 5.0,  "max": 40.0},
}

# ── 기본 목표값 ───────────────────────────────────────────────────
DEFAULT_TARGET_EC: float = 2.0
DEFAULT_TARGET_PH: float = 6.5

# ── 데이터베이스 ──────────────────────────────────────────────────
DB_PATH: str = "data/sensor.db"  # data/ 디렉터리는 init_db()에서 자동 생성
