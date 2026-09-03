# QGroundControl (QGC) — 지상통제 소프트웨어 연결 절차

[Striver Mini VTOL](../../airframes/striver-mini-vtol/README.md) 기체([Pixhawk 6C Mini](../../components/fc/holybro-pixhawk-6c-mini/README.md) / PX4)를 QGroundControl로 감시·설정하기 위한 **접속 절차 통합 문서**. 배선·부품 사양은 각 부품 문서에, **"어디에 어떻게 붙는지"는 이 문서**에 모은다.

| 항목 | 값 |
|---|---|
| 버전 | **QGroundControl v5.1.4** — 직접 빌드 + VTOL 패치 ([BUILD.md](BUILD.md), 2026-09-02) |
| 이전 | v5.0.8 AppImage — `~/SHADE01/Applications/QGroundControl.AppImage` 에 남겨 뒀다 (되돌아갈 때) |
| 배포 형태 | AppImage — `~/SHADE01/Applications/QGroundControl.AppImage` (약 172 MB) |
| 대상 FC 펌웨어 | **PX4** v1.17.0 커스텀 |
| 프로토콜 | MAVLink v2 |
| 공식 문서 | https://docs.qgroundcontrol.com |

> 버전 확인: QGC 실행 → 좌상단 **Q 아이콘** → `About`.
> `--version` 플래그는 **아무것도 출력하지 않는다** (AppImage 가 GUI 로 바로 뜬다).

---

## 설치 (Ubuntu) — 실기 기준

`ku-dgs1` 에 이 방식으로 설치돼 있다. 새 GCS PC 를 붙일 때 그대로 따르면 된다.

### 1. 사전 조건 — 시리얼 권한

USB 직결(경로 B)을 쓰려면 계정이 `dialout` 그룹이어야 한다. **재로그인해야 적용된다.**

```bash
sudo usermod -aG dialout $USER
sudo apt remove -y modemmanager        # FC USB 포트를 가로채므로 제거 권장
```

무선(경로 A)만 쓸 거면 이 단계는 건너뛰어도 된다.

### 2. AppImage 내려받기

```bash
mkdir -p ~/SHADE01/Applications
cd ~/SHADE01/Applications
# https://github.com/mavlink/qgroundcontrol/releases 에서 x86_64 AppImage 를 받는다
chmod +x QGroundControl.AppImage
```

> ⚠️ **버전을 임의로 올리지 마라.** 이 기체는 PX4 v1.17.0 **커스텀 빌드**라 QGC 가
> 표준 릴리스 기준으로 검사하며 파라미터 경고를 낼 수 있다.
>
> 🔵 **2026-09-02 — v5.0.8 → v5.1.4 로 올렸다.** 공식 AppImage 가 아니라 [직접 빌드](BUILD.md)
> 다. VTOL 에서 미션 예상시간이 안 맞고 기종이 Tailsitter 로 잘못 뜨는 버그 3곳을 고쳤다.
> 올리기 전에 회귀를 실측으로 확인했다 — MAVLink v1 프레임 0개, compid 전부 1,
> 파라미터·미션·지오펜스 FC 실제값과 일치. 상세는 BUILD.md.

### 3. 실행

```bash
~/SHADE01/Applications/QGroundControl.AppImage
```

⚠️ 터미널에서 백그라운드로 띄울 때는 **`setsid` 로 세션에서 분리**할 것 —
그냥 `&` 로 띄우면 셸이 종료될 때 QGC 도 같이 죽는다.

```bash
setsid ~/SHADE01/Applications/QGroundControl.AppImage >/dev/null 2>&1 &
```

### 4. 바탕화면 아이콘 등록

아이콘 파일을 먼저 넣는다 (AppImage 안에서 꺼내거나 저장소 사본을 쓴다):

```bash
mkdir -p ~/.local/share/icons/hicolor/128x128/apps
# qgroundcontrol.png 를 위 경로에 둔다
```

`.desktop` 항목을 만든다. **바탕화면용과 앱 목록용 두 곳**에 같은 내용을 둔다:

```bash
cat > ~/.local/share/applications/qgroundcontrol.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Version=1.0
Name=QGroundControl
GenericName=Ground Control Station
Comment=Ground control station for MAVLink vehicles
Exec=/home/ku/SHADE01/Applications/QGroundControl.AppImage
Icon=qgroundcontrol
Terminal=false
StartupWMClass=QGroundControl
StartupNotify=true
Categories=Science;Robotics;
Keywords=MAVLink;PX4;drone;UAV;QGC;
DESKTOP

cp ~/.local/share/applications/qgroundcontrol.desktop ~/Desktop/
chmod +x ~/Desktop/qgroundcontrol.desktop
gio set ~/Desktop/qgroundcontrol.desktop metadata::trusted true   # GNOME 신뢰 표시
update-desktop-database ~/.local/share/applications 2>/dev/null
```

- `Exec` 은 **절대경로**여야 한다. `~` 는 `.desktop` 에서 확장되지 않는다.
- 계정명이 PC 마다 다르므로(`ku`/`dsa`/`raspb1`) 경로를 그대로 복사하지 말 것.
- 바탕화면 아이콘이 회색 물음표로 뜨면 `gio set ... trusted` 를 안 한 것이다.
- ⚠️ **QGC 버전을 바꾸면 `Exec` 도 같이 고쳐라.** 2026-09-02 v5.1.4 로 올린 뒤에도
  바탕화면 아이콘만 옛 AppImage 를 가리키고 있었다. 앱 목록과 바탕화면 **두 곳 다** 본다:
  `grep -h Exec ~/.local/share/applications/qgroundcontrol.desktop ~/Desktop/qgroundcontrol.desktop`

#### 조종기 ELRS 링크 아이콘

백팩 AP 로 전환해서 QGC 를 띄우는 항목을 따로 둔다. 저장소에 사본이 있다
([`qgc-elrs-backpack.desktop`](qgc-elrs-backpack.desktop)) — **`Exec` 경로의 계정명만
자기 PC 에 맞게 고쳐서** 쓴다:

```bash
sed "s|/home/[^/]*/|$HOME/|g" gcs/qgroundcontrol/qgc-elrs-backpack.desktop \
  > ~/.local/share/applications/qgc-elrs-backpack.desktop
cp ~/.local/share/applications/qgc-elrs-backpack.desktop ~/Desktop/
chmod +x ~/Desktop/qgc-elrs-backpack.desktop
gio set ~/Desktop/qgc-elrs-backpack.desktop metadata::trusted true
update-desktop-database ~/.local/share/applications 2>/dev/null
```

`Terminal=true` 는 의도된 것이다 — AP 전환 진행을 보여주고, 창을 닫을 때 원래 WiFi 로
되돌리는 `trap` 이 돌아야 한다.

### 5. 연결

설치가 끝나면 [경로 A](#경로-a--무선-접속-tailscale--udp-14550)(무선) 또는
[경로 B](#경로-b--usb-직결-폴백--펌웨어-작업용)(USB)로 붙는다.

> 🔴 **무선으로 붙으려면 이 PC 가 브리지의 고정 송신 대상에 등록돼 있어야 한다.**
> QGC 의 UDP 링크는 기체가 먼저 말을 걸어오기를 기다릴 뿐 스스로 쏘지 않기 때문이다.
> [3단계 — 새 GCS PC 추가](#3단계--새-gcs-pc-추가-필요시) 참조.

---

## 링크 3개 구성 (2026-09-02 확정)

경로가 셋이라 QGC 에 **각각 이름 붙은 링크**로 등록해 두고 필요한 것을 고른다.
`~/.config/QGroundControl/QGroundControl.ini` 의 `[LinkConfigurations]` 절이다.

| # | 이름 | 방식 | 자동연결 | 쓰는 때 |
|---|---|---|---|---|
| 1 | **Pi 브리지** (raspb1 / LTE·WiFi) | UDP **14550** 리슨 | **ON** | 평소 비행 — 주 경로 |
| 2 | **ELRS 백팩** (조종기 WiFi) | UDP **14555** → `10.0.0.1:14550` | OFF | Pi 가 죽었을 때 |
| 3 | **FC USB 직결** | Serial `/dev/ttyACM0` @921600 | OFF | 펌웨어·캘리브레이션 |

### 🔴 `autoConnectUDP` 를 꺼야 한다

**이걸 켜두면 QGC 가 등록된 링크와 별개로 익명 UDP 링크를 하나 더 만든다.** 같은 기체가
두 링크로 보여 `Comm Lost` → `Switching communication to secondary link` 팝업이 뜨고,
어느 링크로 붙었는지 알 수 없게 된다.

```ini
[AutoConnect]
autoConnectPixhawk=true      ← 유지. USB 로 FC 꽂으면 자동으로 잡아준다
autoConnectUDP=false         ← 반드시 끈다
```

증상 확인: `ss -ulpn | grep QGroundControl` 이 **14550 소켓을 2개** 보이면 익명 링크가
살아 있는 것이다. 정상이면 1개다.

> ⚠️ **이 값은 QGC 가 되돌려 놓는다.** 2026-09-02 rim3 에서 `autoConnectUDP=true`,
> `autoConnectPixhawk=false` 로 뒤집혀 있는 것을 발견했다 (QGC 버전 교체 중 발생한 것으로
> 보인다). **QGC 를 끄고** 고친 뒤, 켜서 다시 끄고 값이 유지되는지 확인할 것 —
> 켜진 채로 고치면 종료할 때 덮어쓴다.

### ⚠️ 리슨 포트를 겹치지 마라

1번과 2번을 **둘 다 14550 으로 두면 안 된다.** ELRS 백팩은 조종기 AP 에 붙었을 때만 쓰는
경로라 리슨 포트를 겹칠 이유가 없다 — **14555** 로 분리해 둔다.

### 🔴 백팩 AP 는 붙어도 30초~2분 뒤 원래 WiFi 로 끌려간다 (2026-09-02 원인 규명)

**증상**: `nmcli con up "ExpressLRS TX Backpack 17B49E"` 가 **성공을 보고하는데**
잠시 뒤 보면 `iptimE` 로 돌아와 있다. `10.0.0.1` 은 100% packet loss 로 안 잡히고
QGC 의 2번 링크도 당연히 안 붙는다. 재시도해도 같다.

**원인**: **백팩 AP 에는 인터넷이 없다.** NetworkManager 의 연결성 검사가 이 AP 를
"인터넷 없음" 으로 판정하고, `autoconnect=yes` 인 다른 프로파일(`iptimE` 등)이
같은 우선순위(0)에 있으면 라디오를 도로 가져간다. 로그에 그대로 찍힌다:

```
17:35:33  Connected to wireless network "ExpressLRS TX Backpack 17B49E"
17:37:31  state change: activated -> deactivating (reason 'new-activation')   ← 2분 뒤 뺏김
17:37:32  Activation: starting connection 'iptimE'
```

확인:

```bash
journalctl -u NetworkManager --since "5 minutes ago" | grep -E "Backpack|new-activation"
```

**해결** — 백팩 프로파일에 우선순위를 주고, 기본 경로를 주장하지 않게 한다:

```bash
nmcli con modify "ExpressLRS TX Backpack 17B49E" \
  connection.autoconnect-priority 100 \
  ipv4.never-default yes \
  ipv6.never-default yes \
  ipv4.dns-priority 200
```

`never-default yes` 가 핵심이다 — 인터넷 없는 AP 가 기본 라우트·DNS 를 가져가지 않으니
NM 이 "끊긴 링크" 로 보고 되돌리지 않는다. `autoconnect` 는 **`no` 로 둔다**: 평시에
라디오를 멋대로 뺏지 않고, 쓸 때만 명시적으로 붙이기 위해서다.

확인:

```bash
nmcli -f connection.autoconnect,connection.autoconnect-priority,ipv4.never-default \
  con show "ExpressLRS TX Backpack 17B49E"
# autoconnect:no / priority:100 / never-default:yes
```

### ⚠️ 백팩에 붙어 있는 동안은 Pi 브리지 경로를 못 쓴다

노트북 WiFi 는 **하나뿐**이다. 백팩 AP 에 붙으면 인터넷과 Tailscale 이 끊기므로
1번(Pi 브리지) 링크는 그동안 죽는다. **둘은 배타적인 폴백 관계**지 병행 경로가 아니다.
SSH 로 raspb1 을 만지는 작업도 그동안 안 된다.

### 어느 PC 에서 되나 (2026-09-03 확인)

백팩 링크는 **WiFi 라디오가 있는 PC 에서만** 된다. 조종기 AP 에 직접 붙는 방식이라
유선 랜으로는 대체가 안 된다.

| PC | WiFi 장치 | 백팩 링크 | QGC 바이너리 |
|---|---|---|---|
| `rim3` | `wlo1` | ✅ 된다 (여기서 처음 구축) | `SHADE01/qgc-5.1.4/bin/QGroundControl` |
| `gram-labtop` | `wlp0s20f3` | ✅ 된다 (2026-09-03 반영) | `SHADE01/Applications/QGroundControl.AppImage` |
| `ku-dgs1` | **없음** | ❌ 못 쓴다 | (WiFi 가 없어 무관) |

`ku-dgs1` 은 `enp3s0` 유선 하나뿐이고 USB WiFi 동글도 안 꽂혀 있다. 확인:

```bash
nmcli -t -f DEVICE,TYPE dev status | grep ':wifi$'   # 아무것도 안 나오면 불가
```

**동글을 꽂으면 그때 된다.** 프로파일과 QGC 링크 설정은 이미 `ku` 에도 들어가 있으므로
(아래 1·2 단계는 완료된 상태), 동글 인식만 확인하고 바로 실행하면 된다. 스크립트는 WiFi 가
없으면 nmcli 오류 대신 그 사실을 말하고 멈춘다.

### 새 PC 에 백팩 링크 붙이기

스크립트 자체는 PC 를 안 가린다 — WiFi 장치·복귀망·QGC 바이너리를 **실행할 때 감지**한다
(2026-09-03). 하드코딩된 `wlo1`/`iptimE` 는 없앴다. PC 마다 해줄 일은 셋뿐이다.

**1. 백팩 AP 프로파일 만들기.** 이름·우선순위·`never-default` 가 핵심이다 —
왜 그런지는 [바로 위 "끌려간다" 항목](#-백팩-ap-는-붙어도-30초2분-뒤-원래-wifi-로-끌려간다-2026-09-02-원인-규명)에 있다.

```bash
AP="ExpressLRS TX Backpack 17B49E"
DEV=$(nmcli -t -f DEVICE,TYPE dev status | grep ':wifi$' | cut -d: -f1 | head -1)

nmcli con add type wifi con-name "$AP" ifname "$DEV" ssid "$AP" \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk 'expresslrs' \
  connection.autoconnect no \
  connection.autoconnect-priority 100 \
  ipv4.method auto ipv4.never-default yes ipv6.never-default yes ipv4.dns-priority 200
```

확인 — 네 값이 아래와 같아야 한다:

```bash
nmcli -f connection.autoconnect,connection.autoconnect-priority,ipv4.never-default,ipv4.dns-priority \
  con show "ExpressLRS TX Backpack 17B49E"
# no / 100 / yes / 200
```

**2. QGC 에 2번 링크 등록.** `~/.config/QGroundControl/QGroundControl.ini` 의
`[LinkConfigurations]` 에 아래가 있어야 한다. **QGC 를 끈 상태에서** 고친다 — 켜져 있으면
종료할 때 자기 메모리 값으로 덮어써서 편집이 날아간다.

```ini
Link1\auto=false
Link1\high_latency=false
Link1\host0=10.0.0.1
Link1\hostCount=1
Link1\name=2. ELRS 백팩 (조종기 WiFi)
Link1\port=14555
Link1\port0=14550
Link1\type=1
```

`port=14555` 는 로컬 리슨 포트다. **1번(Pi 브리지)이 쓰는 14550 과 겹치면 안 된다** —
[위 표](#링크-3개-구성-2026-09-02-확정) 참조.

**3. 아이콘 설치** — 바로 아래 [조종기 ELRS 링크 아이콘](#조종기-elrs-링크-아이콘) 절차.

### 실행 — `elrs-backpack`

AP 전환·확인·QGC 실행·원복을 한 번에 한다. 창을 닫으면 원래 WiFi 로 되돌아간다.

```bash
./gcs/qgroundcontrol/elrs-backpack            # 복귀망 = 지금 붙어 있는 WiFi
./gcs/qgroundcontrol/elrs-backpack eduroam    # 복귀망 지정
```

인자를 안 주면 **지금 그 WiFi 가 붙어 있는 망**으로 되돌아온다. 옛 버전은 `iptimE` 가
기본값으로 박혀 있어 다른 PC·다른 장소에서는 엉뚱한 망으로 복귀하려 했다.
환경변수로도 덮어쓸 수 있다: `ELRS_DEV`(WiFi 장치), `ELRS_AP`(AP 이름), `QGC_BIN`(실행파일).

QGC 가 뜨면 **Comm Links → `2. ELRS 백팩` 을 Connect** 한다 (이 링크는 `auto=false` 다).
위의 "끌려감" 이 재발하면 스크립트가 그것을 감지하고 **조용히 진행하지 않고 멈춘다.**

바탕화면·앱 목록의 **"QGC — 조종기 ELRS 링크"** 아이콘이 같은 스크립트를 띄운다
(`~/.local/share/applications/qgc-elrs-backpack.desktop`). AP 전환 과정을 보여줘야 하고
창을 닫을 때 WiFi 를 되돌려야 하므로 `Terminal=true` 다 — 터미널 창이 뜨는 게 정상이다.

> 그냥 **"QGroundControl"** 아이콘은 AP 전환 없이 QGC 만 띄운다. Pi 브리지(1번)·USB(3번)
> 경로용이다.

### FC 쪽은 건드릴 게 없다

ELRS 링크는 **TELEM1** 로 들어온다. 이미 켜져 있다:

| 파라미터 | 값 | 뜻 |
|---|---|---|
| `MAV_0_CONFIG` | `101` | TELEM1 에 MAVLink 인스턴스 |
| `SER_TEL1_BAUD` | `460800` | ELRS 수신기 보레이트 |
| `MAV_0_MODE` | `0` | Normal — 텔레메트리 전량 |

> ⚠️ **`MAV_1_CONFIG=0` 을 되돌리지 마라.** 그건 **TELEM2**(사망한 포트)다.
> 2026-09-02 에 `102` → `0` 으로 내린 것이 맞다 — 죽은 포트에 쏘느라 FC CPU 7.4% 를
> 태우고 있었다. **ELRS 링크와 무관하다.**

### 설정 파일 직접 편집 시

> 🔴 **QGC 를 끄고 편집하라.** 켜진 채로 `.ini` 를 고치면 종료할 때 QGC 가 메모리 내용으로
> 덮어써서 작업이 사라진다.

```ini
[LinkConfigurations]
Link0\auto=true
Link0\high_latency=false
Link0\hostCount=0
Link0\name=1. Pi 브리지 (raspb1 / LTE·WiFi)
Link0\port=14550
Link0\type=1
Link1\auto=false
Link1\high_latency=false
Link1\host0=10.0.0.1
Link1\hostCount=1
Link1\name=2. ELRS 백팩 (조종기 WiFi)
Link1\port=14555
Link1\port0=14550
Link1\type=1
Link2\auto=false
Link2\baud=921600
Link2\dataBits=8
Link2\flowControl=0
Link2\name=3. FC USB 직결
Link2\parity=0
Link2\portName=/dev/ttyACM0
Link2\stopBits=1
Link2\type=0
count=3
```

`type=1` 이 UDP, `type=0` 이 Serial 이다. **편집 전 `.ini` 를 백업**해 둘 것.

> ⚠️ **소문자 `[linkConfigurations]` 절이 따로 있을 수 있다.** rim3 에서 실제로 나왔다 —
> 옛 QGC 가 만든 것으로, 대문자 절만 고치면 **두 절이 공존해 링크가 중복**된다.
> `grep -n '^\[' QGroundControl.ini` 로 절 목록을 먼저 확인하고, 소문자 절은 지운다.

배포용 스크립트는 이 문서 아래 [세 PC 일괄 적용](#세-pc-일괄-적용) 참조.

### 세 PC 일괄 적용

`ku` · `rim` · `rim3` 세 대가 같은 구성을 쓴다. 각 PC 에서:

```bash
# 1. QGC 를 끈다 (켜져 있으면 종료 시 덮어쓴다)
pgrep -x QGroundControl && echo "먼저 QGC 를 종료하라"

# 2. 백업
cp ~/.config/QGroundControl/QGroundControl.ini{,.bak.$(date +%Y%m%d-%H%M%S)}

# 3. 위 [LinkConfigurations] 블록으로 교체 + autoConnectUDP=false
# 4. 소문자 [linkConfigurations] 절이 있으면 제거
grep -n '^\[' ~/.config/QGroundControl/QGroundControl.ini
```

확인:

```bash
grep -E 'Link[012]\\name=|^count|autoConnectUDP' ~/.config/QGroundControl/QGroundControl.ini
# count=3, autoConnectUDP=false, 링크 이름 3개가 나와야 한다
```

⚠️ **1번과 3번은 동시에 못 쓴다** — FC USB 포트가 하나뿐이라 raspb1 이 잡고 있으면 노트북에
꽂을 수 없다.

## 결론부터 — 무엇에 접속하는가

**QGC는 FC에 직접 접속하지 않는다.** 무선 경로에서 QGC가 실제로 붙는 상대는 기체에 탑재된 [Raspberry Pi 5 `raspb1`](../../components/companion/raspberry-pi-5/README.md)가 띄운 **UDP 14550 MAVLink 브리지**다.

| 경로 | QGC의 접속 상대 | 링크 종류 | 상태 |
|---|---|---|---|
| **A. 무선 (주 경로)** | RPi 5 `raspb1`의 `mav_bridge.py` — **UDP 14550** | Tailscale VPN (인터넷 경유) | ✅ **전 구간 검증 (2026-08-31)** — 21.8 KB/s. Pi↔FC 는 **USB 직결**(TELEM2 포트 사망) |
| **B. USB 직결 (폴백/설정용)** | FC USB-C 포트 → PC 시리얼 | USB 케이블 | ✅ 검증 완료 (2026-08-11) — ⚠️ 수동 링크 등록 금지, [아래 참조](#-수동-usb-링크는-1초-뒤-끊긴다) |
| ~~C. 무선 모뎀 직결~~ | T900 Pro 등 텔레메트리 라디오 | 900MHz 등 | ❌ 미보유 — [미구매 항목](../../airframes/striver-mini-vtol/README.md#보유-사양-메모-shade-기체--pnp) |

> 🟡 **경로 A 는 인터넷 경유다.** Pi 가 WiFi/LTE 클라이언트라 두 망이 다 끊기면 링크도 끊긴다. LTE 모뎀 장착(2026-08-31)으로 WiFi 범위 의존은 해소됐으나, **장거리 비행 중 신뢰성은 미검증**이다.

### 전체 링크 구조

```
[Pixhawk 6C Mini] ──USB-C ⟷ USB-A────────► [Raspberry Pi 5 "raspb1"]
   (PX4, MAVLink v2)                          /dev/ttyACM0
   🔴 TELEM2 포트는 사망 (2026-08-31)
        │                                          │
        │                                   mav_bridge.py
        └── USB-C ──┐                     (UDP :14550 브리지)
                    │                              │
              (경로 B 폴백)          WiFi/LTE → 인터넷 → Tailscale
                    │                              │
                    │                  ┌───────────┴───────────┐
                    ▼                  ▼                       ▼
              [로컬 PC]        [ku-dgs1 100.99.120.110]  [rim / rim3]
            QGroundControl        QGroundControl          QGroundControl
                                        └──── 경로 A ────┘
```

---

## 경로 A — 무선 접속 (Tailscale + UDP 14550)

### 사전 조건

| 항목 | 요구 상태 | 확인 방법 |
|---|---|---|
| 기체 전원 | FC에 전원 인가 ([PM08-CAN](../../components/power/holybro-pm08-can/README.md) → Power1) | FC LED 점등 |
| Pi 전원 | RPi 5 부팅 완료 | Tailscale에 `raspb1-dgs3` 온라인 표시 |
| Pi ↔ FC 배선 | **USB-C 직결** (`/dev/ttyACM0`) — 구 Telem2 GPIO 결선은 폐기 | [USB 직결](../../components/companion/raspberry-pi-5/README.md#-fc--raspb1-usb-직결-2026-08-31-현행) |
| 브리지 서비스 | `mavlink-bridge.service` **active** | 아래 1단계 |
| GCS PC | Tailscale 로그인 + 해당 tailnet 소속 | `tailscale status` |
| GCS PC IP | 브리지 **고정 송신 대상에 등록**되어 있어야 함 | 아래 2단계 |

### 1단계 — 기체측 브리지 상태 확인

`raspb1`에 SSH 접속해 서비스가 살아 있는지 본다.

```bash
# GCS PC에서
ssh raspb1@100.126.161.1

# raspb1에서
systemctl status mavlink-bridge.service
```

`active (running)` 이어야 한다. 죽어 있으면:

```bash
sudo systemctl start mavlink-bridge.service
journalctl -u mavlink-bridge.service -f
```

로그에 시리얼 오픈과 패킷 수신이 보이면 정상. 서비스는 `enabled` + `Restart=always`이므로 통상 부팅만 하면 자동 기동된다.

### 2단계 — 내 PC가 고정 송신 대상인지 확인

브리지는 **ExecStart 인자로 등록된 IP에만 먼저 텔레메트리를 밀어준다.** 등록된 PC는 QGC를 켜기만 하면 자동으로 기체가 뜬다.

```bash
# raspb1에서 — 현재 등록된 대상 확인
grep ExecStart /etc/systemd/system/mavlink-bridge.service
```

현재 등록 상태:

| Tailscale 노드 | IP | 상태 |
|---|---|---|
| `ku-dgs1` | `100.99.120.110:14550` | ✅ 등록됨 |
| `rim` | `100.107.83.47:14550` | ✅ 등록됨 (2026-08-11 추가) |
| `rim3` | `100.117.47.105:14550` | ✅ 등록됨 (2026-08-30 추가, **2026-09-02 IP 변경**) |

> ⚠️ **Tailscale 계정을 바꾸면 IP 가 바뀐다.** rim3 를 `yyrrm@` → `6K5EUQ@` 로 옮기자
> 노드가 새로 등록되며 `100.105.212.78` → `100.117.47.105` 이 됐다. 옛 노드는 offline 으로
> 남는다. **브리지의 고정 송신 대상(`ExecStart`)을 반드시 새 IP 로 고쳐야** 그 PC 에서
> 기체가 보인다 — QGC 의 UDP 링크는 기체가 먼저 말을 걸어오길 기다릴 뿐이기 때문이다.
> SSH 호스트키도 바뀌므로 `ssh-keygen -R <옛IP>` 가 필요하다.
| `gram-labtop` | `100.66.204.25:14550` | ✅ 등록됨 (2026-08-31 추가) |

**내 PC가 목록에 없으면** → [3단계](#3단계--새-gcs-pc-추가-필요시)로. 있으면 → [4단계](#4단계--qgc-실행)로 건너뛴다.

### 3단계 — 새 GCS PC 추가 (필요시)

먼저 추가할 PC의 Tailscale IP를 확인한다.

```bash
# 추가할 GCS PC에서
tailscale ip -4
```

그 IP를 브리지의 고정 대상에 덧붙인다.

```bash
# raspb1에서 — 아래 명령은 유닛 파일을 수정한다. 실행 전 아래 주의사항을 읽을 것.
sudo cp /etc/systemd/system/mavlink-bridge.service \
        /etc/systemd/system/mavlink-bridge.service.bak-$(date +%Y%m%d)
sudo sed -i 's|mav_bridge.py .*|& 새IP:14550|' /etc/systemd/system/mavlink-bridge.service
grep ExecStart /etc/systemd/system/mavlink-bridge.service   # 결과 확인
sudo systemctl daemon-reload && sudo systemctl restart mavlink-bridge.service
```

이 절차는 systemd 유닛 파일을 직접 수정하고 서비스를 재시작합니다. 다음 사항을 확인하고 진행하십시오.

- `sed`의 치환 패턴은 `mav_bridge.py` 뒤의 **모든 인자를 매칭한 뒤 그 뒤에 새 IP를 덧붙이는(`&`) 방식**입니다. 패턴을 잘못 수정하면 기존 대상(`ku-dgs1`, `rim`)이 삭제될 수 있으므로, 실행 후 반드시 `grep ExecStart`로 결과를 눈으로 확인하십시오.
- 서비스 재시작 중 **기존에 연결된 모든 GCS 링크가 1~2초간 끊깁니다.** 자동 재연결되지만, **비행 중이나 기체 시동(armed) 상태에서는 절대 실행하지 마십시오.** 지상에서 시동이 꺼진 상태에서만 수행합니다.
- 위 명령은 변경 전 유닛 파일을 `.bak-YYYYMMDD`로 백업합니다. 문제 발생 시 `sudo cp` 로 백업 파일을 되돌린 뒤 `daemon-reload` + `restart` 하면 복구됩니다.
- 기존 백업 예시: `/etc/systemd/system/mavlink-bridge.service.bak-20260811` (2026-08-11 `rim` 추가 전 상태)

> 참고: 고정 대상에 등록하지 않아도, GCS가 브리지의 UDP 14550으로 **먼저 패킷을 보내면** 30초 유효한 `peer`로 자동 등록되어 양방향 통신이 된다. 다만 QGC 기본 설정은 수신 대기(bind)만 하므로, 이 경우 QGC에 **송신 대상을 명시한 UDP 링크를 수동 추가**해야 한다. 고정 대상 등록이 훨씬 단순하다.

### 4단계 — QGC 실행

```bash
# rim PC 예시
setsid ~/Downloads/QGroundControl-x86_64.AppImage
```

- QGC가 **UDP 14550을 바인딩하면 링크 수동 추가 없이 기체가 자동으로 뜬다.** Application Settings → Comm Links에서 별도 설정할 필요 없다.
- ⚠️ 터미널에서 백그라운드로 띄울 때는 `setsid`로 세션에서 분리할 것 — 그냥 `&`로 띄우면 셸이 종료될 때 QGC도 함께 죽는다.
- ⚠️ **QGC가 켜져 있어야 14550을 점유한다.** QGC를 닫으면 브리지 `peers`에서 30초 뒤 빠지지만 **고정 대상 등록분은 유지**되므로, 다시 켜면 즉시 재수신된다.

### 5단계 — 연결 성립 확인

QGC 화면에서 아래 항목을 순서대로 확인한다.

| 확인 항목 | 정상 표시 | 실패 시 참조 |
|---|---|---|
| 기체 인식 | 상단 바에 기체(Vehicle 1) 표시, "Waiting for vehicle connection" 소멸 | [트러블슈팅](#트러블슈팅) |
| 배터리 | 전압/잔량/전류 표시 (예: **22.88V / 48% / 0.17A**) | [PM08-CAN](../../components/power/holybro-pm08-can/README.md) |
| GPS | 위성 수 / HDOP 표시 | [M10N GPS](../../components/gps/holybro-m10n/README.md) |
| 자세 | HUD의 수평선이 기체 기울임에 반응 | FC IMU |
| 에어스피드 | VFR_HUD의 airspeed 값 존재 | [Airspeed 센서](../../components/sensors/holybro-airspeed-dronecan/README.md) |
| 양방향 | 파라미터 화면 로딩 완료 (Vehicle Setup → Parameters) | 아래 참조 |

**양방향 통신이 성립했는지**는 기체측 브리지 로그로도 확인할 수 있다.

```bash
# raspb1에서
journalctl -u mavlink-bridge.service -f | grep "GCS connected"
```

`GCS connected: ('100.107.83.47', 14550)` 처럼 내 PC IP가 등록되면 명령 전송·파라미터 읽기/쓰기가 가능한 상태다.


## 경로 B — USB 직결 (폴백 / 펌웨어 작업용)

무선 링크가 불가할 때, 또는 **펌웨어 플래싱·센서 캘리브레이션처럼 링크 단절이 치명적인 작업**에 사용한다.

1. FC의 **USB-C 포트**를 PC에 연결한다. (FC USB 전원 입력 4.75–5.25V — [전원 규격](../../components/fc/holybro-pixhawk-6c-mini/README.md#전원-규격))
2. QGC를 실행하면 시리얼 포트를 **자동 인식**해 연결된다. **링크를 수동으로 추가하지 말 것** — 아래 참조.
3. Linux에서 포트 권한 오류가 나면 실행 계정이 `dialout` 그룹에 있어야 한다.

```bash
sudo usermod -aG dialout $USER   # 적용에는 재로그인 필요
```

### 🔴 수동 USB 링크는 1초 뒤 끊긴다

**증상**: Comm Links에 시리얼 링크를 직접 등록해 Connect 하면 붙었다가 **약 1초 만에 끊긴다.** 반복해도 동일하다.

**원인**: QGC(AppImage 번들 Qt)의 포트 열거 문제로 보인다. 등록된 수동 시리얼 링크가 이 환경에서 유지되지 않는다. `Link0`에 `auto=true`를 줘도 해결되지 않는다 — QGC는 저장된 링크와 **무관하게 autoconnect 전용 동적 링크를 따로 생성**하기 때문이다.

```
4.282  "FC USB" 링크 연결
5.357  1초 뒤 끊김            ← 수동 등록 링크
7.052  New auto-connect port added: "PX4 FMU V6C on ttyACM0 (AutoConnect)"
7.068  이 동적 링크로 연결 → 유지됨   ← 실제로 붙어 있는 것은 이쪽
```

**해결**: 수동 USB 링크를 **등록하지 않고**, autoconnect 동적 링크만 쓴다. 이미 등록해 두었다면 삭제한다.

| 설정 | 값 | 효과 |
|---|---|---|
| `autoConnectPixhawk` | `true` | USB 케이블을 꽂으면 **자동 연결**. Comm Links 목록에는 표시되지 않는다 |
| `autoConnectUDP` | `false` | Pi 링크가 멋대로 붙지 않음 — 필요할 때 **수동 Connect** |

이 조합이 "상황에 따라 골라 쓰기"에 가장 가깝다: **USB는 꽂으면 자동, Pi는 클릭해서 연결.**

- Comm Links에 "FC USB" 같은 항목이 Connect 버튼인 채 남아 있다면 혼란만 주므로 삭제할 것.
- ⚠️ **USB 전원만으로는 서보·ESC가 동작하지 않는다.** USB는 FC 로직만 살린다. 액추에이터 테스트에는 [UBEC](../../components/fc/holybro-pixhawk-6c-mini/README.md#서보-전원-mfe-ubec-연결)의 서보 레일 전원과 메인 배터리가 필요하다.
- 🔴 **경로 A 와 동시 사용 불가** — 경로 A(raspb1 브리지)가 FC 의 **같은 USB 포트**를 점유한다. 노트북을 직결하려면 Pi 쪽 USB 를 뽑거나 `sudo systemctl stop mavlink-bridge.service` 로 브리지를 내려야 한다.
- 🔶 이 경로는 아직 본 기체에서 별도 기록된 검증 이력이 없다(표준 동작이므로 문제 없을 것으로 예상). 실제 수행 후 결과를 이 문서에 추가할 것.

---

## QGC로 수행할 설정 작업

QGC 접속이 성립한 뒤 진행할 기체 설정 항목과 참조 문서.

| 작업 | QGC 위치 | 참조 문서 |
|---|---|---|
| 액추에이터(모터/서보) 출력 배정 | Vehicle Setup → Actuators | [FC — Actuators 화면 설정](../../components/fc/holybro-pixhawk-6c-mini/README.md#qgc-actuators-화면-설정) |
| 채널 배정안 (ESC 5 + 서보 5) | Vehicle Setup → Actuators | [FC — 채널 배정안](../../components/fc/holybro-pixhawk-6c-mini/README.md#채널-배정안-px4-기준) |
| ESC 캘리브레이션 | Vehicle Setup → Power (⚠️ **프로펠러 제거 필수**, 🔴 **USB 직결에서만 동작**) | [ESC 650 튜닝](../../components/esc/mfe-esc-650-50a/README.md#튜닝-프로세스-throttle-travel-tuning) |
| 배터리 / 전원 파라미터 확인 | Vehicle Setup → Power / Parameters | [PM08-CAN](../../components/power/holybro-pm08-can/README.md) |
| CAN 파라미터 확인 | Parameters → `UAVCAN_ENABLE`, `UAVCAN_SUB_BAT`, `BAT1_SOURCE` | [PM08-CAN](../../components/power/holybro-pm08-can/README.md) |
| RC 수신기 설정 | Vehicle Setup → Radio | [RP4TD-M](../../components/receivers/radiomaster-rp4td-m/README.md) — ✅ Telem1 결선 완료. `RC_CRSF_PRT_CFG=101`, `COM_RC_IN_MODE` 확인 필수 |

> ⚠️ **파라미터 변경 전 백업**: Parameters 화면 우상단 Tools → **Save to file**로 현재 값을 저장해 둘 것. 되돌릴 수단이 없으면 설정 실수를 복구할 수 없다.

### 🔴 무선(경로 A)으로 하면 안 되는 작업

타이밍이 정밀하거나 링크 단절이 치명적인 작업은 **반드시 USB 직결(경로 B)**에서 수행한다.

| 작업 | 이유 |
|---|---|
| **ESC 캘리브레이션** | QGC가 무선 링크에서는 **아예 허용하지 않는다.** 타이밍 정밀도 요구 |
| 펌웨어 플래싱 | 중간에 끊기면 FC가 벽돌이 될 수 있다 |
| 파라미터 대량 읽기/쓰기 | 누락·타임아웃 위험 |
| 미션·랠리포인트 업/다운로드 | 전송 안정성 |
| 액추에이터 테스트 | 응답 지연이 오판을 부른다 |

USB는 지연이 1ms 수준이라 이런 전송이 안정적이다. 반대로 **비행 중 모니터링**은 무선 경로만 가능하다.

### ⚠️ `COM_RC_IN_MODE` — RC가 안 먹을 때 첫 번째 확인 대상

스틱을 움직여도 제어면이 반응하지 않으면 이 파라미터부터 본다.

- `COM_RC_IN_MODE = 1` 은 **"Joystick only"** 모드로, **RC 입력을 통째로 무시**하고 QGC 조이스틱만 받는다. 배선과 `RC_CRSF_PRT_CFG`가 모두 정상이어도 서보가 움직이지 않는 직접적 원인이 된다.
- ⚠️ **표시값 함정** — QGC나 스크립트가 이 값을 `1065353216`처럼 보여주는 경우가 있다. 이는 float `1.0`의 비트 패턴을 정수로 잘못 읽은 것으로, **실제 값은 `1`**이다. 이상한 큰 수가 보인다고 해서 값이 깨진 것이 아니다.

### 파라미터 조회 대안 — `px4_param.py`

QGC 없이도 기체측에서 파라미터를 읽고 쓸 수 있다. `/home/raspb1/px4_param.py` (자체 제작, pymavlink 없이 MAVLink v2 프레임 직접 생성). 정본은 [px4_param.py](../../components/companion/raspberry-pi-5/px4_param.py).

⚠️ **브리지와 동시 실행 불가** — 같은 시리얼 포트를 열기 때문에 먼저 브리지를 내려야 한다. 이때 **모든 QGC 링크가 끊긴다.**

```bash
sudo systemctl stop mavlink-bridge.service
python3 /home/raspb1/px4_param.py get SENS_DPRES_OFF
python3 /home/raspb1/px4_param.py set SENS_DPRES_OFF 0.0
sudo systemctl start mavlink-bridge.service  # 작업 후 반드시 재기동
```

상세: [RPi 5 — px4_param.py](../../components/companion/raspberry-pi-5/README.md#부수-도구--px4_parampy)

---

## 트러블슈팅

### QGC에 기체가 안 뜬다 (경로 A)

아래 순서로 **기체측에서 GCS측으로** 좁혀 나간다.

**1) 브리지가 시리얼에서 데이터를 받는가**

```bash
# raspb1에서
journalctl -u mavlink-bridge.service -n 50
```

- 서비스가 `inactive`/`failed` → `sudo systemctl start mavlink-bridge.service`
- 시리얼 오픈 실패 → FC 전원 미인가, 또는 **USB 케이블 빠짐**. `ls /dev/ttyACM0` 과 `lsusb | grep Auterion` 으로 확인 ([USB 직결](../../components/companion/raspberry-pi-5/README.md#-fc--raspb1-usb-직결-2026-08-31-현행))
- 포트 점유 충돌 → `px4_param.py` 나 노트북 USB 직결(경로 B)이 같은 FC 를 잡고 있는지 확인
- 시리얼은 열렸는데 패킷 0 → USB 경로는 보레이트 무관. FC 재부팅 후 `/dev/ttyACM0` 재생성 확인

**2) Tailscale 링크가 살아 있는가**

```bash
# GCS PC에서
tailscale status | grep raspb1
ping -c 3 100.126.161.1
```

- 노드 offline → Pi의 WiFi 연결 상태 확인. Pi는 **AP 모드가 아니라 클라이언트 모드**이므로 WiFi 범위 밖이면 링크가 없다. raspb1 프로필 우선순위: `iptimE`(20) → `eduroam`(10) → `5G_LGWiFi_2459`(1) → `SK_WiFiGIGA6311_5G`(0).

**3) UDP 14550이 실제로 도달하는가**

```bash
# GCS PC에서 — QGC를 먼저 끈 상태로 실행 (포트 경합 방지)
sudo tcpdump -i any -n udp port 14550
```

- 패킷이 보이는데 QGC가 못 잡음 → **QGC 아닌 다른 프로세스가 14550을 점유** 중일 수 있다. 아래 확인
- 패킷이 안 보임 → 내 IP가 [고정 대상에 등록](#2단계--내-pc가-고정-송신-대상인지-확인)되지 않았거나, GCS PC 방화벽이 UDP 14550 인바운드를 막고 있다

```bash
# 14550 점유 프로세스 확인
sudo ss -ulpn | grep 14550
```

**4) 그래도 안 되면 — QGC 링크 수동 추가**

Application Settings → Comm Links → Add:

| 항목 | 값 |
|---|---|
| Type | UDP |
| Listening Port | `14550` |
| Target Hosts | `100.126.161.1:14550` (raspb1. 추가 시 QGC가 먼저 말을 걸어 `peer` 등록됨) |
| High Latency | 미사용 |
| Automatically Connect on Start | 체크 |

### 배터리가 표시되지 않는다

FC까지의 CAN 센싱 문제일 가능성이 높다. [PM08-CAN 배선](../../components/fc/holybro-pixhawk-6c-mini/README.md#pm08-can-연결---결선-완료-2026-08-11)과 `UAVCAN_ENABLE=2` / `UAVCAN_SUB_BAT=2` / `BAT1_SOURCE=External` 파라미터를 확인한다. 이 구성은 **CURRENT1/VOLTAGE1 아날로그 핀 미결선 상태로 CAN 센싱만으로 동작**함이 검증되어 있다.

### 링크가 붙었다 끊긴다

- 경로 A는 **WiFi + 인터넷 + Tailscale** 3중 의존이다. 지상 벤치에서도 WiFi 신호가 약하면 간헐 단절이 발생한다.
- ✅ **LTE 모뎀 장착(2026-08-31)** 으로 WiFi 범위 의존은 해소됐다. ⚠️ 다만 **장거리 비행 중 신뢰성은 미검증** — 실비행 전 LTE 폴백이 실제로 인계받는지 확인할 것.
- 브리지 서비스가 반복 재시작하는지 확인: `systemctl status mavlink-bridge.service`의 재시작 횟수

### QGC를 닫았다 켰는데 안 붙는다

고정 대상 등록분은 유지되므로 정상적으로는 즉시 재수신된다. 안 되면 14550을 다른 프로세스가 잡고 있는지(`sudo ss -ulpn | grep 14550`), 또는 이전 QGC 프로세스가 좀비로 남아 있는지 확인한다.

---

## 🔶 확인 필요

- ~~경로 B(USB 직결) 실측 미기록~~ → **해소(2026-08-11)**: USB autoconnect로 접속·펌웨어 플래시·ESC 캘리브레이션까지 수행 완료. 단 **수동 링크 등록은 1초 뒤 끊기는 문제**가 있어 autoconnect만 쓴다. ([상세](#-수동-usb-링크는-1초-뒤-끊긴다))
- **수동 시리얼 링크 1초 끊김 근본 원인 미해결** — AppImage 번들 Qt의 포트 열거 문제로 추정되나 확정하지 못했다. QGC를 소스 빌드하면 해소될 가능성이 있다. 현재는 autoconnect로 우회 중이라 실사용에 지장 없음.
- **FC측 MAVLink 파라미터 실측값 미확정** — `MAV_*_MODE`가 `Onboard`인지 `Normal`인지 미확인. 수신 스트림에 HIGHRES_IMU·ATTITUDE_QUATERNION이 고레이트로 포함된 것으로 보아 `Onboard` 가능성이 높다. QGC Parameters에서 확정할 것. ([RPi 5 문서](../../components/companion/raspberry-pi-5/README.md#-확인-필요))
- **QGC 버전 미기록** — `rim` PC의 `QGroundControl-x86_64.AppImage` 버전 미확인. Actuators 화면 구성이 버전에 따라 다르므로 기록 필요.
  `ku-dgs1` 설치 형태는 확인됨 (2026-08-31): **AppImage** `~/SHADE01/Applications/QGroundControl.AppImage` (2026-07-24 내려받음, 180MB), 셸 런처 `~/.local/bin/qgroundcontrol`, 앱 메뉴 항목 `~/.local/share/applications/qgroundcontrol.desktop`, 바탕화면 아이콘 `~/Desktop/qgroundcontrol.desktop` (아이콘은 AppImage 에서 꺼내 `~/.local/share/icons/hicolor/128x128/apps/qgroundcontrol.png` 에 설치). AppImage 는 `--version` 을 지원하지 않아 버전 문자열은 QGC 실행 후 화면에서 확인해야 한다.
- ⚠️ **커스텀 펌웨어로 인한 QGC 경고** — FC에 PX4 v1.17.0 커스텀 빌드(플래시 98.30%)가 올라가 있어, QGC가 표준 릴리스 기준으로 검사하며 **"파라미터 누락" 경고**를 띄울 수 있다. 경고 자체보다 실제 기능 오작동 여부로 판단할 것. ([상세](../../components/fc/holybro-pixhawk-6c-mini/README.md#-플래시-용량-9830의-부작용))
- 🔴 **실비행 텔레메트리 경로 미확보** — 경로 A는 지상 전용. T900 Pro 등 [미구매 항목](../../airframes/striver-mini-vtol/README.md#보유-사양-메모-shade-기체--pnp).
- **비행 중 링크 신뢰성 미검증** — 지상 테스트만 완료.

## 관련 문서

| 문서 | 이 문서와의 관계 |
|---|---|
| [Raspberry Pi 5 "raspb1"](../../components/companion/raspberry-pi-5/README.md) | 브리지 구현·배선·systemd 유닛 상세 |
| [Pixhawk 6C Mini](../../components/fc/holybro-pixhawk-6c-mini/README.md) | FC 포트/파라미터/Actuators 설정 |
| [Striver Mini VTOL](../../airframes/striver-mini-vtol/README.md) | 기체 전체 구성 계통도 |
| [PM08-CAN](../../components/power/holybro-pm08-can/README.md) | 배터리 텔레메트리 소스 |
| [RadioMaster RP4TD-M](../../components/receivers/radiomaster-rp4td-m/README.md) | TELEM1 의 RC 수신기 (MAVLink over ELRS) |
