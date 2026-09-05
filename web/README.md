# web — shade01.bewe.co.kr 비행로그 뷰어

로그를 올리면 목록이 뜨고, 클릭하면 **지도 위 궤적과 시간축 그래프가 동기화되어 재생되는**
분석 페이지가 나온다. 파싱은 리포의 [`tools/qgclog`](../tools/qgclog/) 를 그대로 쓴다.

**조회는 공개, 업로드만 공유 암호.**

```
목록      https://shade01.bewe.co.kr/
분석      https://shade01.bewe.co.kr/log/<id>          ?t=113.5 로 그 순간부터
비교      https://shade01.bewe.co.kr/compare?a=<id>&b=<id>
상태      https://shade01.bewe.co.kr/api/health
```

## 왜 만들었나

CLI 분석은 `gram` 한 대에 묶여 있었고, 결과가 터미널 텍스트라 **시간축을 못 보여줬다.**
[#184 지오펜스 사건](../flights/2026-09-02-log184-geofence-lockout.md)을 밝힌 결정적 증거는
"113.5초 failsafe 발동 → 스로틀 -1.00 인데 하강률 0.00 → 165.5초 POSCTL 전환 후에야
-1.5 m/s" 라는 **시간에 따른 변화**였고, 그건 표로 옮겨 적어야 겨우 보였다.
이제 `?t=155` 로 열면 한눈에 보인다.

로그가 PC 3대에 흩어져 있던 문제도 같이 해결한다 — 서버가 정본 보관소다.

## 구조

```
server.js        node:http 서버. 외부 의존 0. 라우팅·업로드·gzip·정적 서빙
extract.py       .venv 로 실행. qgclog 로 파싱해 JSON 을 stdout 으로
public/          index.html(목록) log.html(분석) compare.html(비교)
                 chart.js(SVG 차트) player.js(재생) app.css
                 vendor/leaflet/  자체 호스팅 (CDN 미사용)
deploy/          systemd 유닛 2개 + cloudflared ingress + deploy.sh
tools/gather.sh  3대에서 로그 수집 → 서버 업로드
```

**Node 가 Python 을 서브프로세스로 부른다.** `qgclog` 는
`contextlib.redirect_stdout` 으로 전역 `sys.stdout` 을 바꾸고 `_patch_pyulog()` 로
pyulog 클래스를 영구 변형하므로 **스레드로 돌리면 서로 밟는다.** 프로세스를 나누면
그 문제가 원천적으로 없다. 실측 파싱 비용이 10MB 에 0.45초라 감당이 된다.

결과는 `DATA_DIR/cache/v1.<지문>/` 에 굽는다. **지문은 `qgclog.py` + `extract.py` 의
해시**라 파서를 고치면 캐시가 저절로 무효화된다 — 오늘 고친 버그가 캐시에 굳어
계속 보이는 일이 없다.

## 반드시 지킬 것

🔴 **`pyulog` 를 직접 부르지 마라.** 잘린 메시지 하나에서 읽기를 포기해 23MB 로그가
27초로 보인다. `extract.py` 가 유일한 파싱 경로다. 근거:
[PROCEDURE.md](../PROCEDURE.md) "분석기 — 잘린 메시지에서 멈추지 않는다".

🔴 **업로드는 한 디렉토리에 평면으로 쌓는다.** `qgclog._repair()` 가 구독 섹션이
유실된 로그를 복구할 때 **자기 디렉토리의 형제 로그**를 기증자로 쓴다. 하위 폴더를
만들면 기증자 풀이 쪼그라들어 복구가 안 된다.

🔴 **고도는 `_agl()` 을 거친다.** `z` 를 그대로 읽으면 EKF 원점 기준이라 지상 로그가
`-7.0 m` 로 나온다.

🔴 **`kill` / `fuser -k` 금지.** `Restart=` 때문에 TERM 을 보내면 유닛이 죽은 채 남는다.
`systemctl` 로만 다룬다.

🔴 **`.ulg` 원본은 웹으로 안 내보낸다.** 조회가 공개라 링크를 아는 누구나 받아가게
되고, 로그에는 비행장 좌표와 기체 전체 텔레메트리가 들어 있다. 분석에 필요한 값은
`sum`/`trk` 로 나가므로 원본을 열 이유가 없다. `/api/logs/<id>/file` 은 403 이다.
원본이 필요하면 서버의 `~/shade01-data/logs/` 에서 직접 가져와라.

🔴 **리포는 public 이다.** 서버 IP·터널 UUID·업로드 암호를 커밋하지 마라.
설정에는 `localhost` 만 쓴다 (앱이 루프백에 바인딩하므로 실제로 동작한다).

## 데이터 계약

`extract.py full <path>` 가 `{ok, row, sum, trk}` 를 낸다.

- **`row`** — 목록 한 줄. `badge` 는 규칙 기반 분류
  (`flight`/`hover`/`ground`/`abort`/`noarm`/`unknown`).
- **`sum`** — `qgclog.analyse()` 결과 그대로 + `uuid`. 최대/최소는 **원본 레이트**에서 뽑는다.
- **`trk`** — **균일 5 Hz 격자** 시계열. 토픽마다 레이트가 달라(자세 20Hz, 위치 10Hz,
  배터리·스틱 5Hz) 각자의 시간축을 보내면 지도·차트·커서가 서로 다른 인덱스를 쓰게 된다.
  격자 하나를 공유하면 `i = round(t * hz)` 하나로 전부 정렬된다.

⚠️ **격자 값은 보여주기용이다.** 5Hz 는 79.3A 같은 순간 첨두를 놓칠 수 있으므로
최대값은 항상 `sum` 을 쓴다. (실측: 격자 78.5A vs 요약 79.3A)

### 올릴 값이 없는 로그는 안 올라간다 (2026-09-05)

`gather.sh` 가 업로드 전에 세 가지를 거른다:

| 사유 | 기준 |
|---|---|
| `unreadable` | **서버가 렌더하지 못한다** |
| `abort` | arm 하자마자 disarm (6초 이하) |
| `indoor` | GPS 가 붙어 있는데 **3D fix 를 한 번도 못 잡았다** |

`ground`·`hover`·`noarm`·`unknown` 은 **올린다.** 지상 시험도 진동·전류 점검에
쓰이고 나중에 되돌아볼 수 있어야 한다.

판정은 [`web/tools/uploadable.py`](tools/uploadable.py) 가 하고, 배지는
`extract.py` 의 `classify()` 를 그대로 쓴다 — 기준을 두 곳에 두면 "목록에
`abort` 로 보이는데 올라와 있는" 어긋남이 생긴다.

🔴 **판정은 서버가 실제로 도는 경로를 그대로 태운다.** `summarize()` 만 보고
통과시키면 안 된다 — **요약이 멀쩡해도 `build_track()` 에서 터지는 로그가 있다.**
실측(2026-09-05): `SP` 미정의로 6개가 회색 행이 됐는데 `extract.py row` 로는
전부 정상으로 보였다. 그래서 `armed_window`·`flight_key`·`decoded_points`·
`build_track` 까지 같은 순서로 부른다.

#### 실내 판정에 함정이 둘 있다 — 둘 다 실측으로 찾았다

**1. 토픽 이름이 펌웨어마다 다르다.** `sensor_gps` 만 보면 9/2 의 **실제 야외
비행**(`log_182`·`log_186`)이 "GPS 없음"으로 잡힌다 — 그쪽은
`vehicle_gps_position` 을 쓴다. 둘 다 봐야 한다.

**2. `fix_type` 에도 깨진 바이트가 들어온다.** `log_182` 는 1584샘플이 4(RTK)인데
한 샘플만 **215** 였다. 0~8 밖의 값을 버리고 최대를 본다.

⚠️ **GPS 토픽이 아예 없는 것은 실내로 치지 않는다.** 너무 짧아 한 번도 발행되지
않았을 수 있다 (실측: 9/5 야외 세션의 1.5초 로그).

🔴 **서버에 이미 있는 파일은 판정하지 않는다.** 기준이 나중에 바뀌어도 서버
목록이 저절로 흔들리면 안 된다.

⚠️ **판정이 터지면 올리는 쪽으로 기운다.** 막는 쪽으로 기울면 멀쩡한 비행이
조용히 사라진다 — 서버가 정본 보관소다.

2026-09-05 에 이 기준으로 서버를 정리했다: **117 → 72개.**
`abort` 34, `unreadable` 3, `indoor` 8 (8/31 세션 전체). 사본은 `ku` 에
전부 남아 있고, 문서가 인용한 5건은 수치 인용이라 링크가 깨지지 않는다.

## 로컬에서 돌리기

```bash
cd <repo>
LOG_DIR=$PWD/logs DATA_DIR=$PWD/web/data QGCLOG_PYTHON=$PWD/.venv/bin/python \
  PORT=4399 ~/.nvm/versions/node/v20.20.1/bin/node web/server.js
# http://localhost:4399
```

## 서버 설치 (ku-labserver, 최초 1회)

```bash
# 1. 리포 — public 이라 배포키가 필요 없다
ssh ku@<서버> 'git clone https://github.com/6K5EUQ/SHADE01.git ~/SHADE01'

# 2. venv — 이 서버에는 pip 도 ensurepip 도 없다. get-pip 로 부트스트랩한다.
ssh ku@<서버> '
  python3 -m venv --without-pip ~/shade01-venv
  curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  ~/shade01-venv/bin/python /tmp/get-pip.py -q
  ~/shade01-venv/bin/pip install -q -r ~/SHADE01/web/requirements.txt
  rm -f /tmp/get-pip.py
  ~/shade01-venv/bin/python -c "import pyulog, numpy; print(\"ok\")"'

# 3. 설정 — 암호는 여기서 만들고 커밋하지 않는다
ssh ku@<서버> '
  mkdir -p ~/shade01-data/logs
  cd ~/SHADE01/web && cp .env.example .env
  sed -i "s|^UPLOAD_PASSWORD=.*|UPLOAD_PASSWORD=$(openssl rand -base64 18)|" .env
  grep UPLOAD_PASSWORD .env'      # ← 이 값을 조종자에게 알려준다

# 4. 로그 올리기 (gram 에서)
./web/tools/gather.sh

# 5. 터널 — UUID 는 create 가 만들어 준다
ssh ku@<서버> '
  ~/.local/bin/cloudflared tunnel create shade01
  # 출력된 UUID 로 config 를 채운다
  sed "s/REPLACE_WITH_TUNNEL_UUID/<UUID>/g" ~/SHADE01/web/deploy/config-shade01.yml \
    > ~/.cloudflared/config-shade01.yml
  ~/.local/bin/cloudflared tunnel route dns shade01 shade01.bewe.co.kr'

# 6. systemd
ssh ku@<서버> '
  sudo cp ~/SHADE01/web/deploy/lab-shade01.service /etc/systemd/system/
  sudo cp ~/SHADE01/web/deploy/lab-tunnel-shade01.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now lab-shade01 lab-tunnel-shade01
  systemctl is-active lab-shade01 lab-tunnel-shade01'
```

## 배포 (이후)

```bash
ssh ku@<서버> 'cd ~/SHADE01 && ./web/deploy/deploy.sh'
```

## 장애 대응

| 증상 | 확인 | 대응 |
|---|---|---|
| 500 / 페이지 안 뜸 | `systemctl status lab-shade01`, `tail ~/shade01-data/server.log` | `sudo systemctl restart lab-shade01` |
| 502 / 도메인만 죽음 | `systemctl status lab-tunnel-shade01` | 터널만 재시작. 다른 도메인엔 영향 없다 |
| 전부 "파싱 실패" | `curl .../api/health` 의 `upload`·`logs` | venv 가 깨졌다. 위 2단계를 다시 |
| 업로드 401 | `.env` 의 `UPLOAD_PASSWORD` | 비어 있으면 업로드가 막힌다 (의도된 동작) |
| 수치가 옛날 값 | `/api/health` 의 `fingerprint` | 파서를 고쳤으면 지문이 바뀌어 자동 재계산된다 |
| 디스크 | `df -h /`, `du -sh ~/shade01-data` | 실측 67개 = 209MB. 여유 205GB |
