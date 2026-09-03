# QGroundControl 직접 빌드 (v5.1.4 + VTOL 패치)

공식 AppImage 는 VTOL 기체에서 **미션 예상시간이 틀리고 기종 이름이 잘못 뜬다**.
세 곳을 고쳐 빌드한다. 한국어 번역은 넣지 않는다 (문자열이 깨진다).

## 왜 재빌드인가

QGC 는 C++ 단일 실행파일이고 QML 까지 Qt 리소스로 컴파일해 넣는다. 고칠 곳이
전부 C++/QML 소스라 **런타임 설정이나 부분 패치로는 안 된다.**

## 고친 것

패치: [`shade01-vtol-fixes.patch`](shade01-vtol-fixes.patch) (upstream v5.1.4 기준)

### 1. 미션 시간 — 속도 필드가 무시된다

`src/MissionManager/SpeedSection.cc:48`

```cpp
if (available && (... ->multiRotor() || ... ->fixedWing())) {   // VTOL 이 없다
```

VTOL 이 조건에서 빠져 `setAvailable(true)` 가 조용히 무시된다. 그 결과
`MissionSettingsItem::specifiedFlightSpeed()` 가 항상 NaN 을 돌려주고,
`MissionFlightStatusCalculator.cc:227` 의 `if (!qIsNaN(newSpeed))` 가 안 걸려
**속도 오버라이드 경로 전체가 죽는다.** Mission Start 패널에서 속도를 바꿔도
계산에 도달하지 못한다.

→ 조건에 `|| vtol()` 추가.

### 2. 미션 시간 — 재계산이 안 걸린다

`src/MissionManager/MissionController.cc:1633`

```cpp
connect(_managerVehicle, &Vehicle::defaultCruiseSpeedChanged, ...);
```

시그널은 `_managerVehicle` 에 연결돼 있는데, 실제 계산은
`MissionFlightStatusCalculator.cc:25-26` 에서 **`_controllerVehicle`** 값을 읽는다.
기체가 연결되면 이 둘은 서로 다른 객체라 (`PlanMasterController.cc:125`)
속도가 바뀌어도 재계산 시그널이 오지 않는다.

→ `_controllerVehicle` 에도 연결.

### 3. 기종 오인식 + 라벨 겹침

`src/PlanView/PlanInfoEditor.qml:92`

FC 는 **MAV_TYPE 22 = `MAV_TYPE_VTOL_FIXEDROTOR`** 를 정확히 보낸다
(PX4 `rc.vtol_defaults:10-11`). "hover 와 cruise 용 로터가 분리된 VTOL,
동체와 날개는 모든 비행 단계에서 수평" — 이 기체 그대로다.

그런데 QGC 가 받아서 뭉갠다:

```cpp
// QGCMAVLink.h:35
static constexpr const VehicleClass_t VehicleClassVTOL = MAV_TYPE_VTOL_TAILSITTER_QUADROTOR;  // = 20
```

7 종 VTOL MAV_TYPE(19~25) 을 클래스 하나로 묶는데 그 값이 하필 20(Tailsitter) 이다.
연결 시 `PlanMasterController.cc:130` 이 이 값을 offline 설정에 쓰고, 그게
`_controllerVehicle` 의 타입이 되어 **22 → 20 으로 바뀐다.** 그래서 패널에
"Quad-rotor VTOL using a V-shaped quad config ... Tailsitter" 가 뜬다.

같은 문자열이 겹침의 원인이기도 하다 — 76 자인데 `QGCLabel` 에 `elide` 도
`wrapMode` 도 없고 `Layout.minimumWidth` 도 없어 RowLayout 이 압축하지 못한다.

→ 라벨이 **연결된 기체의 실제 타입**을 읽게 하고, `elide: Text.ElideRight` +
`Layout.minimumWidth/preferredWidth: 0` 을 준다.

⚠️ `vehicleClass()` 구조 자체는 건드리지 않았다. 파급이 크다. **표시만** 고쳤고
미션 계획 로직에는 영향이 없다.

## 빌드

### 준비 (최초 1회)

```bash
sudo apt-get install -y build-essential ninja-build cmake \
  libgl1-mesa-dev libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-xinput0 \
  libsdl2-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
  libgstreamer-plugins-good1.0-dev patchelf fuse libfuse2
```

⚠️ **Ubuntu 의 `qt6-base-dev` 는 6.4.2 라 쓸 수 없다.** v5.1.4 는 Qt 6.11.1 을
요구한다 (`.github/build-config.json` 의 `qt.version`). `aqtinstall` 로 받는다:

```bash
~/SHADE01/venv-ardupilot/bin/pip install aqtinstall
~/SHADE01/venv-ardupilot/bin/python -m aqt install-qt linux desktop 6.11.1 linux_gcc_64 \
  -O ~/Qt \
  -m qtgraphs qtlocation qtpositioning qtspeech qtmultimedia qtserialport \
     qtimageformats qtshadertools qtconnectivity qtquick3d qtsensors qtscxml \
     qtwebsockets qthttpserver
```

약 1.9 GB. **모듈 목록은 버전마다 다르다** — `.github/build-config.json` 의
`qt.modules` 를 그대로 쓴다.

### 소스 + 패치

```bash
git clone --recursive --depth 1 --branch v5.1.4 \
  https://github.com/mavlink/qgroundcontrol.git ~/qgc-build
cd ~/qgc-build
git checkout -b shade01-vtol-fixes
git apply /path/to/SHADE01/gcs/qgroundcontrol/shade01-vtol-fixes.patch
```

### 빌드

```bash
cd ~/qgc-build
~/Qt/6.11.1/gcc_64/bin/qt-cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
ninja -C build -j 14
```

첫 구성에서 CPM 이 의존성(LibArchive, geographiclib, Shapelib, libexif,
ulog_cpp, valijson …)을 받으므로 시간이 걸린다.

## 버전 확인

빌드할 태그가 요구하는 Qt 는 소스에서 직접 읽는다:

```bash
python3 -c "import json; print(json.load(open('.github/build-config.json'))['qt'])"
```

| QGC | Qt |
|---|---|
| v5.0.8 | 6.8.3 |
| v5.1.0 ~ v5.1.4 | **6.11.1** |

## 설치 — 홈에 풀어 쓴다

`ninja -C build qgc-package` 가 `.deb` 를 만든다. 시스템에 넣지 않고 홈에 풀어 쓰면
sudo 가 필요 없고, 기존 AppImage 를 남겨둔 채 되돌아갈 수 있다.

```bash
dpkg-deb -x build/QGroundControl_5.1.4-*_amd64.deb /tmp/qgcpkg
rm -rf ~/SHADE01/qgc-5.1.4 && mkdir -p ~/SHADE01/qgc-5.1.4
cp -a /tmp/qgcpkg/usr/. ~/SHADE01/qgc-5.1.4/
~/SHADE01/qgc-5.1.4/bin/QGroundControl --version    # v5.1.4 가 나와야 한다
```

⚠️ **`.deb` 를 만들려면 `gstreamer1.0-plugins-bad` 가 깔려 있어야 한다.** 없으면
CPack 이 `missing required plugins in lib/gstreamer-1.0: videoparsersbad` 로 멈춘다.
설치한 뒤에는 **cmake 를 다시 구성해야** 한다 — 번들할 플러그인 목록이 구성 시점에
고정되기 때문이다.

### 메뉴·아이콘으로 띄우기

터미널 런처(`gcs/qgroundcontrol/qgc`)만으로는 데스크톱 메뉴가 안 바뀐다. 메뉴는 별도
`.desktop` 을 읽으므로 거기도 고쳐야 **여전히 옛 버전이 뜨는 일**이 없다.

```bash
cp ~/.local/share/applications/qgroundcontrol.desktop{,.bak.5.0.8}
sed -i "s|^Exec=.*|Exec=env QT_QPA_PLATFORM=xcb $HOME/qgc-5.1.4/bin/QGroundControl|" \
  ~/.local/share/applications/qgroundcontrol.desktop
sed -i "s|^Icon=.*|Icon=QGroundControl|" ~/.local/share/applications/qgroundcontrol.desktop

mkdir -p ~/.local/share/icons/hicolor/{256x256,scalable}/apps
cp ~/SHADE01/qgc-5.1.4/share/icons/hicolor/256x256/apps/QGroundControl.png \
   ~/.local/share/icons/hicolor/256x256/apps/
cp ~/SHADE01/qgc-5.1.4/share/icons/hicolor/scalable/apps/QGroundControl.svg \
   ~/.local/share/icons/hicolor/scalable/apps/
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor
update-desktop-database ~/.local/share/applications
```

⚠️ `Icon=` 은 **대문자 `QGroundControl`** 이다. 기존 항목은 소문자 `qgroundcontrol` 을
가리키는데 새 아이콘 파일명은 대문자라 안 맞는다.

⚠️ 메뉴에 옛 항목이 남아 보이면 로그아웃 후 재로그인한다 (GNOME 은 `Alt+F2` → `r`).

되돌리려면 `Exec=` 한 줄만 AppImage 경로로 바꾸면 된다. 백업이 옆에 있다.

### 다른 PC 로 옮기기

같은 배포판·아키텍처(Ubuntu 24.04.4 / x86_64)면 `.deb` 를 그대로 옮겨 같은 절차를 쓴다.
2026-09-02 에 `ku` 에서 빌드한 것을 `rim3` 로 옮겨 두 대가 같은 바이너리를 쓴다.

```bash
scp build/QGroundControl_5.1.4-*_amd64.deb rim3@100.117.47.105:/tmp/
```

## 함정

### 기존 AppImage 를 먼저 지우지 마라

새 빌드가 실기로 검증될 때까지 `~/SHADE01/Applications/QGroundControl.AppImage` 를 남겨둔다.
문제가 생기면 그대로 되돌아갈 수 있어야 한다.

### v5.0.8 → v5.1.4 는 1 년치 변경이다

미션 시간 외에도 UI·동작이 달라진다. 실비행 전에 **미션 업로드/다운로드와
파라미터 읽기가 정상인지** 확인한다.

### UDP 14550 은 하나만 잡는다

QGC 가 켜져 있으면 `mav_bridge` 나 분석 스크립트가 붙지 못한다. 반대도 같다.

```bash
ss -ulnp | grep 14550
```
