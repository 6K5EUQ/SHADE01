# RadioMaster RP4TD-M — ExpressLRS 2.4GHz Mini True Diversity Receiver

RadioMaster의 ExpressLRS(오픈소스 장거리 RC 링크) 초소형 수신기. RC 송신기(조종기)의 무선 신호를 받아 FC(비행제어) 또는 ESC로 전달하는 역할.

- 제조사: RadioMaster
- 제품명: RP4TD-M ExpressLRS 2.4GHz Mini True Diversity Receiver
- 판매처: radiomasterrc.com, 단가 $19.99 (2026-08-02 확인)
- 리전 옵션: FCC / LBT (전파 규격 지역 옵션, 구매 시 선택)
- 용도: [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md) 등 ExpressLRS 기반 RC 시스템의 수신기

## ✅ 현재 운용 상태 (2026-08-21 기준)

> **링크 모드가 CRSF → MAVLink over ELRS로 전환됐다.** 아래 CRSF 절차/파라미터 절은 이력 참고용.

| 항목 | 값 |
|---|---|
| 수신기 펌웨어 | ExpressLRS **3.5.6** (ee188b) ISM2G4 |
| Serial Protocol | **MAVLink** (WebUI에서 CRSF → MAVLink 변경) |
| 바인딩 | ✅ 완료 — bind phrase 방식, Persistent 저장. **Bound UID `45,5,9,157,112,199`** |
| TX (Boxer 내장) | Unified 4.1.0 **커스텀 빌드**, Link Mode = **MAVLink** — [배터리 텔레메트리 패치](../../transmitters/radiomaster-boxer/elrs-battery-telemetry-fix.md) |
| 백팩 | 1.5.9, Telemetry = wifi (노트북 QGC용 AP) |
| FC 포트 | TELEM1 (UART7), MAVLink 인스턴스, 460800 baud |

RC 조종과 텔레메트리가 MAVLink 단일 링크로 흐르며, `RC_CRSF_*` 파라미터는 더 이상 사용하지 않는다.

> **본 수신기는 패치 대상이 아니다.** MAVLink→CRSF 변환은 TX에서만 일어나므로(`tx_main.cpp:1544` 단독 호출,
> `rx_main.cpp`에 해당 코드 없음), 배터리 텔레메트리 문제는 TX 펌웨어만 고쳐 해결했다. RX는 공식 3.5.6 유지.

전체 현황: [SHADE01 개요](../../../README.md)

## FC 연결 방법 (Pixhawk 6C Mini)

본 수신기의 버스 인터페이스는 **CRSF (Crossfire Protocol)** — TBS Crossfire가 원조이며 ExpressLRS가 채택한 양방향 시리얼 디지털 프로토콜. PPM(아날로그 펄스폭)이나 SBUS(단방향 시리얼)와는 물리/전기적으로 다른 방식이라, **RC IN / PPM·SBUS 포트에는 꽂을 수 없고 UART 포트(Telem1 또는 Telem2)에 연결**해야 한다.

### 배선 (Telem1 — ✅ 확정, 2026-08-19 결선)

**PX4는 특정 포트를 강제하지 않는다** — 공식 문서는 "any spare UART port can be used"라고만 하고, 오히려 예시로 `TELEM1`을 든다([PX4 CRSF Telemetry](https://docs.px4.io/main/en/telemetry/crsf_telemetry.html)). 즉 Telem1·Telem2 어느 쪽이든 기능상 동일하다.

**본 기체는 Telem1을 채택**했다. 당초 계획은 Telem2였으나, [Raspberry Pi 5 컴패니언](../../companion/raspberry-pi-5/README.md)이 Telem2(UART5)를 MAVLink 브리지로 점유해 작동 중이었다. **Pi를 옮기는 대신 수신기를 Telem1(UART7)로 배치**해 충돌을 해소했다 — Pi 링크가 이미 검증·가동 중이었으므로 건드리지 않는 쪽이 안전했다.

> 이로써 T900 Pro 등 지상국 텔레메트리 무선모듈용으로 비워두려던 Telem1이 수신기에 배정됐다. 무선모듈 추가 시 남은 UART(GPS2/UART8 등) 재배치를 검토해야 한다.

| RP4TD-M 패드 | → | Pixhawk 6C Mini Telem1 핀 | 신호 |
|---|---|---|---|
| VCC (5V) | → | 1 (red) | VCC +5V |
| GND | → | 6 (black) | GND |
| **TX** | → | **3 (black)** | UART7_RX (in) |
| **RX** | → | **2 (black)** | UART7_TX (out) |

- ⚠️ **TX/RX는 반드시 교차(cross)** — 수신기 TX → FC RX, 수신기 RX → FC TX. 동봉된 CRSF 케이블이 이미 교차되어 있는지 반드시 육안 확인 후 연결할 것.
- 신호 반전(inverter) 회로 불필요 — CRSF는 비반전 UART라 직결 가능.
- Telem 포트 커넥터는 **JST-GH 1.25mm 6핀**. 동봉 CRSF 케이블의 FC측 커넥터 규격이 다르면 별도 제작/구매 필요.
- 수신기 동작 전압은 5.0V이며 Telem 포트 1번 핀이 5V를 공급하므로 별도 BEC 불필요. (Telem1+GPS1 합산 1.5A 제한 — 본 수신기 소비전류는 미미)

### 펌웨어별 설정

> ✅ **SHADE 기체는 PX4 확정** (2026-08-04). 아래 PX4 절차를 따른다. ArduPilot 항목은 참고용.

**PX4 (본 기체 채택 — ✅ 커스텀 펌웨어 빌드·플래시 완료, 2026-08-11)**

기본 배포 펌웨어에는 CRSF 드라이버(`crsf_rc`)가 **포함되어 있지 않다.** QGroundControl로 펌웨어를 설치하는 것만으로는 이 수신기가 동작하지 않으며, 소스를 받아 직접 빌드해야 한다.

> ✅ **완료** — PX4 **v1.17.0** + `crsf_rc` 빌드 후 FC에 플래시했다. `RC_CRSF_PRT_CFG` 파라미터가 QGC에 나타나는 것으로 드라이버 정상 탑재를 확인했다. 상세: [FC 문서 — 커스텀 펌웨어](../../fc/holybro-pixhawk-6c-mini/README.md#커스텀-펌웨어-px4-v1170--crsf_rc)

```bash
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
make holybro_6c-mini_default boardconfig
#   drivers          → rc_input   비활성화(해제)
#   drivers > RC     → crsf_rc    활성화
make holybro_6c-mini_default upload
```

| 파라미터 | 값 | 의미 |
|---|---|---|
| `RC_CRSF_PRT_CFG` | **101 (Telem1)** | CRSF를 쓸 UART 지정 |
| `RC_CRSF_TEL_EN` | Enabled | 텔레메트리 활성화 |

- ✅ **Telem2 충돌 해소** — 수신기를 Telem1에 두어 Pi 5의 Telem2 MAVLink 매핑(당시 `MAV_1_CONFIG=102`, 2026-09-02 에 `0` 으로 내림)을 **건드리지 않는다.** 두 링크가 공존한다.
- ⚠️ `RC_CRSF_PRT_CFG = 0`(미할당)이면 **FC가 해당 UART를 열지 않아 스틱 입력이 전혀 들어오지 않는다.** 배선을 마쳤는데 RC가 안 잡히면 이 값부터 확인할 것.
- ⚠️ **`COM_RC_IN_MODE` 확인 필수** — 이 값이 `1`이면 *Joystick only* 모드라 **RC 입력을 통째로 무시**한다. 스틱을 움직여도 제어면이 반응하지 않는 직접적 원인이 된다. QGC가 이 파라미터를 `1065353216`처럼 표시하는 경우가 있는데, 이는 float `1.0`의 비트 패턴을 정수로 잘못 읽은 것으로 **실제 값은 `1`**이다.
- 빌드 타깃명(`holybro_6c-mini_default`)은 PX4 버전에 따라 다를 수 있으므로 `make list_config_targets`로 확인할 것.

**ArduPilot (참고 — 미채택)**
| 파라미터 | 값 | 의미 |
|---|---|---|
| `SERIAL1_PROTOCOL` | 23 | RCIN (CRSF). Telem1 = SERIAL1 |
| `RSSI_TYPE` | 3 | CRSF 링크 품질을 RSSI로 사용 |
| `RC_OPTIONS` | bit 13 설정 | ELRS용 보레이트 420K (기본 416K에서 변경) |

- 보레이트는 펌웨어가 자동 관리하므로 `SERIAL1_BAUD` 수동 설정 불필요.
- 해당 UART는 **DMA 지원**이 필요 (6C Mini는 STM32H743이라 문제 없음).
- ⚠️ MAVLink로 FC를 재부팅하면 수신기 전원을 껐다 켜기 전까지 통신이 끊김 — 알려진 동작.

> 대안: 커스텀 빌드를 피하고 싶다면 `SERIALx_PROTOCOL`=2 / baud 115 / `RSSI_TYPE`=5로 두고 **MAVLink 모드**로 쓰는 방법도 있으나, RC 링크로서의 지연/신뢰성은 CRSF 네이티브가 우수하다.

### 🔶 남은 확인 필요

- ~~PX4 vs ArduPilot 미확정~~ → **해소(2026-08-04): PX4 확정.** 위 커스텀 펌웨어 빌드가 필수 작업으로 확정됨.
- ~~동봉 CRSF 케이블의 커넥터 규격 확인~~ → **해소(2026-08-08)**: 실물 확인 결과 **양 끝 커넥터 없는 맨선(주석 도금), 4가닥 트위스트 — 적/초/흰/검**. 아래 [배선 작업](#-배선-작업-납땜-필요) 참조
- ~~**수신기 패드 실크 인쇄 판독 필요**~~ → **실질 해소(2026-08-19)**: 실크 판독 대신 **초↔흰 교환 재결선으로 정상 동작 확인**. 다만 어느 색이 TX인지 문서상 확정 표기는 여전히 없다.
- ~~Telem2 포트 충돌~~ → **해소(2026-08-19)**: 수신기를 **Telem1(UART7)**에 배치. Pi 5는 Telem2 유지. 두 링크 공존.
- **ELRS 바인딩 — Binding Phrase 방식 사용** — 송신기 웹UI(`ExpressLRS TX` AP → `http://10.0.0.1`)와 수신기 웹UI에 **동일한 phrase**를 입력해 바인딩했다. ⚠️ Binding Phrase가 설정된 수신기는 **수동 바인딩 모드로 진입하지 않는다**(ELRS 공식 문서). LED가 `Green heartbeat`(Web update mode)에 머무르면 phrase 불일치를 의심할 것.
- **Model Match 불일치 주의** — LED가 `Triple blink then pause`면 송수신기의 model-match 설정이 어긋난 상태다. 조종기 모델 설정에서 `Receiver 01[Bnd]` 등 번호를 맞춰야 고정색으로 바뀐다.

## ⚠️ 배선 작업 (납땜 필요)

무개조 연결 불가. **양쪽 다 가공이 필요**하다.

```
RP4TD-M 패드 4개 ──[미세 납땜]── 동봉 CRSF wire ──[압착]── JST-GH 1.25mm 6핀 → FC Telem1
   (커넥터 없음)                  (맨선 4가닥)              (별도 구매 필요)
```

| 구간 | 작업 | 난이도 |
|---|---|---|
| 수신기 쪽 | 기판 패드에 직접 납땜 | **높음** — 기판 18.10×16.00mm, 패드 간격 약 1.5~2mm |
| FC 쪽 | JST-GH 6핀 커넥터 압착 | 보통 |

**동봉품**: CRSF wire 1개(맨선 4가닥), 열수축 튜브 3개 — 납땜 후 절연을 전제한 구성이다.

### 결선

| 케이블 색 | 신호 | → Telem1 핀 |
|---|---|---|
| 적 | VCC 5V | 1 |
| 초 또는 흰 | 수신기 TX | **3** (UART7_RX) |
| 흰 또는 초 | 수신기 RX | **2** (UART7_TX) |
| 검 | GND | 6 |
| — | (CTS/RTS 미사용) | 4, 5 비움 |

- ⚠️ **TX/RX 교차 필수**. 초/흰 중 어느 것이 TX인지는 패드 실크로 확인.
- ✅ **뒤바꿔 연결해도 하드웨어 손상 없음** (통신만 안 됨). CRSF·FC 모두 3.3V 로직이라 전압 충돌도 없다. 동작하지 않으면 초↔흰만 서로 바꿔 재시도.
- 📌 **실제 작업 기록 (2026-08-19)**: 초/흰 판독이 확정되지 않아 처음 결선에서 통신이 되지 않았고, **초↔흰을 서로 교환해 재결선한 뒤 정상 동작**했다. 위 "뒤바꿔도 손상 없음"이 실증된 셈이다.

### 납땜 시 주의

- 인두 팁 1mm 이하, 300~330℃. **패드당 2초 이내** — 과열 시 패드가 벗겨지며 복구 불가
- 피복은 2~3mm만 벗기고 미리 납 먹임(pre-tinning) 후 부착 — 길면 인접 패드와 단락
- 작업 후 테스터 도통 모드로 **인접 패드 간 단락 확인**
- 기판 근처에서 케이블을 별도 고정(글루건 등)해 납땜부에 장력이 걸리지 않게 할 것
- 동봉 열수축 튜브로 기판째 절연 마감
- Striver 기체의 RC 시스템(ET10 송신기/수신기)은 [구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list)상 IND(완제품) 옵션에만 포함되며, 보유 기체는 PNP라 RC 수신기가 미포함 상태였음. 본 RP4TD-M을 그 대체품으로 사용하려는 것으로 추정 — ET10과는 별개의 송신기 생태계(ExpressLRS 지원 송신기 필요).
- **조종기(TX)는 [RadioMaster Boxer](../../transmitters/radiomaster-boxer/README.md)로 확인됨.** 단 Boxer는 CC2500/4in1/ExpressLRS 3가지 내장 RF 모듈 버전이 있어, 보유 기체가 **ExpressLRS 버전(FCC ID: 2A337-BOXER-ELRS)**인지 실물 확인 필요 — ExpressLRS 버전이어야 본 수신기와 무개조 페어링 가능.

## 특징 (Features, 원문 요약)

- 미니 사이즈 트루 다이버시티(True Diversity) Gemini 수신기 — 듀얼 2.4GHz 라디오로 신호 민감도, SNR, 안정성 향상
- 클래스 최고 수준의 SNR/RSSI 성능
- 내장 TCXO(온도보상 수정발진기) — 온도 변화에도 고정밀 주파수 유지, 주파수 드리프트 방지
- 최적화된 PCB 설계로 방열 개선
- 업그레이드된 안테나(강성 개선) — 내구성/성능 향상
- 텔레메트리 RF 출력 2×10mW
- 2.4GHz ExpressLRS 내장 송신기/모듈과 전 기종 호환

## 사양 (Specifications)

| 항목 | 값 |
|---|---|
| 타입 | ISM |
| MCU | ESP32 |
| RF 칩 | SX1281 ×2 |
| 안테나 | 65mm 2.4GHz T타입 안테나 ×2 |
| 주파수 대역 | 2.4GHz |
| 최대 갱신률(Refresh Rate) | 500Hz / F1000Hz |
| 텔레메트리 RF 출력 | 최대 2×10mW |
| 동작 전압 | DC 5.0V |
| WiFi 업데이트 | 지원 |
| 무게 | 1.00g (안테나 미포함) / 3.30g (안테나 포함) |
| 크기 | 18.10×16.00mm |
| 펌웨어 버전 | ExpressLRS V3.4.3 사전 설치 |
| FW 타깃 | RadioMaster RP4TD-M 2400 RX |
| 버스 인터페이스 | CRSF |

## 치수 상세

| 항목 | 값 |
|---|---|
| 기판 크기 | 18.10 × 16.00mm |
| 기판 두께 | 2.00mm |
| 전체 높이(안테나 포함) | 79.00mm |
| 안테나 길이 | 65.00mm |

## 패키지 구성 (Package Includes)

| 품목 | 수량 |
|---|---|
| RP4TD-M ExpressLRS True 2.4GHz Diversity Receiver | 1 |
| CRSF wire (CRSF 배선 케이블) | 1 |
| 열수축 튜브(Heat-Shrinkable Tube) | 3 |
| 65mm 2.4GHz T 안테나 (수신기에 사전 장착됨) | 2 |
| User Manual | 1 |

## 사진/자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 페이지 (외형, 가격, 옵션) | [images/01-product-page.png](images/01-product-page.png) | radiomasterrc.com 제품 페이지 캡처 |
| 사양 + TCXO/듀얼 트랜시버/듀얼안테나 설명 | [images/02-specifications-and-tcxo.png](images/02-specifications-and-tcxo.png) | |
| 사양표(재확인) + 무게/크기 실측 + 패키지 구성 | [images/03-specs-weight-size-package.png](images/03-specs-weight-size-package.png) | 저울 실측 사진, 치수 도면 포함 |
| 수신기 WebUI 메인 (펌웨어 3.5.6 확인) | [images/webui-rx-main-fw356.jpg](images/webui-rx-main-fw356.jpg) | 10.0.0.1, 바인딩 작업 중 캡처 (2026-08-19) |
| WebUI — Binding storage 옵션, Bound UID | [images/webui-rx-binding-storage.jpg](images/webui-rx-binding-storage.jpg) | Persistent 선택 |
| WebUI — Serial Protocol 목록 | [images/webui-rx-serial-protocol.jpg](images/webui-rx-serial-protocol.jpg) | 이후 MAVLink로 전환 |
| WebUI — Model Match / Force telemetry off | [images/webui-rx-modelmatch-forcetelem.jpg](images/webui-rx-modelmatch-forcetelem.jpg) | 둘 다 미사용 |
| 제조사 매뉴얼 (RP4TD 시리즈) | [RP4TD-manual.pdf](RP4TD-manual.pdf) | |

> 원본 자료는 radiomasterrc.com 제품 페이지의 풀페이지 스크린샷(PDF, 4페이지)이며, 이 문서에는 제품 정보(사양/패키지 구성)까지만 반영함. 이후 페이지의 리뷰, "You may also like", 사이트 푸터 등은 제외.

## 보유 수량 (SHADE 기체)

- ✅ 1개 보유 — 기체에 장착 완료 (TELEM1 결선, 바인딩 완료, 2026-08-19~21)
- Striver Mini VTOL은 PNP 옵션으로 RC 수신기 미포함 상태였으며, 본 제품이 그 자리를 채움
