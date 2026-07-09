# NFT 배양액 탱크 모니터링 시스템 — Claude Code 작업 컨텍스트

> 이 파일은 Claude Code에서 작업을 이어받기 위한 인수인계 문서입니다.

---

## 프로젝트 개요

상추 수경재배 NFT 시스템의 배양액 탱크 모니터링 및 제어 시스템.
아두이노에서 EC/pH를 측정 → Raspberry Pi 4B에서 수신 → 웹 대시보드로 표시 → 도징 제어.

> 온도 센서는 미장착 상태입니다. 시리얼 포맷·센서 카드 등 온도 관련 항목은 전부 제외합니다.

---

## 현재 상태

- [x] 기술 스택 확정
- [x] 시스템 아키텍처 확정
- [x] 화면 레이아웃 확정
- [x] requirements.txt 생성 완료
- [x] Phase 1 (프론트엔드 목업) 완료
- [x] Phase 2 일부 완료 — 목표값 저장/조회 API, 도징 계산 API(dose/ph, dose/ec)
- [x] 아두이노 스케치(`unoCode/unoV1.ino`) 작성 완료 — EC/pH JSON 전송 + STIR 교반 제어
- [ ] **다음 작업**: Phase 2 잔여(WebSocket, 센서 히스토리 API, 백엔드 더미 데이터 생성기) 또는 Phase 3(RPi `serial_reader.py`)

> 상세 체크리스트는 아래 "개발 단계(Phase)" 참고.

---

## 기술 스택

| 영역        | 기술                    |
|-----------|-----------------------|
| 백엔드 프레임워크 | FastAPI + uvicorn     |
| 시리얼 통신    | pyserial-asyncio      |
| 데이터베이스    | SQLite + aiosqlite    |
| 프론트엔드     | Vanilla JS (프레임워크 없음) |
| 차트        | Chart.js (CDN)        |
| 브라우저      | Chromium 키오스크 모드      |
| 하드웨어      | Raspberry Pi 4B       |
| 디스플레이     | 8인치 정전식 터치 디스플레이      |

### requirements.txt (확정)
```
aiosqlite==0.22.1
annotated-types==0.7.0
anyio==4.14.1
click==8.4.2
fastapi==0.138.0
h11==0.16.0
idna==3.18
pydantic==2.13.4
pydantic_core==2.46.4
pyserial==3.5
pyserial-asyncio==0.6
starlette==1.3.1
typing_extensions==4.15.0
uvicorn==0.49.0
```

---

## 시스템 아키텍처

```
[Arduino Uno — unoCode/unoV1.ino]
    │  UART (Serial 9600bps, JSON 포맷, 1초 주기)
    │  ← 명령: STIR:<seconds> / STOP (텍스트, RPi가 프로그램적으로 전송)
    ▼
[Raspberry Pi 4B - FastAPI 서버 단일 프로세스]
    ├── Serial Reader (asyncio background task) — 미구현 (Phase 3)
    │     ├── JSON 파싱 및 유효성 검증
    │     ├── SQLite 저장
    │     └── WebSocket broadcast
    ├── REST API
    │     ├── GET  /api/sensor/latest       현재 센서값 (예정)
    │     ├── GET  /api/sensor/history      히스토리 (예정)
    │     ├── GET  /api/settings/target     목표값 조회 (구현됨)
    │     ├── POST /api/settings/target     목표값 저장 (구현됨)
    │     ├── POST /api/control/dose/ph     1단계 B액 도징량 계산 (구현됨, Mock)
    │     └── POST /api/control/dose/ec     2단계 A액 도징량 계산 (구현됨, Mock)
    └── Static 서빙
          └── GET / → index.html

[Chromium 키오스크 모드]
    └── localhost:8000 → 웹 대시보드
          └── 같은 WiFi 내 외부 기기에서도 접근 가능
```

### 시리얼 데이터 포맷 (아두이노 → RPi)
```json
{"ec": 1.85, "ph": 6.2, "stir": 0}
```
- `temp` 필드 없음 — 온도 센서 미장착.
- `ts` 필드 없음 — Uno에 RTC가 없어 실제 시각을 못 만듦. RPi가 수신 시각을 기록.
- `stir`: 이 샘플이 측정된 순간 교반 모터가 돌고 있었는지(0/1). 1인 샘플은 전기적 노이즈로
  흔들릴 수 있으므로 정상치 판정에서 제외 권장.

### 명령 포맷 (RPi → 아두이노)
```
STIR:30    30초간 교반 모터 구동 후 자동 정지
STOP       즉시 정지
```
사람이 로그로 보는 방향이 아니라 RPi가 프로그램적으로 생성/전송하는 명령이라 JSON으로
통일하지 않고 텍스트로 둠 (Uno의 파싱 비용/SRAM 절약). 응답은 `ACK:STIR_START` / `ACK:STIR_STOP`.

---

## 화면 설계

### 전체 레이아웃
탭 2개 구조 (단일 페이지, 스크롤 없음, 8인치 기준)

```
┌─────────────────────────────┐
│  NFT 배양액 모니터    ● 연결 │  ← 헤더
├──────────┬──────────────────┤
│  모니터  │  설정            │  ← 탭
├──────────┴──────────────────┤
│  탭 내용                    │
└─────────────────────────────┘
```

### [모니터 탭] - 기본 탭
```
┌─────────────────────────────┐
│  EC              pH         │
│  1.85            6.2        │  ← 현재값 (WebSocket 실시간)
│  목표 1.6        목표 6.6   │  ← 목표값 표시만
│  [정상]          [주의]     │  ← 상태 뱃지
├─────────────────────────────┤
│  EC  현재 1.85 / 목표 1.6   │
│  → 초과 +0.25 mS/cm         │  ← 차이값 계산 표시
│  pH  현재 6.2  / 목표 6.6   │
│  → 부족 -0.4                │
├─────────────────────────────┤
│        [ 도징 시작 ]         │  ← 도징 버튼 (현재 Mock)
└─────────────────────────────┘
```

### [설정 탭]
```
┌─────────────────────────────┐
│  목표값 설정                 │
│                             │
│  EC 목표   [  1.6  ] mS/cm  │  ← 터치 입력 (숫자 키패드)
│  pH 목표   [  6.6  ]        │  ← 터치 입력 (숫자 키패드)
│                             │
│          [ 저장 ]           │
└─────────────────────────────┘
```

### 상태 뱃지 색상
| 상태 | 색상 | 조건       |
|----|----|----------|
| 정상 | 초록 | 정상 범위 내  |
| 주의 | 노랑 | 범위 경계 근접 |
| 위험 | 빨강 | 범위 초과    |

### 센서 정상 범위 (상추 기준)
| 센서 | 정상 범위           | 비고         |
|----|-----------------|------------|
| EC | 1.2 ~ 2.0 mS/cm | 최적 1.5~1.8 |
| pH | 5.5 ~ 6.8       | 최적 6.0~6.2. 상한을 6.5→6.8로 상향 — 표준 혼합액 실측 pH 6.58([설계서 v2](docs/설계서%20v2.md) 실험 3)에 여유(±0.2)를 두기 위함 |

### 기본 목표값
[설계서 v2](docs/설계서%20v2.md) 실험 3(A+B 표준 1배 혼합, 4L 기준)의 실측값을 그대로 사용:
**EC 1.634 mS/cm, pH 6.58** (`config.py DEFAULT_TARGET_EC/PH`). 표준 레시피대로 도징했을 때 도달하는 지점을
목표로 잡아, 그 지점에서는 도징이 자연히 SKIP(데드밴드 이내)되는 것을 기대할 수 있다.

---

## 파일 구조

`✅` = 구현됨, `⏳` = 미구현(계획)

```
nft-tank-measure-display/
├── CLAUDE.md                  # 이 파일                                    ✅
├── main.py                    # FastAPI 앱 진입점, lifespan                ✅
├── serial_reader.py           # 시리얼 수신 asyncio 태스크                  ⏳ Phase 3
├── database.py                # SQLite 초기화·목표값 저장/조회             ✅ (sensor_logs 테이블은 ⏳)
├── websocket_manager.py       # WebSocket 연결 관리, broadcast             ⏳ Phase 2 잔여
├── models.py                  # Pydantic 데이터 모델                       ✅
├── dosing.py                  # 도징 알고리즘 본체(연립방정식 풀이)         ✅
├── config.py                  # 탱크 용량·도징 계수·범위 임계값 등 설정      ✅
├── routers/
│   ├── sensor.py              # /api/sensor 라우터                         ⏳ Phase 2 잔여
│   ├── settings.py            # /api/settings 라우터 (목표값 저장/조회)     ✅
│   └── control.py             # /api/control/dose/ph, /dose/ec (계산 전용) ✅
├── static/
│   ├── index.html             # 탭 레이아웃(모니터/설정)                   ✅
│   ├── app.js                 # 상태 갱신, WS 클라이언트, 더미 fallback     ✅
│   ├── keypad.js               # 터치 숫자 키패드                          ✅
│   └── style.css
├── unoCode/
│   └── unoV1.ino               # 아두이노: EC/pH JSON 전송 + STIR 교반 제어 ✅
├── data/
│   └── sensor.db               # SQLite DB (자동 생성)
├── requirements.txt
├── deploy.sh / run-server.command  # 배포·로컬 실행 스크립트
└── docs/                       # 실험 설계서·API 명세·도징 알고리즘 설계 문서
```

---

## 개발 단계 (Phase)

### Phase 1 — 프론트엔드 목업 ✅ 완료
- [x] `index.html` 탭 레이아웃 구현 (모니터 / 설정)
- [x] 더미 데이터로 현재값 카드 표시 (`static/app.js injectDummy()`, 백엔드 미연결 시 폴백)
- [x] 터치 숫자 키패드 입력 구현 (목표값 설정) (`static/keypad.js`)
- [x] 차이값 계산 및 표시 로직 (프론트에서 계산)
- [x] 도징 버튼 UI — 순차 2단계(① pH/B액 → 재측정 → ② EC/A액) 로 구현, 실제 계산 API 호출
- [x] 8인치 터치 디스플레이 기준 CSS 최적화
- [x] 온도 관련 코드 정리 완료 (`index.html` 온도 카드 삭제, `app.js`의 `state.sensor.temp`/`RANGE.temp` 제거, `style.css` 센서 카드 그리드 3열→2열)

### Phase 2 — 백엔드 기본 (일부 완료)
- [x] FastAPI 서버 기동 (`main.py`)
- [x] 목표값 저장/조회 API (`routers/settings.py` + `database.py`)
- [x] 도징 계산 API — `/api/control/dose/ph`, `/api/control/dose/ec` (`routers/control.py`, `dosing.py`) — 센서값은 아직 요청 body/더미값 기준, DB 연동 전
- [x] 프론트와 연결 (설정 저장, 도징 버튼)
- [ ] 더미 데이터 생성기 (시리얼 대체, 백엔드 측) — 현재는 프론트(`app.js`)에서만 더미 생성
- [ ] WebSocket broadcast 구현 (`websocket_manager.py`, `/ws` 라우트) — 프론트는 이미 연결 시도 중, 백엔드 미구현이라 항상 폴백
- [ ] SQLite 센서 히스토리 저장/조회 API (`sensor_logs` 테이블, `routers/sensor.py`)

### Phase 3 — 시리얼 연동
- [x] 아두이노 스케치 작성 완료 (`unoCode/unoV1.ino`) — EC/pH JSON 1초 전송, STIR/STOP 텍스트 명령 수신
- [ ] RPi `serial_reader.py` — 시리얼 수신·JSON 파싱·유효성 검증·SQLite 저장·WS broadcast
- [ ] 더미 데이터 → 실제 센서 데이터로 교체 (프론트 폴백 제거는 `serial_reader`+`/ws` 완료 후)

### Phase 4 — 제어 시스템 연동
- [ ] 도징 계산 결과로 실제 펌프(A액/B액) 구동 — 현재 `routers/control.py`에 TODO만 존재
- [ ] 교반 모터 제어 API 추가 (RPi → 아두이노 `STIR:<sec>`/`STOP` 전송) — 아두이노 쪽은 이미 준비됨, RPi API/펌프 연동만 남음
- [ ] 키오스크 모드 자동 실행 설정

---

## 배포 방식

- **개발:** Mac (IntelliJ Ultimate)
- **배포:** rsync + SSH → RPi
- **실행:** systemd 서비스로 등록

```bash
# deploy.sh
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='venv' \
  ./ pi@raspberrypi.local:/home/pi/nft-monitor/

ssh pi@raspberrypi.local "cd /home/pi/nft-monitor && \
  source venv/bin/activate && \
  pip install -r requirements.txt -q && \
  sudo systemctl restart nft-monitor"
```

---

## 미결 사항

| 항목 | 내용 |
|---|---|
| 시리얼 포트 | `/dev/ttyUSB0` or `/dev/ttyACM0` 확인 필요 |
| 도징 알고리즘 계수 | [설계서 v2](docs/설계서%20v2.md) 실험 완료 전까지 placeholder 값 사용 중 (`config.py DEFAULT_COEFFS`) |
| RPi `serial_reader.py` | 아직 미구현 (Phase 3) — `unoCode/unoV1.ino`의 JSON(`ec`,`ph`,`stir`) 포맷에 맞춰 파싱해야 함 |

### 결정된 사항 (참고)
| 항목 | 결정 내용 |
|---|---|
| 아두이노 전송 주기 | 1초 (실험 중 값 변화를 빠르게 모니터링하기 위해 30초 대신 1초 유지) |
| 타임스탬프 | 아두이노는 `ts` 미전송 (RTC 없음) → RPi가 수신 시각을 기준으로 기록 |
| 온도 센서 | 미장착 확정 — `temp` 필드/온도 보상 로직 전부 제외 |
| RPi → 아두이노 명령 포맷 | 텍스트(`STIR:30`, `STOP`) — 사람이 보는 로그가 아니므로 JSON 통일 안 함 |
| 기본 목표값 | EC 1.634 / pH 6.58 — 설계서 v2 실험 3(표준 1배 혼합) 실측값 그대로 사용 |
| pH 정상범위 상한 | 6.5 → 6.8로 상향 — 표준 혼합액 실측 pH 6.58에 마진(±0.2) 확보 |