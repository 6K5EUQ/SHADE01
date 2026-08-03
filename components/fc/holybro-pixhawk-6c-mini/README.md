# Holybro Pixhawk 6C Mini — 비행제어기(FC)

Holybro의 소형 오토파일럿. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [FC 캐빈](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료)에 장착되는 비행 컨트롤러로, PNP 옵션에는 미포함이라 별도 구매한 부품.

- 제조사: Holybro
- 제품명: Pixhawk 6C Mini
- 공식 문서: https://docs.holybro.com/autopilot/pixhawk-6c-mini/overview
- 용도: PX4/ArduPilot 기반 비행 제어. VTOL/고정익 모드 전환, 모터/서보/센서 통합 제어
- 지원 펌웨어: PX4, ArduPilot (모두 오픈소스)

## 프로세서 / 센서

| 항목 | 값 |
|---|---|
| FMU 프로세서 | STM32H743, Arm Cortex-M7, 480MHz, 2MB 플래시, 1MB SRAM |
| IO 프로세서 | STM32F103, Arm Cortex-M3, 72MHz, 64KB SRAM |
| 가속도계/자이로 | ICM-42688-P, BMI088 (구형 BMI055는 단종) |
| 지자기 센서(Mag) | IST8310 |
| 기압계(Barometer) | MS5611 |

## 치수/무게

| 모델 | 치수 | 무게 |
|---|---|---|
| Model A (Legacy) | 53.3×39×16.2mm | 39.2g |
| Model A (Current) | 54.3×39×17.5mm | 42.4g |
| Model B | 58.3×39×18.15mm | 46.8g |

> 보유 기체에 실제 장착된 모델(A/B)은 실물 확인 필요.

## 전원 규격

| 항목 | 값 |
|---|---|
| 최대 입력 전압 | 6V |
| USB 전원 입력 | 4.75–5.25V |
| 서보 레일 입력 | 0–36V |
| Telem1+GPS1 출력 제한 전류 | 1.5A |
| 기타 전 포트 합산 제한 전류 | 1.5A |

## 커넥터 규격

| 포트군 | 커넥터 규격 |
|---|---|
| 대부분의 포트 | JST-GH, 1.25mm 피치 |
| FMU 디버그 포트 | JST-SH, 1mm 피치 |
| DSM RC 포트 | JST-ZH, 1.5mm 피치 |

## 주요 포트 핀아웃

| 포트 | 핀 수 | 비고 |
|---|---|---|
| Power1 | 6핀 | VDD5V_BRICK1(in), CURRENT1, VOLTAGE1, GND 등 |
| Telem1 / Telem2 | 각 6핀 | UART TX/RX + CTS/RTS + GND |
| GPS1 | 10핀 | [Holybro M10N GPS](../../gps/holybro-m10n/README.md) 연결 포트 |
| GPS2 | 6핀 | 보조 GPS/컴퍼스용 |
| CAN1 / CAN2 | 각 4핀 | CAN*_H, CAN*_L, VCC, GND — [PM08-CAN](../../power/holybro-pm08-can/README.md), [Airspeed(DroneCAN)](../../sensors/holybro-airspeed-dronecan/README.md) 연결 |
| DSM RC | 3핀 | |
| PPM/SBUS(legacy) | 5핀 | |

전체 핀아웃 원문: https://docs.holybro.com/autopilot/pixhawk-6c-mini/pixhawk-6c-mini-ports

## Striver Mini VTOL 장착 시 연결 부품

| 연결 대상 | 포트 |
|---|---|
| [Holybro M10N GPS](../../gps/holybro-m10n/README.md) | GPS1 (10핀) |
| [Holybro DroneCAN Airspeed](../../sensors/holybro-airspeed-dronecan/README.md) | CAN1 또는 CAN2 |
| [Holybro PM08-CAN 파워모듈](../../power/holybro-pm08-can/README.md) | CAN1 (센싱) + Power1/Power2 (전원 입력) |
| VTOL ESC ×4 ([MFE ESC 650](../../esc/mfe-esc-650-50a/README.md)) | MAIN OUT 또는 AUX OUT — 🔶 아래 참조 |
| 크루즈 ESC ([MFE ESC 6100](../../esc/mfe-esc-6s-100a/README.md)) | MAIN OUT 또는 AUX OUT — 🔶 아래 참조 |
| 서보 ×5 ([MFE 3054](../../servos/mfe-s3054/README.md)) | MAIN OUT 또는 AUX OUT — 🔶 아래 참조 |
| RC 수신기 ([RadioMaster RP4TD-M](../../receivers/radiomaster-rp4td-m/README.md)) | 🔶 CRSF 프로토콜 — 지원 UART 포트(Telem 등) 확인 필요, 자세한 내용은 수신기 문서 참조 |

## 🔶 확인 필요

- **ESC/서보의 MAIN OUT vs AUX OUT 배정은 Holybro 공식 문서에 규정되어 있지 않음.** Pixhawk 6C Mini 문서는 MAIN OUT(I/O PWM)과 AUX OUT(FMU PWM)이라는 물리적 포트 그룹만 정의할 뿐, "VTOL 모터는 MAIN, 서보는 AUX"처럼 역할별로 어디에 꽂아야 하는지는 규정하지 않는다. 위 표의 배정은 PX4/ArduPilot VTOL 빌드에서 흔히 쓰이는 일반적 관례를 참고한 것일 뿐 이 기체에 대해 공식 확인된 내용이 아니므로, 실제 배선/파라미터 설정 시 PX4 또는 ArduPilot의 VTOL 에어프레임 설정 문서를 별도로 확인해야 함.
- 원문 PDF 기반 [Striver 배선 다이어그램](../../../airframes/striver-mini-vtol/README.md#4-1-모드-배선-다이어그램-요약-참고용--pixsurvey-v3-fc-기준-pnp에는-fc-미포함)은 **Pixsurvey V3** FC 기준으로 작성되어 있어, 채널 배치(A1~A5, M1~M8)가 그대로 Pixhawk 6C Mini에 적용되지 않음. 위와 마찬가지로 새로 매핑 필요.
- 실제 장착 모델(A 레거시/A 현재/B) 확인 필요 — 치수/무게가 모델별로 다름.

## 보유 수량 (SHADE 기체)

- 1개, PNP 옵션에는 미포함되어 별도 구매
