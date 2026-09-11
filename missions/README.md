# 미션 — `.plan` 정본

FC 에 올리는 미션은 전부 여기 둔다. 번호가 곧 이름이다.

| # | 파일 | 내용 | 이착륙 | 상태 |
|---|---|---|---|---|
| 01 | [`01-square-5pt.plan`](01-square-5pt.plan) | 5 m 사각 순회 4점, 163.6 m / 약 77초 | 22 / 21 | 보존 |
| 02 | [`02-hover-test.plan`](02-hover-test.plan) | **수직 이륙 5 m → 5초 호버 → 착륙** | 22 / 21 | 🟢 **FC 에 올라가 있다** (2026-09-11) |

둘 다 이륙점은 `35.1810871, 128.5538216` 로 같다.

## 🔴 쿼드 전용 — 미션에 넣으면 안 되는 명령

[고정익 사용 금지](../README.md#-고정익-사용-금지--쿼드-전용-2026-09-04) 가 걸려 있는 동안:

| 명령 | 왜 |
|---|---|
| `84` VTOL_TAKEOFF | 고정익 전환을 건다 |
| `85` VTOL_LAND | 〃 |
| `3000` DO_VTOL_TRANSITION | 〃 |

**이륙·착륙은 `22`(TAKEOFF) / `21`(LAND) 를 쓴다.**
`NAV_FORCE_VT=1` 로도 84 를 못 막는다 — 그 파라미터는 기체가 **이미 FW 일 때만**
동작한다. `mission_push.py verify` 가 이 셋을 발견하면 올리기를 거부한다.

## 5초 호버를 어떻게 적었나

`LOITER_TIME`(19) 의 **param1 이 체류 초**다. 멀티콥터는 그 점에서 **정지**해 기다린다
(고정익이면 선회한다 — `mission_block.cpp:225` 의 분기가 `VEHICLE_TYPE_FIXED_WING`
일 때만 선회 경로를 탄다).

```
0  TAKEOFF     (22)  alt 5.0
1  LOITER_TIME (19)  alt 5.0   param1 = 5.0  ← 5초
2  LAND        (21)  alt 0.0
```

`WAYPOINT`(16) + `time_inside` 로도 같은 효과가 나지만
([`get_time_inside()`](../PX4-Autopilot/src/modules/navigator/mission_block.cpp) 는
`ROTARY_WING` 일 때 WAYPOINT 도 체류시킨다) **그 길은 쓰지 않는다** — 나중에
천이를 풀면 조용히 무시되어 호버가 사라진다. 19 는 어느 기체 형태에서도 체류한다.

## 올리는 법

🔴 **FC 에 쓴다.** 작업 전 [`FC_CHANGELOG.md`](../FC_CHANGELOG.md) 를 읽어라.

```bash
# rim3 (FC 가 붙은 PC) 에서
systemctl --user stop shade-bridge          # 포트 독점 해제 — kill 금지

.venv/bin/python tools/fc/mission_push.py backup --backup ~/fc-backup/mission.plan.fcbak-$(date +%Y%m%d-%H%M%S)
.venv/bin/python tools/fc/mission_push.py verify --new missions/02-hover-test.plan
.venv/bin/python tools/fc/mission_push.py push   --new missions/02-hover-test.plan

systemctl --user start shade-bridge         # 🔴 반드시 되살린다
```

`push` 는 올린 뒤 **전량을 되읽어 항목마다 대조**한다. extras.txt 와 달리 미션에는
CRC 가 없어서 그것이 유일한 확인이다 — `MISSION_ACK` 는 "받았다" 이지 "같다" 가 아니다.

## 함정

- ⚠️ **웹 트래커의 「미션 항목 0」은 FC 가 비었다는 뜻이 아니다.** 트래커는 미션을
  요청하지 않는다. 실제로 무엇이 올라가 있는지는 `mission_push.py backup` 으로 봐라.
  실측 2026-09-11: 트래커는 0 이라고 했는데 FC 에는 6항목이 들어 있었다.
- ⚠️ **`plannedHomePosition` 은 QGC 표시용이다.** 실제 홈은 ARM 할 때 FC 가 잡는다.
  미션 항목의 위경도는 절대좌표이므로, 엉뚱한 자리에서 ARM 하면 그 좌표까지 날아간다.
- ⚠️ **`params` 의 `null` 은 0 으로 보낸다.** NaN 을 넣으면 FC 가 항목을 거부한다.
  QGC 도 0 으로 보낸다.
