# RadioMaster Boxer Radio Controller (M2) — 2.4GHz RC 송신기(조종기)

RadioMaster의 2.4GHz RC 송신기, **M2 개정판**. [RadioMaster RP4TD-M 수신기](../../receivers/radiomaster-rp4td-m/README.md)와 짝을 이루는 조종기로, [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 RC 조종 시스템에 사용된다.

- 제조사: RadioMaster (ShenZhen RadioMaster Co., Ltd)
- 제품명: Boxer Radio Controller (M2)
- 판매처: radiomasterrc.com, $153.99 (2026-08-07 확인, ELRS/FCC 기준)
- 운영체제/펌웨어: EdgeTX (오픈소스)
- 구매 옵션: 버전(ELRS / 4in1 / CC2500) × 리전(FCC / LBT) 조합 선택
- FCC ID: 2A337-BOXER-4IN1 (4-in-1/CC2500 버전), 2A337-BOXER-ELRS (ExpressLRS 내장 버전) — *(구형 A1.9 매뉴얼 기준, M2도 동일 ID 사용 여부는 미확인)*
- 리뷰: 5.00/5.0 (13건, 2026-08-07 확인)

## ⚠️ 내장 ELRS는 커스텀 펌웨어다 (2026-08-22~)

내장 ELRS TX에 **1줄 패치한 4.1.0 커스텀 빌드**가 올라가 있다. [PM08-CAN](../../power/holybro-pm08-can/README.md)
DroneCAN 파워모듈의 배터리 텔레메트리가 조종기 화면에 표시되지 않던 문제를 해결한 것.

- 공식 펌웨어로 덮어쓰면 **배터리 표시가 다시 사라진다**
- 재플래시할 때마다 **바인딩 재설정 필요** (Bound UID `45,5,9,157,112,199`)
- 상세 절차·빌드 방법: [ELRS 배터리 텔레메트리 수정](elrs-battery-telemetry-fix.md)

## 🔶 확인 필요 (버전/리전 선택)

구매 시 아래 2가지를 선택해야 하며, 실제 보유/구매할 조합을 확정해야 나머지 문서(수신기 페어링, 프로토콜 등)가 정확해진다.

| 구분 | 옵션 | 비고 |
|---|---|---|
| 버전(내부 RF 모듈) | **ELRS** / 4in1 / CC2500 | [RP4TD-M 수신기](../../receivers/radiomaster-rp4td-m/README.md)와 페어링하려면 **ELRS 버전 필수** |
| 리전 | FCC / LBT | 국내(한국) 사용 시 통상 FCC 리전 선택, 정확한 규정은 별도 확인 필요 |

- **ELRS 버전**: 고출력(30dBm/1W), 냉각팬 내장, ExpressLRS ISM FW(FCC) 사전 설치. [RP4TD-M 수신기](../../receivers/radiomaster-rp4td-m/README.md)와 바로 페어링 가능 — 이전에 남겨뒀던 "조종기가 ExpressLRS 호환 기종인지" 이슈 해소.
- **4in1 버전**: CC2500, NRF24L01, A7105, CYRF6936 등 다양한 MPM 프로토콜 지원(20dBm).
- **CC2500 버전**: CC2500 프로토콜 전용.
- LBT(유럽) 리전은 프로토콜이 FrSky X/X2 LBT, HoTT LBT, DSMX 등으로 제한되며 ELRS LBT는 출력이 100mW로 제한됨 — **국내 사용 시 FCC 리전이 유리**.

## 사양 (Specification, M2 공식)

| 항목 | 값 |
|---|---|
| 크기 | 235×178×77mm |
| 무게 | 532.5g |
| 주파수 | 2.400GHz–2.480GHz |
| 내장 RF 옵션 | CC2500 멀티프로토콜 / 4-in-1 멀티프로토콜 / ExpressLRS 2.4GHz |
| 지원 프로토콜 | 모듈 종속(module dependent) |
| 전압 범위 | 6.6–8.4V DC |
| 라디오 펌웨어 | EdgeTX(송신기) / Multi-Module(RF모듈) / ELRS |
| 채널 수 | 최대 16채널 (수신기 종속) |
| 배터리 | 7.4V 2셀 리튬폴리머 또는 3.7V 18650 리튬이온 ×2 (배터리 미포함) |
| 디스플레이 | 128×64 흑백 LCD |
| 짐벌 | 고정밀 V4.0 홀 짐벌 기본, AG01 CNC 홀 짐벌 업그레이드 옵션 |
| 모듈 베이 | JR 호환 외장 모듈 베이 |
| 업그레이드 방법 | USB/SD카드 & EdgeTX Companion PC 소프트웨어 |
| 프로세서 | STM32F407VGT6, 1MB Flash, 192KB RAM |
| 내부 ELRS 모듈 갱신률 | 최대 1,000Hz |
| 충전 | QC3.0 고속충전 지원, 최대 2.0A |

> 이전에 정리했던 구형 매뉴얼(A1.9) 스펙과 대조 시 프로세서가 **STM32H743(문서 오류 정정: 실제로는 이전 매뉴얼에 프로세서 명시 없었음) → STM32F407VGT6**로 명확히 확인됨. Flash 용량 1MB, 제어거리 Max 2km는 기존과 동일.

## M2 신규/개선 특징 (Features, 원문 요약)

- ExpressLRS 백팩(Backpack) 내장형 또는 4-in-1/CC2500 MPM RF 모듈 내장형 중 선택 가능
- 강력한 STM32F407VGT6 프로세서(1MB Flash, 192KB RAM)
- EdgeTX 펌웨어 사전 설치
- **내부 ELRS 모듈 최대 1,000Hz 갱신률**
- QC3.0 고속충전 지원(최대 2.0A)
- 컴팩트 디자인, 우수한 인체공학
- **신형 저프로파일(low-profile) SE 래칭 스위치 / SF 모멘터리 스위치**
- RadioMaster 표준화 버튼 레이아웃, 다용도 프로그래머블 6단 스위치
- **조절/탈착 가능한 T자형 안테나**
- 업계 최초 **패브릭 핸들**(휴대성 개선)
- 교체 가능한 인체공학적 그립
- **재설계된 SD카드 슬롯**(사전 로딩된 SD카드 동봉)
- **배터리 커버에 외장 모듈 전원 슬롯** 내장
- RadioMaster 시그니처 **캐리 케이스** 및 **짐벌 프로텍터** 기본 동봉

### ExpressLRS 버전 상세

기존 인기 있던 내부 4-in-1 멀티프로토콜 모듈(CC2500, NRF24L01, A7105, CYRF6936)과 CC2500 전용 버전에 더해, **고출력·팬냉각·기본 100mW(최대 1W)** 내부 2.4GHz ExpressLRS(ELRS) 모듈 버전이 추가됨. 신뢰성 있는 장거리 제어, 최소 지연시간, 고갱신률을 제공하도록 설계.

### FCC/EU LBT 버전별 지원 프로토콜

| 항목 | FCC(표준) | EU LBT |
|---|---|---|
| CC2500 | 모든 CC2500 프로토콜 | FrSky X/X2 LBT, HoTT LBT만 |
| 4in1 | 모든 MPM 프로토콜 | FrSky X/X2 LBT, HoTT LBT, DSMX만 |
| ELRS | ExpressLRS ISM FW 사전 설치 (최대 출력은 하드웨어 종속) | ExpressLRS CE EU domain LBT FW 사전 설치 (출력 100mW 제한) |

## 조작부 레이아웃

### 전면(Front)

| 구성 | 설명 |
|---|---|
| 좌/우 짐벌(Gimbal) | 스로틀/에일러론/엘리베이터/러더 조작, 고정밀 V4.0 홀 짐벌 |
| S1 / S2 다이얼 | 보조 아날로그 채널 |
| SA/SB/SC/SD | 2~3단 토글 스위치 (SA 2단, SB 3단, SC 3단, SD 2단) |
| SE | **저프로파일** 래칭(latching) 스위치 |
| SF | **저프로파일** 모멘터리(momentary) 스위치 |
| T1–T4 | 트림 버튼 |
| SYS / RTN / PAGE×2 / TELE | 메뉴 탐색 버튼 |
| MDL | 모델 설정 진입 버튼 |
| 스크롤 휠 | 메뉴 선택/입력 |
| 전원 버튼 | |
| LCD (128×64 흑백) | 메뉴/텔레메트리 표시 |
| USB-C 데이터 포트 / 충전 포트(QC3.0) | 별도 |
| 헤드폰 잭, 스피커 | 오디오 알림 |
| 안테나 | T자형, **조절/탈착 가능**, 상단 장착 — 전원 켜기 전 반드시 장착 필수(아래 IMPORTANT 참조) |

### 후면(Back)

| 구성 | 설명 |
|---|---|
| Fabric Handle | 패브릭 손잡이 (업계 최초, 휴대성 개선) |
| External JR Bay | 외장 RF 모듈 장착부 (JR 표준 호환) |
| Removable Grips | 착탈식 인체공학 그립 |
| Battery bay / Battery cover | 배터리 베이 — 커버에 **외장 모듈 전원 슬롯** 내장 |
| SD Card | **재설계된** SD카드 슬롯, 사전 로딩된 SD카드 동봉 |
| 냉각팬 | **내장(ExpressLRS 버전에 한함)** |

### 짐벌 조정 (후면 트리머, 각 짐벌 4방향) — 구형 A1.9 매뉴얼 기준, M2 동일 여부 확인 필요

| 조정 항목 | 방향 |
|---|---|
| ① 수평 텐셔너(좌우) | CW: 텐션 증가 / CCW: 텐션 감소 |
| ② 스틱 트래블 리미터 | CW: 트래블 증가 / CCW: 트래블 감소 |
| ③ 수직 텐셔너(상하) | CW: 텐션 증가 / CCW: 텐션 감소 |
| ④ 짐벌 모드 | CW: 셀프센터링 비활성화 / CCW: 셀프센터링 활성화 |

## 치수 (Dimensions, M2 공식)

| 항목 | 값 |
|---|---|
| 높이 | 235mm |
| 폭 | 178mm |
| 안테나 포함 상단 폭 | 76.7mm |

## 전원 / 배터리

USB-C 내장 충전 기능 탑재(QC3.0, 최대 2.0A). **충전 회로는 3.7V 리튬 배터리 전용으로 설계**되어 있어 사용 가능한 배터리가 제한적임 (구형 A1.9 매뉴얼 기준, 내용 변경 없음으로 추정):

| 지원 | 값 |
|---|---|
| 지원 배터리 | 3.7V Li-ion 18650 ×2 또는 3.7V Li-Poly ×2 (2S 7.4V 팩 구성) |
| 공칭 전압 | 3.7V/셀 |
| 완충 전압 | 4.2V/셀 |
| 배터리 공간 | **2S 6200mAh 팩까지 수납 가능**(최대 20시간 사용, M2 신규 사양) |

⚠️ **주의(원문)**: LiFe 배터리팩이나 공칭전압 3.6V/완충 4.10V인 18650 리튬이온 배터리는 **사용 금지** — 잘못된 종류의 배터리를 충전하면 충전회로 손상 또는 화재 위험. Li-ion 사용 시 보호회로 없는(unprotected) 버튼탑(button-top) 셀이어야 함.

배터리는 기본 동봉되지 않음 (Batteries can't be shipped separately — 배터리는 조종기 본품과 함께 주문해야 함, 별도 배송 불가).

## ⚠️ 중요 (IMPORTANT, 구형 A1.9 매뉴얼 원문 — M2도 유효할 것으로 추정)

- **안테나**: 배터리 장착 및 전원을 켜기 **전에** 반드시 동봉된 안테나를 상단에 설치할 것. 안테나 없이 내부 RF 모듈에 전원이 들어간 상태로 조종기를 켜면 **내부 RF 모듈이 손상되며 보증 대상에서 제외**됨.
- **펌웨어**: 출고 시 가장 안정적인 펌웨어가 사전 설치되어 있음. 업데이트 과정에 확신이 없다면 시도하지 말 것 — 잘못된 펌웨어 업데이트는 조종기를 작동 불능 상태로 만들 수 있음.

## 모델/프로토콜 선택 및 바인딩 (구형 A1.9 매뉴얼 원문 — 절차 자체는 M2도 동일할 것으로 추정)

### 멀티프로토콜 모듈 (4in1/CC2500 버전)

- MDL 버튼 길게 눌러 모델 설정 진입 → SETUP 페이지에서 MULTI 선택 → 하위 옵션에서 사용할 프로토콜 선택. 선택한 RF 프로토콜에 따라 해당 RF 모듈이 자동으로 켜짐.
- Bind [BND]: 바인딩(페어링) 프로세스 시작
- Range [RNG]: 출력을 1/30로 낮춰 조종거리 테스트 용이

### ExpressLRS 버전 바인딩 절차

1. 송신기(조종기) **전원 끄기**
2. 수신기 전원을 3회 순환(재인가) — 수신기 LED가 2번 깜빡이면 바인드 모드 진입
3. 송신기 전원 켜기 → **SYS 버튼 길게 누르기** → TOOLS 메뉴에서 **ExpressLRS LUA** 선택 → [Bind]로 스크롤 후 Enter
4. 수신기 LED가 **점등(solid)**되면 바인딩 성공

> ExpressLRS 최적 성능을 위해 Dynamic Power 활성화 및 500Hz 이하 패킷 레이트 사용 권장 — 배터리 수명 연장 및 내부 모듈 발열 최소화.

### 4in1/CC2500 사용자 주의 (ATTENTION, 원문)

사용 중인 수신기가 주파수 튜닝(frequency tuning)을 필요로 할 수 있음 — 비행 전 튜닝 절차 필요: https://www.multi-module.org/using-the-module/frequency-tuning

### mLRS 호환 (M2 신규 안내)

Boxer 라디오는 mLRS(오픈소스 고성능 라디오 시스템, LoRa 기반, 2.4GHz/915·868MHz/433MHz·70cm 대역 지원)와도 호환됨. MAVLink 및 MSP 최적화를 염두에 두고 설계되었으며, 투명 시리얼 링크도 제공. 온라인 mLRS 웹 플래셔로 펌웨어 적용 가능.

## 안전 정보 (Safety Information, 구형 A1.9 매뉴얼 원문)

다음 상황에서는 Boxer 조종 시스템을 작동하지 말 것:
- 비/우박/눈/폭풍 등 악천후 또는 강풍, 전자기 환경
- 시야가 제한된 상황
- 사람, 재산, 고압선, 공공도로, 차량, 동물이 있을 수 있는 구역
- 피곤하거나 몸이 좋지 않거나, 약물/음주 영향 하에 있을 때
- 조종기나 모델이 손상되었거나 정상 작동하지 않는 것으로 보일 때
- 2.4GHz 간섭이 심하거나 2.4GHz 무선 사용이 금지된 구역
- 조종기 배터리 전압이 너무 낮아 사용할 수 없을 때
- 현지 법규가 RC 항공기 사용을 금지하는 구역

모델 조립/유지보수 시 반드시 전원을 끄고 프로펠러를 제거할 것.

## 안테나 이격 거리 (FCC RF 노출 안전 요구사항)

작동 중 신체(손가락/손/손목/발목/발 제외)와 안테나 사이 **최소 20cm 이격** 유지.

## 패키지 구성 (Package Includes, M2 공식)

| 품목 | 수량 |
|---|---|
| BOXER Radio | 1 |
| Signature Carry Case (시그니처 캐리케이스) | 1 |
| T Antenna | 1 |
| USB-C Cable | 1 |
| Gimbal Protector (짐벌 프로텍터) | 1 |
| 1.5mm Allen Key | 1 |
| M4*4 Screws | 2 |
| Low Tension Springs (저텐션 스프링) | 4 |
| 18650 Battery Tray | 1 |
| Stickers | 1 |
| Manual | 1 |

## 추천 액세서리 (Accessories, M2 공식)

| 품목 |
|---|
| 2S 7.4V 6200mAh Lipo Battery |
| AG01 CNC Hall Gimbals |
| AG01 CNC Hall Gimbal Sets New Colors |

## 함께 구매 시 5% 할인 묶음 (Buy Together, 2026-08-07 확인가)

| 품목 | 개별가 |
|---|---|
| Boxer Radio Controller (M2), ELRS/FCC | $153.99 |
| 2S 7.4V 6200mAh Lipo Battery | $29.99 |
| Bandit Micro ExpressLRS 915MHz RF Module | $49.99 |
| RP3 V2 ExpressLRS 2.4GHz Nano Receiver, FCC | ~~$22.99~~ $19.99 |
| **합계(5% 할인 적용)** | ~~$256.96~~ **$241.26** |

> [RP4TD-M](../../receivers/radiomaster-rp4td-m/README.md)이 아닌 **RP3 V2** 수신기가 묶음 상품으로 제안됨 — 참고용, SHADE 기체는 RP4TD-M 기준으로 문서화되어 있음.

## 사진/자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 페이지 (가격, 버전/리전 옵션, 함께구매 묶음) | [images/m2-01-product-price-options-buytogether.png](images/m2-01-product-price-options-buytogether.png) | radiomasterrc.com M2 제품 페이지 캡처 |
| Features 전체 + Specification + EdgeTX/ELRS·4in1 버전 설명 | [images/m2-02-features-specs-edgetx-versions.png](images/m2-02-features-specs-edgetx-versions.png) | FCC/LBT 리전별 지원 프로토콜 표 포함 |
| STM32VGT6 프로세서 + 저프로파일 스위치 + 표준 버튼레이아웃 + V4.0 홀짐벌 + 배터리공간 | [images/m2-03-cpu-switches-gimbals-battery.png](images/m2-03-cpu-switches-gimbals-battery.png) | |
| T자형 탈착 안테나 + 패브릭 핸들 + JR모듈베이 + 냉각팬/전원슬롯 + SD카드/QC3.0 + 캐리케이스 | [images/m2-04-antenna-handle-jrbay-fan-sdcard-case.png](images/m2-04-antenna-handle-jrbay-fan-sdcard-case.png) | |
| 짐벌 프로텍터 + 치수도면 + Radio Overview + 패키지구성 | [images/m2-05-gimbalprotector-dimensions-overview-package.png](images/m2-05-gimbalprotector-dimensions-overview-package.png) | Accessories, Package Includes 표 포함 |
| (구형 A1.9 매뉴얼) 전/후면 조작부 다이어그램 + 짐벌조정 + 스펙표 | [images/01-front-back-diagram-specs.png](images/01-front-back-diagram-specs.png) | Quick Start Guide 원문, 참고용 |
| (구형 A1.9 매뉴얼) 소개/안전정보/배터리·충전/중요사항/모델·프로토콜 선택/바인딩 절차 | [images/02-intro-safety-battery-charging.png](images/02-intro-safety-battery-charging.png) | 매뉴얼 본문 전체(영문), 참고용 |

> 이번 자료는 radiomasterrc.com M2 제품 판매 페이지의 풀페이지 스크린샷(PDF, 7페이지)이며, 이 문서에는 **Package Includes까지(1~5페이지)만 반영**함. 이후 페이지의 Reviews of BOXER Radio, mLRS 소개 영상, EdgeTX Gold Partner, FAQs, Customer Reviews, You may also like, Recently viewed, 사이트 푸터 등은 제외.

## Striver Mini VTOL 연동

| 연결 대상 | 관계 |
|---|---|
| [RadioMaster RP4TD-M 수신기](../../receivers/radiomaster-rp4td-m/README.md) | ELRS 버전 구매 시 페어링 가능. 수신기는 [Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)의 Telem 포트에 CRSF로 연결 |

## 보유 수량 (SHADE 기체)

- 현재 보유/구매 검토 중 (수량 미정, 버전/리전 미확정 — 위 "확인 필요" 참조)
- Striver Mini VTOL은 PNP 옵션으로 RC 송신기 미포함 상태였으며, ET10(완제품 옵션 동봉품) 대신 본 Boxer + RP4TD-M 조합을 사용하는 것으로 추정
