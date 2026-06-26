# 배포 가이드 — NFT 배양액 모니터

## 사전 준비

### Mac 쪽
- SSH 클라이언트 (기본 내장)
- rsync (기본 내장)

### Raspberry Pi 쪽
- SSH 활성화
- Python 3 설치 확인

```bash
# RPi에서 SSH 활성화
sudo systemctl enable ssh
sudo systemctl start ssh

# Python 3 확인
python3 --version
```

---

## RPi IP / 호스트명 확인

```bash
# RPi에서
hostname -I        # IP 주소 출력
hostname           # 호스트명 출력 (보통 raspberrypi)
```

같은 Wi-Fi라면 `raspberrypi.local`로 접근 가능.
안 되면 IP 주소를 직접 사용한다.

---

## Phase 1 — 정적 파일만 배포 (백엔드 없음)

### 1. 파일 전송

```bash
# Mac에서 실행 (프로젝트 루트에서)
rsync -avz static/ pi@raspberrypi.local:/home/pi/nft-monitor/static/
```

### 2. RPi에서 서버 실행

```bash
ssh pi@raspberrypi.local
cd /home/pi/nft-monitor
python3 -m http.server 8080 --directory static
```

### 3. 브라우저 접속

- RPi 본체: `http://localhost:8080`
- 같은 Wi-Fi의 다른 기기: `http://raspberrypi.local:8080`

---

## Phase 2 — 백엔드 포함 전체 배포

### 1. RPi에 가상환경 및 의존성 설치 (최초 1회)

```bash
ssh pi@raspberrypi.local
mkdir -p /home/pi/nft-monitor
cd /home/pi/nft-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 파일 전송 (deploy.sh)

프로젝트 루트의 `deploy.sh` 실행:

```bash
./deploy.sh
```

`deploy.sh` 내용:

```bash
#!/bin/bash
set -e

HOST="pi@raspberrypi.local"
REMOTE_DIR="/home/pi/nft-monitor"

rsync -avz \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='venv' \
  --exclude='data/' \
  ./ "$HOST:$REMOTE_DIR/"

ssh "$HOST" "
  cd $REMOTE_DIR &&
  source venv/bin/activate &&
  pip install -r requirements.txt -q &&
  sudo systemctl restart nft-monitor
"

echo "배포 완료"
```

```bash
chmod +x deploy.sh
```

### 3. FastAPI 서버 실행 (systemd 등록 전 테스트)

```bash
ssh pi@raspberrypi.local
cd /home/pi/nft-monitor
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

접속: `http://raspberrypi.local:8000`

---

## systemd 서비스 등록 (상시 자동 실행)

### 서비스 파일 생성

```bash
sudo nano /etc/systemd/system/nft-monitor.service
```

```ini
[Unit]
Description=NFT Monitor FastAPI Server
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/nft-monitor
ExecStart=/home/pi/nft-monitor/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 서비스 등록 및 시작

```bash
sudo systemctl daemon-reload
sudo systemctl enable nft-monitor
sudo systemctl start nft-monitor

# 상태 확인
sudo systemctl status nft-monitor

# 로그 확인
journalctl -u nft-monitor -f
```

---

## Chromium 키오스크 모드 자동 실행

RPi 부팅 시 브라우저가 자동으로 대시보드를 전체화면으로 열도록 설정.

```bash
mkdir -p /home/pi/.config/autostart
nano /home/pi/.config/autostart/nft-kiosk.desktop
```

```ini
[Desktop Entry]
Type=Application
Name=NFT Kiosk
Exec=chromium-browser --noerrdialogs --disable-infobars --kiosk http://localhost:8000
```

---

## 트러블슈팅

| 증상 | 확인 사항 |
|---|---|
| `raspberrypi.local` 접속 불가 | IP 주소 직접 사용 |
| SSH 연결 거부 | `sudo systemctl start ssh` |
| 포트 8000/8080 접속 불가 | 방화벽 확인 `sudo ufw status` |
| 시리얼 포트 권한 오류 | `sudo usermod -a -G dialout pi` 후 재로그인 |
| systemd 서비스 시작 실패 | `journalctl -u nft-monitor -n 50` 로그 확인 |
