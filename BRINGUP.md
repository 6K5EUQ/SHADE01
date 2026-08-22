# SHADE 브링업 현황

기준일: **2026-08-21** (DGS-1 작업 세션 종료 시점)

## 링크 아키텍처 (확정)

```
[Boxer 내장 ELRS TX] ←RF 2.4GHz (MAVLink over ELRS)→ [RP4TD-M] ─UART─ FC TELEM1
        │
        └─ 백팩 WiFi AP (10.0.0.1) ─UDP→ 노트북 QGC        (대역폭 ~2KB/s)

[Pi5 raspb2] ─UART─ FC TELEM2 (921600) ─UDP 14550→ PC / rim   (mav_bridge, systemd 서비스)

[USB 직결] /dev/ttyACM0 — QGC 자동연결
```

- RC 조종 + 텔레메트리가 **MAVLink over ELRS** 단일 링크. CRSF 아님 (전환 완료).
- 실비행 운용 계획: 노트북 2대 — 1대 Pi 링크, 1대 조종기 백팩 WiFi 링크.
- QGC USB 링크 1초 끊김 버그 해결: 원인은 `autoConnectPixhawk=false` 시 포트 스캔 중단 →
  `_checkPortAvailability()`가 빈 목록 보고 close. 현재 `autoConnectPixhawk=true`,
  `autoConnectUDP=false` (Pi 링크는 Comm Links에서 수동 Connect).

## FC — Pixhawk 6C Mini

| 항목 | 값 |
|---|---|
| 펌웨어 | **PX4 v1.17.0 커스텀 빌드** (fmu-v6c, CRSF 드라이버 포함, 플래시 98.3%) |
| 파라미터 | 1360개 유지, 캘리브레이션 `CAL_*` 82개 보존 (플래시 후 초기화 안 됨) |
| TELEM1 | MAVLink (수신기), `SER_TEL1_BAUD=460800` |
| TELEM2 | Pi 브릿지, `MAV_1_CONFIG=102`, `MAV_1_MODE=2`, `SER_TEL2_BAUD=921600` |
| 전원 | PM08 DroneCAN — `UAVCAN_ENABLE=2`, `UAVCAN_SUB_BAT=2`, `BAT1_SOURCE=1`, `BAT1_N_CELLS=6` |
| 기체 | `MAV_TYPE=22` Standard VTOL |
| 백업 | `param_backup/px4_params_20260811-121719.params` (1359개) |

## ELRS

| 장치 | 펌웨어 | 설정 |
|---|---|---|
| TX (Boxer 내장, ESP32 2400) | Unified **4.1.0 커스텀 빌드** (DroneCAN 배터리 패치) | Link Mode = **MAVLink** |
| RX RP4TD-M | **3.5.6** (ee188b) ISM2G4 | Serial Protocol = **MAVLink**, 바인딩 완료 — Bound UID `45,5,9,157,112,199` |
| 백팩 | **1.5.9** | Telemetry = **wifi** (노트북 QGC 연결용) |

> **TX는 커스텀 펌웨어다.** PM08 DroneCAN 파워모듈이 `BATTERY_STATUS.id=124`로 보고하는데
> ELRS 4.1.0이 `id != 0`을 버려 조종기 화면에 배터리가 안 떴다. 1줄 패치로 해결.
> 재플래시 시 바인딩 재설정 필요 — 절차와 상세: [ELRS 배터리 텔레메트리 수정](components/transmitters/radiomaster-boxer/elrs-battery-telemetry-fix.md)

바인딩 과정 스크린샷: `components/receivers/radiomaster-rp4td-m/images/webui-rx-*`,
`components/transmitters/radiomaster-boxer/images/webui-tx-*`
수신기 매뉴얼: `components/receivers/radiomaster-rp4td-m/RP4TD-manual.pdf`

## 조종기 (Boxer)

- 스위치 맵핑: **SA=arm (CH5), SB=비행모드 (CH6), SD=VTOL 천이 (CH7), SE=kill (CH8)**
- 비행모드 (SB 3단): 위=Position, 중간=Altitude, 아래=Stabilized
  (`RC_MAP_FLTMODE=6`, `COM_FLTMODE1=2 / 4=1 / 6=8`)
- 텔레메트리 화면: Nums 레이아웃에 RxBt, Bat%, Sats, GAlt, GSpd, FM 등 배치. GPS 좌표는 스크립트 위젯.

## 기체 세팅

- **모터 지오메트리 수정 완료**: 좌전 CW / 우전 CCW / 좌후 CCW / 우후 CW + 크루즈 모터(Forward).
  (기존엔 5개 전부 CCW로 잘못 설정돼 있었음 — 요 제어 불능 상태였음)
- 모터 역회전은 ESC-모터 3상 중 2선 교체로 해결.
- **ESC 캘리브레이션 완료.**
- 서보: 에일러론 MAIN6/7, 엘리베이터·러더는 AUX. 세션 중 MAIN/AUX 배치 변경 이력 있음 —
  **최종 기준은 FC의 Actuators 설정** (QGC에서 확인).
- 모터/서보는 **배터리 전원 인가 시에만 동작** (USB 전원만으로는 안 돎 — 과거 "안 돈다" 이슈의 원인).

## 미해결 / 비행 전 필수

1. **지상테스트용 임시 파라미터 복구** (이대로 비행 금지):
   `COM_ARM_WO_GPS=0`, `COM_DISARM_PRFLT=10`, `COM_PREARM_MODE=0`, `SYS_HAS_NUM_ASPD=1`
2. **나침반 야외 재캘리브레이션** — 실내 자기 간섭 경고. 백팩 WiFi 링크로 무선 캘리브 가능 (권장).
3. **에어스피드 이상** — 값이 음수/변동. `SENS_DPRES_OFF=-4.52` 비정상. 피토관 배관 점검 필요.
4. `BAT1_CAPACITY=16000` 설정 반영 확인 (요청됨, 미검증).
5. 에일러론 좌우 비대칭 (30° vs 15°), 서보 중립 드리프트 관측됨.
6. 실내 arm 거부는 `GPS PDOP too high` / `Global position estimate required` — 야외에서 해소.
7. RC loss failsafe `COM_RC_LOSS_T=0.5s` — 첫 비행 전 1~2s로 완화 검토.
8. 호버링 실비행 테스트 (개활지, 무풍, 위성 10+).
