# Raspberry Pi 5 (raspb2) — 컴패니언 컴퓨터 / MAVLink 브리지

[Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md) 기체에 탑재되어 [Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)와 시리얼(UART)로 연결되는 온보드 컴퓨터. 역할은 **MAVLink 시리얼 ↔ UDP 브리지** — FC를 PC에 USB로 직접 연결하지 않아도, Tailscale 망을 통해 원격 PC의 QGroundControl이 붙는다.

> **GCS 접속 절차는 [QGroundControl 연결 절차](../../../gcs/qgroundcontrol/README.md) 문서**에 단계별로 정리되어 있다. 본 문서는 브리지 구현·배선·systemd 유닛 상세를 다룬다.

> 아래 내용은 2026-08-11 실기 SSH 접속으로 확인한 값이다.

- 모델: **Raspberry Pi 5 Model B Rev 1.0**
- OS: **Ubuntu 24.04.4 LTS** (aarch64, kernel 6.8.0-1060-raspi)
- 호스트명: `raspb2` / Tailscale 노드명 `raspb2-dgsx`
- FC 연결: **Telem2 (UART5) ↔ `/dev/ttyAMA0` @ 921600**

## 배선 (FC Telem2 ↔ RPi GPIO)

FC의 Telem2(JST-GH 1.25mm 6핀)와 Pi 5의 40핀 GPIO 헤더를 3선(TX/RX/GND)으로 연결한다.

| Pixhawk 6C Mini Telem2 핀 | 신호 | → | RPi 5 GPIO 물리핀 | RPi 신호 |
|---|---|---|---|---|
| 2 | UART5_TX (out) | → | **10** | GPIO15 / RXD (in) |
| 3 | UART5_RX (in) | → | **8** | GPIO14 / TXD (out) |
| 6 | GND | → | **6** | GND |
| 1 | VCC 5V | ✕ | — | **연결하지 않음** |

- ⚠️ **TX/RX 교차 필수** — FC TX(2번) → Pi RX(물리 10번), FC RX(3번) → Pi TX(물리 8번).
- ⚠️ **Telem2의 5V로 Pi 5에 급전하지 말 것** — FC의 Telem1+GPS1 합산 출력 제한은 1.5A인데 Pi 5는 피크 5A급을 요구한다. Pi 전원은 별도 계통에서 공급한다.
- GND는 반드시 공통으로 묶어야 UART 기준전위가 잡힌다. 신호 레벨은 양쪽 다 3.3V라 레벨 시프터 불필요.

> 핀 번호 기준: FC측은 [6C Mini 커넥터 Pin1 도해](../../fc/holybro-pixhawk-6c-mini/images/04-pin-number.png), RPi측은 40핀 헤더 **물리 핀 번호**(BCM 번호 아님).

### Pi측 UART 활성화 설정

`/boot/firmware/config.txt`에 아래 2줄이 들어가 있어야 `/dev/ttyAMA0`이 GPIO 14/15에 연결된다. **설정 확인 완료**.

```ini
dtoverlay=uart0-pi5
enable_uart=1
```

- Pi 5는 이전 세대와 UART 매핑이 달라 **`uart0-pi5` 전용 오버레이**가 필요하다.
- `serial-getty@ttyAMA0`는 **disabled** 상태 — 시리얼 콘솔이 포트를 잡으면 MAVLink와 충돌하므로 반드시 꺼두어야 한다. ✅ 확인됨.
- `/boot/firmware/cmdline.txt`에 `console=serial0` 항목 없음(콘솔은 `tty1`만) — 정상.
- 실행 계정 `raspb2`는 `dialout` 그룹 소속이라 포트 접근 권한 있음. ✅

## MAVLink 브리지 (`mav_bridge.py`)

패키지가 아니라 **자체 제작 파이썬 스크립트**다. mavlink-router·MAVProxy·pymavlink 모두 미설치이며, 순수 `pyserial` + `socket`으로 동작한다.

| 항목 | 값 |
|---|---|
| 스크립트 | `/home/raspb2/mav_bridge.py` |
| systemd 유닛 | `/etc/systemd/system/mavlink-bridge.service` |
| 시리얼 | `/dev/ttyAMA0` @ **921600** (환경변수 `MAV_SERIAL`/`MAV_BAUD`로 변경 가능) |
| UDP 리슨 | `0.0.0.0:14550` |
| 고정 송신 대상 | `100.99.120.110:14550` (**`ku-dgs1`**) + `100.107.83.47:14550` (**`rim`**) — 유닛의 ExecStart 인자 |
| 자동 시작 | `enabled` (부팅 시 기동) |
| 재시작 정책 | `Restart=always`, `RestartSec=3` |

현재 ExecStart 행:

```ini
ExecStart=/usr/bin/python3 /home/raspb2/mav_bridge.py 100.99.120.110:14550 100.107.83.47:14550
```

동작 방식:

- 시리얼에서 읽은 MAVLink 바이트를 **① ExecStart 인자로 준 고정 대상**과 **② 최근 30초 내에 먼저 패킷을 보내온 GCS**(peer) 양쪽으로 전달한다.
- 고정 대상이 있으므로 GCS가 먼저 말을 걸지 않아도 텔레메트리가 흘러간다 → QGC의 기본 "UDP 14550 대기" 자동연결이 그대로 성립.
- 시리얼 포트가 사라지면 재연결을 시도하며 부팅 순서에 관계없이 살아남도록 작성되어 있다.

```bash
# 상태 확인 / 기동
systemctl status mavlink-bridge.service
sudo systemctl start mavlink-bridge.service
journalctl -u mavlink-bridge.service -f
```

### GCS 여러 대 동시 수신

브리지는 시리얼에서 읽은 데이터를 **모든 대상에 동시 전송**하므로, GCS를 여러 대 붙여도 서로 방해하지 않는다. 대상 추가는 ExecStart 인자에 `IP:포트`를 덧붙이면 된다.

```bash
# raspb2에서 실행 — 대상 추가 후 반영
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
[Pixhawk 6C Mini] ──Telem2 UART 921600──► [Raspberry Pi 5 "raspb2"]
                                             /dev/ttyAMA0
                                                  │
                                          mav_bridge.py
                                        (UDP :14550 브리지)
                                                  │
                                    WiFi(eduroam) → 인터넷 → Tailscale
                                                  │
                                    ┌─────────────┴─────────────┐
                                    ▼                           ▼
                        [ku-dgs1 100.99.120.110]     [rim 100.107.83.47]
                            QGroundControl              QGroundControl
                                                     (2026-08-11 추가)
```

- **QGC는 기체에 붙어 있지 않고 원격 노드에서 실행**된다. 로컬 WiFi 직결이 아니라 **인터넷 경유 Tailscale VPN** 링크다.
- Pi의 WiFi는 **`eduroam` 클라이언트 모드** (wlan0: 10.200.114.166/17). AP 모드 아님 — 기체가 자체 핫스팟을 띄우는 구조가 아니다.
- ✅ **배터리 잔량 QGC 표시 가능** — [PM08-CAN](../../power/holybro-pm08-can/README.md)이 CAN1으로 FC에 보낸 전압/전류 센싱값이 MAVLink를 타고 QGC까지 도달함. PM08 → FC → Pi → QGC 전 구간이 검증된 셈이다.

## ✅ Telem2 포트 충돌 — 해소 (2026-08-19)

Telem2를 두고 Pi 5와 RC 수신기가 경합하던 문제는 **수신기를 Telem1(UART7)로 배치**해 해소했다. **Pi는 Telem2를 그대로 유지**한다 — 브리지가 이미 검증·가동 중이었으므로 건드리지 않는 쪽이 안전했다.

| 부품 | 포트 | 파라미터 | 상태 |
|---|---|---|---|
| Raspberry Pi 5 (본 문서) | **Telem2 (UART5)** | `MAV_1_CONFIG=102` @921600 | ✅ 가동 중, 변경 없음 |
| [RadioMaster RP4TD-M](../../receivers/radiomaster-rp4td-m/README.md) | **Telem1 (UART7)** | `RC_CRSF_PRT_CFG=101` | ✅ 결선·바인딩 완료 |

- 서로 다른 UART이므로 **두 링크가 공존**한다. 수신기 설정 과정에서 Telem2의 MAVLink 매핑을 제거할 필요가 없다 — 이전 판 문서의 해당 경고는 무효다.
- ⚠️ 남은 여유 UART는 **GPS2(UART8)뿐**이다. T900 Pro 등 지상국 무선모듈 도입 시 포트 재배치를 검토해야 한다.

## 부수 도구 — `px4_param.py`

`/home/raspb2/px4_param.py` — **pymavlink 없이** MAVLink v2 프레임을 직접 만들어 시리얼로 PX4 파라미터를 읽고 쓰는 자체 제작 스크립트. `PARAM_SET`(msgid 23) / `PARAM_REQUEST_READ`(msgid 20)를 구현하며, 포트·보레이트는 브리지와 동일(`/dev/ttyAMA0` @ 921600)로 하드코딩되어 있다.

⚠️ **브리지와 동시 실행 불가** — 둘 다 같은 시리얼 포트를 열기 때문에, 이 스크립트를 쓰려면 먼저 `sudo systemctl stop mavlink-bridge.service`로 브리지를 내려야 한다.

## 🔶 확인 필요

- **FC측 PX4 파라미터 실측값 미확인** — Telem2가 921600으로 동작 중인 것으로 보아 `SER_TEL2_BAUD`=921600, `MAV_x_CONFIG`=TELEM2로 설정돼 있을 것이나, `MAV_x_MODE`가 `Onboard`인지 `Normal`인지 등은 QGC에서 직접 읽어 확정 필요. (`px4_param.py`로 조회 가능)
  - 참고: 수신 스트림에 HIGHRES_IMU·ATTITUDE_QUATERNION이 고레이트로 포함된 것으로 보아 `Onboard` 모드일 가능성이 높다. QGC 파라미터 화면에서 확정할 것.
- **Pi 전원 공급 계통 미기록** — 어느 BEC/배터리에서 5V를 받는지, 전류 여유가 충분한지. Pi 5는 순간 소비가 커서 [UBEC(5.3V/10A)](../../fc/holybro-pixhawk-6c-mini/README.md#서보-전원-mfe-ubec-연결)를 서보와 공유하면 서보 동작 시 전압 강하 위험.
- 🔴 **실비행 텔레메트리로 부적합** — 현재 링크는 `eduroam` WiFi + 인터넷 + Tailscale 경유다. 지상 벤치 테스트/설정용으로는 충분하나, **기체가 학내 WiFi 범위를 벗어나면 즉시 끊긴다.** 실비행에는 별도 무선 모뎀(T900 Pro 등) 또는 LTE 모뎀이 필요하다.
- **비행 중 링크 신뢰성 미검증** — 위 사유로 지상 테스트만 완료.
- ~~Telem2 포트 충돌 해소 방안 미확정~~ → **해소(2026-08-19)**: 수신기를 Telem1로 배치. [Telem2 포트 충돌 — 해소](#-telem2-포트-충돌--해소-2026-08-19) 참조.

## 보유 수량 (SHADE 기체)

- 1개, 별도 구매 (PNP 옵션 미포함)

> 참고: 이 Pi에는 드론과 무관한 별도 프로젝트(KrakenSDR 기반 BEWE DGS-X 서비스)가 함께 상주한다. 본 문서의 범위 밖이며, 다만 **CPU/전력/USB 자원을 공유**한다는 점만 유의.
