---
name: qgc-log
description: PX4/QGC 비행 로그(.ulg) 목록·분석. "qgc log list" 로 최근 비행을 번호로 나열하고 "qgc log N" 으로 그 비행을 분석해 문제·잘된점·다음 할일을 리포트한다. 비행 후 디브리핑, 진동/전류/EKF/에어스피드 이상 진단, 사고 원인 추적에 사용.
---

# qgc-log — 비행 로그 분석

PX4 ULog 를 읽어 **무엇이 문제였고, 무엇이 잘 됐고, 다음에 뭘 고쳐야 하는지**를 뽑는다.

**이 스킬은 SHADE_parts 리포가 정본이다** (`skills/qgc-log/SKILL.md`).
`~/.claude/skills/qgc-log` 는 그쪽을 가리키는 심볼릭이다 — 사본을 만들지 마라.
판정 임계값이 이 기체 하드웨어에 묶여 있어 기체 문서와 함께 버전 관리되어야 한다.

도구 본체:

```
<SHADE_parts>/tools/qgclog/qgclog        런처 (bash)
<SHADE_parts>/tools/qgclog/qgclog.py     분석기 (python)
<SHADE_parts>/qgc                        진입점 — ./qgc log ...
```

## 사용법

```bash
qgclog list          # 최근 로그 나열 — 1 이 가장 최근
qgclog 1             # 1번 로그 분석
qgclog <path.ulg>    # 경로 직접 지정
qgclog list -n 30    # 더 많이 나열
qgclog 1 --dir ~/다른/Logs
```

사용자가 `./qgc log list` / `./qgc log 1` 처럼 말하면 위 명령으로 옮겨 실행한다.

## 실행 절차

1. **리포를 찾는다.** `SHADE_parts` 경로는 PC 마다 다르다. 하드코딩하지 마라.
   ```bash
   for d in ~/QGroundControl/SHADE_parts ~/SHADE_parts ./SHADE_parts; do
     [ -x "$d/tools/qgclog/qgclog" ] && { QL="$d/tools/qgclog/qgclog"; break; }
   done
   ```
2. **`qgclog list` 를 먼저 보여준다** — 사용자가 번호를 고를 수 있게.
   번호를 이미 지정했으면 바로 분석으로 간다.
3. **`qgclog <N>` 결과를 그대로 보여주고**, 그 위에 해석을 붙인다.
   자동 판정은 임계값 기반이라 **맥락을 모른다** — 지상 테스트인지 실비행인지,
   의도한 기동인지 사고인지는 로그만으로 구분 못 한다. 그 판단을 네가 채워라.

## FC 에서 로그 받아오기

로그가 로컬에 없으면 **FC 내장 SD 에서 직접** 받는다. QGC 불필요, USB 만 있으면 된다.

```bash
~/.venv-mav/bin/python <SHADE_parts>/tools/qgclog/fcfetch.py ls /fs/microsd/log/2026-08-24
~/.venv-mav/bin/python <SHADE_parts>/tools/qgclog/fcfetch.py fetch 2026-08-24 /tmp/fclogs
```

⚠️ **파일명은 UTC** — KST = UTC+9. 19시 비행은 `10_*.ulg` 다.
⚠️ **QGC 가 포트를 잡고 있으면 실패** — 먼저 `fuser -v /dev/ttyACM0` 확인. 사용자 창이면 물어볼 것.

절차·API 함정·복구 원리 전부: [FETCHING.md](../../tools/qgclog/FETCHING.md)

## 로그 디렉토리

`--dir` > `$QGC_LOG_DIR` > `~/QGroundControl/Logs` > `~/Documents/QGroundControl/Logs` > `./Logs` 순으로 찾는다.

## 의존성

`pyulog`, `numpy`. 런처가 아래 순으로 인터프리터를 찾는다:
`$QGCLOG_PYTHON` → `~/venv-ardupilot/bin/python` → `python3` → `python`.

없으면: `python3 -m pip install pyulog numpy`

## 자동 검출 항목

| 항목 | 임계값 | 의미 |
|---|---|---|
| 전류 | > 45A 연속 / 90A 순간 | 커넥터 정격 초과 (XT90 기준) |
| 셀 전압 | < 3.5V | 배터리 처짐·용량 부족 |
| 진동 | accel_vibration > 10 경고, > 30 위험 | 프로펠러 밸런스·마운트 |
| 클리핑 | accel_clipping > 0 | IMU 포화, 방진 필요 |
| EKF | innovation test ratio > 1.0 | 센서 간 불일치 |
| 에어스피드 | 평균 < 0 | 피토관 역결선/영점 오류 |
| 자세 | 경사 > 45° | 제어 상실 의심 |
| 제어 배분 | 미배분 토크 > 0.3 | 추력 부족·불균형 |
| 자기 간섭 | 전류-자기장 상관 > 0.5 | 전력선이 나침반 교란 |

**임계값은 기체마다 다르다.** SHADE 기준값이므로 다른 기체면 `qgclog.py` 상단 상수를 고친다.

## 해석 시 주의

- **failsafe 플래그는 대부분 정상이다.** `auto_mission_missing`, `gcs_connection_lost`,
  `offboard_control_signal_lost` 는 미션 없이 수동 비행하면 항상 뜬다. 실제 failsafe 발동은
  `vehicle_status.failsafe` 로 판단하라.
- **시각은 arm 시점 기준 상대초**로 표시된다. 로그 파일 절대시각과 다르다.
- **`gravity[N]` innovation 초과**는 기동 중에는 흔하다. 정지 호버에서 크면 IMU 문제.
- **"파싱 실패" 를 손상으로 단정하지 마라.** `qgclog` 가 원인을 구분해 준다 —
  *구독 섹션 유실* 은 자동 복구되고(데이터는 멀쩡하다), *데이터 깨짐 N%* 만 실제 손상이다.
- **고도를 원점 기준으로 읽지 마라.** `local_position` 의 z 는 EKF 원점 기준이라
  이륙 지점과 다르다. 실제 비행 여부는 **GPS 누적 이동거리·수평속도·전류**로 판단하라.
  (지상 테스트: 이동 1~2m, 속도 0.5m/s 이하 / 실비행: 이동 수십 m, 속도 3m/s 이상)
- **VTOL 전환이 없으면** 에어스피드 이상은 당장 비행에 영향 없다. 다만 고정익 전환 전에는
  반드시 고쳐야 한다 — 전환 판단이 에어스피드에 걸려 있다.

## 조종자에게 물어라 — 가장 중요하다

**로그는 "무엇이" 일어났는지 알려주지만 "왜"는 모른다.**

비행 #85 에서 실제로 겪은 일: 스틱이 전 구간 중립인데 기체가 진동하며 추락했다.
로그만 보면 **PID 자발 발산**으로 읽을 수밖에 없다. 실제로 그렇게 오진했다.

조종자의 한 마디가 판정을 뒤집었다 — *"호버 안정성 보려고 손으로 밀었다"*.
외란이 손이었으므로 발산이 아니었고, 진짜 원인은 **회복 시간보다 짧은 간격의 연타**였다.
PID 를 낮추라고 권했다면 회복이 더 느려져 오히려 위험해졌을 것이다.

그러니 분석 결과를 확정하기 전에 반드시 물어라:

- 그 구간에서 **무엇을 하려고 했나** (테스트? 착륙? 급기동?)
- **바람**은 어땠나
- 이상을 **몸으로 느꼈나** (진동, 소리, 냄새)
- 착륙 후 **만져본 것**이 있나 (커넥터, 모터, 배터리 온도)

## 리포트를 남길 때

분석 결과를 문서로 남기면 `<SHADE_parts>/flights/` 아래에 날짜-번호로 둔다.
비행마다 누적되면 추세(진동 증가, 전류 상승, 배터리 열화)가 보인다.

**조종자 증언은 반드시 리포트에 적어라.** 로그에 없는 정보이고, 나중에
같은 로그를 다시 볼 때 그 맥락이 없으면 같은 오진을 반복한다.

관련 문서: `<SHADE_parts>/BRINGUP.md`, `components/power/holybro-pm08-can/README.md`
