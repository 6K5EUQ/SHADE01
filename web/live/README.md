# web/live — 실시간 비행 트래킹

지금 나는 기체를 브라우저로 본다. 한쪽은 지도, 한쪽은 계기다 —
[shade01.bewe.co.kr](https://shade01.bewe.co.kr) 의 로그 뷰어가 **끝난 비행**을
보는 것이라면, 이쪽은 **지금 이 순간**이다.

```bash
./qgc live on                   # 켠다 → http://localhost:4400
./qgc live off                  # 끈다
./qgc live status               # 상태 + 링크 수신 여부
./qgc live on 14551             # QGC 와 14550 이 겹칠 때 비켜서 켠다
```

`systemd --user` 로 돈다 — **터미널을 닫아도 살아 있다.** 비행 중에 창이 닫혔다고
화면이 죽으면 곤란하기 때문이다. 유닛은 처음 `on` 할 때 저절로 설치된다.

직접 띄우려면 (포그라운드, Ctrl-C 로 종료):

```bash
./web/live/live                 # http://localhost:4400
```

🔴 **읽기 전용이다. FC 로 아무것도 보내지 않는다.** ARM·모드변경·미션업로드는
이 페이지로 못 한다 — 조작은 QGC 로 한다. 근거는 아래 「상행이 없다」.

## 무엇이 보이나

| 영역 | 내용 |
|---|---|
| 지도 | 항적, 기체(기수 방향), 홈(H), 위경도·홈거리 |
| 큰 숫자 | 고도(AGL)·대지속도·전압·전류 — 곁눈질로 읽는 값 |
| 인공수평의 | roll/pitch. 지도만으로는 기울기를 못 본다 |
| 계기 | roll·pitch·기수·상승률·스로틀·대기속도 |
| 배지 | GPS·EKF·진동·배터리·RC·소모 — 초록/노랑/빨강 |
| 차트 | 최근 60초 고도·속도·전류 |
| 메시지 | FC 의 STATUSTEXT (`Sensor lost` 등이 여기 뜬다) |

헤더의 **ARMED / 모드 / VTOL 상태**는 항상 보인다. 쿼드 전용 운용이므로
[VTOL 상태가 `MC` 가 아니면](../../README.md#-고정익-사용-금지--쿼드-전용-2026-09-04)
빨간 배너가 뜬다.

## PC 별 구축 상태 (2026-09-04)

| PC | 상태 | UDP 포트 | 왜 |
|---|---|---|---|
| `ku` | ✅ 가동 | **14550** | 비어 있다 |
| `rim3` | ✅ 가동 | **14551** | `shade-bridge` 가 14550 을 쥔다 (Tailscale 주소에 바인딩) |
| `rim` | ✅ 가동 | **14551** | QGC 가 14550 을 쥔다 |
| `gram-labtop` | ⬜ 미설치 | — | 이 PC 들의 SSH 키가 gram 에 없다. **아래를 gram 에서 직접 한 번 돌린다** |

`gram` 에서 (한 번만):

```bash
cd ~/SHADE01
git pull
python3 -m venv .venv 2>/dev/null            # 이미 있으면 건너뛴다
.venv/bin/pip install -r web/requirements.txt
loginctl enable-linger $(whoami)             # 로그아웃해도 살아 있게
./qgc live on                                # 14550 이 막혀 있으면: ./qgc live on 14551
./qgc live status
```

⚠️ `.venv` 를 `--without-pip` 로 만든 PC (`ku` 가 그렇다) 는 `pip` 이 없다.
그때는 [ACCESS.md 의 휠 옮기기](../../gcs/ACCESS.md#pip--휠을-미리-받아-옮기기)를 쓴다.

⚠️ **`linger` 를 켜야 로그아웃 후에도 산다.** 안 켜면 SSH 를 끊는 순간 유닛이
죽는다 — `rim3`·`rim` 은 처음에 `Linger=no` 였고 켜 줬다.

## 어디서 데이터를 받나

**UDP 14550 하나로 두 경로를 다 받는다.** 어느 쪽이든 그냥 켜면 된다.

| 경로 | 되는 PC | 방법 |
|---|---|---|
| **ELRS 백팩** (조종기 WiFi) | `rim3`, `gram-labtop` | `./gcs/qgroundcontrol/elrs-backpack` 로 AP 에 붙은 뒤 `./qgc live on` |
| **shade-bridge** (FC USB 직결) | 전부 (Tailscale) | 브리지가 도는 상태에서 `./qgc live on` |

⚠️ **`ku` 는 WiFi 장치가 없다** (유선 `enp3s0` 뿐). 백팩 AP 에 못 붙으므로
`ku` 에서는 브리지 경로로만 볼 수 있다 — [링크 구성](../../README.md#링크-구성--3-경로).

### 포트가 겹칠 때

QGC 나 `shade-bridge` 가 이미 14550 을 쓰고 있으면 **시끄럽게 죽는다.** 일부러
그렇게 했다 — `SO_REUSEADDR` 로 조용히 나눠 가지면 커널이 패킷을 한쪽에만 주어
QGC 와 이 페이지가 서로 프레임을 훔쳐 간다 (`mav_bridge.py` 와 같은 이유).

같이 쓰려면 **브리지의 고정 대상에 이 페이지를 하나 더 추가**하고 비켜 준다:

```bash
# 브리지 쪽: 기존 대상들 + 로컬 14551 로도 같은 스트림을 보낸다
./shade-bridge/pc_bridge.sh ... 127.0.0.1:14551

# 이 페이지: 14551 을 듣는다
./qgc live on 14551
```

## 상행이 없다 — 어떻게 보장하나

기체 FC 는 상행이 열려 있어서 `PARAM_SET` 한 줄로 ARM·모드변경이 들어간다
([README](../../README.md#2-pc-usb-직결-브리지----현재-가동중-rim3)). 브라우저에
붙는 페이지가 그 경로를 건드리면 안 되므로 **구조적으로** 막았다:

| 막은 방법 | 확인 |
|---|---|
| 소켓에 `sendto`/`send` 호출이 코드에 없다 | `grep -n "sendto" web/live/mav_live.py` |
| 파서를 `MAVLink(None)` 으로 만든다 — 출력 파일이 없다 | 실수로 `*_send()` 를 불러도 전송이 아니라 예외가 난다 |
| `mavutil.mavlink_connection()` 을 안 쓴다 | 그 래퍼는 하트비트를 자동으로 되쏜다 |
| HTTP 는 `do_GET` 만 있다 | POST 는 501 |
| HTTP 는 `127.0.0.1` 에만 바인딩 | `ss -tlnp \| grep 4400` |

**실측 (2026-09-04)** — 가짜 FC 를 세워 8초간 텔레메트리를 보내면서 페이지가
`/api/state`·`/api/reset` 을 두드리게 했다. FC 쪽으로 **돌아온 바이트 0**.

## 구조

```
mav_live.py        UDP 수신 → MAVLink 디코딩 → 상태 1개 → 로컬 HTTP
public/index.html  지도|데이터 2단 레이아웃
public/live.js     200ms 폴링, 지도·인공수평의·차트
public/live.css    배치. 팔레트는 ../public/app.css 를 그대로 쓴다
live               직접 실행 (포그라운드)
shade-live.service systemd --user 유닛 — `./qgc live on` 이 설치한다
```

`./qgc live` 의 본체는 [`tools/live/livectl`](../../tools/live/livectl) 이다.

Leaflet 과 `app.css` 는 **로그 뷰어의 것을 그대로 재사용**한다 (`web/public/`).
없으면 못 뜨므로 이 폴더만 떼어 옮기지 마라.

### 왜 폴링인가 (WebSocket 이 아니라)

서버가 "지금 상태" 하나만 들고 있고 화면은 그것을 5Hz 로 긁어 간다. 잠깐
끊겨도 다음 폴에서 저절로 복구되고, 되감을 상태가 없어 재접속 로직이 필요
없다. 텔레메트리 자체가 5Hz 라 더 자주 받아도 같은 값이 두 번 온다.

항적만 증분으로 받는다 (`?since=n`) — 40분 비행이면 점이 만 개가 넘는데 매번
전부 보내면 폴 하나가 수백 KB 가 된다.

## 알아 둘 것

🔴 **PX4 는 `ESTIMATOR_STATUS` 를 보낸다.** ArduPilot 의 `EKF_STATUS_REPORT` 가
아니다 — pymavlink `common` 에는 `EKF_*` 상수 자체가 없다. 그리고 그 값은
**분산이 아니라 비율(ratio)** 이다: **1.0 을 넘으면** 그 센서의 혁신 검사가
깨지고 있다는 뜻이다. 근거: `PX4-Autopilot/src/modules/mavlink/streams/ESTIMATOR_STATUS.hpp`

🔴 **`BATTERY_STATUS.voltages[]` 는 셀 전압이 아닐 수 있다.** PX4 는 셀 전압을
모르면(PM08 이 그렇다) **총 전압을 첫 칸에** 넣고, 65535 를 넘으면 65534 짜리
덩어리로 쪼갠다. 그래서 미사용 표식 **65535 만** 걸러야 한다 — 65534 까지
빼면 65.5V 를 통째로 잃는다. 실측 검증: 6S 셀별/총전압/쪼갠 값/14셀 전부 일치.

🟡 **백팩 AP 에는 인터넷이 없다.** 지도 타일이 외부에서 오므로 **백팩으로 붙어
있는 동안은 지도가 회색**이다. 항적·계기·차트는 전부 정상으로 돈다.

🟡 **PX4 모드는 `custom_mode` 상위 바이트에 있다.** pymavlink 의 `mode_mapping`
은 ArduPilot 용이라 그대로 쓰면 엉뚱한 이름이 나온다.

## 장애 대응

| 증상 | 확인 | 대응 |
|---|---|---|
| "서버 없음" | `./qgc live status` | `./qgc live on` |
| "링크 없음" 이 안 바뀜 | `ss -ulnp \| grep 14550` | 다른 게 포트를 쥐고 있다. 위 「포트가 겹칠 때」 |
| 지도만 회색 | 백팩 AP 인가 | 정상이다. 인터넷이 없어 타일을 못 받는다 |
| 값이 멈춤 | 헤더의 `pkt` 가 느나 | 안 늘면 링크가 끊긴 것. 늘면 FC 가 그 메시지를 안 보낸다 |
| `on` 이 실패 | `./qgc live log` | 대개 포트 충돌이다. `./qgc live on 14551` |
| 항적이 안 그려짐 | GPS 배지 | fix 3 미만이면 좌표가 0,0 이라 안 쌓는다 |
