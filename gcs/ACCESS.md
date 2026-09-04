# 분석 PC 접속 — Tailscale

QGC 를 돌리고 로그를 분석하는 PC 들. **전부 Tailscale 주소로 붙는다** — 집/학교 어디에
있든 같은 주소다. 공인 IP·포트포워딩 없다.

## 접속

```bash
ssh ku@100.99.120.110      # ku-dgs1
ssh rim3@rim3              # rim3  (IP 로는 22 번이 안 열린다)
ssh rim@100.107.83.47      # rim
```

⚠️ **사용자명이 호스트마다 다르다.** `dsa` 로는 안 붙는다 (`Permission denied`).
공개키 인증이고 비밀번호는 안 받는다.

| 호스트 | Tailscale | 사용자 | 리포 경로 | 비고 |
|---|---|---|---|---|
| `gram-labtop` | 100.66.204.25 | `dsa` | `~/SHADE01` | 이 문서를 쓴 PC |
| `ku-dgs1` | 100.99.120.110 | **`ku`** | `~/SHADE01` | RTT ~48ms |
| `rim3` | 100.117.47.105 | **`rim3`** | `~/SHADE01` | RTT ~2.2s — **느리다.** 타임아웃 넉넉히. ⚠️ **IP 로는 22 번이 안 열린다 — `ssh rim3@rim3` 로 이름을 써라** (2026-09-03) |
| `rim` | 100.107.83.47 | **`rim`** | `~/SHADE01` | 호스트명은 `RIM`. RTT ~0.3ms |
| `raspb1-dgs3` | 100.126.161.1 | `raspb1` | (리포 없음) | 기체 컴패니언 — [PROCEDURE.md](../PROCEDURE.md) 참조 |

> ⚠️ **`rim` 은 붙는다 — 계정명이 `rim` 이다** (2026-09-04 실측). 이 문서는 오랫동안
> "소유자가 `yyrrm@` 라 위 키로는 안 붙는다" 고 적고 있었는데 **틀렸다.** Tailscale 의
> 소유자 태그(`yyrrm@`)와 SSH 계정명은 별개다. `yyrrm@`·`ku@`·`rim3@` 로는 실제로
> `Permission denied` 가 나지만 `rim@` 은 붙는다.
>
> 이 오기 때문에 `rim` 이 동기화 대상에서 계속 빠져 있었다 — 9/4 에 확인했을 때
> 6 커밋 뒤처져 있었다.

### 원본 저장소는 `6K5EUQ` 하나다 (2026-09-04)

`yyrrm` 리모트는 **전부 제거했다.** 원본은 `github.com/6K5EUQ/SHADE01` 이고, 각 PC 에서
`origin` 이 그것을 가리킨다.

```bash
git remote -v      # origin  https://github.com/6K5EUQ/SHADE01.git 만 나와야 한다
```

`yyrrm` 에만 있던 `rim-legacy` 브랜치(8/22 기체 치수, 8/31 Telem 포트·LTE 모뎀)는
**제거 전에 6K5EUQ 로 옮겨 뒀다** — 이력은 사라지지 않았다.

| PC | 처리 |
|---|---|
| `ku-dgs1` | ✅ origin 교체 완료 |
| `rim3` | ✅ origin 교체 + 커밋 신원 `6k5euq` 로 변경 |
| `gram-labtop` · `rim` · `central` | ⬜ **미처리** — 그때 꺼져 있었다 |

미처리 PC 는 각각 한 번씩 돌려야 한다:

```bash
cd ~/SHADE01
git remote remove origin
git remote rename 6k5euq origin
git branch --set-upstream-to=origin/main main
git config --global user.name 6k5euq
git config --global user.email 6k5euq@gmail.com
```

⚠️ **`rim3`·`rim` 은 여전히 push 가 안 된다.** `gh` 가 `yyrrm` 계정으로 로그인돼 있어서고,
리모트를 바꾼다고 풀리지 않는다. 풀려면 그 PC 에서 `gh auth login` 을 6K5EUQ 로 다시 해야
한다 (대화형이라 원격으로 못 한다).

### PC 별 하드웨어 제약

| | WiFi 라디오 | [ELRS 백팩 링크](qgroundcontrol/README.md#어느-pc-에서-되나-2026-09-03-확인) | GitHub 접속 |
|---|---|---|---|
| `gram-labtop` | `wlp0s20f3` | ✅ | ✅ |
| `rim3` | `wlo1` | ✅ | fetch 만 (`gh` 가 `yyrrm` 로그인) |
| `rim` | **없음** (유선) | ❌ 동글 필요 | fetch 만 (`gh` 가 `yyrrm` 로그인) |
| `ku-dgs1` | **없음** (유선 `enp3s0`) | ❌ 동글 필요 | ✅ |

## 살아있는지 확인

```bash
tailscale status                  # 전체 목록 + offline 여부
ping -c1 100.99.120.110
```

⚠️ `tailscale status` 가 `offline, last seen ...` 로 나오면 **그 PC 가 꺼진 것**이다.
Tailscale 은 껐다 켜도 주소가 안 바뀌므로 주소를 의심할 필요는 없다.

## 원격에서 로그 분석 준비

각 PC 에서 리포 안 `.venv` 를 만든다 — 절차는 [PROCEDURE.md](../PROCEDURE.md#2-0-분석-pc-준비-새-pc-최초-1회).

```bash
ssh ku@100.99.120.110 'cd ~/SHADE01 && git pull && ./qgc log list'
ssh rim3@100.117.47.105 'cd ~/SHADE01 && git pull && ./qgc log list'
```

⚠️ **로그는 PC 마다 다르다.** 각자 자기 리포의 `logs/` 만 본다 — 공유 저장소가
아니다 (`.ulg` 는 `.gitignore` 되어 git 으로 오가지 않는다). 회수는 `scp` 로 한다.
어느 PC 에 어느 비행이 있는지는 `./qgc log list` 로 확인한다.

## 인터넷이 막힌 PC 에 설치하기

평소에는 어느 PC 에서나 `git`·`pip` 이 그대로 된다. 네트워크가 막힌 자리에서
작업할 때만 아래를 쓴다.

### git — Tailscale 로 직접 밀어넣기

```bash
git push ssh://ku@100.99.120.110/home/ku/SHADE01 main:refs/heads/from-gram
ssh ku@100.99.120.110 'cd ~/SHADE01 && git merge --ff-only from-gram && git branch -d from-gram'
```

⚠️ 체크아웃된 브랜치(`main`)로 직접 push 하면 거부된다. 임시 브랜치로 받아 병합한다.

### pip — 휠을 미리 받아 옮기기

`ku` 도 Python **3.12.3** 이라 gram 에서 받은 `cp312` 휠이 그대로 맞는다.

```bash
# gram 에서
.venv/bin/pip download -d /tmp/wheels pyulog numpy pymavlink pyserial
scp /tmp/wheels/*.whl ku@100.99.120.110:/tmp/shade-wheels/

# ku 에서 — 새 venv 는 pip 이 없으므로 기존 venv 의 pip 을 빌려 쓴다
cd ~/SHADE01
python3 -m venv --without-pip .venv
~/SHADE01/venv-ardupilot/bin/python -m pip --python .venv/bin/python install \
  --no-index --find-links /tmp/shade-wheels pyulog numpy pymavlink pyserial
```

⚠️ `--python` 은 **`install` 앞에** 와야 한다. 뒤에 두면
`The --python option must be placed before the pip subcommand name` 로 죽는다.

## 파일 주고받기

```bash
scp ku@100.99.120.110:'~/SHADE01/logs/*.ulg' logs/
```

⚠️ `.ulg` 는 git 에 안 들어간다 (`.gitignore`). 분석 **수치를 문서로** 남기는 것이
유일한 영구 기록이다 — [PROCEDURE.md 3장](../PROCEDURE.md#3-기록).
