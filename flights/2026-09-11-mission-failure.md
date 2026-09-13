# 미션 3회 실패 — 원인은 dataman 읽기 타임아웃 (2026-09-11)

야외에서 미션을 **3회 걸어 3회 다 실패**했다. 미션 파일을 바꿔서 다시 올려도 같았다.

**원인: `dataman_client` 가 미션 항목을 못 읽는다.** 저장 매체·미션 내용·GPS 는
전부 정상이었다. PX4 v1.17.0 의 소프트웨어 결함이다.

대응: 펌웨어를 교체했다 (2026-09-12) — [`docs/firmware/BUILD.md`](../docs/firmware/BUILD.md),
[`FC_CHANGELOG`](../FC_CHANGELOG.md#-2026-09-12-1845--펌웨어-교체-dataman-수정--슬림화).
🔴 **아직 야외 재시도로 검증되지 않았다.**

## 무슨 일이 있었나 — 세 번 다 같은 모양

미션 시도 로그 3편은 **1MB 미만이라 sync 기본 문턱에 안 걸린다.** 따로 받았다
(`fcfetch.py get`). 그래서 처음 분석 때 이 로그들을 못 보고 헛다리를 짚었다.

### 1차 KST 16:53 — `07_53_49.ulg`

```
 +0.000s  [commander] Armed by RC switch
 +0.007s  [logger] Opened full log file
 +2.192s  nav_state=3 AUTO_MISSION 진입
 +7.242s  [dataman_client] timeout after 5000 ms!      ← 진입 5.05초 뒤
 +7.242s  [navigator] mission check failed
 +7.242s  [navigator] No valid mission available, refusing takeoff
 +7.747s  [dataman_client] timeout after 500 ms!
 +7.747s  [navigator] Waypoint could not be read.
 +7.818s  [failsafe] Failsafe activated → AUTO_RTL
+11.030s  Disarmed by auto preflight disarming
```

### 2차 KST 17:09 — `08_09_54.ulg`

문구·순서·시간차까지 같다. 진입 `+3.376s` → 타임아웃 `+8.426s` (역시 5.05초).
**`mission_id` 가 `20692890` → `4063430179` 로 바뀌었다** — 조종자가 다른 미션을
올린 것이 확인된다. 그래도 같은 지점에서 실패했다.

### 3차 KST 17:10 — `08_10_30.ulg`

```
 +2.533s  [commander] Switching to Mission is currently not available
```
아예 진입을 거부당했다.

## 🔴 결정적 증거 — 같은 부팅에서 되다가 안 됐다

13편 전체가 **하나의 부팅 세션**이다. uptime 축으로 세우면:

| 부팅후 | mission_result | mission_id |
|---|---|---|
| **+76.8초** | **valid=1 warning=0** | 20692890 |
| +1004초 | 🔴 valid=0 **warning=1** | 20692890 |
| +1970초 | 🔴 valid=0 **warning=1** | 4063430179 |

**같은 미션(`20692890`)이 부팅 76초에는 유효했다.** 파일이 문제면 처음부터 안 됐다.

`home_position_counter` 는 `4599 → 4633 → 4661` 로 계속 늘었다. 홈이 갱신될 때마다
`check_mission_valid()` 가 미션 전체를 dataman 에서 다시 읽는다 (비행당 2~6회).

## 왜 dataman 인가 — `warning=1` 은 한 경로뿐이다

v1.17.0 [`mission_feasibility_checker.cpp:86`](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/navigator/mission_feasibility_checker.cpp#L86):

```c
bool success = _dataman_client.readSync(...);
if (!success) {
    _navigator->get_mission_result()->warning = true;   // ← 여기뿐
    return false;
}
```

실패 로그 둘 다 `valid=0 warning=1 failure=0` 이다. `failure=0` 이라 **미션 내용
문제가 아니고**, `warning=1` 이라 **dataman 읽기 실패**다.

### 읽어온 데이터가 실제로 비어 있었다

`navigator_mission_item` 토픽 대조:

| 로그 | `nav_cmd` | |
|---|---|---|
| 07_53_49 (실패) | **0, 0** | 🔴 빈 명령 |
| 08_09_54 (실패) | **0, 0** | 🔴 빈 명령 |
| 08_10_43 (정상) | **16**(WAYPOINT), **21**(LAND) | ✅ |

`mission_base.cpp:935` 가 `nav_cmd = _mission_item.nav_cmd` 를 그대로 싣는다.
**구조체가 초기값 그대로 = dataman 이 아무것도 안 채웠다.** `sequence_current=8`
인데 `seq_total=3` 인 것도 같은 이야기다.

## 배제한 것 — 전부 실측

| 후보 | 실측 | |
|---|---|---|
| GPS·위치 | fix 4(RTK) · 위성 29~31 · eph 0.14~0.18 | 실패·정상 **동일** ❌ |
| 홈 유효성 | `valid_alt`·`valid_hpos`·`valid_lpos` 전부 True | 동일 ❌ |
| CPU 부하 | 실패 5초 구간 **27~28% 평탄**, 스파이크 0 | ❌ |
| RAM | 38.1% 고정 | ❌ |
| SD 쓰기 정체 | dropout 0~18ms, **실패 순간엔 0** | ❌ |
| 미션 내용 | MAVLink 로 3항목 0~1ms 즉시 읽힘 | ❌ |
| SD 하드웨어 | `SYS_DM_BACKEND=1`(RAM 백엔드)로도 동일 증상 | ❌ |
| 지오펜스 | 86행에서 `return` 하므로 검사 자체를 안 함 | ❌ |
| CRSF | 전 경로 MAVLink (`input_source=6`, CRSF 0회) | ❌ |

🔴 **CPU 가 한가한데 dataman 이 5초를 넘겼다.** 자원 경쟁이 아니라 응답 유실이다.

실기 실측으로도 뒷받침된다 — dataman 은 평소 **읽기 0.4ms / 쓰기 3ms** 다.
5000ms 는 1만 배다.

## 웹 교차 확인

| 출처 | |
|---|---|
| [Flight Review 로그](https://review.px4.io/plot_app?log=22901583-91bf-470c-842f-98955ad045b4) | v1.15.0 · **FMU_V6X** · 옥토 — 동일 `dataman_client timeout after 5000 ms!` |
| [#24608](https://github.com/PX4/PX4-Autopilot/issues/24608) | 동일 5000ms. **v1.15 회귀, v1.14.4 정상** |
| [#27135](https://github.com/PX4/PX4-Autopilot/issues/27135) | `Waypoint could not be read` 동문. **home_position 갱신 시점**을 트리거로 지목 |

**다른 보드·다른 기체에서도 난다 → 하드웨어 무관.**
**#27135 이 지목한 트리거가 우리 `home_position_counter` 증가와 일치한다.**

🔴 **해결 후기는 하나도 없다.** 두 이슈 다 댓글 0으로 stale 종료됐다.

개발팀 자신의 기록은 있다 — [PR #27254](https://github.com/PX4/PX4-Autopilot/pull/27254):

> *"Invalid Mission 경고를 관측했는데 **정확한 이유를 찾을 수 없었다**"*

그래서 넣은 것이 진단 메시지다 (`"Mission rejected: dataman read failed at item %zu"`).
**우리 v1.17.0 에는 그 메시지가 없어서** 야외에서 원인이 안 보였다.

## 왜 실내에서는 재현이 안 되나

`checkMissionFeasible` 은 dataman 읽기 **앞에서** 위치를 먼저 본다:

```c
if (!home_alt_valid) {
    "Not yet ready for mission, no position lock."
    return false;                     // ← 실내는 여기서 끝. dataman 까지 안 간다
}
```

전역 원점과 홈을 손으로 주면 그 관문을 넘길 수 있다
([FLASHING.md §8](../docs/firmware/FLASHING.md)). 그렇게 해서 **재검증 10회 ·
재업로드 5회를 돌렸는데 전부 성공했다** — 펌웨어를 바꾸기 **전**에도 그랬다.

🔴 **그러므로 실내 통과는 판정 근거가 못 된다.** 야외 재시도만이 답이다.

## 2026-09-12 실내 대조 — 펌웨어 교체 후

펌웨어를 바꾼 뒤 같은 지표를 실내에서 다시 쟀다. 로그
`2026-09-12_11_16_07.ulg` (랩서버에 올려 뒀다).

⚠️ **`SDLOG_MODE=0`(arm~disarm)이라 실내 시험은 로그가 안 남는다.** 파라미터를
건드리지 않고 NuttX 셸에서 `logger on` / `logger off` 로 수동 기록했다.

| 지표 | 9/11 실패 (`07_53_49`) | **9/12 실내 (`11_16_07`)** |
|---|---|---|
| `mission_result` | `valid=0` **`warning=1`** | **`valid=1` `warning=0`** |
| `dataman_client timeout` | 4건 | **0건** |
| `navigator_mission_item` | 2건, **`nav_cmd=0`** (빈 값) | **발행 없음** |
| `nav_state` | AUTO_MISSION → **5.6초 뒤 AUTO_RTL** | AUTO_MISSION **유지** |
| 토픽 수 | 91 | 90 |

`navigator_mission_item` 이 오늘 아예 없는 것이 오히려 정상이다.
[`mission_base.cpp:578`](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/navigator/mission_base.cpp#L578)
은 **미션 종료(`finished=true`) 처리에서** 그것을 발행한다 — 9/11 은 dataman
읽기에 실패해 곧바로 종료 경로로 빠지며 빈 `_mission_item` 을 찍은 것이다.

로그에 남은 `ekf2 New NED origin (LLA): 35.1811180, 128.5537579, 20.000` 이
전역 원점 수동 지정이 실제로 먹혔음을 보여준다. dataman 관련 메시지는 한 건도
없다.

#### 같은 세션에서 돌린 실내 검증 (로그 밖)

| 단계 | 내용 | 결과 |
|---|---|---|
| A | 부팅 직후 (GPS 없음) | `NO_MISSION` — 위치 관문에서 정상 차단 |
| B | 원점·홈 수동 지정 | → `NOT_STARTED`, dataman 읽기 +7 |
| C | AUTO_MISSION 진입 | → `ACTIVE`, timeout 0 |
| D | 홈 재지정 20회 | 20/20 (단 캐시 처리라 dataman 미경유) |
| E | 동일 미션 재업로드 10회 | 10/10, dataman 쓰기 30회 |
| F | **내용이 다른 미션 교대 12회** | **12/12, 읽기 97 + 쓰기 48회** |
| G | 재부팅 후 | 미션 3항목 SD 에서 복원 |
| H | dataman 스택 | **308 B → 892 B** (1376 → 1960) |

dataman I/O 총 195회에 실패 0. 읽기 평균 322 µs · 최대 3.2 ms,
쓰기 평균 2.6 ms · 최대 5.3 ms — **5000 ms 타임아웃과 견주면 최대치도 1500배
여유**다.

#### 🔴 그래도 이것은 판정이 아니다

**실내에서는 펌웨어를 바꾸기 전에도 전부 통과했다** (재검증 10회·재업로드 5회).
9/11 실패는 arm·로깅·EKF·GPS·MAVLink 1400 B/s 가 동시에 도는 야외 부하에서만
났고, F 단계로 dataman 읽기를 97회 강제해도 그 조건은 재현되지 않았다.

**확인된 것은 "회귀가 없다" 와 "정상일 때의 기준선" 두 가지다.**

⚠️ 실내 조회값을 판정에 쓰지 않는 원칙은
[`CLAUDE.md` 「값을 뽑을 때」](../CLAUDE.md#-값을-뽑을-때--실내-조회값과-실비행값을-섞지-마라)
에 있다. 여기 적은 dataman 수치(읽기 322 µs, 쓰기 2.6 ms, 스택 892 B)는 **환경에
의존하지 않는 소프트웨어 지표**라 실내값을 그대로 쓴다 — 기압계·대기속도처럼
바깥 조건이 섞이는 값과는 성격이 다르다. 반면 **미션 성패는 부하에 좌우되므로
실내 통과가 판정이 될 수 없다.**

## 다음에 볼 것

| | 고쳐졌다 | 아직이다 |
|---|---|---|
| STATUSTEXT | `dataman_client timeout` 없음 | `timeout after 5000 ms!` |
| `mission_result` | `valid=1 warning=0` | `valid=0 warning=1` |
| `navigator_mission_item` | `nav_cmd=22/19/21` | `nav_cmd=0` |

비행 뒤 `./shade01 sync` 로 올리고 이 문서에 결과를 덧붙인다.

⚠️ **미션 시도 로그는 1MB 미만이라 sync 가 안 받는다.** 따로 받아라:

```bash
tools/qgclog/fcfetch.py get /fs/microsd/log/<날짜>/<이름>.ulg logs/<날짜>_<이름>.ulg
```
