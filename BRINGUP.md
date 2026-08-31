# SHADE 브링업 현황

기준일: **2026-08-25** (야외 호버 세션 14회 분석 반영)

## 비행 기록

| 회차 | 일시 | 내용 | 리포트 |
|---|---|---|---|
| #85 | 2026-08-22 14:07 | 첫 호버 107초, 이동 45m, 착륙 직전 추락 | [분석](flights/2026-08-22-log85-first-hover.md) |
| #94 | 2026-08-24 19:13 | 옥외 기동 148초, 이동 80m, 고도 +7.2m | [분석](flights/2026-08-24-log94-outdoor-flight.md) |
| **8/25 세션** | **2026-08-25 18:03~18:19** | **호버 14회, 최고 6.1m. 3m 상공 의도적 KILL → 낙하. 천이 시도했으나 PX4 미실행(MC 고정)** | [분석](flights/2026-08-25-outdoor-session.md) |

분석 도구: `./qgc log list` / `./qgc log <번호>` ([qgclog](tools/qgclog/README.md))
FC 에서 로그 받기: [FETCHING.md](tools/qgclog/FETCHING.md) — MAVFTP, 7.6MB 를 18초에

**🔴 #94 발견 → 8/25 추적**
- XT90 45A 초과: #94 에서 77초 연속 초과 → 8/25 는 **조작 방식만으로 45A 초과 시간 −72%** (최장 연속 13~24초). 여전히 정격 초과, 착륙 후 커넥터 **40~50℃**. 장시간 비행 전 XT120/AS150 교체 권장
- **모터 M2 만 71.7%** (나머지 58%대, 편차 13.8%p) — 8/22 엔 2.6%p 였다. 원인 규명 필요

**🔴 8/25 신규**
- **킬 스위치 낙하 (약 3.1m)** — 이후 5회 비행 클리핑 0·진동 정상이라 손상 징후 없음. **육안 점검(프레임·모터 마운트·프롭) 필요**
- **천이가 실제로 실행되지 않았다** (`vtol_vehicle_state=3` 전 구간). 에어스피드 −5 m/s 라 `VT_ARSP_TRANS=10` 에 구조적으로 도달 불가 → **에어스피드 해결 전 천이 시도 금지**
- 진동 최대 10.6 (경고선 10) — 프로펠러 밸런싱 권장
- 전류-자기장 상관 −0.63 (8/24 −0.89) — 자기 간섭 잔존. GPS 마스트·전력선 이격/트위스트
- 로그 3건(8/24 log_88·89, 8/25 09_09_49) 파일 끝부분 손상 — **SD 카드 점검**

**미해결 (다음 비행 전 필수)**: 에어스피드 **영점 오프셋** 어긋남 — 정지 시 음수라 고정익 전환 불가.
⚠️ 배관은 정상이다(불면 양수 확인). 튜브 건드리지 말고 **영점만 재보정**할 것 —
[상세](components/sensors/holybro-airspeed-dronecan/README.md#️-영점-오프셋-어긋남--미해결-2026-08-24)

## 조종기 스위치 (2026-08-24 확정)

⚠️ **위=1000 / 중간=1500 / 아래=2000** — 직관과 반대. PX4 는 1500 초과를 ON 으로 보므로
**아래로 내리면 발동**한다. 가운데(1500)는 임계값 경계라 쓰지 않는다.

| 스위치 | CH | 기능 | 아래(2000) |
|---|---|---|---|
| SA | 5 | ARM | ARM |
| SB | 6 | 비행모드 | POSCTL (위 STAB / 중간 ALTCTL) |
| SD | 7 | VTOL 전환 | 고정익 |
| SE | 8 | KILL | KILL |
| **SC** | **9** | **RTL** | **RTL** |

⚠️ 3단은 **SB·SC 뿐**이다. SA·SD·SE 는 2단(중간 없음), SF 는 모멘터리(TOGGLE).
P3 는 **6단 스위치**로 자동미션 진입용 검토 중.

상세·RTL 동작·주의사항: [스위치 매핑](components/transmitters/radiomaster-boxer/switch-mapping.md)

## 링크 아키텍처 (확정)

```
[Boxer 내장 ELRS TX] ←RF 2.4GHz (MAVLink over ELRS)→ [RP4TD-M] ─UART─ FC TELEM1
        │
        └─ 백팩 WiFi AP (10.0.0.1) ─UDP→ 노트북 QGC        (대역폭 ~2KB/s)

[Pi5 raspb1] ─USB─ FC USB-C (/dev/ttyACM0) ─UDP 14550→ ku-dgs1 / rim / rim3 / gram-labtop
              (mav_bridge, systemd 서비스)   ※ TELEM2 포트 사망으로 2026-08-31 전환

[USB 직결] /dev/ttyACM0 — QGC 자동연결
```

- RC 조종 + 텔레메트리가 **MAVLink over ELRS** 단일 링크. CRSF 아님 (전환 완료).
- 실비행 운용 계획: 노트북 2대 — 1대 Pi 링크, 1대 조종기 백팩 WiFi 링크.
- QGC USB 링크 1초 끊김 버그 해결: 원인은 `autoConnectPixhawk=false` 시 포트 스캔 중단 →
  `_checkPortAvailability()`가 빈 목록 보고 close. 현재 `autoConnectPixhawk=true`.
- 🔴 **컴패니언 Pi 교체 (2026-08-30)** — `raspb2`(DGS-X) → **`raspb1`(DGS-3)**.
  **raspb2 는 고장 확정**이며 되돌아가지 않는다. 브리지 코드는 이제 repo 안에 있다
  ([mav_bridge.py](components/companion/raspberry-pi-5/mav_bridge.py)).
  raspb1 상태: 유닛 `enabled`+`active`, `/dev/ttyAMA0` 921600 오픈 성공.
  고정 타겟 4개(`ku-dgs1`·`rim`·`rim3`·`gram-labtop`).
- 🔴 **FC TELEM2 포트 사망 → USB 링크로 전환 (2026-08-31)** — 빈 포트에서도 FC 가 자기
  패킷을 22.4kB/s 로 되받고(`sysid:1 compid:1`), TELEM1 에서 멀쩡하던 **수신기를 그 케이블째
  옮기자 LED 조차 안 켜졌다** (5V 출력도 사망). 미연결 대조 포트 `ttyS4` 는 유효 프레임 0 이라
  PX4 카운터 착시가 아니다. Pi(물리 8↔10 루프백 64/64)·케이블·네트워크는 전부 무죄.
  **Pi 는 이제 FC USB(`/dev/ttyACM0`) 로 붙는다** — `ku-dgs1` 에서 **21.8 KB/s** 실측
  (2572패킷/8초, RC_CHANNELS 포함). 유닛에 `Environment=MAV_SERIAL=/dev/ttyACM0` 한 줄.
  죽은 포트에 CPU 7.4% 를 태우고 있어 `MAV_1_CONFIG=0` 으로 껐다.
  진단은 `pxsh.py`(MAVLink SERIAL_CONTROL 로 PX4 NSH 셸 접속)로 했다.
  [상세](components/companion/raspberry-pi-5/README.md#-telem2-포트-사망--usb-링크로-전환-2026-08-31)
- ⚠️ **문서-실기 불일치** — 이 문서는 `autoConnectUDP=false` 라고 적어 왔으나 `ku-dgs1` 의
  실제 `QGroundControl.ini` 는 **`autoConnectUDP=true`** 다 (2026-08-30 실측).

## FC — Pixhawk 6C Mini

| 항목 | 값 |
|---|---|
| 펌웨어 | **PX4 v1.17.0 커스텀 빌드** (fmu-v6c, CRSF 드라이버 포함, 플래시 98.3%) |
| 파라미터 | 1360개 유지, 캘리브레이션 `CAL_*` 82개 보존 (플래시 후 초기화 안 됨) |
| TELEM1 | MAVLink (수신기), `SER_TEL1_BAUD=460800` |
| TELEM2 | 🔴 **포트 사망 (2026-08-31)** — `MAV_1_CONFIG=0` 으로 꺼 둠. Pi 는 USB 로 이설 |
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

## 미해결 / 다음 비행 전 (2026-08-25 갱신)

호버링 실비행은 완료 (#85, #94, 8/25 ×14). 남은 것은 **천이 전 조건**과 안전 마진.

1. **기체 육안 점검** — 8/25 3m 낙하 이력. 프레임·모터 마운트·프롭.
2. **에어스피드 영점 오프셋** — 정지 시 −4.7~−5.0 m/s, `SENS_DPRES_OFF=-4.52`. **배관은 정상**(불면 양수). 무풍에서 영점만 재보정, ±2 이내 확인. 천이의 전제 조건.
3. **프로펠러 밸런싱** — 진동 10.6, 경고선.
4. **자기 간섭 저감** — 전류-자기장 상관 −0.63. GPS 마스트 높이기, 전력선 이격·트위스트. 나침반 재캘리브는 백팩 WiFi 무선으로 가능.
5. **커넥터 업그레이드** — XT90(45A) → XT120/AS150. 장시간 임무 비행 전.
6. **SD 카드 점검** — 로그 끝부분 손상 3건 반복.
7. 모터 M2 추력비 편차(13.8%p) 원인 규명.
8. 지상테스트용 임시 파라미터 원복 여부 확인: `COM_ARM_WO_GPS=0`, `COM_DISARM_PRFLT=10`, `COM_PREARM_MODE=0`, `SYS_HAS_NUM_ASPD=1`.
9. `BAT1_CAPACITY=16000` 반영 확인 (미검증). 에일러론 좌우 비대칭(30° vs 15°)·서보 중립 드리프트.
10. RC loss failsafe `COM_RC_LOSS_T=0.5s` — 1~2s 완화 검토.

**천이 테스트는 2번 해결 전까지 시도하지 말 것.**
