# Raspberry Pi 5 (raspb1) — 컴패니언 컴퓨터 / MAVLink 브리지

[Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md) 기체에 탑재되어 [Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)와 시리얼(UART)로 연결되는 온보드 컴퓨터. 역할은 **MAVLink 시리얼 ↔ UDP 브리지** — FC를 PC에 USB로 직접 연결하지 않아도, Tailscale 망을 통해 원격 PC의 QGroundControl이 붙는다.

> **GCS 접속 절차는 [QGroundControl 연결 절차](../../../gcs/qgroundcontrol/README.md) 문서**에 단계별로 정리되어 있다. 본 문서는 브리지 구현·배선·systemd 유닛 상세를 다룬다.

> **2026-08-30 — 컴패니언 Pi 를 `raspb2` 에서 `raspb1` 로 옮겼다.**
> 🔴 **raspb2 는 고장이다 (2026-08-30 확정).** 처음엔 일시 오프라인으로 봤으나 복구되지
> 않았고, 운용자가 하드웨어 고장으로 판정했다. **되돌아갈 계획은 없다** — raspb1 이 정본이다.
> 이전 기기의 실측 기록은 근거 자료로만
> [이전 구성 (raspb2, 2026-08-11)](#이전-구성-raspb2-2026-08-11) 절에 남겨 둔다.

- 모델: **Raspberry Pi 5 Model B Rev 1.0**
- OS: **Ubuntu 24.04.4 LTS** (aarch64, kernel 6.8.0-1056-raspi)
- 호스트명: `raspb1` / Tailscale 노드명 `raspb1-dgs3` (`100.126.161.1`)
- FC 연결: **Telem2 (UART5) ↔ `/dev/ttyAMA0` @ 921600**
- **BEWE DGS-3 지상 SDR 기지를 겸한다** — CPU/전력/USB 를 공유한다.
  BEWE 는 박스 전체의 약 4% 만 쓰고(RSS 66 MB), 유휴 3.5 코어·RAM 7.3 GB 가 남는다.
  자원은 다르다: BEWE 는 USB RTL-SDR, 브리지는 GPIO UART.
- ⚠️ **BEWE 는 부팅 자동시작이 꺼져 있다** (2026-08-30, `systemctl disable`).
  운용자가 손으로 켠다: `sudo systemctl start bewe-station.service`
- 🔴 **전원 감시 수단이 없다** — `/sys/class/power_supply/` 가 비어 있다.
  raspb2 에 있던 X1200 UPS 배터리 로거 같은 장치가 없어 저전압 경고·안전 종료를 못 한다.
  (`vcgencmd get_throttled` 도 `raspb1` 이 `video` 그룹이 아니라 권한 오류.)

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

`/boot/firmware/config.txt`에 아래 2줄이 들어가 있어야 `/dev/ttyAMA0`이 GPIO 14/15에 연결된다.
**raspb1 에 2026-08-30 추가 완료** (추가 전 백업 `/root/config.txt.bak-20260830-231430`).

```ini
dtoverlay=uart0-pi5
enable_uart=1
```

- Pi 5는 이전 세대와 UART 매핑이 달라 **`uart0-pi5` 전용 오버레이**가 필요하다.
- `serial-getty@ttyAMA0`는 **disabled** 상태 — 시리얼 콘솔이 포트를 잡으면 MAVLink와 충돌하므로 반드시 꺼두어야 한다. ✅ 확인됨.
- `/boot/firmware/cmdline.txt`에 `console=serial0` 항목 없음(콘솔은 `tty1`만) — 정상.
- 실행 계정 `raspb1`은 `dialout` 그룹 소속이라 포트 접근 권한 있음. ✅ (2026-08-30 `usermod -aG dialout` 실행)
- ⚠️ **두 줄을 넣어도 재부팅 전에는 `/dev/ttyAMA0`이 생기지 않는다.** 재부팅 전 상태에서는
  `/dev/ttyAMA10`(전용 디버그 UART)만 보이며, 이건 FC 연결과 무관하다.
- Pi 5 는 Bluetooth 가 **별도 내부 UART**(`107d50c000.serial`)에 붙어 있어 GPIO 14/15 를
  건드리지 않는다. Pi 4 이하에서 필요하던 `dtoverlay=disable-bt` 는 불필요하다.

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
| 시리얼 | `/dev/ttyAMA0` @ **921600** (환경변수 `MAV_SERIAL`/`MAV_BAUD`로 변경 가능) |
| UDP 리슨 | `0.0.0.0:14550` (환경변수 `MAV_UDP_PORT`) |
| 고정 송신 대상 | `100.99.120.110:14550` (**`ku-dgs1`**) + `100.107.83.47:14550` (**`rim`**) + `100.105.212.78:14550` (**`rim3`**) + `100.66.204.25:14550` (**`gram-labtop`**, 2026-08-31 추가) — 유닛의 ExecStart 인자 |
| 자동 시작 | `enabled` (부팅 시 기동) |
| 재시작 정책 | `Restart=always`, `RestartSec=3` |

현재 ExecStart 행:

```ini
ExecStart=/usr/bin/python3 /home/raspb1/mav_bridge.py 100.99.120.110:14550 100.107.83.47:14550 100.105.212.78:14550 100.66.204.25:14550
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
[Pixhawk 6C Mini] ──Telem2 UART 921600──► [Raspberry Pi 5 "raspb1"]
                                             /dev/ttyAMA0
                                                  │
                                          mav_bridge.py
                                        (UDP :14550 브리지)
                                                  │
                                        WiFi → 인터넷 → Tailscale
                                                  │
                          ┌───────────────────────┼───────────────────────┐
                          ▼                       ▼                       ▼
              [ku-dgs1 100.99.120.110]  [rim 100.107.83.47]   [rim3 100.105.212.78]
                  QGroundControl            QGroundControl        QGroundControl
```

- **QGC는 기체에 붙어 있지 않고 원격 노드에서 실행**된다. 로컬 WiFi 직결이 아니라 **인터넷 경유 Tailscale VPN** 링크다.
- Pi의 WiFi는 **클라이언트 모드**다. AP 모드 아님 — 기체가 자체 핫스팟을 띄우는 구조가 아니다.
  raspb1 의 NetworkManager 프로필 우선순위 (2026-08-30):
  `iptimE`(20, 휴대폰 핫스팟) → `eduroam`(10) → `5G_LGWiFi_2459`(1) → `SK_WiFiGIGA6311_5G`(0).
  AP 가 사라지면 다음 순위로 자동 폴백한다 (실증 확인).
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

`/home/raspb1/px4_param.py` (정본: [px4_param.py](px4_param.py)) — **pymavlink 없이** MAVLink v2 프레임을 직접 만들어 시리얼로 PX4 파라미터를 읽고 쓰는 자체 제작 스크립트. `PARAM_SET`(msgid 23) / `PARAM_REQUEST_READ`(msgid 20)를 구현하며, 포트·보레이트는 브리지와 같은 환경변수(`MAV_SERIAL` / `MAV_BAUD`, 기본 `/dev/ttyAMA0` @ 921600)를 쓴다.

```bash
./px4_param.py get SENS_DPRES_OFF
./px4_param.py set SENS_DPRES_OFF 0.0
./px4_param.py set COM_ARM_WO_GPS 0 --type int32
```

정수 파라미터는 `--type int32` 를 붙인다. PX4 는 정수도 `PARAM_VALUE` 의 float 칸에 비트
그대로 실어 보내므로, 스크립트가 타입을 보고 되돌려 해석한다.

⚠️ **브리지와 동시 실행 불가** — 둘 다 같은 시리얼 포트를 열기 때문에, 이 스크립트를 쓰려면 먼저 `sudo systemctl stop mavlink-bridge.service`로 브리지를 내려야 한다.

## 🔶 확인 필요

- **FC측 PX4 파라미터 실측값 미확인** — Telem2가 921600으로 동작 중인 것으로 보아 `SER_TEL2_BAUD`=921600, `MAV_x_CONFIG`=TELEM2로 설정돼 있을 것이나, `MAV_x_MODE`가 `Onboard`인지 `Normal`인지 등은 QGC에서 직접 읽어 확정 필요. (`px4_param.py`로 조회 가능)
  - 참고: 수신 스트림에 HIGHRES_IMU·ATTITUDE_QUATERNION이 고레이트로 포함된 것으로 보아 `Onboard` 모드일 가능성이 높다. QGC 파라미터 화면에서 확정할 것.
- **Pi 전원 공급 계통 미기록** — 어느 BEC/배터리에서 5V를 받는지, 전류 여유가 충분한지. Pi 5는 순간 소비가 커서 [UBEC(5.3V/10A)](../../fc/holybro-pixhawk-6c-mini/README.md#서보-전원-mfe-ubec-연결)를 서보와 공유하면 서보 동작 시 전압 강하 위험.
- 🔴 **실비행 텔레메트리로 부적합** — 현재 링크는 WiFi + 인터넷 + Tailscale 경유다. 지상 벤치 테스트/설정용으로는 충분하나, **기체가 WiFi 범위를 벗어나면 즉시 끊긴다.** 실비행에는 별도 무선 모뎀(T900 Pro 등) 또는 LTE 모뎀이 필요하다.
- **비행 중 링크 신뢰성 미검증** — 위 사유로 지상 테스트만 완료.
- 🟡 **raspb1 실측 — 절반 완료 (2026-08-30 23:21 확인)**
  1. ✅ 재부팅 → `/dev/ttyAMA0` 생성 확인 (`crw-rw---- root dialout 204,64`)
  2. ✅ 유닛 `enabled` + `active`, 부팅 자동기동 확인
  3. ✅ 시리얼 오픈 성공 — `mav_bridge: serial opened: /dev/ttyAMA0 @ 921600`
  4. ⬜ **FC Telem2 결선 미완** — 패킷 수신 로그가 없다. 시리얼은 열렸으나 반대편이 조용하다
  5. ⬜ QGC 에서 기체 인식·배터리·GPS·자세 (4번 이후)

  현재 `ExecStart` 고정 타겟: `100.99.120.110:14550`(ku-dgs1), `100.107.83.47:14550`(rim),
  `100.105.212.78:14550`.
  ✅ **`gram-labtop`(`100.66.204.25`) 도 고정 타겟에 등록됐다 (2026-08-31).** 유닛의
  `ExecStart` 에 추가하고 재시작했으며, 원본은 `mavlink-bridge.service.bak-20260831-*` 로
  백업돼 있다. 이제 gram 의 QGC 는 링크만 Connect 하면 FC 데이터가 도착하는 대로 붙는다.

  참고로 QGC 의 UDP 링크는 **기체가 먼저 말을 걸어오기를 기다린다** — 스스로 먼저 쏘지 않는다.
  그래서 브리지의 동적 peer 등록(먼저 패킷을 보내온 GCS 를 30초간 기억)만으로는 QGC 가 절대
  등록되지 않는다. GCS 를 추가하려면 반드시 **유닛의 고정 타겟에 넣어야 한다.**
- 🔴 **전원 감시 부재** — raspb1 에는 UPS/배터리 모니터가 없다 (머리말 참조). 기체 탑재 시
  저전압 상황을 소프트웨어로 알 수 없다.
- ~~Telem2 포트 충돌 해소 방안 미확정~~ → **해소(2026-08-19)**: 수신기를 Telem1로 배치. [Telem2 포트 충돌 — 해소](#-telem2-포트-충돌--해소-2026-08-19) 참조.

## 보유 수량 (SHADE 기체)

- 1개, 별도 구매 (PNP 옵션 미포함)

> 참고: 이 Pi에는 드론과 무관한 별도 프로젝트(KrakenSDR 기반 BEWE DGS-X 서비스)가 함께 상주한다. 본 문서의 범위 밖이며, 다만 **CPU/전력/USB 자원을 공유**한다는 점만 유의.

---

## 이전 구성 (raspb2, 2026-08-11)

2026-08-30 이전에는 컴패니언 Pi 가 **`raspb2`** (Tailscale `raspb2-dgsx`, `100.123.59.3`) 였다.
아래는 그 기기에서 나온 **실측 기록**이다. 지금 기체에 실린 것은 raspb1 이지만, PM08 → FC →
Pi → QGC 전 구간이 한 번 실증됐다는 근거는 여기에 있다.

| 항목 | 값 |
|---|---|
| 호스트명 / 노드 | `raspb2` / `raspb2-dgsx` (`100.123.59.3`) |
| OS | Ubuntu 24.04.4 LTS (aarch64, kernel 6.8.0-1060-raspi) |
| 스크립트 | `/home/raspb2/mav_bridge.py`, `/home/raspb2/px4_param.py` |
| ExecStart | `/usr/bin/python3 /home/raspb2/mav_bridge.py 100.99.120.110:14550 100.107.83.47:14550` |
| WiFi | `eduroam` 클라이언트 (wlan0: 10.200.114.166/17) |
| 겸업 | KrakenSDR 기반 BEWE DGS-X 서비스 |

**`rim` PC 수신 검증 (2026-08-11)** — UDP 14550 수신 150패킷 / 17.4KB (출처 `100.123.59.2`),
ATTITUDE·HIGHRES_IMU·GPS_RAW_INT·ALTITUDE·VFR_HUD·SYS_STATUS·EXTENDED_SYS_STATE 수신,
배터리 **22.88V (셀당 3.81V) / 잔량 48% / 0.17A** 도달, QGC 자동 연결, 양방향 통신
(`GCS connected: ('100.107.83.47', 14550)`), `ku-dgs1` 동시 수신 유지.
변경 전 유닛 백업은 그 기기의 `/etc/systemd/system/mavlink-bridge.service.bak-20260811`.

### 왜 옮겼나

raspb2 는 드론 탑재 Pi 인 동시에 BEWE DGS-X 기지였는데, **2026-08-21 무렵부터 오프라인**
(Tailscale `last seen 9d ago`, ping 100% 손실)이라 브리지를 띄울 수 없었다.
**2026-08-30 운용자가 하드웨어 고장으로 확정했다** — 복구·재사용 계획 없음.

**이때 드러난 문제 — 스크립트가 기기 안에만 있었다.** `mav_bridge.py` / `px4_param.py` 가
git 에 없어 기기가 꺼지자 회수 불가였고, README 에 남은 동작 명세를 근거로 **재작성**해야 했다.
그래서 지금은 두 스크립트와 유닛 파일 모두 이 폴더에 정본으로 둔다.
