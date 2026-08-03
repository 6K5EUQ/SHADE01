# Holybro M10N — GPS 모듈

Holybro의 GNSS+컴퍼스 통합 모듈. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [RTK/GPS 캐빈](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료)에 장착되며, PNP 옵션에는 미포함이라 별도 구매한 부품. [Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)의 GPS1 포트에 연결된다.

- 제조사: Holybro
- 제품명: M10N GPS (Standard M10/M9N/M8N GPS 시리즈)
- 공식 문서: https://docs.holybro.com/gps-and-rtk-system/m8n-m9n-m10-gps/standard-m10-m9n-m8n-gps/overview
- 용도: 위치/헤딩 측위 + 지자기 컴퍼스

## 사양

| 항목 | 값 |
|---|---|
| GNSS 칩셋 | u-blox M10 |
| 컴퍼스(지자기 센서) | IST8310 |
| 커넥터 | JST-GH-10P (10핀) |
| 측위 정확도 (CEP) | 2.0m CEP |
| 기본 통신속도 | 115200 baud |
| 출력 프로토콜 | UBX, NMEA |

## 치수

| 버전 | 치수 |
|---|---|
| V1 | ⌀50 × 14.4mm |
| V2 | ⌀51 × 18.5mm |

> 보유 기체에 실제 장착된 버전(V1/V2) 확인 필요.

## LED / SWITCH 기능 (모듈 상단)

모듈 상단에 "GPS FIX" LED와 "SWITCH" 버튼이 있음(사진 참고, V1 기준):

| 표시/버튼 | 기능 |
|---|---|
| **GPS FIX** LED | 3D 포지션 픽스 여부 표시 — 꺼짐: 3D 픽스 안 됨 / 점멸 또는 점등: 3D 픽스 완료. (정확한 LED 색상은 공식 문서에 명시 없음) |
| **SWITCH** | **세이프티 스위치(안전스위치)** — FC가 모터/서보로 출력을 내보내도 되는지 최종적으로 허가하는 물리 버튼. 펌웨어별 동작: |

세이프티 스위치 LED 점멸 패턴:

| 펌웨어 | 점멸 패턴 | 의미 |
|---|---|---|
| ArduPilot | 지속 점멸(constant blinking) | 시스템 초기화 중 |
| ArduPilot | 빠른 간헐 점멸 | 준비 완료 — 세이프티 스위치를 눌러야 모터/서보 출력 활성화 |
| ArduPilot | 점등(solid) | 스위치 눌림, Arm 시 모터/서보 작동 가능 |
| PX4 | 느린 점멸 | 준비 완료 — 스위치를 눌러야 모터 출력 활성화 |
| PX4 | 빠른 간헐 점멸 | 스위치 눌림, Arm 시 모터/서보 작동 가능 |
| PX4 | 점등(solid) | Armed 상태 |

> 세이프티 스위치 기능은 모델/설정에 따라 PX4 및 일부 ArduPilot 설정에서 **기본값이 꺼짐(비활성)**일 수 있음.

## 🔶 확인 필요 (V1/V2 하드웨어 차이)

Holybro 공식 문서에 따르면 **V2 설계에서는 세이프티 스위치와 GPS FIX LED가 제거**되고, FC가 제어하는 RGB UI LED만 남는다고 명시되어 있음. 즉:
- 보유 기체의 실물 사진에 "GPS FIX"/"SWITCH" 라벨이 보인다면 **V1**일 가능성이 높음 (아래 치수표의 V1: ⌀50×14.4mm와 대조해 확인 권장)
- V2라면 이 섹션의 LED/스위치 기능 자체가 해당 모델에는 존재하지 않으므로, 실물의 정확한 버전(V1/V2)을 먼저 확인할 것

## 핀아웃 (JST-GH-10P)

| 핀 | 신호 |
|---|---|
| 1 | VCC (+5V) |
| 2 | RX (in, TTL 3.3V) |
| 3 | TX (out, TTL 3.3V) |
| 4 | SCL1 (TTL 3.3V) |
| 5 | SDA1 (TTL 3.3V) |
| 6 | SAFETY_SWITCH (TTL 3.3V) |
| 7 | SAFETY_SWITCH_LED (TTL 3.3V) |
| 8 | VDD_3V3 (+3.3V) |
| 9 | BUZZER− (open drain 0~5V) |
| 10 | GND |

## Pixhawk 6C Mini GPS1 포트 연결

| GPS 핀 | Pixhawk GPS1 핀 | 신호 |
|---|---|---|
| 1 | 1 | VCC (+5V) |
| 2 (RX) | 2 (TX1 out) | 시리얼 데이터 |
| 3 (TX) | 3 (RX1 in) | 시리얼 데이터 |
| 4 (SCL1) | 4 (SCL1) | I2C |
| 5 (SDA1) | 5 (SDA1) | I2C |
| 6 | 6 (SAFETY_SWITCH) | 안전스위치(옵션) |
| 7 | 7 (SAFETY_SWITCH_LED) | 안전스위치 LED(옵션) |
| 9 | 9 (BUZZER−) | 부저(옵션) |
| 10 | 10 (GND) | GND |

JST-GH-10P 커넥터는 1:1 대응이라 별도 변환 없이 Pixhawk GPS1 포트에 직결 가능.

## 보유 수량 (SHADE 기체)

- 1개, PNP 옵션에는 미포함되어 별도 구매
- 연결 대상: [Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md) GPS1 포트
