# 스킬 — Claude Code 에이전트용

이 리포에서 정의하는 작업 절차. Claude Code 가 `/스킬이름` 으로 호출한다.

비행 하나를 시간 순으로 따라가면 넷이 차례로 쓰인다 —
**전** `shade01-test` → **중** `shade01-live` → **직후** `shade01-sync` → **끝난 뒤** `shade01-log`.

| 스킬 | 용도 |
|---|---|
| [shade01-test](shade01-test/SKILL.md) | **비행 전** — FC·미션·GPS·전원·failsafe 를 한 번에 읽고 GO / NO-GO. `./shade01 test` (읽기 전용, 3~7초) |
| [shade01-log](shade01-log/SKILL.md) | **끝난 비행** — PX4 로그(.ulg) 목록·분석. `./qgc log list`, `./qgc log <번호>` |
| [shade01-live](shade01-live/SKILL.md) | **지금 이 순간** — 실시간 트래킹 켜기·끄기·진단. `./qgc live on\|off\|status` |
| [shade01-sync](shade01-sync/SKILL.md) | **비행 직후** — FC 로그를 받아 웹에 올린다. `./qgc sync` |

## 설치

Claude Code 는 `~/.claude/skills/` 아래를 읽는다. 심볼릭으로 연결한다:

```bash
mkdir -p ~/.claude/skills
for s in shade01-test shade01-log shade01-live shade01-sync; do
  ln -sfn "$(pwd)/skills/$s" ~/.claude/skills/$s
done
```

새 PC 에서 한 번 돌린다. 확인은 링크가 아니라 **내용이 읽히는지**로 한다 —
끊어진 심볼릭도 `ls -l` 에는 멀쩡해 보인다:

```bash
for s in shade01-test shade01-log shade01-live shade01-sync; do
  [ -f ~/.claude/skills/$s/SKILL.md ] && echo "✔ $s" || echo "✖ $s"
done
```

**정본은 이 리포다.** `~/.claude/skills/` 에 사본을 두면 두 곳이 갈라진다 —
기체 문서·임계값과 함께 버전 관리되어야 하므로 여기가 맞는 위치다.

## 왜 여기 있나

`shade01-log` 의 판정 임계값(전류 45A, 진동 10/30 등)은 **이 기체에 묶여 있다**.
45A 는 [PM08 의 XT90 병목](../components/power/holybro-pm08-can/README.md#-전류-용량-주의)에서 온 값이고,
다른 기체에서는 틀린 값이다. 스킬과 기체 문서가 같이 움직여야 한다.

`shade01-live` 도 마찬가지다 — PC 별 UDP 포트(`rim3`·`rim` 이 14551 인 이유), 상행이
막혀 있다는 보장, NaN 함정이 전부 이 리포의 구현에 묶여 있다.

`shade01-sync` 의 1MB 크기 문턱과 재연결 7.7초는 **이 FC 의 MAVFTP 실측치**다
([FLIGHT-SYNC.md](../FLIGHT-SYNC.md)). 브리지 유닛 이름도 이 기체의 PC 구성에서 온다.

`shade01-test` 의 기대값은 전부 [FC_CHANGELOG.md](../FC_CHANGELOG.md) 에서 왔다 —
`GF_*=0`(지오펜스를 **일부러** 껐다), 미션 이착륙 `22/21`(`84` 는 고정익 전환을
건다), `MPC_THR_HOVER=0.65`. 다른 기체에서는 전부 틀린 값이다.
