# 펌웨어 플래시 · 복원 절차

🔴 **플래시는 파라미터를 전부 날린다.** 캘리브레이션·failsafe·고정익 차단·
액추에이터 배치가 한꺼번에 사라진다. 복원 정본 없이 시작하지 마라.

빌드는 [`BUILD.md`](BUILD.md) 가 정본이다.

## 시작 전 — 4가지를 확인한다

| | 확인 방법 |
|---|---|
| 🔴 **배터리 분리** | `SYS_STATUS` 전압이 안 오는 것. 모터가 돌 수 있다 |
| 🔴 **DISARMED** | `HEARTBEAT` 의 `MAV_MODE_FLAG_SAFETY_ARMED` |
| **USB 직결** | `/dev/ttyACM0` 존재. 무선으로 플래시하지 마라 |
| **복원 정본** | `params/px4_params_<날짜>-preflash.params` |

## 1. 파라미터 백업 — 플래시 직전에 다시 뜬다

리포에 있는 스냅샷이 최신이라고 믿지 마라. **FC 가 스스로 바꾸는 값이 있다.**

```bash
./shade01 test                      # NO-GO 면 여기서 멈춘다
.venv/bin/python tools/fc/param_backup.py params/px4_params_$(date +%Y%m%d-%H%M%S)-preflash.params
```

FC 가 자동으로 갱신하는 값 — 백업이 실기와 달라도 놀라지 마라:

| 파라미터 | 누가 쓰나 |
|---|---|
| `EKF2_MAG_DECL` | EKF ([`EKF2.cpp:2758`](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/ekf2/EKF2.cpp#L2758) `commit_no_notification()`) |
| `CAL_BARO0_OFF` | 부팅 1초 뒤 상대보정 ([`VehicleAirData.cpp:352`](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/sensors/vehicle_air_data/VehicleAirData.cpp#L352) `ParametersSave()`) |
| `_HASH_CHECK` | PX4 내부 해시 |

## 2. 🔴 플래시 전 관문 — 파라미터 diff

**이 검사를 건너뛰지 마라.** 실제로 사고를 막았다 — PX4IO 를 뺀 빌드가
`PWM_AUX_*` 52개를 없애 서보 3개를 죽일 뻔했다.

```bash
~/opt/px4-venv/bin/python - <<'EOF'
import json, io, glob
meta = json.load(io.open(
  '/home/rim3/PX4-Autopilot/build/px4_fmu-v6c_shade01/parameters.json'))
std = {p['name'] for p in meta['parameters'] if p.get('name')}
snap = sorted(glob.glob('params/*-preflash.params'))[-1]
have = set()
for line in io.open(snap, encoding='utf-8'):
    if line.startswith('#'): continue
    f = line.rstrip('\n').split('\t')
    if len(f) >= 4: have.add(f[2])
lost = sorted(have - std)
print('%s\n실기 %d개 → 사라지는 것 %d개' % (snap, len(have), len(lost)))
for n in lost: print('  ', n)
EOF
```

**사라지는 것이 나오면 하나하나 현재 값을 확인한다.** 0/-1(꺼짐)이면 안전하고,
켜져 있는 값이 사라지면 **기능이 죽는다 — 거기서 멈춰라.**

2026-09-12 실측: 10개, 전부 꺼짐 (`MNT_MODE_IN=-1`, `RC_CRSF_PRT_CFG=0`,
`SEP_PORT1/2_CFG=0`, `TC_A/B/G/M_ENABLE=0`, `UXRCE_DDS_CFG=0`, `_HASH_CHECK`).

## 3. 브리지 정지

플래시는 시리얼을 독점한다.

```bash
ssh rim3@rim3 'systemctl --user stop shade-bridge.service'
ssh rim3@rim3 'fuser /dev/ttyACM0'      # 비어 있어야 한다
```

⚠️ **`fuser` 가 뭔가를 잡고 있으면 정체를 먼저 확인하라.** `fcfetch.py` 가
로그를 받는 중일 수 있다 — 남의 작업을 끊지 마라.

```bash
ssh rim3@rim3 'ps -o pid,cmd -p $(fuser /dev/ttyACM0 2>/dev/null)'
```

## 4. 플래시

```bash
source ~/opt/px4env.sh
cd ~/PX4-Autopilot
python3 Tools/px_uploader.py --port /dev/ttyACM0 \
  build/px4_fmu-v6c_shade01/px4_fmu-v6c_shade01.px4
```

업로더가 보드를 재부팅시켜 부트로더로 들어간다. **케이블을 뽑지 마라.**
board_id 가 안 맞으면 업로더가 거부한다 — v6c 는 **56** 이다.

## 5. 파라미터 복원

부팅을 기다린 뒤(약 20초) QGC 로 복원한다.

```
QGC → Vehicle Setup → Parameters → Tools → Load from file
  params/px4_params_<날짜>-preflash.params
```

QGC 가 없으면 스크립트로도 된다:

```bash
.venv/bin/python tools/fc/param_restore.py params/px4_params_<날짜>-preflash.params
```

🔴 **복원 뒤 저장하고 재부팅한다.** 저장을 안 하면 사라진다.

## 6. 되읽기 대조 — 복원이 실제로 됐는지

```bash
.venv/bin/python tools/fc/param_backup.py /tmp/after.params
diff <(grep -P "^1\t1\t" params/px4_params_<날짜>-preflash.params | cut -f3,4 | sort) \
     <(grep -P "^1\t1\t" /tmp/after.params | cut -f3,4 | sort)
```

**차이가 나와야 정상인 것들** — 2절의 자동 갱신값과 사라진 10개뿐이어야 한다.
그 밖의 것이 다르면 복원이 덜 된 것이다.

## 7. 판정

```bash
ssh rim3@rim3 'systemctl --user start shade-bridge.service'
./shade01 test
```

**GO 가 아니면 날리지 마라.** 특히 이것들을 눈으로 확인한다:

```
RC_MAP_TRANS_SW=0 · VT_ELEV_MC_LOCK=1     고정익 차단
NAV_RCL_ACT=2 · NAV_DLL_ACT=2             failsafe
미션 이착륙 22/21                          🔴 84/85 면 천이가 걸린다
COM_FLTMODE1=3 … COM_FLTMODE6=5           조종기 5슬롯
CA_AIRFRAME=2 · PWM_MAIN_FUNC / PWM_AUX_FUNC
```

## 8. 실내 미션 검증 — GPS 없이도 된다

`checkMissionFeasible` 은 **위치가 아니라 `home_alt_valid` 만** 본다
([`navigator.h:176`](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/navigator/navigator.h#L176)).
전역 원점과 홈을 손으로 주면 실내에서도 dataman 읽기 경로까지 간다.

```
① SET_GPS_GLOBAL_ORIGIN   lat/lon/alt
② MAV_CMD_DO_SET_HOME     같은 좌표
```

**파라미터를 안 쓰므로 재부팅하면 사라진다.** 확인:

```
mission_state:  1(NO_MISSION) → 2(NOT_STARTED) 또는 3(ACTIVE)
mission_result: valid=1  warning=0
```

⚠️ **실내에서 통과했다고 고쳐진 것이 아니다.** 9/11 실패는 야외에서만 났고,
실내에서는 부하 조건이 재현되지 않는다 (미션 재검증 10회·재업로드 5회 전부 성공).

## 9. 🔴 최종 검증은 야외뿐이다

배터리를 물리고 실제로 미션을 걸어야 판정된다. 볼 것:

| | 정상 | 실패 |
|---|---|---|
| STATUSTEXT | `dataman_client timeout` **없음** | `timeout after 5000 ms!` |
| `mission_result` | `valid=1 warning=0` | `valid=0 warning=1` |
| `navigator_mission_item` | `nav_cmd=16/21` 등 | `nav_cmd=0` (빈 값) |

비행 뒤 `./shade01 sync` 로 로그를 올리고 `flights/` 에 기록한다.

## 되돌리기

문제가 생기면 표준 펌웨어로 돌아간다. **같은 백업으로 복원하면 원상 복구된다.**

```bash
cd ~/PX4-Autopilot && git checkout v1.17.0
make px4_fmu-v6c_default
python3 Tools/px_uploader.py --port /dev/ttyACM0 \
  build/px4_fmu-v6c_default/px4_fmu-v6c_default.px4
```

QGC 의 펌웨어 탭에서 안정판을 받아 굽는 방법도 있다.
