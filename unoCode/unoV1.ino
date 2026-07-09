/*
  배양액 탱크 제어 - 기능 테스트용 스케치 (v2, JSON 포맷)

  구현 범위 (현재 요청 2가지):
  1) EC/pH 센서값을 상시로 시리얼 전송 (온도 센서 미장착 — temp 없음)
  2) 라즈베리파이가 STIR 명령을 보내면, 지정 시간만 교반 모터를 돌리고 자동 정지

  통신 구조: 대시보드 --(HTTP API)--> 라즈베리파이 --(USB 시리얼)--> 아두이노 우노
  - 시리얼 1개(9600bps)를 센서 출력 + 명령 수신 겸용으로 사용
  - 포맷은 CLAUDE.md / API-명세서.md 의 JSON 스펙에 맞춤 (ArduinoJson 없이 직접 조립/파싱)

  Arduino -> RPi (1초 주기, 개행 종료)
      {"ec":1.85,"ph":6.21,"stir":0}
      temp 필드는 없음 — 온도 센서 미장착. (CLAUDE.md 원안은 temp 포함을 가정하나,
      실제 하드웨어에 온도 센서가 없어 제외. RPi/대시보드 쪽도 temp 없는 포맷에 맞춰야 함)
      ts(타임스탬프)는 넣지 않음 — Uno에 RTC가 없어 millis() 기준 값만 가능하므로,
      실제 시각은 RPi가 수신 시각을 기준으로 기록한다(CLAUDE.md 미결 사항 참고).
      모터 구동 중(stir:1) 읽힌 EC/PH는 전기적 노이즈로 흔들릴 수 있으니,
      대시보드/로깅 쪽에서 stir:1 샘플은 참고용으로만 쓰고 정상치 판정에서 제외 권장.

  RPi -> Arduino (명령, 개행 종료, 텍스트)
      STIR:30   30초간 교반 시작
      STOP      즉시 정지

  주의: rawToEC(), rawToPH() 는 ph_ec_calibration_tool.ino 실험 결과를 반영한 1차 캘리브레이션입니다.
        - EC: 1413uS/cm 1점 보정(원점통과 가정) + 온도 보정식 포함
        - PH: 4.01 / 6.86 버퍼 2점 보정
        EC 온도 보정은 온도 센서가 없어 ASSUMED_TEMP_C(25.0) 고정값을 사용 — 사실상 no-op이며,
        실제 수온이 25도에서 크게 벗어나면 EC 값이 ±2%/°C 수준으로 오차가 날 수 있음(주석 참고).
        EC는 1점 보정이라 1413 근처 농도에서는 정확하지만 목표 EC 범위를 벗어난 고농도에서는
        오차가 커질 수 있음. 표준액 추가 확보되면 재보정 권장(ph_ec_calibration_tool.ino 재사용).
*/

#include <Arduino.h>
#include <string.h>
#include <stdlib.h>

// ----- 핀 정의 (실제 배선에 맞게 조정) -----
const uint8_t PIN_EC_SENSOR   = A1;
const uint8_t PIN_PH_SENSOR   = A0;
const uint8_t PIN_MOTOR       = 9;    // PWM 가능 핀. 모터 드라이버(EN/IN)에 연결

// 온도 센서 미장착 — EC 온도 보정용 고정 가정값(°C). 실측 수온이 아니므로
// 25도에서 크게 벗어나면 EC 오차가 커짐(±2%/°C 수준). 필요 시 실측값으로 교체.
const float ASSUMED_TEMP_C = 25.0;

// ----- 타이밍 설정 -----
const unsigned long SENSOR_INTERVAL_MS = 1000;  // 센서 전송 주기 (실험 모니터링용으로 1초 유지)
unsigned long lastSensorSend = 0;

// ----- 교반 상태 -----
bool motorRunning = false;
unsigned long motorStopAt = 0;

// ----- 시리얼 명령 버퍼 (String 대신 고정 크기 char 버퍼 — SRAM 단편화/무한 성장 방지) -----
const uint8_t CMD_BUFFER_SIZE = 64;
char cmdBuffer[CMD_BUFFER_SIZE];
uint8_t cmdLen = 0;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_MOTOR, OUTPUT);
  digitalWrite(PIN_MOTOR, LOW);
}

void loop() {
  readAndSendSensors();     // 1) 상시 센서 전송 (non-blocking)
  handleIncomingCommands(); // 2) 명령 수신 파싱
  handleMotorTimeout();     //    지정 시간 경과 시 자동 정지
}

// ---------------------------------------------------------------
// 1) EC/pH 상시 전송 (JSON)
// ---------------------------------------------------------------
void readAndSendSensors() {
  unsigned long now = millis();
  if (now - lastSensorSend < SENSOR_INTERVAL_MS) return;
  lastSensorSend = now;

  int rawEC = analogRead(PIN_EC_SENSOR);
  int rawPH = analogRead(PIN_PH_SENSOR);

  float ec = rawToEC(rawEC);
  float ph = rawToPH(rawPH);

  Serial.print(F("{\"ec\":"));
  Serial.print(ec, 2);
  Serial.print(F(",\"ph\":"));
  Serial.print(ph, 2);
  Serial.print(F(",\"stir\":"));
  Serial.print(motorRunning ? 1 : 0);
  Serial.println(F("}"));
}

// ---------------------------------------------------------------
// 2) 라즈베리파이 명령 수신 (개행 기준 파싱, non-blocking)
// ---------------------------------------------------------------
void handleIncomingCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      cmdBuffer[cmdLen] = '\0';
      processCommand(cmdBuffer);
      cmdLen = 0;
    } else if (c != '\r') {
      if (cmdLen < CMD_BUFFER_SIZE - 1) {
        cmdBuffer[cmdLen++] = c;
      } else {
        // 비정상적으로 긴 라인(깨진 데이터 등) — 버리고 리셋
        cmdLen = 0;
      }
    }
  }
}

// 텍스트 명령 파싱: "STIR:<seconds>" 또는 "STOP"
void processCommand(const char *cmd) {
  if (strncmp(cmd, "STIR:", 5) == 0) {
    long sec = strtol(cmd + 5, nullptr, 10);
    if (sec <= 0) sec = 30;   // 파싱 실패/누락 시 기본값
    startMotor((int)sec);
  } else if (strcmp(cmd, "STOP") == 0) {
    stopMotor();
  }
}

void startMotor(int seconds) {
  motorRunning = true;
  motorStopAt = millis() + (unsigned long)seconds * 1000UL;
  digitalWrite(PIN_MOTOR, HIGH);   // 속도 제어가 필요하면 analogWrite(PIN_MOTOR, speed)로 교체
  Serial.println(F("ACK:STIR_START"));
}

void stopMotor() {
  motorRunning = false;
  digitalWrite(PIN_MOTOR, LOW);
  Serial.println(F("ACK:STIR_STOP"));
}

void handleMotorTimeout() {
  // (long) 캐스트 뺄셈으로 비교 — millis() 오버플로(약 49일)에도 안전
  if (motorRunning && (long)(millis() - motorStopAt) >= 0) {
    stopMotor();
  }
}

// ---------------------------------------------------------------
// 변환 함수 — ph_ec_calibration_tool.ino 결과 반영 (1차 캘리브레이션)
//   EC: 1413uS/cm 1점 보정 (원점통과 가정) + 25도 정규화
//   PH: 4.01/6.86 2점 보정
//   주의: EC는 1점 보정이라 1413 근처 농도에서는 정확하지만,
//         목표 EC 범위를 벗어난 고농도에서는 오차 커질 수 있음.
//         표준액 추가 확보되면 재보정 권장 (ph_ec_calibration_tool.ino 재사용).
// ---------------------------------------------------------------
float rawToEC(int raw) {
  float voltage = raw * (5.0 / 1023.0);
  float ecAtTemp = 4212.23632 * voltage + 0.00000;
  // ASSUMED_TEMP_C가 25.0 고정이라 분모는 항상 1.0(no-op) — 온도 센서 추가 시 실측값으로 교체
  float ec25 = ecAtTemp / (1.0 + 0.02 * (ASSUMED_TEMP_C - 25.0));
  return ec25 / 1000.0;  // uS/cm -> mS/cm (config.py/CLAUDE.md 단위와 일치)
}

float rawToPH(int raw) {
  float voltage = raw * (5.0 / 1023.0);
  return 30.85159 * voltage + (-56.10985);
}
