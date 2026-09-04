# SHADE01 세팅 스냅샷 — 2026-09-02

이 문서는 **저장된 파일에서 그대로 뽑은 값**이다. 해석·판단은 [README](../README.md),
절차는 [PROCEDURE.md](../PROCEDURE.md) 에 있다. 여기는 "지금 기체에 뭐가 들어가 있나" 만 적는다.

| 출처 | 파일 | 시각 |
|---|---|---|
| 파라미터 | [`params/px4_params_20260902-142426.params`](../params/px4_params_20260902-142426.params) | 2026-09-02 14:24 (1354개 전량) |
| 미션·펜스 | [`config/shade01_20260902-142426.plan`](shade01_20260902-142426.plan) | 2026-09-02 14:24 |
| 펌웨어 | PX4 v1.17.0 커스텀 `d6f12ad1c4f7` | 2026-08-11 빌드 |

> ⚠️ **정본은 FC 다.** 이 스냅샷 이후 기체에서 손으로 바꾼 값은 여기 없다.
> 비행 전에는 QGC 로 다시 받아 대조하라.

---

## 1. 기체 · 시스템

| 파라미터 | 값 | 뜻 |
|---|---|---|
| `SYS_AUTOSTART` | 13000 | Standard VTOL |
| `MAV_TYPE` | 22 | VTOL |
| `VT_TYPE` | 2 | Standard (틸트 아님) |
| `CA_ROTOR_COUNT` | 5 | VTOL 4 + 크루즈 1 |
| `CA_SV_CS_COUNT` | 5 | 에일러론 2 · 엘리베이터 2 · 러더 1 |
| `SYS_HAS_MAG` | 1 | |
| `SYS_HAS_NUM_ASPD` | 1 | 🟡 지상테스트용 변경분일 수 있음 — 원복 확인 대상 |

### 전원

| 파라미터 | 값 |
|---|---|
| `UAVCAN_ENABLE` | 2 (DroneCAN, PM08) |
| `BAT1_SOURCE` | 1 (외부/DroneCAN) |
| `BAT1_N_CELLS` | 6 |
| `BAT1_CAPACITY` | 16000 mAh |
| `BAT_LOW_THR` / `BAT_CRIT_THR` / `BAT_EMERGEN_THR` | 0.15 / 0.07 / 0.05 |
| `COM_LOW_BAT_ACT` | 3 (저전압 → RTL) |
| `CBRK_SUPPLY_CHK` | 0 (서킷브레이커 해제 = 공급 검사 켜짐) |

### 통신

| 파라미터 | 값 |
|---|---|
| `MAV_0_CONFIG` | 101 (TELEM1 — ELRS MAVLink) |
| `MAV_1_CONFIG` | 0 (비활성 — 2026-09-02 정리) |
| `MAV_2_CONFIG` | 0 |
| `SER_TEL1_BAUD` | 460800 |

⛔ TELEM2 는 물리적으로 사망(2026-08-31). GCS 링크는 **FC USB → raspb1** 이 유일 경로다.

---

## 2. 출력 배치 (실측 확정 2026-09-01)

`PWM_MAIN_FUNC*` / `PWM_AUX_FUNC*` 원값:

| 커넥터 | FUNC | 기능 | PWM |
|---|---|---|---|
| MAIN1 | 202 | 우 에일러론 (Servo 2) | **100 Hz** |
| MAIN2 | 201 | 좌 에일러론 (Servo 1) | **100 Hz** |
| MAIN3 | 102 | VTOL 우후 (Motor 2) | 400 Hz |
| MAIN4 | 103 | VTOL 우전 (Motor 3) | 400 Hz |
| MAIN5 | 0 | 미사용 (UBEC 5.3V 급전만) | — |
| MAIN6 | 104 | VTOL 좌후 (Motor 4) | 400 Hz |
| MAIN7 | 105 | VTOL 좌전 (Motor 5) | 400 Hz |
| MAIN8 | 101 | **크루즈 모터** (Motor 1) | 400 Hz |
| AUX1 | 204 | 엘리베이터 (Servo 4) | 400 Hz |
| AUX2 | 205 | 러더 (Servo 5) | 400 Hz |
| AUX3 | 203 | 엘리베이터 (Servo 3) | 400 Hz |

**타이머 그룹 레이트** — 서보를 MAIN1–2 한 그룹에 몰아 100Hz 로 분리했다:

| 파라미터 | 값 |
|---|---|
| `PWM_MAIN_TIM0` | **100** (MAIN1–2, 서보) |
| `PWM_MAIN_TIM1` | 400 (MAIN3–4) |
| `PWM_MAIN_TIM2` | 400 (MAIN5–8) |
| `PWM_AUX_TIM0` | 400 |

**Disarm 값**: MAIN1–2 = 1500 (서보 중립), MAIN3–8 = 1000 (모터 정지).
MIN/MAX 는 전 채널 1000 / 2000.

### 제어면 믹싱 (`CA_SV_CS*`)

| # | TYPE | 롤 | 피치 | 요 | 해석 |
|---|---|---|---|---|---|
| 0 | 1 | **−0.5** | 0 | 0 | 좌 에일러론 |
| 1 | 2 | **+0.5** | 0 | 0 | 우 에일러론 |
| 2 | 3 | 0 | **−1** | 0 | 엘리베이터 (반전 — 2026-09-01 수정) |
| 3 | 3 | 0 | **−1** | 0 | 엘리베이터 |
| 4 | 4 | 0 | 0 | **+1** | 러더 |

### 모터 지오메트리 (`CA_ROTOR*`)

| 로터 | 축 | 위치 (PX, PY) | KM |
|---|---|---|---|
| 0 | **AX=1** (전방 추력) | (1.0, 0) | −0.05 |
| 1 | AZ=−1 (상방 추력) | (−1, +1) | −0.05 |
| 2 | AZ=−1 | (+1, +1) | +0.05 |
| 3 | AZ=−1 | (−1, −1) | +0.05 |
| 4 | AZ=−1 | (+1, −1) | −0.05 |

전 로터 `CT=6.5`. 5–11번은 미사용(위치 전부 0).
로터 0 만 `AX=1` 로 전방 추력 = 크루즈 모터다.

> ℹ️ **위 PX/PY 를 물리 암 위치로 옮겨 적지 않았다.** 파라미터 순번(`CA_ROTOR<N>`)과
> 출력 채널(`PWM_MAIN_FUNC` 의 Motor1~5)은 별개 번호 체계이고, 이 대응은 아직
> 실측으로 확인한 기록이 없다. README 가 적은 기하는 **좌전 CW / 우전 CCW /
> 좌후 CCW / 우후 CW + 크루즈**이며, 대조는 QGC Actuators 화면에서 하라.

> ⚠️ **최종 기준은 FC 의 Actuators 화면이다.** 위 표는 파라미터를 옮겨 적은 것이다.
> 모터·서보는 **배터리 인가 시에만** 돈다.

---

## 3. RC · 조종기 매핑

> 정본은 [`switch-mapping.md`](../components/transmitters/radiomaster-boxer/switch-mapping.md) 이다.
> 여기는 파라미터 스냅샷과 대조할 수 있게 옮겨 적는다.

### 🔴 먼저 — 위가 1000, 아래가 2000

**직관과 반대다.** 스위치를 **내릴수록 값이 커진다.**

| 물리 위치 | 3단 (SB·SC) | 2단 (SA·SD·SE) |
|---|---|---|
| 가장 위 | **1000** | **1000** |
| 가운데 | 1500 | — |
| 가장 아래 | **2000** | **2000** |

SA·SB·SC·SD 4개를 서로 다른 위치에 두고 동시 관측해 확정했다 (2026-08-24).
PX4 는 `RC_MAP_*_SW` 에서 **1500 초과를 ON** 으로 본다 → **내리면 발동, 위가 평소 위치.**

⚠️ **가운데(1500)는 쓰지 마라.** 임계 경계라 진동·노이즈로 ON/OFF 가 깜빡인다.

### 조종기 하드웨어 — 단수를 착각하기 쉽다

`radio.yml` 의 `switchConfig` / `potsConfig` 원값:

| 입력 | 종류 | 비고 |
|---|---|---|
| SA | **2POS** | 2단 — 중간 없음 |
| SB | 3POS | 3단 — **현재 어느 채널에도 안 실려 있다** |
| SC | 3POS | 3단 |
| SD | **2POS** | 2단 |
| SE | 2POS | 2단 |
| SF | **TOGGLE** | 🔴 **모멘터리** — 손 떼면 복귀. KILL 같은 래치 기능에 부적합 |
| P1 / P2 | with_detent | 다이얼 (노치) |
| **P3 (S3)** | **multipos_switch** | **6단** — 비행모드 6슬롯에 1:1 대응 |

### 채널 배정

| 스위치 | 채널 | 박서 믹스명 | FC 파라미터 | 위(1000) | 아래(2000) |
|---|---|---|---|---|---|
| SA | CH5 | ARM | `RC_MAP_ARM_SW=5` | 해제 | **ARM** |
| **P3 (S3)** | **CH6** | MOD | `RC_MAP_FLTMODE=6` | 6단 로터리 — 아래 표 ||
| **SD** | CH7 | BP(TRA) | `RC_MAP_TRANS_SW=7` | 멀티로터 | 🔴 **고정익 천이** |
| SE | CH8 | TUR(KIL) | `RC_MAP_KILL_SW=8` | 해제 | **KILL** |
| SC | CH9 | RTL | `RC_MAP_RETURN_SW=9` | 🟡 CH9 는 1500 고정 ||

스틱: `Ail`→CH1, `Ele`→CH2, `Thr`→CH3, `Rud`→CH4
(`RC_MAP_ROLL` / `PITCH` / `THROTTLE` / `YAW` = 1 / 2 / 3 / 4). `RC_CHAN_CNT=16`.

### 스위치 임계값

| 파라미터 | 값 | 임계 PWM |
|---|---|---|
| `RC_ARMSWITCH_TH` | 0.75 | ≈ 1750 |
| `RC_TRANS_TH` | 0.75 | ≈ 1750 |
| `RC_RETURN_TH` | 0.75 | ≈ 1750 |

### 미할당 — 전부 0

`RC_MAP_AUX1~6` · `RC_MAP_PARAM1~3` · `RC_MAP_LOITER_SW` · `RC_MAP_OFFB_SW` ·
`RC_MAP_GEAR_SW` · `RC_MAP_FLAPS` · `RC_MAP_ENG_MOT` — 스냅샷에서 **전부 0** 확인.
박서에 SB·SF 등이 남아 있으니 필요하면 CH10 이후로 배정한다.

---

### 비행모드 6단 — P3(S3) on CH6

2026-08-31 에 CH6 을 **SB(3단) → P3/S3(6단 로터리)** 로 교체했다. 6모드를 각각 쓰기 위해서다.

| 단 | 실측 PWM | 슬롯 여유 | 파라미터 | 모드 | GPS |
|---|---|---|---|---|---|
| 1 | 1000 | 위 107us | `COM_FLTMODE1=8` | **Stabilized** | 불필요 |
| 2 | **1275** | 🔴 **위 7us** | `COM_FLTMODE2=1` | **Altitude** | 불필요 |
| 3 | **1425** | 🔴 위 32us | `COM_FLTMODE3=2` | **Position** | 필요 |
| 4 | **1575** | 🟡 위 57us | `COM_FLTMODE4=2` | **Position** | 필요 |
| 5 | **1725** | ✅ 아래 93 / 위 82us | `COM_FLTMODE5=3` | **Mission** | 필요 |
| 6 | 2000 | 아래 193us | `COM_FLTMODE6=5` | **RTL** | 필요 |

2026-09-02 재측정 — ELRS 실링크로 `RC_CHANNELS` 1800 샘플을 받으며 각 단을 5~7초씩
유지하고, FC 의 `HEARTBEAT` 보고 모드를 함께 기록했다. 6단 전부 의도한 슬롯에 들어갔다.

### PX4 슬롯 경계는 1500us 가 아니다

`rc_update.cpp:568-583` 의 `slot_min=-1.05` / `slot_max=+1.05` / `slot_width_half=1/6` 과
`RC6_MIN/TRIM/MAX = 1000/1500/2000`(스냅샷 확인, 전부 PX4 기본값, `RC6_REV=1`)에서:

```
     1107   1282   1457   1632   1807
 slot1 │ s2  │ s3  │ s4  │ s5  │ s6
```

🔴 **2단 Altitude(1275)가 슬롯3 경계 1282 에서 7us.** 지금은 값이 완전히 고정돼
(5.8초간 변동 0us) 넘어가지 않는다. 하지만:

- ⚠️ **CH6 에 RC 캘리브레이션 금지** — `RC6_*` 가 실측 극값으로 바뀌며 6단 판정이 전부 이동한다
- ⚠️ **EdgeTX 믹스를 건드리면** Altitude 가 Position 으로 바뀐다

여유를 넓히려면 FC 가 아니라 **조종기**를 고친다 (S3 믹스 출력을 슬롯 중앙으로):

| 단 | 현재 | 슬롯 중앙 |
|---|---|---|
| 1 | 1000 | ~1053 |
| 2 | **1275** | **~1194** |
| 3 | 1425 | ~1369 |
| 4 | 1575 | ~1544 |
| 5 | 1725 | ~1719 |
| 6 | 2000 | ~1903 |

⚠️ 3·4단을 같은 모드(Position)로 둔 것은 원래 1500us 경계를 걱정해서였고 **그 전제는
틀렸다.** 다만 3단 여유가 32us 로 좁으므로 **Mission 같은 자동비행을 3·4단에 두지
않는다는 결론은 유효하다.**

---

### 조종기 쪽 설정 — 만질 때 주의

**`MODELS/model00.yml` 직접 편집** (RTL 스위치를 이렇게 추가했다):

```yaml
# expoData
 - { mode: 3, srcRaw: "SC", weight: 100, chn: 8 }    # I8
# mixData
 - { destCh: 8, srcRaw: "I8", weight: 100, name: "RTL" }   # CH9
```

🔴 **USB Storage 모드에서 편집하고 재부팅해야 적용된다.** EdgeTX 는 모델을 RAM 에
들고 있다가 종료 시 SD 에 쓰므로, **켜진 채로 편집하면 덮어써진다.**

🔴 **USB 조이스틱(HID)은 CH1~8 만 내보낸다.** CH9 이상은 **실제 ELRS 링크로만** 검증된다.
S3 를 CH9 에 뒀을 때 USB 로 아무리 돌려도 안 잡혔던 원인이 이것이고,
2026-08-31 자 6단 실측값(1000/1182/1449/1550/1817/2000)이 틀렸던 원인이기도 하다.

---

## 4. Failsafe · 지오펜스 · RTL

| 파라미터 | 값 | 동작 |
|---|---|---|
| `NAV_RCL_ACT` | **2** | RC 상실 → RTL |
| `COM_RC_LOSS_T` | **1** s | 상실 판정 시간 |
| `COM_RCL_EXCEPT` | 0 | 예외 모드 없음 (전 모드에서 발동) |
| `NAV_DLL_ACT` | **0** | 🟡 데이터링크 상실 시 **동작 없음** — `1`(Hold) 권장 |
| `COM_LOW_BAT_ACT` | 3 | 저전압 → RTL |
| `COM_OBL_RC_ACT` | 0 | |
| `COM_DISARM_LAND` | 2 s | 착륙 후 자동 disarm |

### RTL

| 파라미터 | 값 |
|---|---|
| `RTL_RETURN_ALT` | **25** m |
| `RTL_DESCEND_ALT` | **10** m |
| `RTL_LAND_DELAY` | 0 |
| `RTL_TYPE` | 1 |
| `RTL_CONE_ANG` | 45° |

### 지오펜스

| 파라미터 | 값 |
|---|---|
| `GF_MAX_HOR_DIST` | **150** m |
| `GF_MAX_VER_DIST` | **50** m |
| `GF_ACTION` | **2** (Hold) |
| `GF_SOURCE` | 1 (GPS) |
| `GF_PREDICT` | 1 (예측 사용) |

+ `.plan` 에 **인클루전 폴리곤 6각형**. 꼭짓점의 홈 거리:
38.0 / 41.5 / 96.6 / 88.7 / 73.9 / 32.1 m — 전부 150m 원 안쪽이라
**폴리곤이 실효 경계**다.

> 🔴 **펜스도 RTL 도 원점은 "arm 한 자리"(홈)다. 이륙지점이 아니다.**
> arm 후 QGC 지도에서 홈(H) 아이콘이 기체 위에 있는지 반드시 확인.

### ARM 조건

| 파라미터 | 값 | 비고 |
|---|---|---|
| `COM_ARM_WO_GPS` | 1 | GPS 없이 arm 허용. Position·Mission 은 자체 검사가 여전히 막음 |
| `COM_DISARM_PRFLT` | 10 s | 🟡 지상테스트용 변경분 — 원복 확인 대상 |
| `COM_PREARM_MODE` | 0 | 🟡 동상 |
| `COM_ARM_MAG_ANG` | 60° | |

---

## 5. 미션 (`shade01_20260902-142426.plan`)

- 홈: **35.1810871, 128.5538216** / 고도 5 m
- 순항속도 15 m/s · 호버속도 5 m/s · 고도모드 = 상대(홈 기준)
- 랠리 포인트 없음

| # | 명령 | 위도 | 경도 | 고도 | 이전 WP 거리 | 홈 거리 |
|---|---|---|---|---|---|---|
| 1 | VTOL_TAKEOFF | 35.1810871 | 128.5538216 | 5 m | — | 0.0 m |
| 2 | WAYPOINT | 35.1809392 | 128.5539346 | 5 m | 19.4 m | 19.4 m |
| 3 | WAYPOINT | 35.1805049 | 128.5538287 | 5 m | 49.3 m | 64.8 m |
| 4 | WAYPOINT | 35.1805582 | 128.5535262 | 5 m | 28.2 m | 64.7 m |
| 5 | WAYPOINT | 35.1809775 | 128.5536296 | 5 m | 47.6 m | 21.3 m |
| 6 | VTOL_LAND | 35.1810927 | 128.5537881 | **0 m** | 19.3 m | 3.1 m |

**총 경로 163.8 m.** 전 구간 고도 5 m 통일, 착륙 0 m.
**천이 명령(`VTOL_TRANSITION`)은 미션에 없다** — 전 구간 멀티콥터 모드.

### 펜스 여유

| WP | 폴리곤까지 | 150m 원까지 |
|---|---|---|
| 1 이륙 | 22.6 m | 150.0 m |
| 2 | 21.7 m | 130.6 m |
| 3 | 23.5 m | 85.2 m |
| **4** | **11.7 m** ← 최소 | 85.3 m |
| 5 | 14.8 m | 128.7 m |
| 6 착륙 | 22.4 m | 146.9 m |

### 미션 관련 파라미터

| 파라미터 | 값 |
|---|---|
| `MIS_TAKEOFF_ALT` | 5 m (미션 고도와 일치) |
| `NAV_ACC_RAD` | 3 m (최단 구간 19.3m 대비) |
| `NAV_LOITER_RAD` | 80 m |
| `MPC_XY_CRUISE` | 3 m/s |
| `MPC_TKO_SPEED` / `MPC_LAND_SPEED` | 1.0 / 0.7 m/s |
| `MPC_Z_VEL_MAX_UP` / `_DN` | 3.0 / 1.5 m/s |

---

## 6. 센서 · EKF

| 파라미터 | 값 | 비고 |
|---|---|---|
| `EKF2_HGT_REF` | 1 (GPS) | 🟡 기압계가 GPS 대비 **−14m**. GPS 없으면 고도유지 영향 |
| `EKF2_BARO_CTRL` | 1 | |
| `EKF2_GPS_CTRL` | 7 | 위치+속도+고도 전부 |
| `EKF2_MAG_TYPE` | 0 (자동) | 🔴 EKF `mag_field` **3축 전부 이상** — 자기 간섭 |
| `CAL_MAG0_ID` | 396809 | |
| `SENS_DPRES_OFF` | **−4.51782** | 🔴 정지 시 −4.7~−5.0 m/s 잔류. **천이 전 재보정 필수** |
| `CAL_AIR_CMODEL` | 0 | |

---

## 7. VTOL 천이 · 고정익 (⚠️ 미검증)

> 🔴 **천이는 아직 한 번도 안 했다.** 에어스피드 영점이 해결될 때까지 시도 금지.
> 그 전까지는 `RC_MAP_TRANS_SW=0` 으로 CH7 매핑을 빼 두는 편이 안전하다.

| 파라미터 | 값 |
|---|---|
| `VT_F_TRANS_DUR` | 5 s (전진 천이) |
| `VT_B_TRANS_DUR` | 10 s (후진 천이) |
| `VT_F_TRANS_THR` | 1.0 |
| `VT_ARSP_TRANS` | 10 m/s (천이 완료 속도) |
| `VT_ARSP_BLEND` | 8 m/s (블렌딩 시작) |
| `VT_TRANS_MIN_TM` | 2 s |
| `VT_ELEV_MC_LOCK` | 1 |
| `FW_AIRSPD_STALL` / `MIN` / `TRIM` / `MAX` | 7 / 10 / 15 / 20 m/s |
| `FW_THR_TRIM` / `FW_THR_MAX` | 0.6 / 1.0 |

---

## 8. 이전 스냅샷과의 차이

| 항목 | 2026-08-24 | **2026-09-02** |
|---|---|---|
| 미션 고도 | 3 m | **5 m** (`MIS_TAKEOFF_ALT` 도 3→5) |
| 이륙 위치 | 별도 좌표 | **홈 = 이륙점** 일치 |
| 지오펜스 | 없음 | **150/50 + 폴리곤 6각형** |
| RTL 고도 | (기본) | **25 / 10 m** |
| `MAV_1_CONFIG` | TELEM2 활성 | **0** (포트 사망 후 정리) |
| `COM_RC_LOSS_T` | (기본 0.5) | **1 s** |
| 서보 PWM | 모터와 같은 400 Hz | **MAIN1–2 100 Hz 분리** |
| 크루즈 모터 | 미할당 | **MAIN8** 복구 |

관련 파일:
- [`QGroundControl/Missions/0824_test.plan`](../QGroundControl/Missions/0824_test.plan) — 고도 5m, 펜스 있음 (현행의 직전 판)
- [`QGroundControl/Missions/0824_test_px4.plan`](../QGroundControl/Missions/0824_test_px4.plan) — 고도 3m, 펜스 없음 (구판)
- [`QGroundControl/Parameters/px4_params_0824.params`](../QGroundControl/Parameters/px4_params_0824.params) — 4개짜리 부분 패치
- [`px4-backup/px4_v6c_backup_20260731.params`](../px4-backup/px4_v6c_backup_20260731.params) — 최초 백업

> ⚠️ [`QGroundControl/Parameters/CHANGELOG.md`](../QGroundControl/Parameters/CHANGELOG.md) 와
> `NEWVEHICLE_baseline.params` 는 **SHADE01 이 아니다.** ArduCopter 3.6.12 / Pixhawk PX4v3
> Quad X 의 기록이다. 이 기체 값과 섞지 마라.

---

## 9. 다음 비행 전 확인할 것

| # | 항목 | 관련 값 |
|---|---|---|
| 🔴 1 | **기체 육안 점검** — 8/25 3m 낙하 이력 | 프레임·모터 마운트·프롭 |
| 🔴 2 | **에어스피드 영점** — 무풍에서 재보정, ±2 이내 | `SENS_DPRES_OFF=-4.52` |
| 🔴 3 | **CH7 천이 매핑 제거** (2번 전까지) | `RC_MAP_TRANS_SW` 7 → **0** |
| 🔴 4 | **커넥터 교체** — 8/31 최대 66.8A, 453초 중 270초가 45A 초과 | XT90 → XT120/AS150 |
| 🟡 5 | **홈 위치 확인** — arm 후 지도에서 H 가 기체 위인지 | 펜스·RTL 전부 홈 기준 |
| 🟡 6 | **RX failsafe 실측** — 조종기 끄고 몇 초 만에 인지하는지 | `NAV_RCL_ACT=2`, `COM_RC_LOSS_T=1` |
| 🟡 7 | **`NAV_DLL_ACT` 0 → 1(Hold)** 검토 | RC 살아있는데 인터넷만 끊겨도 발동하므로 |
| 🟡 8 | **자기 간섭 저감** — GPS 마스트 높이기, 전력선 이격·트위스트 | `mag_field` 3축 이상 |
| 🟡 9 | **기압계 −14m** — GPS 없는 고도유지에 영향 | `EKF2_HGT_REF=1` |
| 🟡 10 | **지상테스트 임시값 원복** | `COM_DISARM_PRFLT` · `COM_PREARM_MODE` · `SYS_HAS_NUM_ASPD` |

⚠️ **CH6 RC 캘리브레이션은 하지 마라** — 2단 여유가 7us 뿐이다.
