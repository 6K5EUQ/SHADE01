# Holybro DroneCAN Airspeed — 에어스피드 센서

Holybro의 차압식(differential pressure) 에어스피드 센서, DroneCAN 프로토콜 사용. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [어댑터/에일러론 서보 캐빈](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료)(피토관 모듈 장착부)에 설치되며, PNP 옵션에는 미포함이라 별도 구매한 부품.

- 제조사: Holybro
- 제품명: DroneCAN Airspeed Sensor (DLVR 기반)
- 공식 문서: https://docs.holybro.com/peripherals/dlvr-airspeed-dronecan/overview
- 용도: 대기속도(Airspeed) 측정 — 고정익/VTOL 모드 전환 시 스톨 방지, 항법 보정에 사용
- 센서 칩: DLVR_L10D 디지털 압력 센서

## 사양

| 항목 | 값 |
|---|---|
| 측정 방식 | 차압식(Differential Pressure) |
| 압력 범위 | 2500 Pa |
| 측정 가능 속도 | 0–226.8 km/h |
| 동작 전압 | 4.75–5.25V |
| 소비 전류 | 약 100mA |
| 동작 온도 | −20 ~ 85℃ |
| 통신 프로토콜 | DroneCAN (CAN 인터페이스) |

## 커넥터 / 핀아웃 (CAN 포트, 4핀)

| 핀 | 색상 | 신호 |
|---|---|---|
| 1 | 적색 | VCC (+5V 입력) |
| 2 | — | CAN_H (+3.3V) |
| 3 | — | CAN_L (+3.3V) |
| 4 | — | GND |

## Pixhawk 6C Mini 연결

| 센서 핀 | Pixhawk CAN 포트 핀 |
|---|---|
| 1 (VCC/+5V) | 1 (VCC, +5V) |
| CAN_H | 2 (CANH, +3.3V) |
| CAN_L | 3 (CANL, +3.3V) |
| GND | 4 (GND) |

[Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)의 CAN1 또는 CAN2 포트에 연결. I2C 방식이 아닌 **DroneCAN(CAN 버스)** 프로토콜을 사용하므로, 기존 I2C 에어스피드 센서(MS4525DO/MS5525DSO)와는 배선/설정 방식이 다름.

## 🔶 확인 필요 (수량)

- [Striver Mini VTOL 문서](../../../airframes/striver-mini-vtol/README.md#구조캐빈별-사양)의 "어댑터/에일러론 서보 캐빈" 항목에는 원문 PDF 기준 **"좌우 듀얼 에어스피드 센서로 이중화 가능(옵션)"**이라는 설명이 있음. 반면 사용자 확인으로는 **본 센서가 1개만 보유** 중. 이중화 옵션을 사용하지 않고 단일 센서 구성으로 진행하는 것으로 이해하고 본 문서는 1개 기준으로 작성함. 추후 이중화가 필요하면 동일 제품 추가 구매 검토.

## 보유 수량 (SHADE 기체)

- **1개** (사용자 확인 기준, 이중화 미적용)
- 연결 대상: [Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md) CAN1/CAN2 포트
