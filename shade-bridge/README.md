# PC 직결 브리지

FC 를 **PC 에 USB 로 직결**했을 때, 그 PC 를 중계기로 삼아 다른 PC 의 QGC 도
Tailscale 로 붙게 한다. raspb1 이 하던 일을 PC 가 대신 하는 것이다.

## 언제 쓰나

평시에는 **쓰지 않는다.** raspb1 이 FC USB 를 잡고 있고, 이미 4 대 전부에 중계한다
([링크 구성](../../../README.md#링크-구성--raspb1-단독)).

**FC USB 는 하나뿐**이라, PC 직결은 raspb1 USB 를 뽑았다는 뜻이다. 그때만 쓴다:

- 펌웨어 플래시
- 부트로더 작업
- raspb1 이 고장났을 때

## 쓰는 법

```bash
cd SHADE01
./components/companion/pc-direct/pc_bridge.sh
```

시리얼 포트를 자동으로 찾는다 (`ttyACM0` → `ttyACM1` → `ttyUSB0`).
다른 포트면 지정한다:

```bash
MAV_SERIAL=/dev/ttyACM1 ./components/companion/pc-direct/pc_bridge.sh
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
