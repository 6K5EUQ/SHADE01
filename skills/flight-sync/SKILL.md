---
name: flight-sync
description: 비행이 끝난 뒤 한 줄로 FC 로그를 웹에 올린다. "qgc sync" 로 그날 실제로 뜬 비행만 FC 에서 받아 shade01.bewe.co.kr 에 등록한다. 지상 시험·즉시 disarm·실내·읽기 실패는 받지도 올리지도 않는다. 비행 후 정리, "로그 올려줘", "오늘 비행 웹에 등록" 에 쓴다. 지나간 .ulg 분석은 qgc-log, 실시간 화면은 qgc-live 쪽이다.
---

# flight-sync — 비행 로그를 웹에 올린다

비행이 끝나면 **한 줄**이다.

```bash
./qgc sync
```

**이 스킬은 SHADE01 리포가 정본이다** (`skills/flight-sync/SKILL.md`).
`~/.claude/skills/flight-sync` 는 그쪽을 가리키는 심볼릭이다 — 사본을 만들지 마라.

전체 근거와 실측치는 **[`FLIGHT-SYNC.md`](../../FLIGHT-SYNC.md)** 에 있다.
이 문서는 에이전트가 무엇을 하고 무엇을 하면 안 되는지만 적는다.

```
<SHADE01>/qgc sync                     진입점
<SHADE01>/tools/flightsync/flightsync  본체 (bash)
<SHADE01>/web/tools/uploadable.py      업로드 판정
<SHADE01>/web/tools/hosts.conf         주소 (gitignore 됨)
```

## 사용자가 뭘 말하면 이걸 쓰나

"비행 로그 올려줘" / "오늘 비행 웹에 등록" / "shade01 에 반영" /
"로그 받아서 올려" / "비행 끝났어 정리해줘"

**지나간 로그를 분석해 달라**는 것은 `qgc-log` 다.
**지금 날고 있는 것을 보겠다**는 것은 `qgc-live` 다.

## 절차

### 그냥 올려 달라고 하면

```bash
./qgc sync
```

인자 없이 부르면 **오늘(KST) 비행**을 찾는다. FC 폴더명이 UTC 라
KST 09시 이전 비행은 어제 UTC 폴더에 있는데, 스크립트가 **두 폴더를 다 훑는다.**

끝나면 출력의 마지막 줄을 그대로 전한다:

```
✅ 8편 올렸다 — https://shade01.bewe.co.kr
```

### 날짜를 말하면

```bash
./qgc sync 2026-09-05          # UTC 폴더명이다
```

⚠️ 사용자가 말한 날짜는 **KST** 일 것이다. 새벽 비행이면 UTC 로는 전날이다.
확실하지 않으면 인자 없이 부르거나 두 날짜를 다 시도한다.

### 뭘 올릴지 먼저 보여 달라고 하면

```bash
./qgc sync --dry
```

받을 목록과 크기만 보여주고 **아무것도 안 받는다.**

## 읽는 법

| 줄 | 뜻 |
|---|---|
| `브리지 정지 (user/shade-bridge.service)` | 정상. QGC 링크가 잠시 끊긴다 |
| `받을 것 N개 / 1.0MB 미만 M개 건너뜀` | 크기 게이트가 걸렀다 |
| `⚠️ 건너뛴 것 중 X MB 가 문턱에 가깝다` | **사용자에게 전해라.** 짧은 비행을 놓쳤을 수 있다 |
| `✅ ... flight` / `hover` | 올라간다 |
| `− ... ground (안 올림)` | 지상 시험. 정상 |
| `− ... abort` / `indoor` / `unreadable` | 걸러진 것. 정상 |
| `✅ 브리지 복구` | **이 줄이 없으면 사용자에게 알려라** |

## 🔴 지켜야 할 것

**브리지 복구를 확인하고 보고하라.** `trap` 이 걸려 있어 Ctrl-C 나 실패에도
돌지만, ssh 자체가 끊기면 못 돈다. 출력에 `✅ 브리지 복구` 가 없으면
**QGC 무선 링크가 끊긴 채 남아 있다** — 그대로 두면 다음 사람이 원인을 모른 채
기체 앞에 선다. 복구:

```bash
ssh rim3@rim3 'systemctl --user start shade-bridge.service'
```

**FC 를 만지는 작업이다.** 다만 **읽기 전용**이다 — MAVFTP 로 파일만 읽고
`PARAM_SET` 을 보내지 않는다. 그래서 `FC_CHANGELOG.md` 에 적을 것이 없다.
파라미터를 바꿨다면 그것은 별도로 기록해야 한다.

**되풀이해서 돌려도 안전하다.** 받은 파일·올린 파일은 건너뛴다.

**임의로 `--all-badges` 를 붙이지 마라.** 지상 시험을 올리면 목록이
회색 줄로 덮인다. 사용자가 "지상 것도 올려" 라고 할 때만 쓴다.

## 놓친 것 같을 때만 손대는 것

```bash
./qgc sync --min-size=0.5      # 짧은 비행이 빠진 것 같을 때
./qgc sync --all-badges        # 지상 시험까지 전부
```

문턱을 낮추면 받는 개수가 늘어 **느려진다** — 파일당 재연결이 7.7초다.
`0.5` 아래로는 내리지 마라. 그 아래는 arm 도 못 한 로그다.

## 왜 크기로 거르나 (짧게)

파일당 재연결이 **7.7초**고, 이것이 총시간의 **72%** 다
(2026-09-05 실측: 49개 79MB 562초 중 377초).

🔴 **FC 는 한 연결에 파일 하나만 내준다** — 두 번째부터
`OpenFileRO failed, no sessions available`. 시리얼 포트도 하나뿐이다.
**병렬화는 불가능하다.** 받는 개수를 줄이는 것만 남는다.

1MB 게이트로 **49개 → 10개, 562초 → ~208초 (2.7배)**. 실비행·호버는
1.17MB 이상이고 지상·abort 는 0.95MB 이하였다 (실측).

사용자가 "왜 이것만 받냐" 고 물으면 이 문단과
[FLIGHT-SYNC.md](../../FLIGHT-SYNC.md) 를 가리켜라.

## 무엇이 올라가는가

`flight`(속도 ≥3 m/s 또는 고도 ≥10 m)와 `hover`(6초 넘게 뜬 것) **둘만**.

`ground`·`abort`·`noarm`·`unknown`·`indoor`·`unreadable` 은 안 올린다.
안 올려도 **`.ulg` 는 이 PC 와 FC 에 그대로 있다** — `./qgc log list` 로 본다.

배지는 `web/extract.py` 의 `classify()` 가 정한다. **여기서 기준을 새로 세우지
마라** — 목록 배지를 만드는 그 함수와 갈리면 "목록엔 abort 인데 올라와 있는"
어긋남이 생긴다.

## 설정을 바꿔야 할 때

FC 를 다른 PC 로 옮겼으면 `web/tools/hosts.conf` 의 `FC_HOST` 한 줄만 바꾼다.
브리지 유닛 이름·스코프는 스크립트가 알아서 가른다
(`rim3` = `--user shade-bridge`, `raspb1` = 시스템 `mavlink-bridge`).

🔴 **`hosts.conf` 는 gitignore 돼 있다. 주소를 커밋하지 마라** — 리포가 public 이다.

## 장애

| 증상 | 대응 |
|---|---|
| `HEARTBEAT 없음` | 브리지가 포트를 쥐고 있다. `ssh $FC_HOST 'fuser -v /dev/ttyACM0'` |
| 받기 실패 여럿 | USB 케이블·FC 재부팅. 다시 돌리면 받은 것은 건너뛴다 |
| `올릴 비행이 없다` | 전부 지상 시험이었다. 아니면 `--min-size=0.5` |
| 서버 502 | 캐시 굽는 중. 12회×5초 기다린다 |
| `설정이 없다` | `cp web/tools/hosts.conf.example web/tools/hosts.conf` 후 채운다 |
