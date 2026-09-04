# SHADE01

Striver Mini VTOL(4+1) 기체 **한 대**의 운용 저장소. 부품 자료·링크 구성·비행 기록·분석
도구가 모두 여기 있다.

| 폴더 | 내용 |
|---|---|
| [`components/`](components/) | 부품별 제원·배선·설정 (FC, ESC, 모터, 전원, 수신기 …) |
| [`airframes/`](airframes/) | 기체 조립·구성 |
| [`gcs/`](gcs/) | [QGroundControl 설치·접속 절차](gcs/qgroundcontrol/README.md) · [분석 PC 접속(Tailscale)](gcs/ACCESS.md) |
| [`flights/`](flights/) | 비행/세션별 분석 — **로그 원본이 사라져도 남는 정본** · [로그 소재 목록](flights/LOG-INVENTORY.md) |
| `logs/` | `.ulg` 원본 (git 제외, **평면으로 쌓는다**) |
| [`tools/`](tools/qgclog/) | 로그 수집(`fcfetch.py`)·분석(`qgclog`) |
| [`web/`](web/) | [shade01.bewe.co.kr](https://shade01.bewe.co.kr) — 지도·시간축 재생 뷰어, 로그 정본 보관소 |
| `params/` `config/` | 파라미터 스냅샷, 조종기 설정 백업 · [**세팅 스냅샷 정리**](config/SETTINGS.md) |
| [`PROCEDURE.md`](PROCEDURE.md) | 로그 수집 → 분석 → 기록 절차 |

```bash
./qgc log list          # 최근 비행 나열
./qgc log 1             # 1번 분석
```

---

## 링크 구성 — **3 경로**

지상국 링크는 셋이다. 지금은 **raspb1 잠정 중단**, `rim3` USB 직결이 현행 주 경로다.

| # | 경로 | 상태 | 쓰는 때 |
|---|---|---|---|
| 1 | **raspb1 브리지** (기체 탑재 Pi) | 🟡 **잠정 중단** — FC USB 를 뽑아 뒀다 | **비행용 정규 경로.** 비행 전 원복 |
| 2 | **PC USB 직결 브리지** (현재 `rim3`) | ✅ **가동중** | 지상 정비·파라미터·펌웨어 |
| 3 | **ELRS 백팩** (조종기 WiFi AP) | ✅ 사용 가능 (WiFi 있는 PC 만) | 1·2 가 다 죽었을 때 폴백 |

**FC USB 는 하나뿐이다.** 1 번과 2 번은 같은 포트를 두고 다투므로 **동시에 못 쓴다** —
한쪽을 쓰려면 다른 쪽 USB 를 물리적으로 뽑아야 한다. 3 번은 TELEM1 로 들어와 독립이지만,
노트북 WiFi 가 하나뿐이라 **백팩 AP 에 붙는 동안은 Tailscale 이 끊겨 1·2 번이 죽는다.**
셋 다 실질적으로 배타적이다.

### 1. raspb1 브리지 — 🟡 잠정 중단

```
[Pixhawk 6C Mini] ──USB-C ⟷ USB-A── [Raspberry Pi 5 "raspb1"]   ← 지금 USB 뽑힘
                                          /dev/ttyACM0
                                       mav_bridge.py (UDP :14550)
                                     WiFi/LTE → Tailscale → QGC 4대
```

| 항목 | 값 |
|---|---|
| FC ↔ Pi | **USB 직결** `/dev/ttyACM0` — Pi 시리얼 읽기 **21.0 KB/s** 실측 |
| Pi ↔ GCS | UDP 14550 over Tailscale — GCS 수신 **21.8 KB/s** 실측 |
| 브리지 | `mavlink-bridge.service` (`enabled`, `Restart=always`) |

- 🟡 **잠정 중단 (2026-09-04)** — FC USB 를 `rim3` 로 옮겼다. raspb1 은 Tailscale 에서도
  `offline` 이다. **기체를 다시 띄우기 전에 반드시 원복한다** — `rim3` 는 기체에 안 실린다.
- ⛔ **TELEM2 는 죽었다** (2026-08-31). 포트 전원까지 사망 —
  [근거](components/companion/raspberry-pi-5/README.md#-telem2-포트-사망--usb-링크로-전환-2026-08-31)
- ✅ **WiFi + LTE 이중화** (2026-08-31) — LTE 모뎀 장착으로 WiFi 범위 의존이 해소됐다.
  ⚠️ 비행 중 링크 신뢰성은 아직 장거리로 검증되지 않았다.

### 2. PC USB 직결 브리지 — ✅ 현재 가동중 (`rim3`)

raspb1 이 하던 일을 PC 가 대신한다. 같은 `mav_bridge.py` 이고, 중계 대상도 같은 4 대다.

```
[Pixhawk 6C Mini] ──USB── [rim3]  /dev/ttyACM0
                          mav_bridge.py (UDP :14550, Tailscale 주소에만 바인딩)
                                  │
        ┌──────────────┬──────────┴───┬──────────────┐
        ▼              ▼              ▼              ▼
     ku-dgs1          rim           rim3       gram-labtop      ← QGC 4대
  100.99.120.110  100.107.83.47  100.117.47.105  100.66.204.25
```

```bash
cd ~/SHADE01 && ./shade-bridge/pc_bridge.sh
```

**2026-09-04 실측 (`rim3` 직결, `ku` 에서 수신):**

| 항목 | 값 |
|---|---|
| 수신 대역 | **28.4 KB/s** — raspb1 의 21.8 KB/s 보다 빠르다 (유선 Tailscale) |
| 하행 | ✅ FC sysid 1 — `ATTITUDE`·`HIGHRES_IMU`·`LOCAL_POSITION_NED` 정상 |
| 상행 | ✅ `PARAM_REQUEST_READ` → `PARAM_VALUE` 왕복 확인 |
| `rim` 레그 | ✅ rim3→rim tx 17.95 MB vs rim3→ku 17.99 MB — 같은 스트림이 양쪽에 나감 |
| `gram` 레그 | 안 감 — gram 이 `offline` (정상 동작) |

- 🔴 **상행이 열려 있다 = ARM·모드변경·미션업로드가 원격에서 된다.** 브리지는 Tailscale
  주소에만 바인딩하고 송신자를 화이트리스트로 거른다 —
  [노출 범위](shade-bridge/README.md#노출-범위--반드시-읽어라)를 반드시 읽어라.
- ⚠️ **`ku-dgs1` 에서 브리지를 돌릴 땐 `MAV_BIND` 를 명시한다.** 공인 IP
  (`203.253.176.74`)가 있고 `ufw` 도 꺼져 있어, Tailscale 자동탐지가 실패하면 인터넷에서
  FC 로 명령이 들어온다.
- ✅ **자동 재시작 (2026-09-04)** — `shade-bridge.service` (`Restart=always`) 로 돌린다.
  `kill -9` 후 3초 만에 복구되는 것을 실측했다. 그전에는 손으로 띄운 프로세스였다 —
  그 탓에 서비스 쪽은 포트 충돌로 634 회 재시작하다 죽어 있었다
  ([상세](shade-bridge/README.md#-손으로-띄우면-서비스가-조용히-죽는다)).

### 3. ELRS 백팩 링크 — 조종기 WiFi

조종기(RadioMaster Boxer) 의 백팩이 AP 를 띄우고, PC 가 거기 붙어 `10.0.0.1:14550` 으로
받는다. FC 쪽은 **TELEM1** 이라 1·2 번과 독립이다. QGC 링크는 로컬 리슨 **14555**.

| PC | WiFi 장치 | 백팩 링크 |
|---|---|---|
| `rim3` | `wlo1` | ✅ |
| `gram-labtop` | `wlp0s20f3` | ✅ |
| `ku-dgs1` | **없음** (유선 `enp3s0`) | ❌ USB 동글 필요 |

```bash
./gcs/qgroundcontrol/elrs-backpack        # AP 전환 → QGC → 닫으면 원래 WiFi 복귀
```

- ⚠️ **백팩 AP 에는 인터넷이 없다.** NetworkManager 가 30초~2분 뒤 원래 WiFi 로 라디오를
  뺏어간다 — 프로파일에 `autoconnect-priority 100` + `never-default yes` 가 있어야 한다.
- 백팩 FW **1.5.9**, Telemetry = **wifi**.

### RC 는 링크와 별개다

| 항목 | 값 |
|---|---|
| RC | MAVLink over ELRS → FC **TELEM1** (CRSF 아님) |

조종은 위 3 경로 중 무엇을 쓰든 **ELRS 무선으로 직접** 들어간다. 브리지가 죽어도
조종은 살아 있다 (반대로 브리지만 살고 RC 가 죽으면 `NAV_RCL_ACT=2` 로 RTL).

상세: [raspb1 브리지 구현](components/companion/raspberry-pi-5/README.md) ·
[PC 직결 브리지](shade-bridge/README.md) ·
[QGC 접속 절차 · 링크 3개 등록](gcs/qgroundcontrol/README.md#링크-3개-구성-2026-09-02-확정)

---

## 기체 식별

| 항목 | 값 |
|---|---|
| 기체 | [Striver Mini VTOL](airframes/striver-mini-vtol/README.md) (4+1), `MAV_TYPE=22` |
| FC | [Pixhawk 6C Mini](components/fc/holybro-pixhawk-6c-mini/README.md) — `PX4_FMU_V6C`, HW `V6C002002` |
| 펌웨어 | **PX4 v1.17.0 커스텀** (`d6f12ad1c4f7`, 2026-08-11 빌드, CRSF 포함, 플래시 98.3%) |
| 컴패니언 | [Raspberry Pi 5 `raspb1`](components/companion/raspberry-pi-5/README.md) |
| 조종기 | [RadioMaster Boxer](components/transmitters/radiomaster-boxer/README.md) (EdgeTX 2.12.1) |
| 수신기 | [RP4TD-M](components/receivers/radiomaster-rp4td-m/README.md) — TELEM1, 바인딩 완료 |
| 전원 | [PM08 DroneCAN](components/power/holybro-pm08-can/README.md) — `UAVCAN_ENABLE=2`, `BAT1_SOURCE=1` |
| 배터리 | [Fullymax 6S 16000mAh](components/batteries/fullymax-6s-16000mah/README.md) |
| 지상국 | **QGroundControl v5.1.4** (직접 빌드, VTOL 패치) — [빌드](gcs/qgroundcontrol/BUILD.md) · [설치 절차](gcs/qgroundcontrol/README.md#설치-ubuntu--실기-기준) |
| 저장소 | `github.com/yyrrm/SHADE01` — 클론: `ku`, `rim3` |
| 파라미터 백업 | [`params/`](params/) 최신 스냅샷 (1354개) · 미션·펜스는 [`config/*.plan`](config/) · 정리본 [`config/SETTINGS.md`](config/SETTINGS.md) |

### ELRS

| 장치 | 펌웨어 | 설정 |
|---|---|---|
| TX (Boxer 내장) | Unified **4.1.0 커스텀** (DroneCAN 배터리 패치) | Link Mode = **MAVLink** |
| RX RP4TD-M | **3.5.6** (ee188b) ISM2G4 | Serial = **MAVLink**, Bound UID `45,5,9,157,112,199` |
| 백팩 | **1.5.9** | Telemetry = **wifi** |

> **TX 는 커스텀 펌웨어다.** 공식 4.1.0 은 `BATTERY_STATUS.id != 0` 을 버려 조종기 화면에
> 배터리가 안 뜬다. 재플래시하면 바인딩도 다시 해야 한다 —
> [상세](components/transmitters/radiomaster-boxer/elrs-battery-telemetry-fix.md)

### 출력 배치 (2026-09-01 실측)

| 커넥터 | 기능 | PWM |
|---|---|---|
| MAIN1 / MAIN2 | **우 / 좌 에일러론** | **100Hz** |
| MAIN3 / MAIN4 | VTOL 우후 / 우전 | 400Hz |
| MAIN5 | UBEC 5.3V (신호 미사용) | — |
| MAIN6 / MAIN7 | VTOL 좌후 / 좌전 | 400Hz |
| MAIN8 | **크루즈 모터** | 400Hz |
| AUX1 / AUX3 | 엘리베이터 ×2 | — |
| AUX2 | 러더 | — |

서보를 MAIN1–2 한 타이머 그룹에 모아 **100Hz 로 분리**했다 (8/31 까지는 모터와 섞여
400Hz 였다). 상세·주의사항: [6C Mini 출력 배치](components/fc/holybro-pixhawk-6c-mini/README.md#-실기-배치-2026-09-01-fc-실측--확정)

### 조종기 스위치

| 스위치 | 채널 | 용도 |
|---|---|---|
| SA | CH5 | ARM |
| **P3 (S3 6단)** | **CH6** | **비행모드** — 1 STAB(1000) / 2 ALT(1275) / 3·4 POS(1425·1575) / 5 Mission(1725) / 6 RTL(2000) |
| SD | CH7 | 🔴 **VTOL 천이 — FC 에 매핑돼 있다** (`RC_MAP_TRANS_SW=7`) |
| SE | CH8 | KILL |

[상세·실측 PWM](components/transmitters/radiomaster-boxer/switch-mapping.md)

### 기체 세팅

- 모터 지오메트리: 좌전 CW / 우전 CCW / 좌후 CCW / 우후 CW + 크루즈(Forward). ESC 캘리브레이션 완료.
- 서보: 에일러론 **MAIN1/2**(위 출력 배치 표), 엘리베이터·러더는 AUX. **최종 기준은 FC 의 Actuators 설정.**
- ⚠️ 모터·서보는 **배터리 인가 시에만** 돈다 (USB 전원만으로는 안 돎).

---

## 현재 상태 (2026-09-02)

| 항목 | 상태 |
|---|---|
| 링크 | 🟡 **raspb1 잠정 중단** (2026-09-04, FC USB 를 `rim3` 로 옮김). 현행은 `rim3` USB 직결 브리지 — ku·rim 중계 양방향 실측 완료. **비행 전 raspb1 원복 필수** |
| 비행모드 | ✅ S3 6단, 실링크로 6단 전부 검증 (2026-09-02 재측정 1000/1275/1425/1575/1725/2000) |
| 🟡 2단 여유 | Altitude(1275us)가 슬롯 경계 1282us 에서 **7us**. 지금은 값이 고정이라 무해하나 **CH6 RC 캘리브레이션 금지** ([상세](components/transmitters/radiomaster-boxer/switch-mapping.md#px4-슬롯-경계--1500us-가-아니다)) |
| GPS | ✅ 위성 21~32, fix 4, eph 0.15~0.23m (야외 실측) |
| 진동 | ✅ 평균 2.5 / 최대 5.0 (8/25 세션 8~10 대비 개선) |
| 미션 | ✅ 6항목 전부 고도 5m, 착륙 0m. 경로 163.6m ([백업](config/)) |
| 지오펜스 | ✅ `GF_MAX_HOR_DIST=150` / `GF_MAX_VER_DIST=50` / `GF_ACTION=2`(Hold) + 폴리곤 6각형. 최소 여유 11.7m (WP#4) |
| failsafe | ✅ RC 상실 → RTL (`NAV_RCL_ACT=2`, `COM_RCL_EXCEPT=0`, 1s) · 저전압 → RTL |
| RTL | ✅ `RTL_RETURN_ALT=25` / `RTL_DESCEND_ALT=10` (5m 였음 — 직선 복귀라 장애물 위험) |
| 🔴 전류 | 최대 **66.8A**, 453초 중 270초를 45A 위에서. XT90 교체 필요 |
| 🟡 기압계 | GPS 대비 **−14m** 오차. 미션(홈 기준)엔 무관, GPS 없는 고도유지엔 영향 |
| 🟡 `NAV_DLL_ACT` | `0` (동작 없음). RC 가 살아있는데 인터넷 링크만 끊겨도 발동하므로 `1`(Hold) 권장 |
| 🔴 CH7 천이 | **매핑돼 있다** (`RC_MAP_TRANS_SW=7`, 임계 1750). SD 내리면 천이 명령. 에어스피드 영점 전까지 `RC_MAP_TRANS_SW=0` 권장 |
| 🟡 CH9 RTL | `RC_MAP_RETURN_SW=9` 매핑됨. CH9 는 1500 고정이라 지금은 무해 (2026-09-02 실측) |

### 지오펜스는 홈 기준이다

`GF_MAX_HOR_DIST` 도 `RTL_*` 도 **arm 한 자리**(홈)가 원점이다. 이륙지점이 아니다.
보통 같지만, 현장에서 **arm 후 QGC 지도에서 홈 아이콘(H) 이 기체 위에 있는지** 확인한다.
어긋나 있으면 펜스·RTL·미션 상대고도가 전부 엉뚱한 기준으로 돈다.

## 다음 비행 전

**천이 테스트는 2번 해결 전까지 시도하지 말 것.**

1. **기체 육안 점검** — 8/25 3m 낙하 이력. 프레임·모터 마운트·프롭.
2. **에어스피드 영점** — 정지 시 −4.7~−5.0 m/s, `SENS_DPRES_OFF=-4.52`. **배관은 정상**(불면 양수).
   무풍에서 영점만 재보정, ±2 이내 확인. **천이의 전제 조건.**
3. **홈 위치 확인** — arm 후 QGC 지도에서 홈(H) 이 기체 위인지. 펜스·RTL 이 전부 홈 기준이다.
4. **RX failsafe 실측** — 조종기를 끄고 FC 가 RC 상실을 몇 초 만에 인지하는지 본다.
   ELRS RX 가 "마지막 값 유지" 로 설정돼 있으면 `NAV_RCL_ACT=2` 가 늦게 걸리거나 안 걸린다.
5. **기압계 −14m 오차** — GPS 대비. `EKF2_HGT_REF=1` 이라 GPS 없는 고도유지에 영향.
6. **자기 간섭 저감** — EKF `mag_field` **3축 전부** 이상. GPS 마스트 높이기, 전력선 이격·트위스트.
7. **커넥터 교체** — 8/31 최대 **66.8A**, 453초 중 270초가 45A 초과. XT120/AS150.
8. **지상테스트용 임시 파라미터 원복 확인** — `COM_DISARM_PRFLT`, `COM_PREARM_MODE`,
   `SYS_HAS_NUM_ASPD`. (`COM_ARM_WO_GPS=1` 은 Position·Mission 에서 자체 검사가 여전히
   막으므로 그대로 둬도 된다.)

**해결됨** — 지오펜스 설정(150/50 + 폴리곤), `MAV_1_CONFIG` → 0, `COM_RC_LOSS_T` 1s,
RTL 고도 25/10, 미션 고도 통일.

## 이력

| 날짜 | 사건 |
|---|---|
| 2026-09-04 | 🟡 **raspb1 링크 잠정 중단** — FC USB 를 `rim3` 로 옮겼다. `rim3` 직결 브리지가 ku·rim 까지 중계되는 것을 양방향 실측 확인 (28.4 KB/s, 상행 PARAM 왕복). README 링크 구성을 **3 경로**(raspb1 / PC 직결 / ELRS 백팩)로 정정 — "raspb1 단독, 대체 경로 없다" 는 백팩 링크 구축(9/3) 이후 낡은 서술이었다 |
| 2026-09-04 | 🔴 **"Sensor lost" 원인 규명 — ELRS 링크 대역폭 포화.** `MAV_0_RATE` 0 → **700** ([상세](components/receivers/radiomaster-rp4td-m/README.md#-링크-대역폭-포화--sensor-lost-의-원인-2026-09-04-규명)) ⚠️ **FC 재부팅 필요** |
| 2026-09-04 | 백팩 링크 로딩 지연 규명·완화 — `noInitialDownloadWhenFlying` ([상세](gcs/qgroundcontrol/README.md#-백팩-링크는-왜-로딩이-느린가-2026-09-04-규명)) |
| 2026-09-02 | 🔴 **CH7 천이가 실제로는 매핑돼 있음을 발견** (`RC_MAP_TRANS_SW=7`) — 문서 3곳이 "미매핑"으로 잘못 적고 있었다 |
| 2026-09-02 | 브리지 보안 수정 — Tailscale 주소에만 바인딩 + 송신자 화이트리스트 ([상세](shade-bridge/README.md#노출-범위--반드시-읽어라)) |
| 2026-09-02 | QGC v5.1.4 직접 빌드 — VTOL 미션시간·기종표시 버그 [패치](gcs/qgroundcontrol/BUILD.md) |
| 2026-09-02 | 지오펜스 설정(150/50 + 폴리곤 6각형), RTL 고도 25/10, `MAV_1_CONFIG`→0 |
| 2026-09-02 | 미션 정리 — 고도 5m 통일, Launch=이륙점, 착륙 0m. `.plan`·파라미터 스냅샷을 git 에 넣기 시작 |
| 2026-09-01 | 출력 배치 정비 — 크루즈 모터 복구, 서보 100Hz 분리, 엘리베이터 반전 |
| 2026-09-01 | 로그 파서 수정 — 21개 전부 100% 디코딩 (마지막 비행 27초→**453초**) |
| 2026-08-31 | 실비행 21회, 최장 **7.6분** ([기록](flights/2026-08-31-ground-tests.md)) |
| 2026-08-31 | 비행모드 S3 6단 전환, `COM_ARM_WO_GPS=1`, 미션 고도 5m, 저전압 RTL |
| 2026-08-31 | FC TELEM2 사망 → **USB 링크 전환** |
| 2026-08-30 | 컴패니언 Pi `raspb2`(고장, 제거) → `raspb1` |
| 2026-08-25 | 야외 세션 14회 ([기록](flights/2026-08-25-outdoor-session.md)) — 3m 낙하 이력 |
| 2026-08-24 | 옥외 비행 #94 ([기록](flights/2026-08-24-log94-outdoor-flight.md)) |
| 2026-08-22 | 첫 호버 #85 ([기록](flights/2026-08-22-log85-first-hover.md)) |
