# NFT 배양액 모니터 — API 명세서

> 백엔드(FastAPI)가 제공하는 HTTP API 목록과 요청/응답 형식을 정리한 문서입니다.
> **구현 완료**와 **구현 예정(Phase 2)** 을 섹션으로 분리해 표기합니다.

---

## 공통 사항

| 항목 | 값 |
| --- | --- |
| Base URL | `http://<host>:8000` (RPi 키오스크는 `http://localhost:8000`) |
| 요청/응답 포맷 | JSON (UTF-8) |
| 정적 대시보드 | `GET /` → `static/index.html` 서빙 |
| 진입점 | [main.py](../main.py) |

---

## 구현 완료 (현재 동작)

### `POST /api/control/dose`

현재 센서값(EC·pH)과 목표값을 받아, 목표 EC·pH에 도달하기 위한 **A액·B액 투입량(mL)** 을 계산해 반환합니다.
도징 알고리즘 본체는 [dosing.py](../dosing.py), 라우터는 [routers/control.py](../routers/control.py)에 있습니다.

> ⚠️ 현재는 **계산 전용(Mock)** — 실제 펌프 구동은 Phase 4에서 추가됩니다.
> 또한 계수가 placeholder 상태이므로 응답의 `calibration_pending`이 `true`입니다(실험 후 `false`).

**Request body** (`application/json`, 모든 필드 optional)

| 필드 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `ec` | number | 더미 1.5 | 현재 EC 측정값 (mS/cm) |
| `ph` | number | 더미 6.8 | 현재 pH 측정값 |
| `target_ec` | number | 2.0 | 목표 EC (mS/cm) |
| `target_ph` | number | 6.5 | 목표 pH |

> body를 생략하거나 일부 필드만 보내면 위 기본값으로 대체됩니다.
> (Phase 2 완료 후에는 서버가 DB에서 최신 센서·목표값을 직접 읽도록 교체 예정.)

**Response** (`DoseResponse` — [models.py](../models.py))

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `a_ml` | number | A액 권장 투입량 (mL, 소수 1자리) |
| `b_ml` | number | B액 권장 투입량 (mL, 소수 1자리) |
| `status` | string | 처리 결과 (아래 표 참조) |
| `message` | string | 사람이 읽는 요약 메시지 |
| `notes` | string[] | 클램프·상한·경고 등 부가 설명 |
| `calibration_pending` | boolean | 계수 미보정(placeholder) 여부 |

**`status` 값**

| 값 | 의미 |
| --- | --- |
| `OK` | 정상 계산 — A·B 투입량 그대로 권장 |
| `SKIP` | 도징 불필요/불가 — 데드밴드 이내, 또는 EC가 이미 목표 초과(희석 필요) |
| `CLAMPED` | 한쪽 양액이 음수로 계산되어 0으로 고정하고 EC 기준 단독 조정 |
| `CAPPED` | 1회 투입 상한을 초과해 상한값으로 제한 (분할 투입 필요) |

**예시 1 — 정상 (CLAMPED: pH가 낮아 A액 우선)**

```bash
curl -X POST http://localhost:8000/api/control/dose \
  -H "Content-Type: application/json" \
  -d '{"ec": 1.5, "ph": 6.8, "target_ec": 2.0, "target_ph": 6.5}'
```

```json
{
  "a_ml": 0.0,
  "b_ml": 13.9,
  "status": "CLAMPED",
  "message": "A액 0.0mL + B액 13.9mL 투입 권장 (탱크 20L 기준)",
  "notes": [
    "A액 0 클램프 — EC 기준 B액만으로 조정 (pH 방향이 B 단독 적합)",
    "계수 미보정(placeholder) — 실험 완료 후 정밀도 확보됩니다"
  ],
  "calibration_pending": true
}
```

**예시 2 — 데드밴드 (SKIP)**

```bash
curl -X POST http://localhost:8000/api/control/dose \
  -H "Content-Type: application/json" \
  -d '{"ec": 1.92, "ph": 6.5, "target_ec": 2.0, "target_ph": 6.5}'
```

```json
{
  "a_ml": 0.0,
  "b_ml": 0.0,
  "status": "SKIP",
  "message": "EC 차이 +0.08 mS/cm — 데드밴드 이내, 도징 불필요",
  "notes": [],
  "calibration_pending": true
}
```

**예시 3 — 상한 초과 (CAPPED)**

```bash
curl -X POST http://localhost:8000/api/control/dose \
  -H "Content-Type: application/json" \
  -d '{"ec": 0.5, "ph": 5.5, "target_ec": 2.0, "target_ph": 6.5}'
```

```json
{
  "a_ml": 20.0,
  "b_ml": 0.0,
  "status": "CAPPED",
  "message": "A액 20.0mL + B액 0.0mL 투입 권장 (탱크 20L 기준) — 상한 적용, 분할 투입 필요",
  "notes": [
    "B액 0 클램프 — EC 기준 A액만으로 조정 (pH 방향이 A 단독 적합)",
    "A액 20mL 상한 — 나머지는 다음 사이클에 처리",
    "계수 미보정(placeholder) — 실험 완료 후 정밀도 확보됩니다"
  ],
  "calibration_pending": true
}
```

---

### `GET /`

정적 대시보드(`static/index.html`)와 자산(JS/CSS)을 서빙합니다. Chromium 키오스크가 이 페이지를 띄웁니다.

---

## 구현 예정 (Phase 2 — 아직 미구현)

> 아래 엔드포인트는 **아직 서버에 구현되어 있지 않습니다.**
> 프론트엔드([static/app.js](../static/app.js))는 이미 일부를 호출하지만, 미구현 상태에서는 graceful fallback(로컬 더미값)으로 동작합니다.
> 설계 근거는 프로젝트 루트 `CLAUDE.MD`의 시스템 아키텍처 절입니다.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/sensor/latest` | 최신 센서값(EC·pH·temp·ts) 1건 반환 |
| `GET` | `/api/sensor/history` | 센서 히스토리 조회 (차트용) |
| `GET` | `/api/settings/target` | 저장된 목표값(EC·pH) 조회 |
| `POST` | `/api/settings/target` | 목표값(EC·pH) 저장 |
| `WS` | `/ws` | WebSocket — 센서 갱신 시 실시간 broadcast |

**예상 형식 (참고용, 변경 가능)**

```jsonc
// GET /api/sensor/latest
{ "ec": 1.85, "ph": 6.2, "temp": 23.4, "ts": 1719123456 }

// GET / POST /api/settings/target
{ "ec": 2.0, "ph": 6.5 }

// WS /ws → 클라이언트로 push 되는 메시지
{ "ec": 1.85, "ph": 6.2, "temp": 23.4 }
```

---

## 엔드포인트 ↔ 소스 매핑

| 엔드포인트 | 소스 파일 | 상태 |
| --- | --- | --- |
| `POST /api/control/dose` | [routers/control.py](../routers/control.py) → [dosing.py](../dosing.py) | ✅ 구현 |
| `GET /` (정적) | [main.py](../main.py) | ✅ 구현 |
| `/api/sensor/*` | (미생성) `routers/sensor.py` | ⏳ 예정 |
| `/api/settings/*` | (미생성) `routers/settings.py` | ⏳ 예정 |
| `/ws` | (미생성) `websocket_manager.py` | ⏳ 예정 |
