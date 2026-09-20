# tools/preflight — 비행 전 점검

한 번 붙어서 한 패스로 끝낸다. 터미널과 웹이 **같은 코드로 같은 답**을 낸다.

```
./shade01 test                              터미널 (사람용)
./shade01 test --json                       JSON (기계용)
https://shade01.bewe.co.kr/preflight         웹 화면 (암호 필요)
```

| 파일 | 하는 일 |
|---|---|
| `preflight.py` | 🔴 **판정의 정본.** 임계값(`EXPECT`)·검사·묶음이 전부 여기 있다 |
| `agent.py` | FC 가 꽂힌 PC 에서 돌며 `preflight.py --json` 을 HTTP 로 낸다 |
| `fakefc.py` | 기체 없이 판정 코드를 돌려 보는 가짜 FC |
| `shade-preflight.service` | `agent.py` 의 systemd user 유닛 |

## 🔴 판정은 `preflight.py` 한 곳에서만 한다

웹 화면(`web/public/preflight.js`)은 서버가 준 `level`·`verdict` 를 **그리기만**
한다. 값을 JS 에서 다시 해석하면 그 순간부터 두 벌이 따로 늙어, 터미널은 GO
인데 웹은 NO-GO 인 날이 온다. 임계값을 고칠 곳은 `preflight.py` 의 `EXPECT`
뿐이고, 바꿀 때는 `FC_CHANGELOG.md` 의 근거를 같이 남긴다.

## 🔴 웹서버는 FC 와 직접 말하지 않는다

```
브라우저 ──HTTP──▶ 웹서버(ku-labserver)
                      │  HTTP + X-Preflight-Key
                      ▼
                  agent.py (rim3 — FC 가 꽂힌 PC)
                      │  subprocess
                      ▼
                  preflight.py ──MAVLink──▶ FC
```

**왜 이렇게 나눠 놨나.** 웹서버는 랩서버에서 돌고 FC 는 정비 PC 에 꽂힌다.
랩서버에서 FC 를 직접 읽으려면 rim3 브리지의 허용 목록(`pc_bridge.sh` 의
`TARGETS`)에 랩서버를 넣어야 하는데, 그러면 **공개 웹이 도는 기계가 FC 조종
포트(14550)에 상행 권한을 얻는다.** 웹서버 쪽 버그 하나가 기체로 흘러갈 길이
생기는 셈이다.

에이전트를 두면 FC 와 말하는 일이 rim3 안에 갇힌다. 랩서버가 보내는 것은
"점검을 돌려라" 라는 HTTP 요청 하나뿐이고, **브리지 허용 목록은 그대로다.**

실측(2026-09-20): 랩서버에서 `udpout:100.117.47.105:14550` 로 직접 붙어 보면
`하트비트 없음` 이다 — 허용 목록에 없어서 상행이 거절되고, 그래서 하행도 안 온다.

## 읽기 전용이라는 사실이 서는 자리

`preflight.py` 가 `PARAM_SET`·`COMMAND_LONG`·미션 업로드를 **보내지 않는다.**
`agent.py` 는 그 프로그램을 부르는 것 외에 아무것도 안 하고, 요청 본문으로
받은 것을 명령줄에 싣지 않는다 (숫자인 수집 시간만 받아 범위로 자른다).
그래서 이 경로로는 FC 값이 안 바뀌고, `FC_CHANGELOG.md` 에 적을 일이 없다.

## 에이전트 띄우기 (FC 가 꽂힌 PC)

```bash
# 1. 암호 파일 — 🔴 리포에 적지 마라 (public 이다)
mkdir -p ~/.config
printf 'SHADE_PREFLIGHT_KEY=%s\n' '<웹서버의 PREFLIGHT_KEY 와 같은 값>' \
  > ~/.config/shade-preflight.env
chmod 600 ~/.config/shade-preflight.env

# 2. 유닛 설치
mkdir -p ~/.config/systemd/user
cp ~/SHADE01/tools/preflight/shade-preflight.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now shade-preflight
loginctl enable-linger "$USER"      # 로그아웃해도 계속 돌게

# 3. 확인
curl -s http://$(tailscale ip -4):4402/health
```

기본 바인드는 그 PC 의 **Tailscale 주소**다. `0.0.0.0` 에 열면 공인 IP 가 있는
호스트에서 인터넷 누구나 점검을 돌릴 수 있게 된다 — 그래서 기본값이 아니다.

| 환경변수 | 기본 | 뜻 |
|---|---|---|
| `SHADE_PREFLIGHT_KEY` | (없음) | 웹서버와 맞춘 암호. **비우면 누구나 돌린다** |
| `SHADE_PREFLIGHT_BIND` | Tailscale 주소 | 바인드 주소 |
| `SHADE_PREFLIGHT_PORT` | `4402` | 포트 |
| `SHADE_PREFLIGHT_TIMEOUT` | `45` | 점검 하나에 줄 시간(초) |
| `SHADE_PREFLIGHT_INTERVAL` | `5` | 연타 방지 간격(초) |

## 웹서버 쪽 (`ku-labserver`)

`~/SHADE01/web/.env` 에 넣는다:

```
PREFLIGHT_KEY=<에이전트와 같은 값>
PREFLIGHT_AGENTS=100.117.47.105:4402,100.99.120.110:4402
```

후보를 앞에서부터 훑어 **먼저 답하는 것**을 쓴다. FC 를 rim3 에서 뽑아 다른 PC
에 꽂아도 그 PC 에 에이전트만 떠 있으면 화면은 그대로 돈다.

화면 접속 암호는 **업로드와 같은 `UPLOAD_PASSWORD`** 다. 점검은 읽기 전용이지만
FC 링크를 실제로 쓰므로 공개 조회와 같은 문에 두지 않는다.

## 기체 없이 시험하기

판정 코드 대부분은 뭔가 잘못됐을 때 도는 코드다. 멀쩡한 실기에서는 NO-GO
경로가 한 줄도 안 돌아 본 채로 남는다.

```bash
# 터미널 A
.venv/bin/python tools/preflight/fakefc.py good --port 14999
#   good fw nogps batt armed vibe — good 만 GO 여야 한다

# 터미널 B
./shade01 test -t 5 --conn udpout:127.0.0.1:14999
./shade01 test -t 5 --conn udpout:127.0.0.1:14999 --json | python3 -m json.tool
```

⚠️ **`good` 이 지금 「확인 후 판단」 을 낸다** (2026-09-20 확인). `fakefc.py` 가
`EXPECT` 최신값을 안 따라간 탓이다 — `RC_MAP_TRANS_SW=0`, `VT_ARSP_TRANS`·
`MAV_0_FORWARD` 미제공, 대기속도 −4.9. **판정 코드가 아니라 가짜 FC 쪽 문제다.**

관련: [`skills/shade01-test/SKILL.md`](../../skills/shade01-test/SKILL.md) 에이전트용 절차 ·
[`web/README.md`](../../web/README.md) 웹 화면 · [`FC_CHANGELOG.md`](../../FC_CHANGELOG.md) 임계값 근거
