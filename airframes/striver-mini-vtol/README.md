# Striver Mini VTOL (Makeflyeasy)

2100mm급 4+1 VTOL 고정익 무인기. 항공 측량/매핑용.

- 제조사: Makeflyeasy (MFE)
- 모델명: Striver Mini VTOL 4+1 2100mm
- 보유 옵션: **PNP** (Plug aNd Play — 비행 플랫폼 + 파워 시스템 포함, 오토파일럿/통신/RC는 미포함)
- 기술 문서: https://doc.makeflyeasy.com
- 커뮤니티(QQ): makeflyeasy 항측교류군, 293334316

## 개요

Striver Mini VTOL은 7kg급 수직 이착륙 고정익기로, 4개의 VTOL(수직 이착륙) 모터와 1개의 크루즈(추진) 모터로 구성된 "4+1" 구성을 기본으로 하며, "4+2" 모드(듀얼 크루즈 모터)도 지원한다.

역T 꼬리 배치를 기반으로 공력 형상을 최적화했고, 공구 없이 분해/조립 가능한 구조(날개, 수직/수평 꼬리)로 휴대성을 확보했다.

## 기본 제원 (Basic Parameters)

| 항목 | 값 |
|---|---|
| 재질 | EPO, EVA, 탄소섬유, 엔지니어링 플라스틱 등 |
| 날개폭 (Wingspan) | 2100mm |
| 로터 암 길이 | 744mm |
| 동체 높이 (풋패드 제외) | 156mm |
| 동체 길이 | 1200mm |
| 날개 면적 | 59dm² |
| 순항 속도 | 18–21 m/s |
| 최대 탑재 하중 | 1kg |
| 최대 이륙 중량 | < 7.5kg |
| 최대 이륙 고도 | 3000m (해발) |
| 실용 상승 고도 | 4500m (해발) |
| 내풍 등급 | Class 5 (정상 운용 기준) |
| 이착륙 방식 | 수직 이착륙 (VTOL) |
| 탑재실(Load compartment) 크기 | 220×150×110mm |
| 운송박스 크기 | 1.08×0.35×0.48m |
| 분해/조립 방식 | 공구 없는(tool-less) 퀵 분해 |

### 항속 성능

| 시나리오 | 시간/거리 | 조건 |
|---|---|---|
| Range 1 | 82min / 95km | 속도 19m/s, 탑재 600g, 배터리 6S@16000mAh([상세: Fullymax 6S 16000mAh](../../components/batteries/fullymax-6s-16000mah/README.md)), 이륙중량 6.5kg, 고도 500m |
| Range 2 | 112min / 127km | 속도 19m/s, 탑재 600g, 배터리 6S@22000mAh, 이륙중량 7.1kg, 고도 500m |

## 구조/캐빈별 사양

PNP는 기체(플랫폼) + 파워 시스템(모터/ESC/프로펠러/서보)만 포함. 아래 표의 캐빈 중 **FC/GPS/디지털전송 관련 캐빈은 빈 공간(장착 예정 공간)으로만 제공**되며, 실제 모듈은 별도 구매해 장착해야 한다.

| 구역 | 내용 | PNP 상태 |
|---|---|---|
| 헤드 캐빈(기수) | 모터 베이스: PC 합금 플라스틱, 최대 외경 φ60mm 모터 지원. ESC 내장형, 최대 지원 사이즈 71×38mm | 크루즈 모터+ESC 장착 포함 |
| 배터리 캐빈 | 크기 260×130×72mm, 최대 6S@30000mAh 배터리 지원. 배터리 홀더는 PC보드 CNC 가공 | 빈 공간 (배터리 별도 구매) |
| 배전(Distribution) 캐빈 | 사출 성형 엔지니어링 플라스틱. (옵션) 2채널 이중화 비행제어 전원 공급, 서보 전원 1계통, 탑재장비 전원 1계통. 디지털 전송 안테나 홀 예약 | 빈 캐빈 구조물만 포함, 이중화 전원보드는 옵션 별매 |
| 로드(탑재) 캐빈 | 크기 220×150×110mm. Sony A7R 시리즈 카메라 및 5렌즈 틸트 카메라 탑재 가능. 보조 탄소튜브 퀵릴리즈 구조 | 빈 공간 (카메라/짐벌 별도) |
| 비행제어(FC) 캐빈 | 개방형 플랫폼 설계, 오픈소스/상용 FC 호환 | **빈 캐빈** — FC 미포함, 별도 구매 필요 (PDB 사진의 Pixsurvey Cube V3는 PIX/PRO/CAN/IND 옵션 예시) |
| RTK/GPS 캐빈 | 동체 후방 위치, 크기 78×58×37mm. GPS + 컴퍼스 모듈 장착 가능. PPK 안테나 위치는 GPS 캐빈 뒤쪽에 예약됨 | **빈 캐빈** — GPS 모듈 미포함, 별도 구매 필요 |
| 날개 구조 | 메인 탄소튜브 φ12×900mm, 보조 탄소튜브 φ10×530mm. 날개-동체 연결: 커스텀 산업용 9+2 고전류 커넥터(D-sub 9핀 + 전원 2핀 구조) | 포함 (플랫폼) |
| VTOL 로터암 | 20mm 탄소섬유 각튜브 사용, **날개의 메인/보조 탄소튜브에 밀착 결합**(동체 직결이 아님), 통째로 탈부착 가능 | 포함 (플랫폼) |
| 로터암-모터 연결 | 알루미늄 합금 자동 잠금 폴딩 구조 (원터치 접힘 + 회전 잠금) | 포함 (플랫폼) |
| 멀티로터 모터 베이스 | 알루미늄 합금 CNC 가공, 아노다이징 처리. 최대 외경 φ65mm 모터 지원. ESC 캐빈 크기 67×31×12mm | VTOL 모터+ESC 장착 포함 |
| 4+2 모드 날개 모터 마운트 | 임베디드 박스 구조, 최대 외경 φ44mm 모터 지원 (4+2 모드 전용) | 구조물만 포함, 4+2용 모터/ESC는 미포함(기본 파워시스템은 4+1 구성) |
| 어댑터/에일러론 서보 캐빈 | 날개 중앙 위치, ESC/서보 배선 정리용. **배선 단자대**(금속 나사단자 2 = 전력 분배 / 커넥터 블록 S1~S4 = 신호 분배, 상세: [MFE Wing Terminal FDZ Mini](../../components/wiring/mfe-wing-wiring-board/README.md))가 장착되어 날개 커넥터에서 온 전력·신호를 전방/후방 로터와 에일러론 서보로 분배. 에어스피드 센서(피토관) 모듈 장착 가능 | 서보 + **날개 터미널(단자대) 2개 포함** (구성표 "Wing terminal ×2"). 에어스피드 센서는 PNP 미포함(옵션 별매) |
| 수직 꼬리 | 5점 통합 툴리스 퀵릴리즈 구조, 9핀 금도금 커넥터로 기계/전기 동시 분리 | 포함 (플랫폼) |
| 수평 꼬리 | 툴리스 퀵릴리즈(원터치 잠금/분리). 좌우 독립 서보 제어 → 한쪽 고장 시에도 귀환 가능 | 서보 장착 포함 |

> ⚠️ **VTOL 전력 경로 주의**: VTOL ESC/모터는 로터암(날개에 결합)에 있으므로, 동체의 PDB에서 로터암까지 전선이 직결되지 않는다. 반드시 **날개-동체 9+2 커넥터**(위 "날개 구조" 행)를 거쳐 날개 내부 배선을 통해 로터암까지 전력이 전달된다. 날개를 분리하면 이 커넥터에서 전원/신호가 함께 분리된다.

### 전체 전력 경로 (SHADE 기체 Holybro 구성 기준)

```
배터리(6S LiPo)
   │
   ▼
[PM08-CAN]  BAT IN ─션트─► BAT OUT        ← 직렬(in-line), 전압/전류 센싱
   │                          │
   ├─CAN──► FC CAN1           │            (센싱, JST-GH 4핀)
   ├─5.2V─► FC Power1         │            (FC 전원, JST-GH 6핀)
   └─5.2V─► 미사용            │            (6C Mini에 Power2 없음)
                              ▼
                       [PDB 300A] BAT-IN
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        크루즈 ESC      날개-동체 9+2 커넥터(좌/우)
        (기수 캐빈)              │
                                 ▼
                          날개 내부 배선 ──► 로터암 ──► VTOL ESC ×4
```

- **PM08은 배터리와 PDB 사이 직렬**로 들어간다. 배터리를 PDB에 직결하면 전류 측정이 되지 않는다. 상세: [PM08-CAN 전력 경로](../../components/power/holybro-pm08-can/README.md#전력-경로-inline-passthrough)
- 시스템 연속 전류 상한은 PM08의 **200A** (PDB는 300A이나 직렬 경로상 PM08이 병목)
- 커넥터 정격 주의 — XT90은 연속 45A. 주 간선(배터리→PM08→PDB)은 링터미널+8AWG 이상 권장
- ⚠️ **PM08↔FC 연결에 분기 케이블 필요** — PM08은 전원+CAN 통합 6핀(Molex 2.0mm), 6C Mini는 CAN1 4핀 + Power1 6핀(JST-GH 1.25mm)으로 분리 수용. 상세: [PM08-CAN FC 연결](../../components/power/holybro-pm08-can/README.md#fc-연결-pixhawk-6c-mini)
- ⚠️ **FC 전원 이중화 불가** — [Pixhawk 6C Mini](../../components/fc/holybro-pixhawk-6c-mini/README.md)에 Power2 포트가 없어 PM08의 5.2V 2계통 중 1개만 사용. 배전 캐빈의 "2채널 이중화 비행제어 전원 공급" 옵션도 FC 입력이 1개이므로 활용 불가

### 현재 구성 계통도 (2026-08-11 기준 — ✅ 실기 확인)

전원 계통과 FC 주변장치를 합친 현재 실제 구성. 아래 경로는 **통전·통신 모두 실물 검증된 상태**다.

```
[배터리 6S 16000mAh]
        │
        ▼
   [PM08-CAN] ──CAN1──────────┐
        │  (전압/전류 센싱)    │
        │  ──5.2V(Power1)────┐│
        ▼                    ▼▼
   [PDB 300A]           [Pixhawk 6C Mini]
        │                    │
   (모터/ESC 전력)           ├── GPS1 ──────► [Holybro M10N GPS]
                             ├── I2C ───────► [Airspeed 센서] ──► 피토관
                             └── Telem2 ────► [Raspberry Pi 5 "raspb1"]
                              (UART 921600)         │
                                              mav_bridge.py
                                              (UDP :14550)
                                                    │
                                       WiFi → 인터넷 → Tailscale
                                                    │
                                        ┌───────────┴───────────┐
                                        ▼                       ▼
                                  [PC "ku-dgs1"]      [PC "rim" / "rim3"]
                                  QGroundControl        QGroundControl
```

- **FC 무선 연결 성립** — FC를 PC에 USB로 연결하지 않아도 QGC가 붙는다 (raspb2 로 실증, 2026-08-11). 단 로컬 WiFi 직결이 아니라 **인터넷 경유 Tailscale VPN** 링크다. 상세: [Raspberry Pi 5 문서](../../components/companion/raspberry-pi-5/README.md) / 접속 절차: [QGroundControl 연결 절차](../../gcs/qgroundcontrol/README.md)
- **배터리 잔량 QGC 표시 확인** — PM08의 CAN 센싱값이 FC → Pi → QGC까지 전 구간 도달함이 실증됨. PM08 배선과 CAN 설정이 정상임을 뜻한다.
- 🟡 **WiFi + LTE 이중화 (2026-08-31)** — LTE 모뎀 장착으로 WiFi 범위 의존은 해소됐다. 다만 인터넷 + Tailscale 경유라 **장거리 비행 중 신뢰성은 미검증**이다.
- ✅ **Telem 포트 경합 해소(2026-08-19)** — Pi는 **Telem2(UART5)** 유지, [RP4TD-M 수신기](../../components/receivers/radiomaster-rp4td-m/README.md)는 **Telem1(UART7)**에 배치. 서로 다른 UART라 공존한다: [포트 배정](../../components/fc/holybro-pixhawk-6c-mini/README.md#-uart-포트-배정--충돌-해소-2026-08-19)
- ✅ **커스텀 펌웨어 적용(2026-08-11)** — PX4 **v1.17.0** + `crsf_rc` 빌드·플래시 완료. ⚠️ 플래시 98.30%로 빠듯: [상세](../../components/fc/holybro-pixhawk-6c-mini/README.md#커스텀-펌웨어-px4-v1170--crsf_rc)
- ✅ **RC 수신기 연결됨** — Telem1(UART7) CRSF, 바인딩 완료(2026-08-19). 위 계통도에는 미반영이며, 이후 갱신 시 `Telem1 ──► [RP4TD-M 수신기]` 분기를 추가할 것
- ESC ×5 / 서보 ×5 결선 및 채널 배정 상태는 [채널 배정안](../../components/fc/holybro-pixhawk-6c-mini/README.md#채널-배정안-px4-기준) 참조 — 실물 배치가 배정안과 다르므로 별도 확인 필요

## 부위별 사진 자료

원문 PDF에서 추출한 부위별 참고 사진. 각 이미지는 해당 부위의 외부 형상과 내부 구조(캐빈 내부, 배선 등)를 함께 보여준다. FC/GPS 등 PNP 미포함 모듈이 사진에 장착되어 있는 경우 [부품 구성 리스트](#부품-구성-리스트-configuration-list) 기준 미포함 항목임에 유의.

| 부위 | 사진 | 비고 |
|---|---|---|
| 전체 외형 (Overview) | [01-overview.png](images/01-overview.png) | |
| 경량/강성 구조 (내부 프레임) | [02-structure-light-stable.png](images/02-structure-light-stable.png) | 탄소섬유 프레임, 내부 박스 구조 |
| 비행 모드 (4+1 / 4+2) | [03-flight-modes.png](images/03-flight-modes.png) | |
| 퀵 분해 결합 상태 / 포장 | [04-disassembly.png](images/04-disassembly.png) | 운송박스 내부 배치 포함 |
| 동체(Fuselage) 단면 | [05-fuselage-section.png](images/05-fuselage-section.png) | 하부 지지대, 배선 슬롯 내부 사진 |
| 헤드 캐빈(기수) — 외부/내부 | [06-head-cabin.png](images/06-head-cabin.png) | 모터, ESC 그릴, 내장 ESC(내부) |
| 배터리 캐빈 — 내부 | [07-battery-cabin.png](images/07-battery-cabin.png) | 빈 공간(PNP 기준 배터리 별매) |
| 배전 캐빈 — 내부 | [08-distribution-cabin.png](images/08-distribution-cabin.png) | 이중화 전원보드는 옵션(사진 예시) |
| 로드(탑재) 캐빈 — 내부 | [09-load-cabin.png](images/09-load-cabin.png) | 카메라 탑재 예시(PNP 미포함) |
| 비행제어(FC) 캐빈 — 내부 | [10-flight-control-cabin.png](images/10-flight-control-cabin.png) | Pixsurvey Cube V3 장착 예시(PNP 미포함, 빈 캐빈으로 제공) |
| RTK/GPS 캐빈 — 외부/내부 | [11-rtk-gps-cabin.png](images/11-rtk-gps-cabin.png) | GPS 모듈 장착 예시(PNP 미포함, 빈 캐빈으로 제공) |
| 날개 구조 — 내부(탄소튜브) / 커넥터 | [12-wing-structure.png](images/12-wing-structure.png) | 9+2핀 커넥터 클로즈업 포함 |
| VTOL 로터암 — 외부/내부 | [13-vtol-rotor-arm.png](images/13-vtol-rotor-arm.png) | 3M 보강 스티커, 각튜브 결합부 |
| VTOL 모터 마운트 상세 | [14-vtol-motor-mount-detail.png](images/14-vtol-motor-mount-detail.png) | 폴딩 결합부, 모터 베이스, ESC 기판(내부) |
| 4+2 모드 날개 모터 마운트 | [15-wing-motor-mount-4plus2.png](images/15-wing-motor-mount-4plus2.png) | 4+2 모드 전용, 기본 파워시스템 미포함 |
| 어댑터/에일러론 서보 캐빈 — 내부 | [16-adaptor-aileron-servo-cabin.png](images/16-adaptor-aileron-servo-cabin.png) | 배선 단자대, 서보 캐빈 내부 |
| 수직 꼬리 — 외부/커넥터 | [17-vertical-tail.png](images/17-vertical-tail.png) | 9핀 커넥터, 서보 결합부 |
| 수평 꼬리 — 외부/내부(서보) | [18-horizontal-tail.png](images/18-horizontal-tail.png) | 좌우 독립 서보 구조 |
| 유통 스펙시트 (재질/원산지/연령/용도) | [19-configuration-list-legacy.png](images/19-configuration-list-legacy.png) | 파일명과 달리 부품 구성표가 아니라 [유통 스펙시트 정보](#유통-스펙시트-정보) 섹션과 동일 내용 |
| 부품 구성표 (최신, 4+1 전 옵션) | [20-configuration-list-4plus1.png](images/20-configuration-list-4plus1.png) | 실제 보유 사양 기준표 |

## 비행 모드

- **4+1 모드**: VTOL 모터 4개 + 전방 견인(pull) 크루즈 모터 1개 (기본)
- **4+2 모드**: VTOL 모터 4개 + 날개 크루즈 모터 2개

## 4+1 모드 배선 다이어그램 요약 (참고용 — Pixsurvey V3 FC 기준, PNP에는 FC 미포함)

> 이 다이어그램은 PDF 원문 기준 완제품(FC 장착 상태) 참고 자료임. PNP 보유 기체는 FC가 없으므로, 아래 채널 배치는 **직접 FC를 장착할 때 참고할 핀맵**으로만 사용.

| 채널 | 기능 |
|---|---|
| A1 (9) | 우측 전방 모터 |
| A2 (10) | 좌측 후방 모터 |
| A3 (11) | 좌측 전방 모터 |
| A4 (12) | 우측 후방 모터 |
| A5 (13) | 카메라 셔터 케이블 |
| M1 | 좌측 에일러론 |
| M2 | 좌측 수평꼬리 |
| M3 | 좌측 스로틀(전방 견인 모터) |
| M4 | 수직꼬리 |
| M5 | 우측 에일러론 |
| M6 | 우측 수평꼬리 |
| M7 | 낙하산(패러슈트) |
| M8 | 우측 스로틀 |
| PPM/SBUS | 수신기 입력 |

날개 커넥터(좌/우 공용 9핀) 핀맵:

| 핀 | 기능 |
|---|---|
| 1 | Airspeed− |
| 2 | Airspeed SDA |
| 3 | Airspeed SCL |
| 4 | Airspeed 5V |
| 5 | ESC A3(좌) / A1(우) |
| 6 | ESC A2(좌) / A4(우) |
| 7 | Servo M1(좌) / M5(우) |
| 8 | Servo 5V |
| 9 | Servo− |
| A1/A2 | Power+ / Power− (VTOL 모터 전원) |

> ⚠️ 주의(원문 경고): 전원 인가 전 커넥터 배선 순서 1:1 대응을 반드시 확인할 것 (단락 방지).

## 부품 구성 리스트 (Configuration List)

옵션 구분: **KIT**(기체만) / **PNP**(플랫폼+파워시스템) / **PIX**(+PixPilotV3 FC) / **PRO**(+PixPilotV6 Pro FC) / **CAN**(+CAN 버스 FC) / **IND**(완제품, PixSurvey A2 + RC 풀세트)

### 비행 플랫폼 (Flying platform) — 전 옵션 공통

| 부품명 | 사양 | 수량 |
|---|---|---|
| Striver 좌측 날개 | — | 1 |
| Striver 우측 날개 | — | 1 |
| Striver 로터암 | — | 2 |
| Striver 로터 모터 시트 | — | 4 |
| Striver 동체 | — | 1 |
| Striver 동체 부속 | — | 1 |
| Striver 수직꼬리 | — | 1 |
| Striver 수평꼬리 | — | 1 |
| Striver 부속 키트 | — | 1 |
| Striver 폼 포장케이스 | — | 1 |

### 파워 시스템 (Power system) — PNP부터 포함

| 부품명 | 사양 | PNP | PIX | PRO | CAN | IND |
|---|---|---|---|---|---|---|
| 크루즈 모터 | 4120 KV430 ([상세: MFE X4120 KV430](../../components/motors/mfe-x4120-kv430/README.md)) | 1 | 1 | 1 | 1 | 1 |
| 크루즈 ESC | 6S 100A ([상세: MFE ESC 6100](../../components/esc/mfe-esc-6s-100a/README.md)) | 1 | 1 | 1 | 1 | 1 |
| 크루즈 프로펠러 | APC1612 | 1 | 1 | 1 | 1 | 1 |
| VTOL 모터 | M4112 KV460 ([상세: MFE M4112 KV460](../../components/motors/mfe-m4112-kv460/README.md)) | 4 | 4 | 4 | 4 | 4 |
| VTOL ESC | 6S 50A ([상세: MFE ESC 650](../../components/esc/mfe-esc-650-50a/README.md)) | 4 | 4 | 4 | 4 | 4 |
| VTOL 프로펠러 | 1550 (정/역 페어) | 2쌍 | 2쌍 | 2쌍 | 2쌍 | 2쌍 |
| 서보 | S3054 ([상세: MFE 3054](../../components/servos/mfe-s3054/README.md)) | 5 | 5 | 5 | 5 | 5 |
| UBEC | 3S–14S, 5.3V 10A ([상세: MFE UBEC](../../components/power/mfe-ubec-3s14s-10a/README.md)) | 1 | 1 | – | – | – |
| 날개 터미널(커넥터) | ([상세: MFE Wing Terminal FDZ Mini](../../components/wiring/mfe-wing-wiring-board/README.md)) | 2 | 2 | 2 | 2 | 2 |
| 파워 케이블 팩 | — | 1 | 1 | 1 | 1 | 1 |

> 참고: 본 문서 앞부분 PDF 원문(구버전 스펙시트)에는 크루즈 ESC 6S 80A, VTOL 모터 5008 KV380, 프로펠러 1755로 기재되어 있었으나, 최신 4+1 구성표 이미지 기준으로는 크루즈 ESC 6S 100A, VTOL 모터 M4112 KV460, 프로펠러 1550으로 업데이트됨. **실제 구매/보유 사양은 최신 구성표(M4112 KV460 / 6S 100A / 1550) 기준.**

### 오토파일럿 시스템 (Autopilot systems) — PNP는 미포함

| 부품명 | PIX | PRO | CAN | IND |
|---|---|---|---|---|
| PixPilotV3 FC 모듈 | 1 | – | – | – |
| PMU 모듈 | 1 | – | – | – |
| POS2 모듈 | 1 | 1 | – | – |
| I2C 에어스피드 센서 | 1 | 1 | – | – |
| PixPilotV6 Pro FC 모듈 | – | 1 | 1 | – |
| PDB CAN 파워 매니지먼트 | – | 1 | 1 | – |
| POS3 CAN GPS 모듈 | – | – | 1 | – |
| CAN 에어스피드 센서 | – | – | 1 | – |
| PixSurvey A2 오토파일럿 | – | – | – | 1 |
| PixSurvey A2 GPS | – | – | – | 1 |
| PixSurvey A2 센터플레이트 | – | – | – | 1 |
| PixSurvey A2 안전스위치 | – | – | – | 1 |
| PixSurvey A2 파워매니지먼트 | – | – | – | 1 |
| PixSurvey A2 에어스피드 센서 | – | – | – | 1 |

### 디지털 전송 시스템 (Digital transmission) — PNP는 미포함

| 부품명 | PIX | PRO | CAN | IND |
|---|---|---|---|---|
| T900 Pro 디지털 전송 (1쌍) | 1 | 1 | 1 | 1 |
| 접착식(Glue Stick) 안테나 | 2 | 2 | 2 | 2 |
| 신호 연장 케이블 | 1 | 1 | 1 | 1 |
| 17dBi 유리섬유 안테나 | – | – | – | 1 |

### RC 시스템 (Remote control) — IND만 포함

| 부품명 | IND |
|---|---|
| ET10 송신기 | 1 |
| ET10 수신기 & 배선 | 1 |
| ET10 배터리 | 1 |

## 보유 사양 메모 (SHADE 기체 — PNP)

- **포함**: 비행 플랫폼(동체/날개/로터암/수직·수평꼬리/포장케이스) + 파워 시스템(크루즈·VTOL 모터/ESC/프로펠러/서보/UBEC/날개터미널/파워케이블)
- **별도 구매/확정 완료** (Makeflyeasy 순정품 대신 Holybro 생태계로 구성):
  - FC(오토파일럿): [Holybro Pixhawk 6C Mini](../../components/fc/holybro-pixhawk-6c-mini/README.md)
  - GPS: [Holybro M10N](../../components/gps/holybro-m10n/README.md)
  - 에어스피드 센서: [Holybro Airspeed](../../components/sensors/holybro-airspeed-dronecan/README.md) (1개, 이중화 미적용) — ✅ **I2C 방식**, FC I2C 포트 연결 + 피토관 물려 **정상 작동 확인 완료**(2026-08-08). 원문 배선도의 날개 커넥터 1~4번 핀(Airspeed−/SDA/SCL/5V)이 그대로 유효
  - 파워 분배: [Holybro PDB 300A Side Entry](../../components/power/holybro-pdb-300a-side-entry/README.md)
  - 파워 모듈: [Holybro PM08-CAN (14S, 200A)](../../components/power/holybro-pm08-can/README.md)
  - 지상통제(GCS): [QGroundControl](../../gcs/qgroundcontrol/README.md) — 접속 절차·트러블슈팅 통합 문서. QGC는 FC에 직접 붙지 않고 Pi의 UDP 14550 브리지에 접속한다
  - 컴패니언 컴퓨터: [Raspberry Pi 5 "raspb1"](../../components/companion/raspberry-pi-5/README.md) — **이 기체의 유일한 링크 기기.** FC 와 **USB 직결**(`/dev/ttyACM0`), 자체 제작 `mav_bridge.py` 로 MAVLink↔UDP 14550 브리지. 고정 대상 4곳(`ku-dgs1`/`rim`/`rim3`/`gram-labtop`) 동시 수신. ✅ 2026-08-31 실비행 검증 완료(453초). WiFi + LTE 이중화.
  - RC 수신기: [RadioMaster RP4TD-M](../../components/receivers/radiomaster-rp4td-m/README.md) — ✅ **FC Telem1(UART7)에 결선 + ELRS 바인딩 완료**(2026-08-19), `RC_CRSF_PRT_CFG=101`. CRSF 구동을 위해 PX4 v1.17.0 커스텀 펌웨어(`crsf_rc`) 플래시 완료
  - RC 송신기: [RadioMaster Boxer](../../components/transmitters/radiomaster-boxer/README.md) — ELRS 바인딩은 **Binding Phrase 방식**(송신기 웹UI ↔ 수신기 웹UI에 동일 문구 입력)
- **미포함 (별도 구매 필요)**:
  - 디지털 전송(텔레메트리/영상) 시스템 (T900 Pro, 안테나 등)
  - 카메라/짐벌 등 탑재장비
- **메인 배터리**: [Fullymax 22.2V 6S 16000mAh 25C (XT90S)](../../components/batteries/fullymax-6s-16000mah/README.md) — Range 1 항속 시나리오와 동일 사양
- 이 문서의 "구조/캐빈별 사양", "배선 다이어그램" 섹션 중 FC/GPS/디지털전송 관련 부분은 PDF 원문(Makeflyeasy 순정 Pixsurvey V3 기준) 참고 자료이며, 실제 보유 기체는 Holybro Pixhawk 6C Mini로 구성되어 채널 배치가 다를 수 있음 ([Pixhawk 6C Mini 문서](../../components/fc/holybro-pixhawk-6c-mini/README.md)의 "확인 필요" 참조)

## 실측 표면 치수 (SHADE 기체 — 2026-08-22 실측)

기체 표면에 표식(신고번호/제작번호 등)을 부착할 때 쓰는 유효 부착면 실측값. 카탈로그 제원(동체 높이 156mm 등)은 단면 전체 기준이라, 곡률·조종면·개구부를 제외한 실제 부착 가능 면적과 다르다.

| 부위 | 유효 부착면 (세로 × 가로) | 비고 |
|---|---|---|
| 동체 옆면 | **100 × 300mm** | 날개 뿌리 아래 구간. 원통 곡면이라 상하 곡률 시작부 제외. 후방은 테이퍼 콘이라 사용 불가 |
| 수직꼬리 고정 핀 | **250 × 150mm** | 러더(조종면) 제외한 앞쪽 고정부. 평면이지만 가로 폭이 좁음 |
| 왼쪽 날개 하면 | **100 × 200mm** | 에일러론(조종면) 제외 |

- 동체 높이 156mm는 단면 전체 기준이며, 곡률을 뺀 실제 평면 구간은 **100~110mm**
- 수직꼬리는 9핀 커넥터로 통째로 탈착되는 구조 → 분리 시 해당 면의 표식도 함께 분리됨
- 날개/꼬리는 조종면(에일러론·러더)에 표식 부착 불가

## 안전/면책 (원문 요약)

- Makeflyeasy 항측 시리즈 제품은 민감 품목이며, 제조사는 직간접적 사고에 대해 책임지지 않음. 군사적 용도 사용 금지.
- 어린이 손이 닿지 않는 곳에 보관. 비행 시 군중/위험물로부터 충분히 이격. 음주/피로/정신적 불편 상태에서 비행 금지.

## 유통 스펙시트 정보

| 항목 | 값 |
|---|---|
| 재질 | Foam |
| 원산지 | 중국 본토 |
| 권장 연령 | 14세 이상 |
| 용도 | 차량/RC 완구 분류 |
