# FC 변경 기록 — 반드시 먼저 읽어라

**기체 FC(Pixhawk 6C Mini)의 설정을 바꾸는 모든 작업은 여기에 남긴다.**
파라미터 쓰기, 캘리브레이션, 펌웨어 플래시, 미션·지오펜스 업로드, 액추에이터 재배치 —
FC 안의 값이 바뀌는 일이면 전부 해당한다.

> 🔴 **작업 전에 이 파일을 읽어라.** 어느 PC 든, 어느 세션이든, 사람이든 에이전트든
> 마찬가지다. 여기에 마지막으로 무엇이 바뀌었는지 모르는 채로 FC 를 만지면,
> 스냅샷과 실기가 어긋난 것을 모르고 잘못된 값을 정본으로 착각한다.

## 왜 필요한가

FC 는 **PC 4대 어디에서나** 브리지를 통해 쓸 수 있다. 상행이 열려 있어
`PARAM_SET` 한 줄이면 값이 바뀌고, 그 순간 리포의 `params/*.params` 스냅샷은
낡은 것이 된다. 누가·언제·왜 바꿨는지가 남지 않으면 다음 사람이 알 방법이 없다.

실제로 2026-09-04 에 `.plan` 의 이착륙 명령이 VTOL 전용(84/85)에서 범용(22/21)으로
바뀌어 있는 것을 발견했는데, **언제 누가 바꿨는지 아무도 몰랐다.** 그 일이 이 파일을
만든 이유다.

## 기록 규칙

작업이 끝나면 **아래 표 맨 위에** 한 줄 추가하고, 필요하면 그 아래 상세 절을 쓴다.
**커밋·푸시까지 해야 기록이 끝난다** — 로컬에만 있으면 다른 PC 가 못 읽는다.

```bash
git add FC_CHANGELOG.md params/ config/
git commit -m "fc: <무엇을 바꿨는지>"
git push 6k5euq main
```

한 줄에 담을 것:

| 항목 | 어떻게 |
|---|---|
| 일시 | **KST** `YYYY-MM-DD HH:MM`. 로그 파일명은 UTC 이므로 헷갈리지 마라 |
| 작업 PC | Tailscale 이름 — `ku` / `rim` / `rim3` / `gram` / `raspb1`. IP 를 쓰지 말고 이름을 써라 |
| 경로 | 어느 링크로 썼나 — `raspb1 브리지` / `rim3 USB 직결` / `USB 직결` / `QGC 수동` |
| 대상 | 파라미터명·미션·펌웨어 등 |
| 변경 | `이전 → 이후`. 값이 여럿이면 상세 절에 표로 |
| 이유 | 한 줄. "왜" 가 없으면 나중에 되돌릴지 판단이 안 된다 |

작업 PC 확인:

```bash
tailscale status | head -1     # 자기 이름
hostname
```

## 지켜야 할 것

- 🔴 **ARM 상태에서 쓰지 마라.** 쓰기 전에 `HEARTBEAT` 의 `MAV_MODE_FLAG_SAFETY_ARMED`
  를 확인한다. 배터리가 연결돼 있으면 모터가 돌 수 있다.
- 🔴 **쓴 뒤에는 저장하고 되읽어라.** `MAV_CMD_PREFLIGHT_STORAGE`(param1=1) 를 보내
  `ACCEPTED` 를 받고, 같은 파라미터를 다시 읽어 값을 확인한다. 저장을 안 하면
  **재부팅 때 사라진다.**
- 🔴 **int 파라미터는 float 비트로 오간다.** `RC_MAP_TRANS_SW=7` 을 float 로 읽으면
  `9.8e-45` 로 보인다. `struct.unpack('<i', struct.pack('<f', v))` 로 되돌려야 한다.
  쓸 때도 `MAV_PARAM_TYPE_INT32` 로 보낸다.
- 🟡 **바꿨으면 스냅샷을 새로 받아라.** `params/px4_params_<YYYYMMDD-HHMMSS>.params`.
  안 받으면 리포의 정본이 실기와 어긋난 채로 남는다.
- 🟡 **정본은 언제나 FC 다.** 이 파일과 스냅샷은 기록일 뿐이다. 비행 전에는
  QGC 로 실제 값을 다시 확인한다.

---

## 변경 이력

| 일시 (KST) | PC | 경로 | 대상 | 변경 | 이유 |
|---|---|---|---|---|---|
| 2026-09-05 17:18 | `ku` | `ku` USB 직결 | `MAV_0_RATE` | `490` → **`300`** | "Sensor lost" 추적 중 대역폭 포화로 오진해 낮췄다. **근거 약함 — 되돌릴 것.** 아래 절 |
| 2026-09-05 17:15 | `ku` | `ku` USB 직결 | `RTL_RETURN_ALT` `RTL_DESCEND_ALT` `MPC_THR_HOVER` | `60`→**`20`** / `30`→**`10`** / `0.50`→**`0.65`** | 순항 5 m 인데 RTL 이 60 m 로 솟았다. 호버추력은 FC 자체 추정과 30% 어긋나 있었다 |
| 2026-09-05 16:45 | `ku` | `ku` USB 직결 | `NAV_ACC_RAD` · 미션 `.plan` | `10` → **`3`** / 이착륙 84·85 → **22·21** | RTK 실측 eph 0.14 m — 10 m 는 과했다. 미션이 고정익 전환을 걸고 있었다 |
| 2026-09-05 15:50 | `ku` | rim3 USB 직결 | `PWM_AUX_TIM0~2` | `400` → **`100`** | AUX1~3 은 서보뿐 — 400Hz 는 아날로그 서보에 과하다 |
| 2026-09-05 15:12 | `ku` | rim3 USB 직결 | `PWM_AUX_DIS2` | `1400` → **`1500`** | 러더만 disarm 중립이 아니어서 arm 할 때 튀었다 |
| 2026-09-05 14:16 | `ku` | rim3 USB 직결 | `GF_ACTION` `GF_MAX_HOR_DIST` `GF_MAX_VER_DIST` `NAV_DLL_ACT` | 아래 절 | 지오펜스 해제 · 데이터링크 두절 시 RTL |
| 2026-09-05 14:04 | `ku` | rim3 USB 직결 | 미션·RTL·failsafe 6개 | 아래 표 | 공개 로그 16대 대조에서 우리 값이 최저 이상치 |
| 2026-09-04 16:37 | `ku` | rim3 USB 직결 | `RC_MAP_KILL_SW` `RC_MAP_RETURN_SW` `COM_FLTMODE1~6` | 아래 절 | 조종기 채널 재배치 (SB/SC/SF 구성) |
| 2026-09-04 16:32 | `ku` | rim3 USB 직결 | `RC_MAP_TRANS_SW` | `7` → **`0`** | 고정익 사용 중지 — 쿼드 전용 제한 |

### 2026-09-05 17:18 — `MAV_0_RATE` 490→300 (조종기 "Sensor lost" 추적)

**작업**: `ku` USB 직결(`/dev/ttyACM0`). `PARAM_SET` → `PREFLIGHT_STORAGE` **ACCEPTED**
→ 되읽기 `300` 확인. DISARM. 배터리 연결 상태(25.0 V).

| 파라미터 | 이전 | 이후 |
|---|---|---|
| `MAV_0_RATE` | `490` | **`300`** |

🔴 **이 변경은 근거가 약하다. 다음 작업 때 `490` 으로 되돌려라.**
ELRS 하향을 "대역폭 포화"로 오진해 낮췄으나, 실측 결과 포화가 아니었다(아래).
ELRS 실측 처리량이 ~400 B/s 인데 300 으로 묶어 오히려 조인 셈이다.

#### 이번 세션에서 실측·규명한 것

**증상**: 조종기에서 "Sensor lost" 음성이 불규칙(약 5 초)하게 반복.

| 측정 | 값 | 방법 |
|---|---|---|
| ELRS 실제 처리량 | **282~419 B/s** | rim3 백팩 WiFi(`10.0.0.1:14555`) 카운터 |
| 333 Hz Full 이론 상한 | 1470 B/s | ELRS 공식 문서 |
| **실사용률** | **약 20~27%** | 포화 아님 |
| 조종기 `cur` 갱신 | 최대 **51.8 s** 공백 | rim3 페이지 90 초 폴링 |

**ELRS 가 CRSF 센서로 변환하는 MAVLink 메시지는 12 종뿐이다**
(`ExpressLRS/src/lib/MAVLink/MAVLink.cpp` 의 `case` 문):
`BATTERY_STATUS` `GPS_RAW_INT` `GLOBAL_POSITION_INT` `ATTITUDE` `HEARTBEAT`
`STATUSTEXT` `VFR_HUD` `SYSTEM_TIME` `SCALED_PRESSURE` `HOME_POSITION`
`ALTITUDE` `HIGH_LATENCY2`. **나머지 스트림은 조종기에 아무 영향이 없다.**

| EdgeTX 센서 | 공급 MAVLink |
|---|---|
| `RxBt` `Curr` `Capa` `Bat%` | `BATTERY_STATUS` |
| `GPS` `GSpd` `Hdg` `GAlt` `Sats` | `GPS_RAW_INT` |
| `Ptch` `Roll` `Yaw` | `ATTITUDE` |
| `Temp` | `SCALED_PRESSURE` |
| `Date` | `SYSTEM_TIME` |
| `VSpd` | `GLOBAL_POSITION_INT` |

**경보는 전역이다.** EdgeTX `radio/src/telemetry/telemetry.cpp`:

```c
if (item.timeout == 0) { item.setOld(); sensorLost = true; }
if (sensorLost && TELEMETRY_STREAMING() && !g_model.disableTelemetryWarning)
    audioEvent(AU_SENSOR_LOST);
```

등록된 26 개 센서 중 **하나만 timeout 돼도** 소리가 난다.

**유력 원인**: `SYSTEM_TIME`(=`Date` 센서)이 PX4 NORMAL 기본값에서 **0.2 Hz(5 초 간격)**.
EdgeTX stale 판정을 매 주기 넘긴다. `Delete All` + `Discover` 를 반복해도
`Date` 는 5 초에 한 번이라도 오므로 **다시 등록되고 다시 stale** — 그래서 삭제로
안 없어졌다. "약 5 초 간격" 증상과 주기가 일치한다.
**미검증**: 조종기에서 재발 여부를 확인해야 확정된다.

**`VSpd` 는 실내에서 구조적으로 불가**: `GLOBAL_POSITION_INT` 은 EKF 전역 위치가
유효할 때만 발행된다. 실측 `ekf.pos_abs=false` → 0 Hz. 야외에서 잡히더라도
`shade.lua` 가 안 쓰므로 지우는 편이 안전하다.

#### 🔴 스트림 레이트는 **MAVLink 인스턴스별**이다 — 이번 세션 최대 함정

`SET_MESSAGE_INTERVAL` 은 **명령을 받은 인스턴스에만** 적용된다.
`mavlink_receiver.h:129,252` (`MavlinkReceiver(Mavlink &parent)`, `Mavlink &_mavlink`)
→ `mavlink_receiver.cpp:2249` 의 `_mavlink.configure_stream_threadsafe()`.

**이번 세션의 스트림 조정은 전부 USB 인스턴스로 갔고, TELEM1(ELRS)에는
한 번도 적용되지 않았다.** ku USB 직결도, rim3 브리지(rim3 의 `/dev/ttyACM0`)도
모두 USB 인스턴스다. ELRS 처리량이 무엇을 하든 안 변한 이유가 이것이다.

**TELEM1 을 바꾸려면 장치를 명시해야 한다** (TELEM1 = `/dev/ttyS5`, fmu-v6c):

```
mavlink stream -d /dev/ttyS5 -s BATTERY_STATUS -r 4
```

`SET_MESSAGE_INTERVAL` 로 하려면 **그 링크를 통해** 보내야 한다.

⚠️ **`SET_MESSAGE_INTERVAL` 은 런타임 전용이다.** `mavlink_receiver.cpp:2249` 는
`configure_stream_threadsafe()` 만 호출하고 저장 코드가 없다 —
`PREFLIGHT_STORAGE` 로도 안 남고 **재부팅하면 사라진다.**
영구화하려면 SD 카드 `/fs/microsd/etc/extras.txt` 뿐이다 (`rcS:599-603`).

🔴 **`extras.txt` 에는 이미 내용이 있다. 덮어쓰지 마라:**

```
ms5525dso start -X -b 2 -a 0x76
```

에어스피드 센서 기동 줄이다(32 바이트). 지우면 에어스피드가 안 뜬다. **추가만 하라.**

#### 다음 작업 때 할 일

1. `MAV_0_RATE` 를 **490 으로 복구** (300 은 근거 없음)
2. `extras.txt` 에 **추가**(기존 줄 보존) — TELEM1 명시:
   `SYSTEM_TIME -r 2`(Sensor lost 대책), `BATTERY_STATUS -r 4`(전류 갱신),
   `ODOMETRY`/`HIGHRES_IMU`/`ATTITUDE_QUATERNION`/`LOCAL_POSITION_NED` `-r 0`
3. FC 재부팅 후 **rim3 백팩 페이지로 검증** (ELRS 경로가 유일한 실검증 경로)

#### 참고 — 확인된 정상 동작 (오해하기 쉬움)

- **PM08 전류 센서 정상.** DISARM 0.60 A → 모터 회전 시 **2.77 A** 로 반응.
  `mah` 적산도 일치(6 mAh/34 s ≈ 0.635 A). 지상 정지 시 값이 안 변하는 것은
  실제로 전류가 일정하기 때문이지 고장이 아니다.
- 🔴 **지상 STABILIZED ARM 시 모터가 저절로 증가한다.** 실측: 스로틀 스틱을
  1039 → 988(최저)로 **내렸는데** 출력은 6% → 8% 로 올랐고, 모터 편차가
  34 → 142 로 4 배 벌어졌다. `MulticopterRateControl.cpp:220` 의 적분기는
  `_maybe_landed || _landed` 일 때만 동결되므로, 스로틀을 올려 착륙 판정이
  풀리면 지면이 자세 오차를 막는 동안 I-term 이 계속 쌓인다.
  **지상 출력·전류 시험은 STABILIZED 로 하지 말고 QGC 모터 테스트를 쓸 것.**
  프로펠러를 반드시 제거하고, KILL(SE)을 즉시 쓸 수 있게 둘 것.

### 2026-09-05 17:15 — RTL 고도 60→20 m, 호버추력 0.50→0.65

**작업**: `ku` USB 직결(`/dev/ttyACM0`). `PARAM_SET` → `PREFLIGHT_STORAGE` **ACCEPTED**
→ 되읽기 확인. DISARM. 근거는 [미션 사전 검토](flights/2026-09-05-mission-preflight-review.md).

| 파라미터 | 이전 | 이후 | 왜 |
|---|---|---|---|
| `RTL_RETURN_ALT` | `60` | **`20`** | 순항 5 m 인데 RTL 이 60 m 로 솟았다 |
| `RTL_DESCEND_ALT` | `30` | **`10`** | 복귀고도를 낮췄으니 같이 내린다 |
| `MPC_THR_HOVER` | `0.50` | **`0.65`** | FC 자체 추정치가 세 비행 모두 0.63~0.65 |

#### 🔴 RTL 이 순항고도의 12배로 솟고 있었다

`RTL_CONE_ANG=45`("집 근처면 낮게 복귀")는 [rtl.cpp:538](PX4-Autopilot/src/modules/navigator/rtl.cpp#L538)
에서 **`RTL_MIN_DIST`(10 m) 안쪽일 때만** 적용된다. 미션 웨이포인트는 19~65 m 에 있어
cone 이 한 번도 켜지지 않고 `RTL_RETURN_ALT` 가 전량 적용됐다 — **미션 어느 지점에서
RTL 이 걸려도 60 m.**

RTL 은 조작 없이도 걸린다: `NAV_DLL_ACT=2`(GCS 두절 10초), `NAV_RCL_ACT=2`(RC 두절 1초),
`COM_LOW_BAT_ACT=3`(잔량 15%). **마당에서 링크가 잠깐 끊기면 기체가 60 m 로 솟는다.**

9/5 14:04 에 25 → 60 으로 올린 것은 함대 중앙값 근거였는데, 그 함대는 수백 m 를 나는
기체들이다. 이 미션 규모에 맞지 않았다.

**적대적 검증** — 20 m 가 오히려 빠르다:

| | 60 m | 20 m |
|---|---|---|
| 최원점(64.7 m)에서 RTL 총 소요 | 103초 | **48초** |

`RTL_DESCEND_ALT=10` 은 `MPC_LAND_ALT1=10` 과 겹쳐, loiter 고도 도달 즉시 착륙 감속에
들어간다 — 급강하 구간이 없다.

⚠️ **주변에 15~20 m 급 고압선이 있으면 20 m 로는 부족하다.** 가로수·전신주(8~12 m)는
문제없다. 현장 확인 대상.

#### 호버추력이 실제와 30% 어긋나 있었다

`hover_thrust_estimate` 토픽이 세 비행 모두 **0.632 / 0.646 / 0.647** 을 냈다.
설정값 0.50 은 실제보다 한참 낮았다.

**적대적 검증** — 착륙 감지를 망가뜨리지 않는다. 저추력 판정선이 0.300 → 0.390 으로
오르지만([MulticopterLandDetector.cpp:217](PX4-Autopilot/src/modules/land_detector/MulticopterLandDetector.cpp#L217)),
9/2 로그의 착륙 직전 실제 추력은 **최저 0.120** 이다. 여유가 크다.

이 값은 HTE 초기값일 뿐이고 비행 중에는 실시간 추정이 덮으므로
([:106](PX4-Autopilot/src/modules/land_detector/MulticopterLandDetector.cpp#L106)),
맞춰두면 **이륙 직후 수렴 전 구간이 안정된다.**

⚠️ **호버에 65%를 쓴다 = 여유가 35% 뿐이다.** log_184 에서 모터 하나가 1.00 포화에
닿았다. 파라미터로 풀 문제가 아니라 **경량화 또는 추력 증대** 대상이다.

#### ❌ 배터리 잔량 — 앞선 진단(16:45 검토)은 틀렸다

같은 날 검토서가 "잔량 추정이 실제와 어긋난다" 고 적었으나 **오진이었다.** 손대지 않았다.

- `discharged_mah` 는 **부팅 후 누적**인데 비행별 잔량과 직접 비교했다
- `BAT1_R_INTERNAL=-1.0` 은 "꺼짐"이 아니라 **"자동추정 사용"**이다
  ([battery.cpp:228](PX4-Autopilot/src/lib/battery/battery.cpp#L228)). 실제 추정값
  0.0014 Ω/셀은 6S 리포 통상 범위 안이다

SoC 는 전류적산과 전압을 **의도적으로 융합**한다
([battery.cpp:287](PX4-Autopilot/src/lib/battery/battery.cpp#L287)). log_187 끝에서
적산 27.5% vs FC 보고 15.2% 였는데, 16000 mAh 팩에서 11595 mAh 를 썼으면 6S 리포
권장 사용량(80% DoD = 12800 mAh)의 **91%** 다 — **FC 쪽이 현실적이다.**

⚠️ 다만 셀당 **3.628 V** 까지 간 것은 사실이다. 설정이 아니라 **운용에서 더 일찍
회수해야 한다**는 뜻이다.

**스냅샷**: `params/px4_params_20260905-171500.params` (1353개). 이전 대비 차이는
위 3개 + `COM_FLIGHT_UUID`·`LND_FLIGHT_T_LO`(자동 증가) 뿐이다.

### 2026-09-05 16:45 — 미션 검토: 도달반경 3 m, 이착륙을 쿼드 전용으로

**작업**: `ku` 에 FC 를 **USB 직결**(`/dev/ttyACM0`, `usb-Auterion_PX4_FMU_v6C.x_0`)하고
`PARAM_SET` → `PREFLIGHT_STORAGE` **ACCEPTED** → 되읽기 확인. DISARM·배터리 연결(25.0 V).
`NAV_ACC_RAD` 는 항법 파라미터라 액추에이터가 움직이지 않는다.

| 대상 | 이전 | 이후 | 왜 |
|---|---|---|---|
| `NAV_ACC_RAD` (FC) | `10` | **`3`** | 아래 실측 |
| `.plan` seq 0 | `84` VTOL_TAKEOFF | **`22`** TAKEOFF | 미션이 고정익 전환을 걸고 있었다 |
| `.plan` seq 5 | `85` VTOL_LAND | **`21`** LAND | 위와 같음 |
| `.plan` geoFence | 6각형 inclusion | **제거** | FC 는 이미 `FENCE count=0` — 9/5 14:16 에 끈 것과 맞춤 |

#### 🔴 `.plan` 의 `VTOL_TAKEOFF`(84) 는 고정익 진입 경로였다

이름과 달리 **"수직으로 떠서 → 고정익으로 전환하라"** 는 뜻이다.
[mission.cpp:380](PX4-Autopilot/src/modules/navigator/mission.cpp#L380) 이 상승 후
`set_vtol_transition_item(..., VEHICLE_VTOL_STATE_FW)` 를 부른다 — **스위치를 거치지 않는다.**

9/4 기록은 "미션 이착륙 = `NAV_FORCE_VT=1` + `.plan` 84/85 이므로 진입 경로 닫힘" 이라고
적었으나 **틀렸다.** `force_vtol()` 은
[navigator_main.cpp:1311](PX4-Autopilot/src/modules/navigator/navigator_main.cpp#L1311)
에서 **기체가 이미 FW 일 때만** true 이므로, 84 를 막는 역할을 전혀 하지 않는다.
`RC_MAP_TRANS_SW=0` 으로 스위치를 닫아도 **미션 시동만으로 전환이 걸렸다.**

실기 FC 의 미션은 다행히 `22`/`21` 이었다(9/4 에 발견만 하고 실기는 안 고친 그 불일치).
그래서 실제로 열려 있던 적은 없다. `.plan` 을 실기에 맞춰 `22`/`21` 로 내렸다.

⚠️ **고정익을 풀 때** — 에어스피드 영점(`SENS_DPRES_OFF=-4.52`)을 잡은 뒤 —
`.plan` 을 `84`/`85` 로 되돌린다. 순서를 바꾸지 마라.

#### `NAV_ACC_RAD` 을 10 에서 3 으로 내린 근거 — 9/2 야외 로그 실측

9/5 14:04 에 `3` → `10` 으로 올리며 "3 m 는 GPS 오차와 비슷해 못 찍고 맴돌 수 있다" 고
적었는데, **실측 없이 함대 중앙값만 보고 쓴 것이었다.** 이 기체는 RTK 가 잡힌다.

| 로그 | eph 평균 | 위성 | fix | 수평 추종오차 최대 |
|---|---|---|---|---|
| `log_177_2026-9-2-17-37-16` | 0.136 m | 25.0 | **4** | 0.30 m |
| `log_184_2026-9-2-17-57-06` | 0.108 m | 25.6 | **4** | 0.24 m |
| `log_187_2026-9-2-18-05-26` | 0.141 m | 25.7 | **4** | 0.36 m |

EKF 수평정확도도 세 비행 전부 0.20 m 이하. 3 m 반경은 실측 오차의 **8배 여유**다.

미션 최단 레그가 19.4 m 이므로 반경 10 m 는 도달 원이 거의 맞닿아 웨이포인트를 뭉갤 수
있었다. 3 m 면 원 사이 13.4 m 가 남는다.

⚠️ **RTK 가 안 잡히는 날**(`fix=3`, 위성 적음)은 eph 가 1~2 m 로 뛴다. 그때는 3 m 가
빠듯하다 — 비행 전 QGC 에서 fix 상태를 확인한다.

#### 미션 자체는 의도대로다

홈에서 5 m 상승 → 웨이포인트 4개를 5 m 로 순회 → 이륙점에서 3.1 m 떨어진 지점에 착륙.
`frame=6`(`GLOBAL_RELATIVE_ALT`)이라 **홈 기준 상대고도**다. 총 경로 163.6 m.

`MIS_TAKEOFF_ALT=20` 은 미션이 고도를 명시하지 않을 때만 쓰는 기본값이라 이 미션에는
영향이 없다 — 5 m 는 의도된 값이다.

**스냅샷**: `params/px4_params_20260905-164500.params` (1353개).
이전 스냅샷 대비 차이는 `NAV_ACC_RAD` 외에 `COM_FLIGHT_UUID`·`LND_FLIGHT_T_LO`(자동 증가),
`MAV_0_RATE`(USB 직결이라 TELEM1 과 다르게 보고), `_HASH_CHECK`(계산값) 뿐이다.

### 2026-09-05 15:50 — AUX 타이머 400 → 100 Hz

**작업**: `ku` 에서 `rim3` USB 직결 브리지로 `PARAM_SET` → `PREFLIGHT_STORAGE` **ACCEPTED**
→ 되읽기 확인. DISARM.

`PWM_AUX_TIM0` `PWM_AUX_TIM1` `PWM_AUX_TIM2` 를 전부 `400` → **`100`**.

AUX 에 실린 것은 **서보 3개뿐**이다 (AUX1 Servo4·엘리베이터, AUX2 Servo5·러더,
AUX3 Servo3·엘리베이터). 모터가 하나도 없으므로 타이머를 내려도 추력에 영향이 없다.
400 Hz 는 아날로그 서보에 과하다 — 참조 함대 12대의 `PWM_AUX_TIM0` 중앙값도 50 Hz 다.

MAIN 쪽은 건드리지 않았다. `PWM_MAIN_TIM0=100`(에일러론 서보), `TIM1`·`TIM2`=400(모터)
구성은 [출력 배치](README.md#출력-배치-2026-09-01-실측) 대로 의도된 것이다.

### 2026-09-05 15:12 — 러더 disarm 값 1400 → 1500

**작업**: 같은 경로·절차. DISARM, 배터리 연결(25.06 V) 상태 — 서보만 움직이고 모터는 돌지 않는다.

`PWM_AUX_DIS2`(Servo5 = 러더) 만 `1400` 이었다. 나머지 서보 넷은 전부 `1500`(중립)이다.

**증상**: `PWM_*_DIS*` 는 **disarm 전용** 값이라 arm 하는 순간 제어기 출력(중립 1500)으로
바뀐다. 그래서 **arm 할 때마다 러더가 100 us 튀었다.**

**원인 추정**: 기계적 중립이 안 맞는 것을 disarm 값으로 덮어둔 것으로 보인다. 누가 언제
넣었는지 기록이 없다. 실제로 1500 으로 되돌리자 **러더가 오른쪽으로 틀어진 채로 남았다** —
기계적 오차가 드러난 것이다.

⚠️ **`PWM_*_DIS*` 로 중립을 맞추지 마라.** arm 하면 사라진다. 순서는:

1. 링키지·서보 혼으로 **기계적 조정** (배터리 분리 후, 조종면을 강제로 돌리지 말 것)
2. 남는 미세 오차만 `CA_SV_CS*_TRIM` (`CS0` 좌에일러론 / `CS1` 우에일러론 / `CS4` 러더).
   arm·disarm 무관하게 적용된다. 범위 −1.0~+1.0, 100 us ≈ 0.2
3. `PWM_*_DIS*` 는 1500 그대로

`PWM_*_CENTER*` 는 이 기체에 없다 — 있으면 PX4 가 `CA_SV_CS*_TRIM` 을 강제로 0 으로
리셋한다([ActuatorEffectivenessControlSurfaces.cpp:123](PX4-Autopilot/src/modules/control_allocator/VehicleActuatorEffectiveness/ActuatorEffectivenessControlSurfaces.cpp#L123)).

**남은 정비** — 셋 다 기계 조정 대상이고 소프트웨어로 덮지 않았다:

| 조종면 | 상태 |
|---|---|
| 러더 | 중립(1500)에서 **오른쪽으로 틀어짐** |
| 좌 에일러론 | **아래로 처짐** |
| 우 에일러론 | **아래로 처짐** |

에일러론이 좌우 같은 방향으로 처진 것은 서보 혼 각도나 링키지 유격을 의심할 만하다.
고정익에서 양쪽이 플랩처럼 작용해 항력이 늘고 트림이 어긋나므로 **전환을 풀기 전에 잡아야 한다.**

**스냅샷**: `params/px4_params_20260905-155034.params` (1354개).

### 2026-09-05 14:16 — 지오펜스 해제, 데이터링크 두절 시 RTL

**작업**: `ku` 에서 `rim3` USB 직결 브리지로 `PARAM_SET` → `PREFLIGHT_STORAGE` **ACCEPTED**
→ 되읽기 확인. DISARM·배터리 미연결.

| 파라미터 | 이전 | 이후 | 왜 |
|---|---|---|---|
| `GF_ACTION` | `2` (Hold) | **`0`** (없음) | 조종자 판단 — 아래 참조 |
| `GF_MAX_HOR_DIST` | `150` | **`0`** | 제한 없음 |
| `GF_MAX_VER_DIST` | `50` | **`0`** | 제한 없음 |
| `NAV_DLL_ACT` | `0` (무시) | **`2`** (RTL) | 함대 18대 중 12대가 `2` |

**지오펜스를 끈 이유**: `GF_ACTION=2`(Hold)가 [비행 #184 조종 불능](flights/2026-09-02-log184-geofence-lockout.md)
의 직접 원인이었다 — 위반 판정 순간 FC 가 조종권을 뺏고 33 m 상공에 정지시켰고, 조종자는
원인을 모른 채 스로틀이 먹지 않는 상황을 겪었다. 참조 함대 **18대 전원이 `GF_MAX_HOR_DIST=0`**
(지오펜스 미사용)이다.

⚠️ **끈 대가**: 이제 기체가 시야 밖으로 나가도 FC 는 아무것도 하지 않는다. 거리 관리는
전적으로 조종자 몫이다. 펜스를 다시 쓰고 싶되 조종권은 지키고 싶다면 `GF_ACTION=1`(경고만)
이 중간 선택지다 — Hold 로 되돌리지 마라.

**`NAV_DLL_ACT` 를 올린 이유**: 같은 날 `COM_RC_IN_MODE` 를 `0`→`3` 으로 바꿔 MAVLink 도
조종 소스가 됐다. 그 상태에서 `NAV_DLL_ACT=0` 이면 **데이터링크가 끊겨도 아무 일이 없다** —
미션 중이라면 감시가 끊긴 채 계속 난다. `2`(RTL)로 올려 RC 두절(`NAV_RCL_ACT=2`)과 같은
동작을 하게 맞췄다.

**스냅샷**: `params/px4_params_20260905-141636.params` (1354개).

### 2026-09-05 14:04 — 미션·RTL·failsafe 6개 (함대 대조 기반)

**작업**: `ku` 에서 `rim3` USB 직결 브리지로 `PARAM_SET` → `PREFLIGHT_STORAGE` **ACCEPTED**
→ 되읽기 확인. DISARM·배터리 미연결.

| 파라미터 | 이전 | 이후 | 함대 중앙값 (n=16) | 왜 |
|---|---|---|---|---|
| `MIS_TAKEOFF_ALT` | `5` | **`20`** | 20 (범위 7~70) | 5 m 는 **16대 최저(7)보다 낮았다**. 미션 이륙 직후 첫 웨이포인트로 향하는 고도라 나무·전선 높이면 위험 |
| `RTL_RETURN_ALT` | `25` | **`60`** | 60 (범위 50~150) | RTL 은 직선 복귀 + 지형회피 없음. 25 는 **최저(50)의 절반** |
| `RTL_DESCEND_ALT` | `10` | **`30`** | 30 (범위 30~70) | 함대 **전원 30 이상**. 10 은 범위 밖 |
| `NAV_ACC_RAD` | `3` | **`10`** | 10 (범위 2~15) | 웨이포인트 도달 판정 반경. 3 m 는 GPS 오차와 비슷해 못 찍고 맴돌 수 있다 |
| `COM_POS_FS_EPH` | `5` | **`10`** | 50 (범위 5~200) | GPS 정확도 failsafe 임계. 5 는 최저값이라 잠깐 나빠져도 미션이 끊긴다 |
| `COM_RC_IN_MODE` | `0` | **`3`** | 3 (범위 1~3) | `0`(RC only)은 **16대 중 우리뿐**. PX4 기본값이자 함대 중앙값인 `3`(RC 또는 MAVLink, 먼저 잡힌 쪽 유지)으로 |

**근거**: [logs.px4.io](https://logs.px4.io/) 공개 DB(CC-BY) 458,577건에서 `VTOL Standard` +
미션 비행 + 무오류 + PX4 1.16~1.17 실기로 좁혀 **9개 제조사 16대**의 파라미터를 뽑아 대조했다.
전류·배터리 임계, 진동 필터, GPS 요구조건, 멀티콥터 속도는 **전부 중앙값과 일치**해 손대지 않았다.

**손대지 않은 이상치** — 에어스피드 4개(`FW_AIRSPD_STALL/MIN/TRIM/MAX` = 7/10/15/20)와
`VT_ARSP_TRANS`(10)는 함대 범위 밖이지만 **전부 PX4 공장 기본값 그대로**다. 이 기체의 실제
실속·순항 속도를 잰 적이 없어 남의 기체 숫자를 넣을 수 없다. 영점(`SENS_DPRES_OFF`)을
잡고 실측한 뒤에 정한다. 지금은 고정익이 막혀 있어 쓰이지 않는다.

**스냅샷**: `params/px4_params_20260905-140408.params` (1354개).

### 2026-09-04 16:37 — 조종기 채널 재배치에 따른 FC 매핑

**작업**: 같은 경로·같은 절차. 조종기 스위치 배치를 P3 6단 로터리에서 **SB(3단) + SC(3단) +
SF(모멘터리)** 구성으로 바꾸면서 FC 쪽 매핑을 맞췄다.

| 파라미터 | 이전 | 이후 | 의미 |
|---|---|---|---|
| `RC_MAP_KILL_SW` | `8` | **`9`** | SE → CH9 |
| `RC_MAP_RETURN_SW` | `9` | **`0`** | RTL 을 전용 스위치가 아니라 `COM_FLTMODE6` 슬롯으로 |
| `COM_FLTMODE1` | `8` | **`3`** | Mission (SC 위 + SF) |
| `COM_FLTMODE2` | `1` | **`8`** | Stabilized (SB 위) |
| `COM_FLTMODE3` | `2` | **`1`** | Altitude (SB 중간) |
| `COM_FLTMODE4` | `2` | `2` | Position (SB 아래) |
| `COM_FLTMODE5` | `3` | **`2`** | Position (미사용 슬롯 안전값) |
| `COM_FLTMODE6` | `5` | `5` | Return (SC 아래 + SF) |

⚠️ `RC_MAP_RETURN_SW` 를 **반드시 `0` 으로 내려야 한다.** `9` 로 두면 CH9 이 KILL 과 RTL 을
동시에 걸어 버린다.

실기 검증 12항목은 [스위치 매핑](components/transmitters/radiomaster-boxer/switch-mapping.md) 참조.

### 2026-09-04 16:32 — `RC_MAP_TRANS_SW` 7 → 0 (쿼드 전용)

**작업**: `ku` 에서 `rim3` USB 직결 브리지를 통해 `PARAM_SET`.
`MAV_CMD_PREFLIGHT_STORAGE` 로 저장 후 되읽어 `0` 확인. DISARM·배터리 미연결 상태.

**이유**: 에어스피드가 정지 상태에서 −5 m/s 를 읽는다(`SENS_DPRES_OFF=-4.52`).
고정익 구간에서 대기속도를 잘못 읽으면 실속이므로, 천이 자체를 못 하게 막았다.
CH7(SD 스위치)이 유일하게 열려 있던 진입 경로였다.

**같이 확인한 것** — 나머지 진입 경로 셋은 이미 닫혀 있었다:

| 경로 | 값 |
|---|---|
| 미션 이착륙 | `NAV_FORCE_VT=1`, `.plan` 이 `VTOL_TAKEOFF`(84)/`VTOL_LAND`(85) |
| 비행모드 슬롯 | 6슬롯 = STAB / ALT / POS / POS / Mission / RTL — 고정익 없음 |
| MC 제어면 | `VT_ELEV_MC_LOCK=1` |

**되돌리는 법**: 에어스피드 영점을 먼저 해결한 뒤 `RC_MAP_TRANS_SW=7`.
순서를 바꾸지 마라. [README 고정익 사용 금지](README.md#-고정익-사용-금지--쿼드-전용-2026-09-04) 참조.

**스냅샷**: `params/px4_params_20260904-163723.params` (1354개).

### 2026-09-04 — 스냅샷 대조에서 발견한 미기록 변경

9/4 스냅샷을 9/2 것과 대조하니 **우리가 바꾸지 않은 값들이 달라져 있었다.**
언제 누가 바꿨는지 기록이 없다 — 이 파일이 없었기 때문이다.

| 파라미터 | 2026-09-02 | 2026-09-04 | 성격 |
|---|---|---|---|
| `CAL_ACC0_XOFF` 외 가속도 오프셋 6개 | | | **가속도계 재캘리브레이션** |
| `CAL_GYRO1_XOFF` 외 자이로1 오프셋 3개 | | | **자이로 재캘리브레이션** |
| `CAL_MAG0_XOFF` 외 지자기 오프셋 3개 | | | **지자기 재캘리브레이션** |
| `CAL_BARO0_OFF` | `-251.46` | `158.69` | **기압계 재캘리브레이션** — 부호가 뒤집혔다 |
| `SENS_EN_MS5525DS` | `1065353216` | `1` | 이전 스냅샷이 float 비트를 정수로 잘못 적은 것 |
| `MAV_0_RATE` | `0` | `490` | TELEM1 전송률 |
| `COM_FLIGHT_UUID` | `174` | `193` | 비행 횟수 카운터 (자동 증가, 정상) |
| `LND_FLIGHT_T_HI` / `_LO` | | | 누적 비행시간 (자동 증가, 정상) |
| `_HASH_CHECK` | | | 파라미터 해시 (자동, 정상) |

⚠️ **`CAL_BARO0_OFF` 가 −251.46 → +158.69 로 바뀐 것은 그냥 넘길 값이 아니다.**
README 가 "기압계가 GPS 대비 −14m" 라고 적고 있는데, 그 관측이 어느 쪽 값 기준인지
불명확해졌다. **다음 비행 전에 기압고도를 다시 확인해야 한다.**

뒤 4개(`COM_FLIGHT_UUID`, `LND_FLIGHT_T_*`, `_HASH_CHECK`)는 FC 가 스스로 올리는
값이라 사람의 변경이 아니다 — 스냅샷 diff 에서 무시해도 된다.
