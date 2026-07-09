/*
  pH / EC 센서 캘리브레이션 도구 (DFRobot Gravity 아날로그 시리즈 기준)

  용도: 표준액(pH 4.01/6.86/9.18, EC 1413uS/12.88mS 등)에 프로브를 담그고
        시리얼 모니터로 명령을 보내면, 전압-측정값 관계를 계산해서
        메인 스케치(rawToPH/rawToEC)에 바로 붙여넣을 수식을 출력해줍니다.

  배선: EC 센서 -> A1,  pH 센서 -> A0  (unoV1.ino와 동일 배선 — 핀 바꾸지 말 것)

  ------------------------------------------------------------------
  시리얼 모니터 사용법 (9600bps, 개행문자 "Newline"로 설정)
  ------------------------------------------------------------------
  READ            : 두 핀의 현재 평균 전압을 한 번 출력 (안정화 확인용)

  [pH 보정]
  PH:6.86         : 지금 pH 6.86 완충액에 담긴 상태 -> 전압 캡처 & 저장
  PH:4.01         : pH 4.01 완충액 상태에서 캡처 & 저장
  PH:9.18         : pH 9.18 완충액 상태에서 캡처 & 저장 (선택, 3점 보정용)
  PHCALC          : 저장된 점들로 회귀식(slope, offset) 계산 및 출력

  [EC 보정] - <표준액_uS/cm>:<측정순간_용액온도_C>
  EC:1413:24.5    : 1413 uS/cm 표준액, 측정 당시 온도 24.5도에서 캡처
  EC:12880:24.8   : 12.88 mS/cm(=12880uS/cm) 표준액에서 캡처 (있으면 추가, 없어도 됨)
  ECCALC          : 저장된 점으로 계산 및 출력
                    - 1점만 있으면: 0uS/cm=0V 가정한 원점통과 직선(1점 보정)
                    - 2점 이상이면: 최소자승 회귀식 (25도 보정 공식 포함)

  RESET           : 저장된 보정 포인트 모두 초기화
  ------------------------------------------------------------------
*/

#include <Arduino.h>

const uint8_t PIN_EC_SENSOR = A1;
const uint8_t PIN_PH_SENSOR = A0;

const int   AVG_SAMPLES = 30;   // 평균낼 샘플 수
const int   AVG_DELAY_MS = 10;  // 샘플 간 간격

const int MAX_POINTS = 5;

float phVoltage[MAX_POINTS];
float phTarget[MAX_POINTS];
int   phCount = 0;

float ecVoltage[MAX_POINTS];
float ecTargetAtTemp[MAX_POINTS];  // 측정 당시 온도에서의 실제 EC(보정 전)
int   ecCount = 0;

String cmdBuffer = "";

void setup() {
  Serial.begin(9600);
  printHelp();
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      cmdBuffer.trim();
      if (cmdBuffer.length() > 0) processCommand(cmdBuffer);
      cmdBuffer = "";
    } else if (c != '\r') {
      cmdBuffer += c;
    }
  }
}

// ---------------------------------------------------------------
void printHelp() {
  Serial.println(F("=== pH/EC 캘리브레이션 도구 ==="));
  Serial.println(F("READ / PH:<value> / PHCALC / EC:<value>:<tempC> / ECCALC / RESET"));
}

float readAvgVoltage(uint8_t pin) {
  long sum = 0;
  for (int i = 0; i < AVG_SAMPLES; i++) {
    sum += analogRead(pin);
    delay(AVG_DELAY_MS);
  }
  float avgRaw = (float)sum / AVG_SAMPLES;
  return avgRaw * (5.0 / 1023.0);
}

void processCommand(String cmd) {
  cmd.toUpperCase();

  if (cmd == "READ") {
    float vEC = readAvgVoltage(PIN_EC_SENSOR);
    float vPH = readAvgVoltage(PIN_PH_SENSOR);
    Serial.print(F("EC_V=")); Serial.print(vEC, 4);
    Serial.print(F("  PH_V=")); Serial.println(vPH, 4);

  } else if (cmd == "RESET") {
    phCount = 0;
    ecCount = 0;
    Serial.println(F("모든 보정 포인트 초기화됨"));

  } else if (cmd.startsWith("PH:")) {
    float target = cmd.substring(3).toFloat();
    float v = readAvgVoltage(PIN_PH_SENSOR);
    if (phCount < MAX_POINTS) {
      phVoltage[phCount] = v;
      phTarget[phCount] = target;
      phCount++;
      Serial.print(F("[PH 저장] target=")); Serial.print(target, 2);
      Serial.print(F("  voltage=")); Serial.print(v, 4);
      Serial.print(F("  (현재 "));  Serial.print(phCount); Serial.println(F("개 포인트)"));
    } else {
      Serial.println(F("PH 포인트 저장 공간이 가득 참. RESET 후 다시 시도"));
    }

  } else if (cmd == "PHCALC") {
    calcAndPrintPH();

  } else if (cmd.startsWith("EC:")) {
    // 형식: EC:<standardValue>:<tempC>
    String rest = cmd.substring(3);
    int sep = rest.indexOf(':');
    if (sep < 0) {
      Serial.println(F("형식 오류. 예: EC:1413:24.5"));
      return;
    }
    float standardValue = rest.substring(0, sep).toFloat();
    float tempC = rest.substring(sep + 1).toFloat();
    float v = readAvgVoltage(PIN_EC_SENSOR);

    // 표준액 라벨값은 25도 기준. 측정 당시 온도가 25도가 아니면
    // 그 온도에서 실제로 존재하는 전도도로 역보정해서 저장.
    float actualAtTemp = standardValue * (1.0 + 0.02 * (tempC - 25.0));

    if (ecCount < MAX_POINTS) {
      ecVoltage[ecCount] = v;
      ecTargetAtTemp[ecCount] = actualAtTemp;
      ecCount++;
      Serial.print(F("[EC 저장] standard="));   Serial.print(standardValue, 1);
      Serial.print(F(" tempC="));               Serial.print(tempC, 1);
      Serial.print(F(" -> actualAtTemp="));      Serial.print(actualAtTemp, 1);
      Serial.print(F("  voltage="));             Serial.print(v, 4);
      Serial.print(F("  (현재 "));  Serial.print(ecCount); Serial.println(F("개 포인트)"));
    } else {
      Serial.println(F("EC 포인트 저장 공간이 가득 참. RESET 후 다시 시도"));
    }

  } else if (cmd == "ECCALC") {
    calcAndPrintEC();

  } else {
    Serial.println(F("알 수 없는 명령. HELP 참고"));
    printHelp();
  }
}

// 최소자승 선형회귀: y = slope*x + offset
void linearFit(float *x, float *y, int n, float &slope, float &offset) {
  if (n < 2) { slope = 0; offset = (n == 1) ? y[0] : 0; return; }
  float sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
  for (int i = 0; i < n; i++) {
    sumX += x[i];
    sumY += y[i];
    sumXY += x[i] * y[i];
    sumX2 += x[i] * x[i];
  }
  float denom = n * sumX2 - sumX * sumX;
  if (denom == 0) { slope = 0; offset = sumY / n; return; }
  slope = (n * sumXY - sumX * sumY) / denom;
  offset = (sumY - slope * sumX) / n;
}

void calcAndPrintPH() {
  if (phCount < 2) {
    Serial.println(F("PH 포인트가 2개 미만 — 최소 2점(예: 6.86, 4.01) 필요"));
    return;
  }
  float slope, offset;
  linearFit(phVoltage, phTarget, phCount, slope, offset);

  Serial.println(F("=== PH 보정 결과 ==="));
  Serial.print(F("slope="));  Serial.print(slope, 5);
  Serial.print(F("  offset=")); Serial.println(offset, 5);
  Serial.println(F("메인 스케치 rawToPH()에 아래처럼 반영:"));
  Serial.println(F("  float voltage = raw * (5.0/1023.0);"));
  Serial.print(F("  return "));
  Serial.print(slope, 5);
  Serial.print(F(" * voltage + "));
  Serial.print(offset, 5);
  Serial.println(F(";"));
}

void calcAndPrintEC() {
  if (ecCount < 1) {
    Serial.println(F("EC 포인트가 없음 — 최소 1점(예: 1413) 필요"));
    return;
  }

  float slope, offset;

  if (ecCount == 1) {
    // 표준액 1개만 있는 경우: 0uS/cm(증류수)에서 전압도 0V라고 가정하고
    // 원점을 지나는 직선으로 처리 (EC 프로브 회로는 대개 0에서 0V 출력이라 이 가정이 합리적).
    // 단, 이 경우 1413 근처 농도에서는 정확하지만 그보다 훨씬 높은 농도(예: 3000uS/cm 이상)로
    // 갈수록 오차가 커질 수 있음 — 나중에 표준액 추가되면 재보정 권장.
    slope = ecTargetAtTemp[0] / ecVoltage[0];
    offset = 0;
    Serial.println(F("=== EC 보정 결과 (1점 보정 — 원점 통과 가정) ==="));
  } else {
    linearFit(ecVoltage, ecTargetAtTemp, ecCount, slope, offset);
    Serial.println(F("=== EC 보정 결과 (측정 당시 온도 기준) ==="));
  }

  Serial.print(F("slope="));  Serial.print(slope, 5);
  Serial.print(F("  offset=")); Serial.println(offset, 5);
  Serial.println(F("메인 스케치 rawToEC()에 아래처럼 반영 (단위: uS/cm):"));
  Serial.println(F("  float voltage = raw * (5.0/1023.0);"));
  Serial.print(F("  float ecAtTemp = "));
  Serial.print(slope, 5);
  Serial.print(F(" * voltage + "));
  Serial.print(offset, 5);
  Serial.println(F(";"));
  Serial.println(F("  // 25도 기준으로 정규화하려면 실시간 온도(tempC) 필요:"));
  Serial.println(F("  float ec25 = ecAtTemp / (1.0 + 0.02 * (tempC - 25.0));"));
  Serial.println(F("  return ec25; // mS/cm 단위 쓰려면 /1000.0"));
}
