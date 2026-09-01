# qgclog — PX4 비행 로그 분석기

ULog(`.ulg`)를 읽어 **무엇이 문제였고, 무엇이 잘 됐고, 다음에 뭘 고쳐야 하는지**를 뽑는다.

```bash
./qgc log list        # 최근 비행 나열 — 1 이 가장 최근
./qgc log 1           # 1번 비행 분석
./qgc log <path.ulg>  # 경로 직접 지정
```

> 🔴 **`pyulog` 를 직접 부르지 마라.** 잘린 메시지 하나에서 읽기를 포기해 로그 대부분을
> 조용히 잃는다 — 에러 없이 **짧은 비행처럼 보인다.** `qgclog.py` 의 `_patch_pyulog()`
> 가 막는다(import 시 자동). 커스텀 분석도 `qgclog._load(path)` 를 거쳐라.
>
> 확인: `python3 decode_rate.py <로그디렉토리>` — 기준치 **DATA 99.36%**
> (2026-08-31 자 21개, 2026-09-01 실측). 크게 낮으면 패치가 안 걸린 것이다.
> [원인과 수정](../../PROCEDURE.md#분석기--잘린-메시지에서-멈추지-않는다-2026-09-01-수정)

**FC 에서 로그 받아오기**: [FETCHING.md](FETCHING.md) — QGC 없이 USB 만으로,
MAVFTP 버스트로 7.6MB 를 18초에. `fcfetch.py` 사용.

`tools/qgclog/qgclog` 를 직접 불러도 같다.

## 출력 예

```
비행 로그 분석  log_85_2026-8-22-14-11-06.ulg
  일시      2026-08-22 14:07:43 KST
  비행시간  107초 (1.8분)
  최고고도  1.7 m   최대속도 3.6 m/s

[배터리]
  전압    22.47 ~ 23.59 V   셀당 최저 3.74 V   강하 1.12 V
  전류    평균 39.2 A   최대 78.2 A   소모 1179 mAh
  >45A    97회, 누적 43.0s, 최장 연속 2.4s

문제 (7건)
  1. [전류] 최대 78.2A — 커넥터 연속 정격 45A 초과
     → 비행 후 XT90 커넥터 발열 확인. 지속되면 AS150/XT120 교체
  ...
```

## 자동 검출 항목과 임계값

| 항목 | 임계값 | 근거 |
|---|---|---|
| 전류 | 연속 45A / 순간 90A | Holybro [Connector & Wire Rating](https://docs.holybro.com/power-module-and-pdb/power-module/connector-and-wire-rating) — XT90 @10AWG |
| 셀 전압 | 3.5V | 6S LiPo 경고선 |
| 진동 | 10 경고 / 30 위험 | PX4 `accel_vibration_metric` 권장 범위 |
| 클리핑 | > 0 | IMU 포화는 무조건 이상 |
| EKF innovation | test ratio > 1.0 | PX4 정의상 1.0 = 거부 임계 |
| 에어스피드 | 평균 < 0 | 물리적으로 불가능한 값 |
| 자세 | 경사 45° | 멀티로터 정상 운용 범위 |
| 미배분 토크 | 0.3 | 제어 배분 여유 소진 |
| 자기 간섭 | 전류-자기장 상관 0.5 | 전력선 간섭 판정 |

**기체가 바뀌면 `qgclog.py` 상단 상수를 고친다.** 위 값은 [SHADE 기체](../../README.md) 기준
— 특히 45A 는 [PM08 XT90 병목](../../components/power/holybro-pm08-can/README.md#-전류-용량-주의)에서 온 값이다.

## 해석 주의

- **failsafe 플래그 대부분은 정상이다.** `auto_mission_missing`,
  `gcs_connection_lost`, `offboard_control_signal_lost` 는 미션 없이 수동 비행하면 항상 뜬다.
- **시각은 arm 시점 기준 상대초.**
- **자동 판정은 맥락을 모른다** — 의도한 급기동인지 제어 이탈인지 로그만으로는 구분 못 한다.

## 의존성

`pyulog`, `numpy`. 런처가 `$QGCLOG_PYTHON` → `~/venv-ardupilot/bin/python` → `python3` 순으로 찾는다.

```bash
python3 -m pip install pyulog numpy
```

## 로그 디렉토리 탐색 순서

`--dir` > `$QGC_LOG_DIR` > `~/QGroundControl/Logs` > `~/Documents/QGroundControl/Logs` > `./Logs`

## 분석 기록

비행별 리포트는 [`flights/`](../../flights/) 에 누적한다. 추세(진동 증가, 전류 상승,
배터리 열화)는 단일 비행이 아니라 **여러 비행을 겹쳐봐야** 보인다.
