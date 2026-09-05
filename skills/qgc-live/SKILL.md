---
name: qgc-live
description: 지금 날고 있는 기체를 브라우저로 본다. "qgc live on" 으로 실시간 트래킹(HUD + 흘러가는 차트, localhost:4400)을 켜고 "off" 로 끈다. 비행 중 상태 확인, 링크가 붙었는지 점검, 화면이 안 뜰 때 진단에 쓴다. 읽기 전용이라 FC 로 아무것도 안 보낸다. 지나간 .ulg 분석은 qgc-log 쪽이다.
---

# qgc-live — 실시간 비행 트래킹

**지금 이 순간**의 기체를 브라우저로 띄운다. 좌측은 HUD(인공수평의·테이프·
상태밴드), 우측은 로그 뷰어와 같은 그림의 **흘러가는 시계열 차트**다.

**이 스킬은 SHADE01 리포가 정본이다** (`skills/qgc-live/SKILL.md`).
`~/.claude/skills/qgc-live` 는 그쪽을 가리키는 심볼릭이다 — 사본을 만들지 마라.

**`./qgc live` 만 다룬다.** 형제인 `./qgc log` 는 다른 물건이다 — 끝난 비행의
`.ulg` 를 분석한다. 사용자가 "지난 비행", "로그", "디브리핑" 을 말하면 그쪽이다
(`qgc-log` 스킬).

```
<SHADE01>/qgc                     진입점 — ./qgc live ...
<SHADE01>/tools/live/livectl      본체 (bash) — systemd --user 를 몬다
<SHADE01>/web/live/mav_live.py    UDP MAVLink 수신 → 로컬 HTTP
<SHADE01>/web/live/README.md      설계·함정 전문
```

## 🔴 읽기 전용이다

FC 로 나가는 바이트가 **0** 이다. ARM·모드변경·미션업로드는 이 페이지로 못 한다 —
조작은 QGC 로 한다. 사용자가 이 페이지로 기체를 조작해 달라고 하면 **그건 안 된다고
말하고** QGC 를 쓰라고 안내한다. 구조로 막혀 있다 (소켓 송신 호출 없음,
`MAVLink(None)` 파서, `do_GET` 만, `127.0.0.1` 바인딩).

기체 FC 는 상행이 열려 있어 `PARAM_SET` 한 줄로 ARM 이 들어간다. 그래서 이
페이지는 **일부러** 못 보내게 만들어 뒀다 — 편의를 위해 이 성질을 풀지 마라.

## 사용법

```bash
./qgc live on          # 켠다 → http://localhost:4400
./qgc live on 14551    # UDP 포트 지정 (14550 이 이미 물려 있을 때)
./qgc live always      # 켜고 + 부팅 때도 자동 (재부팅해도 산다)
./qgc live off         # 끈다 (부팅 자동시작도 같이 뗀다)
./qgc live status      # 상태 + 링크 수신 여부 + 지금 모드·고도
./qgc live log [줄수]  # 서비스 로그 (기본 40줄)
./qgc live install     # systemd 유닛만 설치 (on 이 알아서 한다)
```

`systemd --user` 로 돈다 — **터미널을 닫아도 살아 있다.**

`always` 는 `enable` + `linger` 를 둘 다 건다. `--user` 유닛은 `enable` 만으로는
부팅 때 안 뜬다 — 로그인 세션이 없으면 유저 매니저가 없기 때문이다.
`off` 는 `disable` 까지 하므로 **off 는 진짜 off** 다. `ku`·`rim3` 이 `always`
로 걸려 있다 (2026-09-05).

## 절차

### 켜 달라고 하면

1. `./qgc live on` — 포트를 지정했으면 그대로 넘긴다.
2. 출력에 **포트 충돌 경고**가 있으면 그것을 그대로 전한다. 실패했으면
   (exit≠0) `./qgc live on 14551` 을 권한다.
3. `./qgc live status` 로 링크가 붙었는지 확인해 **같이 보고한다.**
   서비스가 떴다는 것과 데이터가 들어온다는 것은 다른 말이다.
4. `http://localhost:4400` 을 알려 준다.

### 상태를 물으면

`./qgc live status` 한 줄이면 끝이다. 읽는 법:

| 표시 | 뜻 |
|---|---|
| `● ON` + `링크: 수신 중` | 정상. 모드·ARMED·고도가 지금 값이다 |
| `● ON` + `링크: 끊김 (N초 전)` | 서비스는 살아 있고 **기체 쪽이 조용하다**. 아래 값은 `(마지막)` 이 붙는다 — 지금 값이 아니다 |
| `● ON` + `링크: 없음` | 한 번도 프레임을 못 받았다. 포트·경로 문제 (아래 「패킷 0」) |
| `· 부팅 자동시작` | `always` 가 걸려 있다 — 재부팅해도 뜬다 |
| `○ OFF` | 꺼져 있다 |

🔴 **`(마지막)` 이 붙은 값을 현재값처럼 말하지 마라.** 링크가 끊긴 뒤에도
마지막 프레임이 남아 있어 고도·모드가 그럴듯하게 보인다.

🔴 **「켜져 있다」와 「데이터가 온다」는 다른 말이다.** `systemctl` 이 `active`·
`enabled` 여도 패킷이 0 일 수 있다. 반드시 `status` 의 `링크:` 줄까지 보고
보고하라 — `rim3` 이 실제로 그 상태였다 (아래 「패킷 0」).

### 화면이 안 뜬다고 하면

순서대로 좁힌다. **`curl` 로 200 이 나온다고 정상이 아니다** — 아래 3번.

```bash
./qgc live status                      # 1. 서비스가 떠 있나
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:4400/   # 2. HTTP 응답
curl -s 'http://localhost:4400/api/state?track=0' \
  | python3 -m json.tool >/dev/null && echo "JSON OK"             # 3. 파싱되나
./qgc live log 30                      # 4. 서비스 로그
ss -ulnp | grep 1455                   # 5. 누가 포트를 쥐었나
```

| 증상 | 원인 | 대응 |
|---|---|---|
| `on` 이 실패 (exit 1) | 대개 **포트 충돌** — QGC 나 `shade-bridge` 가 14550 을 쥠 | `./qgc live on 14551` |
| 화면이 「서버 없음」인데 서비스는 ON | **응답에 NaN 이 섞였다** (아래) | 3번으로 확인 |
| **「링크 없음」·패킷 0** | 그 포트로 MAVLink 가 안 온다 | `pc_bridge.sh` 의 `TARGETS` 에 그 PC 의 `:14551` 이 있나 본다. 고쳤으면 **브리지를 돌리는 PC**(rim3)에서 `systemctl --user restart shade-bridge` |
| 값이 멎음 | 링크 끊김 | 헤더 `pkt` 가 느는지 본다. 안 늘면 링크, 늘면 FC 가 그 메시지를 안 보내는 것 |
| 차트만 빈 채 | `/chart.js` 가 404 | `web/public/chart.js` 가 있어야 한다 (폴백 경로) |

## 반드시 지킬 것

🔴 **NaN 하나가 화면 전체를 끈다.** 파이썬 `json.dumps` 는 NaN 을 그대로 `NaN`
이라 적는데 유효한 JSON 이 아니다. 브라우저 `JSON.parse` 가 응답 **전체**를
거부해 고도·모드·전압·차트가 같이 사라지고 「서버 없음」이 뜬다. 서버는 멀쩡하다.

실기에서 났다 (2026-09-05): `ESTIMATOR_STATUS` 의 vel·pos 비율이 EKF 수렴 전에
NaN 으로 온다. `dumps_json()` 이 NaN·±Inf 를 null 로 바꾼다 — **이 경로를 우회해
`json.dumps` 를 직접 부르지 마라.**

⚠️ **API 는 `curl` 이 아니라 파서로 확인한다.** `curl` 은 파싱을 안 해서 NaN 이
섞여도 200 OK 로 멀쩡해 보인다.

🔴 **포트를 조용히 나눠 갖게 만들지 마라.** `SO_REUSEADDR` 을 켜면 커널이 패킷을
QGC 와 이 페이지 중 한쪽에만 주어 서로 프레임을 훔친다. 지금은 충돌하면 **시끄럽게
죽는다** — 의도된 동작이다. 같이 쓰려면 브리지 고정 대상에 `127.0.0.1:14551` 을
더하고 `./qgc live on 14551` 로 비켜난다.

🔴 **화면을 고쳤으면 자체검사를 돌린다** — `http://localhost:4400/_selftest.html`.
합성 피드로 DOM 을 실측한다(FC·서버 데이터 불필요). **FAIL 0 이어야 배포한다.**

## PC 별 포트 (2026-09-05)

4대 전부 가동. 포트가 다른 이유가 있다:

| PC | UDP | 항상켜기 | 왜 그 포트인가 |
|---|---|---|---|
| `ku` | 14550 | ✅ `always` | 비어 있다 |
| `rim3` | **14551** | ✅ `always` | `shade-bridge` 가 14550 을 쥔다 |
| `rim` | **14551** | ✅ `always` | QGC 가 14550 을 쥔다 (상주 지상국) |
| `gram-labtop` | 14550 | 수동 | 비어 있다. SSH 가 막혀 원격으로 못 건다 |

🔴 **14551 인 PC 는 브리지가 그 포트로도 보내야 한다.** `pc_bridge.sh` 의
`TARGETS` 에 `127.0.0.1:14551`(rim3 자기 자신)과 `100.107.83.47:14551`(rim) 이
있는 이유다. 없으면 **켜져만 있고 패킷 0** — 둘 다 실제로 그랬다.

`ku` 는 **WiFi 장치가 없어** ELRS 백팩 AP 에 못 붙는다 — 브리지 경로로만 본다.

## 더 읽을 곳

- [`web/live/README.md`](../../web/live/README.md) — 설계·함정·자체검사 전문
- [`README.md`](../../README.md#링크-구성--3-경로) — 링크 3경로
- 로그 분석은 `qgc-log` 스킬
