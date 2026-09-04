# PC 직결 브리지

FC 를 **PC 에 USB 로 직결**했을 때, 그 PC 를 중계기로 삼아 다른 PC 의 QGC 도
Tailscale 로 붙게 한다. raspb1 이 하던 일을 PC 가 대신 하는 것이다.

## 언제 쓰나

정규 비행 경로는 **raspb1** 이다. PC 직결은 그 자리를 임시로 대신한다
([링크 구성 — 3 경로](../README.md#링크-구성--3-경로)).

**FC USB 는 하나뿐**이라, PC 직결은 raspb1 USB 를 뽑았다는 뜻이다. 그때만 쓴다:

- 펌웨어 플래시
- 부트로더 작업
- raspb1 이 고장났을 때
- 지상 정비·파라미터 확인

> 🟡 **2026-09-04 현재 이 경로가 가동중이다.** FC USB 가 `rim3` 에 꽂혀 있고,
> raspb1 은 Tailscale 에서 `offline` 이다. ku·rim 까지 중계되는 것을 양방향으로
> 실측했다 (28.4 KB/s, `PARAM_REQUEST_READ` 왕복). **기체를 띄우기 전에 raspb1 로
> 원복한다** — `rim3` 는 기체에 안 실린다.

## 쓰는 법

```bash
cd SHADE01
./shade-bridge/pc_bridge.sh
```

시리얼 포트를 자동으로 찾는다 (`ttyACM0` → `ttyACM1` → `ttyUSB0`).
다른 포트면 지정한다:

```bash
MAV_SERIAL=/dev/ttyACM1 ./shade-bridge/pc_bridge.sh
```

이 PC 를 포함해 네 대 전부에 UDP 14550 으로 중계한다. 각 PC 에서 QGC 를 켜면
기체가 뜬다. 종료는 Ctrl-C.

## 중계 대상

`pc_bridge.sh` 의 `TARGETS` 배열이다. PC 가 늘거나 IP 가 바뀌면 여기를 고친다.

| 호스트 | Tailscale IP |
|---|---|
| ku-dgs1 | 100.99.120.110 |
| rim | 100.107.83.47 |
| rim3 | 100.117.47.105 |
| gram-labtop | 100.66.204.25 |

자기 자신도 목록에 있다 — 로컬 QGC 도 같은 UDP 로 붙기 때문이다.

## 🔴 FC 를 바꿨으면 기록해라

이 브리지는 상행이 열려 있어 **`PARAM_SET` 한 줄로 실기 설정이 바뀐다.** 바꿨으면
[`FC_CHANGELOG.md`](../FC_CHANGELOG.md) 에 일시(KST)·작업 PC·경로·값·이유를 적고
커밋·푸시한다. **작업 전에도 읽어라** — 마지막 변경을 모르면 낡은 스냅샷을 정본으로
착각한다.

## 노출 범위 — 반드시 읽어라

브리지는 받은 UDP 를 **MAVLink 로 해석하지 않고 그대로 FC 에 쓴다.** 즉 이 포트에
닿을 수 있는 사람은 ARM·DISARM·모드변경·미션업로드를 실기에 직접 명령할 수 있다.
PX4 쪽에 서명(signing)도 인증도 없다.

그래서 브리지는 **Tailscale 주소에만 바인딩하고, 허용 목록 밖에서 온 UDP 는 버린다**
(2026-09-02 수정). 시작 로그에서 확인한다:

```
mav_bridge: serial=/dev/ttyACM0 baud=921600 udp=100.99.120.110:14550 (Tailscale 자동탐지)
mav_bridge: 허용 송신자: 100.107.83.47, 100.117.47.105, 100.66.204.25, 100.99.120.110, 127.0.0.1
```

⚠️ **`udp=0.0.0.0:14550` 이 찍히면 멈춰라.** Tailscale 주소를 못 찾았다는 뜻이고, 이
호스트에 공인 IP 가 있으면 인터넷에서 FC 로 명령을 넣을 수 있다. `ku-dgs1` 은 실제로
공인 IP(`203.253.176.74`)를 갖고 있고 `ufw` 도 꺼져 있다 — 2026-09-02 에 캠퍼스 밖에서
UDP 가 그대로 도달하는 것을 실측했다. 이때는 직접 지정한다:

```bash
MAV_BIND=100.99.120.110 ./pc_bridge.sh
```

| 환경변수 | 뜻 |
|---|---|
| `MAV_BIND` | 바인딩 주소. 비우면 Tailscale 주소 자동탐지 |
| `MAV_ALLOW` | 허용 송신자 추가 (쉼표 구분). 고정 대상·로컬은 자동 포함 |
| `MAV_ALLOW_ANY=1` | 송신자 검사를 끈다. **쓰지 마라** |

확인:

```bash
ss -ulnp | grep 14550     # 0.0.0.0 이 아니라 100.x 로 떠야 한다
```

## 🔴 QGC 의 autoConnect — 역할마다 값이 다르다

QGC 는 기본으로 USB 에 붙은 Pixhawk 를 **직접 시리얼로 낚아챈다**. FC 가 꽂힌 PC 에서
QGC 를 켜면 브리지가 `/dev/ttyACM0` 을 빼앗기고, **다른 PC 에서는 기체가 그냥 사라진
것처럼 보인다.** FC USB 는 하나뿐이라 둘이 나눠 쓸 수 없다.

반대로 UDP 쪽은 **등록된 링크와 익명 링크가 겹치는** 것이 문제다. 그래서 두 값은
**PC 의 역할에 따라 다르게** 둔다 — 예전에는 이 문서와
[QGC 접속 절차](../gcs/qgroundcontrol/README.md#-autoconnectudp-를-꺼야-한다)가
서로 반대로 적고 있었다 (2026-09-04 정리).

| PC 역할 | `autoConnectPixhawk` | `autoConnectUDP` | 왜 |
|---|---|---|---|
| **FC 가 꽂힌 PC** (브리지 구동) | **`false`** 🔴 필수 | `false` | QGC 가 시리얼을 뺏으면 링크 전체가 죽는다 |
| **수신만 하는 PC** (QGC 만) | `false` | `false` | 등록된 `1. Pi 브리지` 링크(`auto=true`)가 이미 14550 을 리슨한다 |

`~/.config/QGroundControl/QGroundControl.ini`:

```ini
[AutoConnect]
autoConnectPixhawk=false   # QGC 가 시리얼을 직접 잡지 않는다 — 브리지가 잡는다
autoConnectUDP=false       # 등록된 링크만 쓴다 — 익명 UDP 링크를 만들지 않는다
```

**`autoConnectUDP=true` 를 쓰지 마라.** 링크가 등록돼 있는데(`Link0\auto=true`) 이 값이
켜져 있으면 QGC 가 **익명 UDP 링크를 하나 더** 만든다. 같은 기체가 두 링크로 보여
`Comm Lost` → `Switching communication to secondary link` 팝업이 뜨고, 어느 경로로
붙었는지 알 수 없게 된다. 확인:

```bash
ss -ulpn | grep QGroundControl    # 14550 소켓이 1개여야 한다. 2개면 익명 링크가 산 것
```

⚠️ QGC 는 **종료할 때 설정을 덮어쓴다.** 켜져 있는 동안 `.ini` 를 고치면 날아간다.
**반드시 QGC 를 끄고 고치고**, 켜서 다시 끈 뒤 값이 유지되는지 확인한다.

브리지도 `exclusive=True` 로 시리얼을 열어 뺏기지 않게 해 뒀다 (2026-09-02). 그래도
**브리지가 재시작되는 짧은 틈에 QGC 가 선점할 수 있으므로**, 설정을 끄는 것이 근본이다.

> 🔴 **2026-09-04 — `rim3` 이 `autoConnectPixhawk=true` 인 채로 브리지를 돌리고 있었다.**
> QGC 를 안 켜 둬서 우연히 안 터진 것이다. `false` 로 고쳤다
> (`.ini.bak-20260904-161020` 백업).

## 자동 시작 — systemd user 서비스

`nohup ... &` 로 띄우면 SSH 세션이 닫힐 때 같이 죽는다. 서비스로 올린다.
유닛 파일은 [`shade-bridge.service`](shade-bridge.service) 에 있다.

```bash
mkdir -p ~/.config/systemd/user
cp shade-bridge/shade-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now shade-bridge      # FC 가 꽂힌 PC 에서만
```

확인:

```bash
systemctl --user is-active shade-bridge
journalctl --user -u shade-bridge -n 20 --no-pager
ss -ulnp | grep 14550          # 100.x 주소로 떠야 한다
fuser -v /dev/ttyACM0          # 브리지(python3) 가 잡고 있어야 한다
```

⚠️ **FC 가 꽂힌 PC 에서만 `enable --now` 한다.** 나머지는 유닛만 두고 끈 채로 둔다.
FC 를 옮기면 옛 PC 에서 `systemctl --user disable --now shade-bridge`, 새 PC 에서
`enable --now` 한다.

> ✅ **2026-09-04 — `rim3` 을 서비스로 전환했다.** 그전까지는 9/2 에 손으로 띄운
> 프로세스(PID 65067)가 돌고 있었다. 강제 종료(`kill -9`) 후 3초 만에 재기동해
> 링크가 28.5 KB/s 로 돌아오는 것까지 확인했다.

### ⚠️ 손으로 띄우면 서비스가 조용히 죽는다

`rim3` 의 서비스는 9/2 16:11 에 이미 `enable` 돼 있었는데, 같은 날 18:22 부터
**634 회 재시작을 반복하다 죽어 있었다.** 원인은 그 시각에 누군가 같은 브리지를
손으로 띄운 것이다 — 서비스가 올라올 때마다 UDP 포트를 먼저 잡힌 채로 만난다:

```
mav_bridge: 100.117.47.105:14550 를 열 수 없다 ([Errno 98] Address already in use)
mav_bridge: 이미 브리지나 QGC 가 이 포트를 쓰고 있다.
```

`Restart=always` 라 계속 재시도하다 systemd 의 재시작 한도에 걸려 멈췄고, 그 뒤로는
**손으로 띄운 프로세스만 남아** 서비스가 죽은 줄도 모르는 상태가 됐다.

**둘을 같이 띄우지 마라.** 서비스를 쓰기로 했으면 손으로 띄운 것을 먼저 죽인다:

```bash
fuser -v /dev/ttyACM0                    # python3 가 잡고 있으면 그 PID
systemctl --user status shade-bridge     # active 가 아니면 위 충돌을 의심
```

## 어느 PC 에 꽂아도 나머지가 본다

```
FC ──USB── (raspb1 | ku | rim | rim3 중 하나) ──브리지── UDP 14550
                                                    │ Tailscale 내부로만
                        ┌──────────┬────────────────┼──────────┐
                        ▼          ▼                ▼          ▼
                     ku-dgs1      rim             rim3    gram-labtop
```

브리지가 도는 PC 한 대만 시리얼을 잡고, 나머지 세 대는 UDP 로 붙는다. 브리지가 도는
PC 의 QGC 도 자기 자신에게 UDP 로 붙는다 — `TARGETS` 에 자기 IP 가 들어 있는 이유다.

## 함정

### raspb1 브리지를 먼저 멈춰라

FC USB 를 PC 로 옮기기 전에:

```bash
ssh raspb1@100.126.161.1 'sudo systemctl stop mavlink-bridge.service'
```

안 멈추면 raspb1 이 사라진 포트를 계속 다시 열려 한다. 작업이 끝나면 되돌린다:

```bash
ssh raspb1@100.126.161.1 'sudo systemctl start mavlink-bridge.service'
```

### UDP 14550 이 비어 있어야 한다

QGC 가 이미 14550 을 잡고 있으면 브리지가 바인딩에 실패한다. QGC 를 켜기 **전에**
브리지를 띄워라. 확인:

```bash
ss -ulnp | grep 14550
```

### dialout 그룹

`/dev/ttyACM0` 접근 권한이 없으면 스크립트가 알려준다:

```bash
sudo usermod -aG dialout $USER   # 후 재로그인
```

### SSH 계정

계정명이 호스트명과 같다. `ku@rim3` 처럼 다른 이름으로 붙으면 거부된다.

| 호스트 | SSH |
|---|---|
| ku-dgs1 | `ku@100.99.120.110` |
| rim | `rim@100.107.83.47` |
| rim3 | `rim3@100.117.47.105` |
| raspb1 | `raspb1@100.126.161.1` |

## 왜 pymavlink 를 안 쓰나

[`mav_bridge.py`](../raspberry-pi-5/mav_bridge.py) 를 그대로 재사용한다. 프레임을
해석하지 않고 바이트만 옮기므로 PC 에서도 동작이 같다. 의존성은 `pyserial` 뿐이다.
