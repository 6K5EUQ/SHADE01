# Raspberry Pi 5 (raspb1) — 컴패니언 컴퓨터 / MAVLink 브리지

[Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md) 기체에 탑재되어 [Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)와 **USB 로 연결되는** 온보드 컴퓨터. 역할은 **MAVLink 시리얼 ↔ UDP 브리지** — 노트북을 기체에 붙이지 않아도, Tailscale 망을 통해 원격 PC의 QGroundControl이 붙는다.

> **GCS 접속 절차는 [QGroundControl 연결 절차](../../../gcs/qgroundcontrol/README.md) 문서**에 단계별로 정리되어 있다. 본 문서는 브리지 구현·배선·systemd 유닛 상세를 다룬다.

> ### 🔵 현재 링크 구성 — **FC USB ↔ raspb1** (2026-08-31 실측)
>
> **드론 링크 체계는 `raspb1` 하나다.** FC 와 Pi 는 **USB 로 직결**돼 있고
> (`/dev/ttyACM0`), TELEM2 UART 경로는 **쓰지 않는다** — 그 케이블의 FC측 커넥터가
> 단락이라 버렸다. 상세는
> [FC ↔ raspb1 USB 직결](#-fc--raspb1-usb-직결-2026-08-31-현행) 절.
>
> 🔴 **raspb2 는 고장으로 기체에서 제거됐다 (2026-08-30 확정, 2026-08-31 철거).**
> 복구·재사용·되돌아갈 계획 **없다.** 이전 기기의 실측 기록은 "PM08 → FC → Pi → QGC
> 전 구간이 한 번은 실증됐다" 는 근거 자료로만
> [이전 구성 — raspb2](#이전-구성--raspb2-2026-08-11-폐기) 절에 남겨 둔다.

- 모델: **Raspberry Pi 5 Model B Rev 1.0**
- OS: **Ubuntu 24.04.4 LTS** (aarch64, kernel 6.8.0-1056-raspi)
- 호스트명: `raspb1` / Tailscale 노드명 `raspb1-dgs3` (`100.126.161.1`)
- FC 연결: **USB-C ↔ `/dev/ttyACM0`** (2026-08-31 전환. TELEM2 포트 사망)
- **BEWE DGS-3 지상 SDR 기지를 겸한다** — CPU/전력/USB 를 공유한다.
  BEWE 는 박스 전체의 약 4% 만 쓰고(RSS 66 MB), 유휴 3.5 코어·RAM 7.3 GB 가 남는다.
  자원은 다르다: BEWE 는 USB RTL-SDR, 브리지는 GPIO UART.
- ⚠️ **BEWE 는 부팅 자동시작이 꺼져 있다** (2026-08-30, `systemctl disable`).
  운용자가 손으로 켠다: `sudo systemctl start bewe-station.service`
- 🔴 **전원 감시 수단이 없다** — `/sys/class/power_supply/` 가 비어 있다.
  raspb2 에 있던 X1200 UPS 배터리 로거 같은 장치가 없어 저전압 경고·안전 종료를 못 한다.
  (`vcgencmd get_throttled` 도 `raspb1` 이 `video` 그룹이 아니라 권한 오류.)

## 🔵 FC ↔ raspb1 USB 직결 (2026-08-31, 현행)

**현재 운용 경로다.** TELEM2 포트 사망([근거](#-telem2-포트-사망--usb-링크로-전환-2026-08-31))으로
UART 경로를 포기하고, FC 의 USB-C 를 Pi 5 의 USB-A 포트에 직접 꽂았다.

| 항목 | 값 (2026-08-31 실측) |
|---|---|
| 물리 연결 | Pixhawk 6C Mini **USB-C** ↔ raspb1 **USB-A** |
| Pi 측 장치 | `/dev/ttyACM0` (`crw-rw---- root dialout 166,0`) |
| `lsusb` | `Bus 002 Device 003: ID 3185:0038 Auterion PX4 FMU v6C.x` |
| 보레이트 | `921600` (USB CDC-ACM 이라 실제로는 무의미 — 값 무관하게 동작) |
| 유닛 설정 | `Environment=MAV_SERIAL=/dev/ttyACM0` |
| 유닛 상태 | `enabled` + `active` |
| 실측 수신량 | **약 24.3 kB/s** (브리지 PID `rchar` 5초 델타 121,608 B) |
| 포트 점유 | 브리지 python3 단독 (`fd 4 -> /dev/ttyACM0`) |

```
mav_bridge: serial=/dev/ttyACM0 baud=921600 udp=:14550
mav_bridge: fixed targets: 100.99.120.110:14550, 100.107.83.47:14550, 100.117.47.105:14550, 100.66.204.25:14550
mav_bridge: serial opened: /dev/ttyACM0 @ 921600
```

- ✅ **FC → Pi 구간 해결됨.** 오래 막혀 있던 마지막 구간이 뚫렸다. UART 시절 0바이트였던
  것과 달리 24 kB/s 가 실제로 흐른다.
- ⚠️ **FC 의 USB 포트를 Pi 가 점유한다** — 노트북 USB 직결(경로 B)과 **동시 사용 불가**.
  노트북으로 붙이려면 Pi 쪽 USB 를 뽑거나 브리지를 내려야 한다.
- ⚠️ **USB 커넥터는 JST-GH 보다 진동에 약하다.** 비행 전 케이블을 기체에 고정할 것.
  비행 중 빠지면 링크가 통째로 죽는다.
- ⚠️ **FC 를 USB 로만 급전하지 말 것** — 메인 배터리 없이 USB 만으로 켜면 서보·ESC 계통이
  죽은 채로 부팅된다. 진단용으로만.
- `MAV_1_CONFIG`(TELEM2) 는 이제 쓰이지 않는다. **2026-09-02 에 `0` 으로 내렸다.** 그전에는 죽은 포트에 계속 쏘느라 FC CPU 7.4% 를
  태우므로 **`MAV_1_CONFIG=0` 으로 꺼두는 것을 권장**한다 (미적용 시 낭비만 발생, 기능 영향 없음).

## ⛔ 폐기된 경로 — TELEM2 GPIO UART

2026-08-31 이전에는 FC TELEM2(JST-GH 6핀)와 Pi 40핀 GPIO 를 3선으로 묶어
`/dev/ttyAMA0` @921600 으로 썼다. **TELEM2 포트가 죽어 USB 로 옮겼다**
([근거](#-telem2-포트-사망--usb-링크로-전환-2026-08-31)).

되살릴 일이 생기면 결선은 이렇다 — FC 2번(TX) → Pi 물리 10번(RX), FC 3번(RX) →
Pi 물리 8번(TX), 6번 GND ↔ 물리 6번. **1번 5V 는 연결하지 않는다**(FC 출력 한계 1.5A,
Pi 5 는 피크 5A 급). Pi 쪽은 `/boot/firmware/config.txt` 에 `dtoverlay=uart0-pi5` +
`enable_uart=1` 이 있어야 하고 **재부팅해야** 포트가 생긴다. `serial-getty@ttyAMA0` 는
꺼져 있어야 하며, 실행 계정은 `dialout` 그룹이어야 한다.

## MAVLink 브리지 (`mav_bridge.py`)

패키지가 아니라 **자체 제작 파이썬 스크립트**다. mavlink-router·MAVProxy·pymavlink 모두 미설치이며, 순수 `pyserial` + `socket`으로 동작한다.

> **정본은 이 repo 다** — [mav_bridge.py](mav_bridge.py). 예전에는 스크립트가 기기 안에만
> 있었고, 그 기기(raspb2)가 오프라인이 되자 회수할 수 없어 재작성해야 했다. 같은 일이
> 반복되지 않도록 유닛 파일([mavlink-bridge.service](mavlink-bridge.service))까지 여기 둔다.
> 기기 배포는 `scp mav_bridge.py raspb1@100.126.161.1:/home/raspb1/`.

| 항목 | 값 |
|---|---|
| 스크립트 | `/home/raspb1/mav_bridge.py` (정본: [mav_bridge.py](mav_bridge.py)) |
| systemd 유닛 | `/etc/systemd/system/mavlink-bridge.service` (정본: [mavlink-bridge.service](mavlink-bridge.service)) |
| 시리얼 | **`/dev/ttyACM0`** @ 921600 — FC USB 직결 (2026-08-31 전환). 유닛의 `Environment=MAV_SERIAL` 로 지정. 구 경로 `/dev/ttyAMA0`(TELEM2 UART)는 폐기 |
| UDP 리슨 | `0.0.0.0:14550` (환경변수 `MAV_UDP_PORT`) |
| 고정 송신 대상 | `100.99.120.110:14550` (**`ku-dgs1`**) + `100.107.83.47:14550` (**`rim`**) + `100.117.47.105:14550` (**`rim3`**) + `100.66.204.25:14550` (**`gram-labtop`**, 2026-08-31 추가) — 유닛의 ExecStart 인자 |
| 자동 시작 | `enabled` (부팅 시 기동) |
| 재시작 정책 | `Restart=always`, `RestartSec=3` |

현재 ExecStart 행:

```ini
ExecStart=/usr/bin/python3 /home/raspb1/mav_bridge.py 100.99.120.110:14550 100.107.83.47:14550 100.117.47.105:14550 100.66.204.25:14550
```

동작 방식:

- 시리얼에서 읽은 MAVLink 바이트를 **① ExecStart 인자로 준 고정 대상**과 **② 최근 30초 내에 먼저 패킷을 보내온 GCS**(peer) 양쪽으로 전달한다.
- 고정 대상이 있으므로 GCS가 먼저 말을 걸지 않아도 텔레메트리가 흘러간다 → QGC의 기본 "UDP 14550 대기" 자동연결이 그대로 성립.
- 시리얼 포트가 사라지면 재연결을 시도하며 부팅 순서에 관계없이 살아남도록 작성되어 있다.
- GCS 가 처음 말을 걸면 `GCS connected: ('IP', 포트)` 를 로그에 남긴다. 30초 무응답이면
  `GCS timed out:` 과 함께 목록에서 빠진다 (고정 대상은 영향 없음).
- 오프라인 대상을 등록해 둬도 무해하다 — UDP 단방향 송신이라 응답을 기다리지 않는다.

```bash
# 상태 확인 / 기동
systemctl status mavlink-bridge.service
sudo systemctl start mavlink-bridge.service
journalctl -u mavlink-bridge.service -f
```

### GCS 여러 대 동시 수신

브리지는 시리얼에서 읽은 데이터를 **모든 대상에 동시 전송**한다. 대상 추가는 ExecStart 인자에
`IP:포트`를 덧붙이면 된다.

> ⚠️ **"방해하지 않는다"는 내려받기(텔레메트리)에 한정된다.** 올려보내기는 다르다 —
> 브리지는 **UDP 로 들어온 패킷을 출처와 무관하게 그대로 FC 시리얼에 쓴다**(필터 없음,
> `mav_bridge.py` 의 `UDP → 시리얼` 절). 따라서 여러 GCS 가 동시에 명령을 보내면 FC 는
> 전부 유효한 명령으로 받아 **마지막 것이 이긴다.**
>
> 실제 위험: 파라미터 동시 쓰기(한쪽 화면이 옛 값 표시 → 덮어쓰기), 캘리브레이션 중 다른 쪽의
> 파라미터 조회로 시퀀스 깨짐, 미션 업로드 중 개입, 한쪽 Arm ↔ 다른 쪽 Disarm.
> QGC 는 기본 GCS system ID 가 모두 **255** 라 FC 로그에서 구분도 안 된다.
>
> **운용 규칙**: 쓰기(설정·캘리브·미션·Arm)는 **한 대에서만**. 나머지는 관찰 전용으로 쓴다
> (QGC 에 읽기전용 모드는 없으므로 사람이 지켜야 한다). 굳이 여러 대에서 조작해야 하면
> QGC 별로 `MAV_SYS_ID`(Application Settings → MAVLink → Ground Station ID)를 다르게 두어
> 최소한 누가 무엇을 했는지 로그로 구분되게 한다.

```bash
# raspb1에서 실행 — 대상 추가 후 반영
sudo sed -i 's|mav_bridge.py .*|& 새IP:14550|' /etc/systemd/system/mavlink-bridge.service
sudo systemctl daemon-reload && sudo systemctl restart mavlink-bridge.service
```

- 재시작 시 기존 GCS 링크가 1~2초 끊기지만 자동 재연결된다.
- **고정 대상은 GCS가 먼저 말을 걸지 않아도 텔레메트리를 받는다.** 따라서 QGC는 별도 링크 설정 없이 기본 "UDP 14550 대기" 자동연결만으로 붙는다.
- GCS가 패킷을 보내오면 `peers`로도 등록되어 **양방향**(명령 전송·파라미터 읽기/쓰기)이 된다.
- ✅ **`rim` PC 추가 및 실측 검증 완료 (2026-08-11)** — 아래 참조.

#### ✅ `rim` PC 수신 검증 (2026-08-11)

`100.107.83.47`(Tailscale 노드 `rim`)을 두 번째 고정 대상으로 추가한 뒤 실측한 결과:

| 확인 항목 | 결과 |
|---|---|
| UDP 14550 수신 | ✅ 150패킷 / 17.4KB / 출처 `100.123.59.2` |
| 수신 메시지 | ATTITUDE, HIGHRES_IMU, GPS_RAW_INT, ALTITUDE, VFR_HUD, SYS_STATUS, EXTENDED_SYS_STATE 등 |
| 배터리 텔레메트리 | ✅ **22.88V (셀당 3.81V) / 잔량 48% / 0.17A** — PM08 센싱값 도달 확인 |
| QGC 자동 연결 | ✅ 링크 수동 설정 없이 UDP 14550 바인딩 후 자동 인식 |
| 양방향 통신 | ✅ 브리지 로그에 `GCS connected: ('100.107.83.47', 14550)` 등록 |
| `ku-dgs1` 동시 수신 | ✅ 유지 (두 GCS 병행 동작) |

> 백업: 변경 전 유닛 파일은 `/etc/systemd/system/mavlink-bridge.service.bak-20260811`에 보관.

`rim` PC에서 QGC 실행:

```bash
~/Downloads/QGroundControl-x86_64.AppImage
```

QGC가 UDP 14550을 바인딩하면 **링크 수동 추가 없이** 기체가 자동으로 뜬다. 별도 설정 불필요.

- ⚠️ 터미널에서 백그라운드로 띄울 때는 `setsid`로 세션에서 분리할 것 — 그냥 `&`로 띄우면 셸이 종료될 때 QGC도 함께 죽는다.
- ⚠️ **QGC가 켜져 있어야 14550을 점유**한다. QGC를 닫으면 브리지의 `peers` 목록에서 30초 뒤 빠지지만, **고정 대상 등록분은 유지**되므로 QGC를 다시 켜면 즉시 재수신된다.

## 데이터 흐름

```
[Pixhawk 6C Mini] ────── USB (CDC-ACM) ──► [Raspberry Pi 5 "raspb1"]
                          ~24.3 kB/s 실측       /dev/ttyACM0
                                                  │
                                          mav_bridge.py
                                        (UDP :14550 브리지)
                                                  │
                                        WiFi 또는 LTE → 인터넷 → Tailscale
                                                  │
                          ┌───────────────────────┼───────────────────────┐
                          ▼                       ▼                       ▼
              [ku-dgs1 100.99.120.110]  [rim 100.107.83.47]   [rim3 100.117.47.105]
                  QGroundControl            QGroundControl        QGroundControl
                                    + [gram-labtop 100.66.204.25]
```

> **드론 링크 체계는 raspb1 단독이다.** raspb2 는 고장으로 제거됐고 대체 경로는 없다.
> FC ↔ Pi 는 USB, Pi ↔ GCS 는 Tailscale UDP 14550.

- **QGC는 기체에 붙어 있지 않고 원격 노드에서 실행**된다. 로컬 WiFi 직결이 아니라 **인터넷 경유 Tailscale VPN** 링크다.
- Pi의 WiFi는 **클라이언트 모드**다. AP 모드 아님 — 기체가 자체 핫스팟을 띄우는 구조가 아니다.
  raspb1 의 NetworkManager 프로필 우선순위 (2026-08-30):
  `iptimE`(20, 휴대폰 핫스팟) → `eduroam`(10) → `5G_LGWiFi_2459`(1) → `SK_WiFiGIGA6311_5G`(0).
  AP 가 사라지면 다음 순위로 자동 폴백한다 (실증 확인).
- ✅ **배터리 잔량 QGC 표시 가능** — [PM08-CAN](../../power/holybro-pm08-can/README.md)이 CAN1으로 FC에 보낸 전압/전류 센싱값이 MAVLink를 타고 QGC까지 도달함. PM08 → FC → Pi → QGC 전 구간이 검증된 셈이다.

## UART 포트 현황

| 포트 | 쓰임 | 파라미터 |
|---|---|---|
| TELEM1 (UART7) | [RadioMaster RP4TD-M](../../receivers/radiomaster-rp4td-m/README.md) — MAVLink over ELRS | `MAV_0_CONFIG=101` @460800 |
| TELEM2 (UART5) | ⛔ **폐기** — 케이블 단락으로 사망 | `MAV_1_CONFIG=0` (2026-09-02 에 102 → 0) |
| GPS1 | [M10N](../../gps/holybro-m10n/README.md) | `GPS_1_CONFIG=201` |
| GPS2 (UART8) | 비어 있음 | — |

- Pi 는 UART 를 쓰지 않는다. **USB(`/dev/ttyACM0`)로 붙는다.**
- ✅ **`MAV_1_CONFIG` 는 `0` 이다** (2026-09-02 적용). 그전까지는 `102`(TELEM2) 였고 죽은 포트에 계속
  송신하느라 FC CPU 7.4% 를 태운다. `0` 으로 꺼두는 것이 맞다. (기능 영향은 없다.)
- 이 보드의 UART 는 셋뿐이다. 지상국 무선모듈(T900 Pro 등)을 넣으려면 GPS2 를 쓰거나
  포트를 재배치해야 한다.

## 부수 도구 — `px4_param.py`

`/home/raspb1/px4_param.py` (정본: [px4_param.py](px4_param.py)) — **pymavlink 없이** MAVLink v2 프레임을 직접 만들어 시리얼로 PX4 파라미터를 읽고 쓰는 자체 제작 스크립트. `PARAM_SET`(msgid 23) / `PARAM_REQUEST_READ`(msgid 20)를 구현하며, 포트·보레이트는 브리지와 같은 환경변수(`MAV_SERIAL` / `MAV_BAUD`, 기본 `/dev/ttyACM0` @ 921600)를 쓴다.

```bash
./px4_param.py get SENS_DPRES_OFF
./px4_param.py set SENS_DPRES_OFF 0.0
./px4_param.py set COM_ARM_WO_GPS 0 --type int32
```

정수 파라미터는 `--type int32` 를 붙인다. PX4 는 정수도 `PARAM_VALUE` 의 float 칸에 비트
그대로 실어 보내므로, 스크립트가 타입을 보고 되돌려 해석한다.

⚠️ **브리지와 동시 실행 불가** — 둘 다 같은 시리얼 포트를 열기 때문에, 이 스크립트를 쓰려면 먼저 `sudo systemctl stop mavlink-bridge.service`로 브리지를 내려야 한다.

## 🔴 TELEM2 포트 사망 → USB 링크로 전환 (2026-08-31)

**결론: FC(Pixhawk 6C Mini)의 TELEM2 포트가 죽었다. Pi 브리지는 USB 직결로 옮겼고
정상 동작한다 (21.8 KB/s 실측).** Pi·케이블·네트워크는 모두 무죄이며,
raspb2→raspb1 교체와도 무관하다 — 시점만 겹쳤다.

### 최종 배선

```
[Pixhawk 6C Mini] ──USB-C ⟷ USB-A── [Raspberry Pi 5 "raspb1"] ──UDP 14550──→ GCS 4대
                                          /dev/ttyACM0
```

TELEM2 (GPIO UART) 는 **더 이상 쓰지 않는다.**

### 판정 근거

Telem2 ↔ Pi GPIO 를 교차 결선하고 **11개 보레이트**(9600~1.5M)를 전부 raw read 해도
`/dev/ttyAMA0` 수신이 0바이트였다. 아래 셋이 포트 사망을 확정한다.

- **빈 포트 자기 수신** — 커넥터를 완전히 뽑은 상태에서 `mavlink status` 인스턴스 #1 이
  `rx ≈ tx ≈ 22.4 kB/s`, `sysid:1 compid:1`(자기 자신) 을 계속 파싱했다. 재부팅해도 즉시 재발.
- **5V 출력까지 사망** — TELEM1 에서 멀쩡히 돌던 **수신기와 그 케이블 그대로** TELEM2 로
  옮기자 **LED 조차 안 켜졌다.** 신호선뿐 아니라 포트 전원이 죽었다.
- **대조군** — 아무것도 안 꽂힌 `ttyS4` 는 rx 339 B/s 노이즈뿐 **유효 프레임 0** →
  "PX4 가 자기 송신을 세는 것" 이라는 해석은 배제된다. TELEM1(`ttyS5`) 은 정상.

Pi(물리 8↔10 루프백 64/64) · 케이블 · 네트워크 · FC 펌웨어 설정은 모두 무죄로 확인됐고,
raspb2→raspb1 교체와도 무관하다 — 시점만 겹쳤다.

### ⚠️ 두 번 오진했다 — 같은 함정을 피하려면

1. **어느 끝을 분리했는지 매번 명시할 것.** 운용자가 뽑은 것은 Pi 쪽이었는데 FC 쪽으로
   가정해 판정했다.
2. **빈 포트에서의 측정만이 유효하다.** 수신기를 꽂았을 때 자기 수신이 사라진 것을 보고
   포트가 멀쩡하다 결론냈으나, 그 수신기는 **전원조차 안 들어온 상태**였다. 되돌이가
   사라진 게 아니라 라인 임피던스가 바뀌어 가려진 것이었다.

### 남은 확인 (물리)

포트 사망까지는 확정이나 기전은 갈린다. **FC 전원을 끄고** 테스터로:

- **TELEM2 1번(5V) ↔ 6번(GND) 전압** — FC 전원 인가 상태에서 0V 면 전원 출력 사망
  (비교: TELEM1 같은 핀에서는 5V 가 나와야 한다)
- **TELEM2 2번(TX) ↔ 3번(RX) 도통** — 삐 울리면 기판/커넥터 납땜 단락

수리 여부와 무관하게 **보드에 여유 UART 가 없다** — `param show SER_*` 결과
`SER_GPS1_BAUD` / `SER_TEL1_BAUD` / `SER_TEL2_BAUD` 셋뿐이고 앞의 둘은 GPS·ELRS 가 쓴다.
그래서 USB 가 유일한 대안이었다.

### 조치 — USB 전환 (완료)

`mav_bridge.py` 는 `MAV_SERIAL` 환경변수를 이미 받으므로 **코드 수정 없이** 유닛 한 줄로 끝난다.

```ini
[Service]
Environment=MAV_SERIAL=/dev/ttyACM0
```

변경 전 유닛 백업: `/etc/systemd/system/mavlink-bridge.service.bak-20260831-usb`

**실측 검증 (2026-08-31)**

| 항목 | 결과 |
|---|---|
| Pi 에서 FC 인식 | `/dev/serial/by-id/usb-Auterion_PX4_FMU_v6C.x_0-if00` → `ttyACM0` |
| Pi 시리얼 수신 | **21.0 KB/s** (5초에 104,981 바이트) |
| `ku-dgs1` UDP 14550 수신 | **21.8 KB/s**, 8초에 2572패킷 / 174.6KB, 출처 `100.126.161.1` |
| 수신 메시지 | ATTITUDE(30) · HIGHRES_IMU(105) · 31 · 32 · **RC_CHANNELS(65)** · GPS_RAW_INT(24) · VFR_HUD(74) · 83 · 111 · 141 · 245 |
| 서비스 | `enabled` + `Restart=always` → 재부팅 자동 기동 |

⚠️ **주의사항**

- FC USB 포트를 Pi 가 점유하므로 **노트북 USB 직결(경로 B)과 동시 사용 불가.**
  펌웨어 플래싱·ESC 캘리브레이션을 하려면 Pi 쪽 USB 를 뽑아야 한다.
- USB 커넥터는 JST-GH 보다 진동에 약하다. **비행 전 케이블 타이로 고정할 것.**
- ✅ `MAV_1_CONFIG` 는 **`0` 이다** (2026-09-02 적용). 그전에는 `102` 로 죽은 TELEM2 에 22kB/s 를
  쏘며 자기 에코를 파싱하느라 FC CPU 를 **7.4% 태운다** (`mavlink_if1` 4.27% + `mavlink_rcv_if1` 3.18%,
  비교: 실제 ELRS 링크 수신 `mavlink_rcv_if0` 는 0.625%). **`0` 으로 꺼두는 것이 맞다.**
- `SER_TEL2_BAUD` 는 921600 으로 원복해 두었다 (수신기 테스트로 460800 에 두었던 것).

### 부수 발견 — 과거 파라미터 임포트 실패

SD 에 `param_import_fail.txt` 가 있다. **PX4 1.16.0 (2025-08-06 빌드)** 시절 기록으로,
내부 파라미터 저장소가 비어 있었다.

```
ERROR [parameters] BSON document size (0) doesn't match bytes decoded (5)
ERROR [param] importing from '/fs/mtd_params' failed (-1)
INFO  [parameters] summary: 0/2065 (used/total)
```

지금 문제와 직접 관련은 없으나 **파라미터가 통째로 날아간 적이 있다**는 기록이라,
현재 값이 문서와 어긋나는 항목(`RC_CRSF_PRT_CFG` 문서 101 / 실측 0 등)의 배경일 수 있다.
하드폴트 이력은 없다 (`hardfault_log check` 무응답, SD 에 `fault_*.txt` 없음).

### 참고 — FC 실측 제원

```
HW arch: PX4_FMU_V6C          HW type: V6C002002 (rev 0x002)
MCU: STM32H7[4|5]xxx, rev. V
PX4: Release 1.17.0  git-hash d6f12ad1c4f70ad3230afd7d86e971421e02fef4
Build datetime: Aug 11 2026 15:28:15   (커스텀 빌드)
NuttX: 11.0.0
```

### 부수 도구 — `pxsh.py`

QGC 없이 MAVLink SERIAL_CONTROL(msgid 126) 로 PX4 NSH 셸을 여는 스크립트를 이번에 만들었다.
`mavlink status` / `ps` / `dmesg` / `top once` / `param show` / `param set` / `reboot` 를
원격 실행할 수 있어 이번 진단의 핵심이 됐다. 정본은 [pxsh.py](pxsh.py).

⚠️ MAVLink v2 헤더는 **10바이트**다 (magic, len, incompat, compat, seq, sysid, compid,
**msgid 3바이트**). msgid 를 2바이트로 넣으면 FC 가 프레임을 통째로 버리며 **아무 에러 없이
무응답**이 된다. 이번에 이 버그로 "FC 가 파라미터 요청에 응답하지 않는다" 고 오진할 뻔했다.

## 🔶 확인 필요

- ✅ **`MAV_1_CONFIG` = `0`** (2026-09-02 적용). 그전에는 `102` 로 죽은 TELEM2 에 송신하며
  FC CPU 7.4% 낭비. `0` 으로 꺼두는 것이 맞다. 기능 영향은 없다.
- **USB 링크의 MAVLink 스트림 모드 미확정** — USB 는 `MAV_x_CONFIG` 없이도 기본 인스턴스가
  뜬다. `Normal` 인지 `Onboard` 인지는 QGC 파라미터 화면에서 확정할 것.
  (실측 21~24 kB/s 로 보아 `Onboard` 급 고레이트로 보인다.)
- **Pi 전원 계통 미기록** — 어느 BEC/배터리에서 5V 를 받는지, 전류 여유가 충분한지.
  Pi 5 는 순간 소비가 커서 [UBEC(5.3V/10A)](../../power/mfe-ubec-3s14s-10a/README.md) 를
  서보와 공유하면 서보 동작 시 전압 강하 위험.
- 🔴 **전원 감시 부재** — raspb1 에 UPS/배터리 모니터가 없다. 기체 탑재 시 저전압을
  소프트웨어로 알 수 없다.
- ✅ **WiFi 범위 의존 해소 (2026-08-31)** — **LTE 모뎀을 장착**해 WiFi + LTE 이중화가 됐다.
  경로는 여전히 인터넷 + Tailscale 경유다.
  ⚠️ **장거리 비행 중 링크 신뢰성은 미검증** — 2026-08-31 비행(453초)은 홈에서 최대 54m,
  WiFi 범위 안이었다. LTE 폴백이 실제로 인계받는지는 아직 확인되지 않았다.

## 보유 수량 (SHADE 기체)

- 1개, 별도 구매 (PNP 옵션 미포함)

> 참고: 이 Pi에는 드론과 무관한 별도 프로젝트(KrakenSDR 기반 BEWE DGS-X 서비스)가 함께 상주한다. 본 문서의 범위 밖이며, 다만 **CPU/전력/USB 자원을 공유**한다는 점만 유의.

---

## 이전 구성 — raspb2 (2026-08-11, 폐기)

2026-08-30 이전 컴패니언은 `raspb2`(`raspb2-dgsx`, `100.123.59.3`) 였다. **하드웨어 고장으로
기체에서 제거했고 복귀 계획은 없다.** 그 기기에서 PM08 → FC → Pi → QGC 전 구간이 한 번
실증됐다는 것이 남은 의미의 전부다 (배터리 22.88V / 잔량 48% 도달 확인).

교훈: 스크립트가 **기기 안에만 있어서** 기기가 죽자 회수할 수 없었다. 그래서 지금은
`mav_bridge.py` · `px4_param.py` · `pxsh.py` 와 유닛 파일 모두 이 repo 가 정본이다.
