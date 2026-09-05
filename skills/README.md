# 스킬 — Claude Code 에이전트용

이 리포에서 정의하는 작업 절차. Claude Code 가 `/스킬이름` 으로 호출한다.

| 스킬 | 용도 |
|---|---|
| [qgc-log](qgc-log/SKILL.md) | **끝난 비행** — PX4 로그(.ulg) 목록·분석. `./qgc log list`, `./qgc log <번호>` |
| [qgc-live](qgc-live/SKILL.md) | **지금 이 순간** — 실시간 트래킹 켜기·끄기·진단. `./qgc live on\|off\|status` |

## 설치

Claude Code 는 `~/.claude/skills/` 아래를 읽는다. 심볼릭으로 연결한다:

```bash
ln -sfn "$(pwd)/skills/qgc-log"  ~/.claude/skills/qgc-log
ln -sfn "$(pwd)/skills/qgc-live" ~/.claude/skills/qgc-live
```

새 PC 에서는 위 두 줄을 한 번씩 돌린다. `~/.claude/skills/` 가 없으면
`mkdir -p ~/.claude/skills` 를 먼저.

**정본은 이 리포다.** `~/.claude/skills/` 에 사본을 두면 두 곳이 갈라진다 —
기체 문서·임계값과 함께 버전 관리되어야 하므로 여기가 맞는 위치다.

## 왜 여기 있나

`qgc-log` 의 판정 임계값(전류 45A, 진동 10/30 등)은 **이 기체에 묶여 있다**.
45A 는 [PM08 의 XT90 병목](../components/power/holybro-pm08-can/README.md#-전류-용량-주의)에서 온 값이고,
다른 기체에서는 틀린 값이다. 스킬과 기체 문서가 같이 움직여야 한다.

`qgc-live` 도 마찬가지다 — PC 별 UDP 포트(`rim3`·`rim` 이 14551 인 이유), 상행이
막혀 있다는 보장, NaN 함정이 전부 이 리포의 구현에 묶여 있다.
