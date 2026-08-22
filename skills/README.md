# 스킬 — Claude Code 에이전트용

이 리포에서 정의하는 작업 절차. Claude Code 가 `/스킬이름` 으로 호출한다.

| 스킬 | 용도 |
|---|---|
| [qgc-log](qgc-log/SKILL.md) | PX4 비행 로그(.ulg) 목록·분석. `./qgc log list`, `./qgc log <번호>` |

## 설치

Claude Code 는 `~/.claude/skills/` 아래를 읽는다. 심볼릭으로 연결한다:

```bash
ln -sfn "$(pwd)/skills/qgc-log" ~/.claude/skills/qgc-log
```

**정본은 이 리포다.** `~/.claude/skills/` 에 사본을 두면 두 곳이 갈라진다 —
기체 문서·임계값과 함께 버전 관리되어야 하므로 여기가 맞는 위치다.

## 왜 여기 있나

`qgc-log` 의 판정 임계값(전류 45A, 진동 10/30 등)은 **이 기체에 묶여 있다**.
45A 는 [PM08 의 XT90 병목](../components/power/holybro-pm08-can/README.md#️-전류-용량-주의)에서 온 값이고,
다른 기체에서는 틀린 값이다. 스킬과 기체 문서가 같이 움직여야 한다.
