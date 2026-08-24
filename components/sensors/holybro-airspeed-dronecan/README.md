# Holybro Airspeed — 에어스피드 센서

Holybro의 차압식(differential pressure) 에어스피드 센서. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [어댑터/에일러론 서보 캐빈](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료)(피토관 모듈 장착부)에 설치되며, PNP 옵션에는 미포함이라 별도 구매한 부품.

> ⚠️ **실제 보유 개체는 I2C 방식** (2026-08-08 사용자 확인). FC의 **I2C 포트**에 연결하고 피토관을 물려 **정상 작동 확인 완료**.
>
> 본 문서는 당초 Holybro의 DroneCAN 버전 스펙으로 작성되었으나, 실물은 I2C 버전이다. 아래 "실제 구성" 절이 유효하며, DroneCAN 관련 서술(폴더명 포함)은 정정 대기 상태다.

## ⚠️ 영점 오프셋 어긋남 — 미해결 (2026-08-24)

정지 상태에서 **에어스피드가 음수**로 나온다. 고정익 전환 판단이 이 값에 걸려 있으므로
**해결 전에는 전환 비행을 하지 말 것.**

```
정지 시 차압        -0.069 hPa = -6.9 Pa
SENS_DPRES_OFF      -4.518 Pa      ← 보정값이 실제보다 작다
남는 오차           약 -2.4 Pa
정지 시 airspeed    -2.5 m/s 수준
```

### 배관은 정상이다

한때 **피토관 역결선**으로 판정했으나 **틀렸다.** 실물 테스트로 확인:

> 입으로 불면 **+10~20 m/s 로 정상 상승**한다. 음수는 가만히 있을 때만 나온다.

부호가 양수로 오르므로 동압/정압 배관 방향은 맞다. **튜브를 바꾸면 정상인 배선을 망가뜨린다.**

> 로그의 "차압이 항상 음수" 라는 관측은 역결선과 영점 오차 양쪽에 들어맞는다.
> 둘을 가르는 것은 **불었을 때 부호가 어느 쪽으로 움직이는가** 뿐이며, 실물로만 알 수 있다.

### 추정 원인

- **온도 드리프트** — MS5525DSO 계열은 온도 민감. 비행 중 센서 온도가 **43~50°C** 였는데
  영점 보정을 다른 온도에서 했다면 어긋난다
- **보정 시 바람** — 보정 시점 차압이 0이 아니었다면 잘못된 값이 저장된다

### 조치

1. 피토관을 막거나 완전 무풍 실내
2. FC 전원 켜고 **5분 이상 대기** — 온도 안정화
3. QGC → Vehicle Setup → Sensors → **Airspeed** 보정
4. 검증: 정지 시 0 근처 / 불면 양수

관련: [비행 #85 분석](../../../flights/2026-08-22-log85-first-hover.md#1--에어스피드-음수--영점-오프셋-드리프트)


## 실제 구성 (SHADE 기체 — 확정)

| 항목 | 내용 |
|---|---|
| 통신 방식 | **I2C** |
| FC 연결 포트 | **[Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md) I2C 포트 (4핀 JST-GH)** |
| 상태 | ✅ 피토관 연결 후 **정상 작동 확인** |
| 수량 | 1개 (이중화 미적용) |

FC I2C 포트 핀맵 (Holybro 공식):

| 핀 | 신호 |
|---|---|
| 1 (red) | VCC +5V |
| 2 | I2C2_SCL (+3.3V) |
| 3 | I2C2_SDA (+3.3V) |
| 4 | GND |

### 이 구성이 배선에 주는 영향

- **CAN 버스가 단순해진다** — CAN1에는 [PM08-CAN](../../power/holybro-pm08-can/README.md) 하나만 물린다. CAN 버스 공유·종단저항·노드 ID 충돌을 따질 필요가 없다.
- 원문 PDF 배선도의 날개 커넥터 1~4번 핀(`Airspeed− / SDA / SCL / 5V`)이 **I2C용 그대로 유효**하다. DroneCAN이었다면 재배정이 필요했으나 그럴 필요가 없어졌다.
- PM08의 POWER2를 에어스피드 급전에 쓰려던 방안은 불필요 — POWER2는 유휴로 둔다.

### 🔶 이 절의 확인 필요

- **정확한 센서 모델명 미확인** — I2C 에어스피드는 통상 MS4525DO 또는 DLVR(I2C 버전). 기판 실크 확인 후 문서 제목·폴더명(`holybro-airspeed-dronecan`) 정정 필요
- 센서 물리 설치 위치(날개 어댑터 캐빈 vs 동체) 및 피토관 튜브 경로 기록 필요

---

## (참고) DroneCAN 버전 스펙

아래는 Holybro DroneCAN Airspeed(DLVR 기반) 기준으로 작성된 내용으로, **보유 개체와 다르다.** 향후 이중화용으로 CAN 버전을 추가 구매할 경우를 대비해 남겨둔다.

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
