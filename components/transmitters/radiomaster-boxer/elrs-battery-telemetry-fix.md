# ELRS 커스텀 펌웨어 — DroneCAN 배터리 텔레메트리 수정

Boxer 내장 ELRS TX 펌웨어를 1줄 패치해 **조종기 화면의 배터리 텔레메트리를 복구**한 작업 기록. 해결일 **2026-08-22**.

관련: [Boxer 조종기](README.md) · [RP4TD-M 수신기](../../receivers/radiomaster-rp4td-m/README.md) · [PM08-CAN](../../power/holybro-pm08-can/README.md) · [BRINGUP.md](../../../BRINGUP.md)

## 증상

MAVLink over ELRS 전환 후, 조종기 텔레메트리 화면에서 **배터리 4개 센서만 값이 안 떴다**.

| 센서 | CRSF 프레임 | 상태 |
|---|---|---|
| `1RSS` `2RSS` `RQly` `RSNR` `TPWR` `TRSS` `TQly` `TSNR` | `0x14` Link Statistics | ✅ 정상 |
| `GPS` `GSpd` `Hdg` `GAlt` `Sats` | `0x02` GPS | ✅ 정상 |
| `Ptch` `Roll` `Yaw` | `0x1E` Attitude | ✅ 정상 |
| `FM` | `0x21` Flight Mode | ✅ 정상 |
| `Temp` | `0x10D` Baro/Vario | ✅ 정상 |
| **`RxBt` `Curr` `Capa` `Bat%`** | **`0x08` Battery Sensor** | ❌ **값 없음** |

**결정적 단서: 같은 링크인데 노트북 QGC에서는 배터리가 정상 표시됐다.** 조종기 백팩 WiFi로 붙은 QGC에 배터리가 보이므로, 데이터는 조종기 안까지 도달하고 있었다. 즉 링크·FC 문제가 아니라 **조종기 내부의 MAVLink→CRSF 변환 문제**로 범위가 좁혀졌다.

## 원인

### 1. PX4가 DroneCAN 배터리 ID에 노드 ID를 그대로 쓴다

`PX4-Autopilot/src/drivers/uavcan/sensors/battery.cpp:131`

```c
_battery_status[instance].id = msg.getSrcNodeID().get();
```

[PM08-CAN](../../power/holybro-pm08-can/README.md)은 DroneCAN 파워모듈이고 노드 ID가 **124**다. 따라서 MAVLink `BATTERY_STATUS.id = 124`로 송신된다.

이 값을 바꾸는 파라미터는 **없다** (하드코딩). DroneCAN 노드 ID는 규격상 1~127이라 0으로 만들 수도 없다.

### 2. ELRS가 배터리 인스턴스 0만 변환한다

`ExpressLRS/src/lib/MAVLink/MAVLink.cpp:112` (4.1.0 기준)

```c
case MAVLINK_MSG_ID_BATTERY_STATUS: {
    mavlink_battery_status_t battery_status;
    mavlink_msg_battery_status_decode(&msg, &battery_status);
    if (battery_status.id != 0) {
        break;                    // ← 124이므로 여기서 탈출
    }
    ...                           // CRSF 0x08 프레임 생성 코드에 도달 못 함
```

`id != 0`이면 CRSF 배터리 프레임(`0x08`)을 만들지 않고 빠져나간다. 아날로그 파워모듈은 `id=0`이라 문제가 없지만, **DroneCAN 파워모듈은 전부 차단된다.**

GPS·자세·비행모드 변환에는 이런 ID 검사가 없어서 정상 통과한다 — 배터리 4개만 죽은 이유.

### 3. 우회 경로 없음

- **`SYS_STATUS` 폴백 없음** — ELRS는 `SYS_STATUS`를 아예 처리하지 않는다 (소스 전체 검색 결과 핸들러 부재). 배터리 경로는 `BATTERY_STATUS` 단일.
- **Yaapu passthrough도 같은 게이트 뒤** — `ap_send_crsf_passthrough_single(destination, 0x5003, ...)`(`MAVLink.cpp:138`)가 `break` 다음 줄에 있어 함께 차단된다. Yaapu 스크립트를 깔아도 배터리는 안 나온다.

### 실측 검증

FC USB 직결(`/dev/ttyACM0`)에서 pymavlink로 확인:

```
GPS_RAW_INT      srcSystem=1 srcComponent=1   → ELRS gate 'compid != 1' : PASS
ATTITUDE         srcSystem=1 srcComponent=1   → PASS
HEARTBEAT        srcSystem=1 srcComponent=1   → PASS
BATTERY_STATUS   srcSystem=1 srcComponent=1   → PASS
BATTERY_STATUS.id = 124                       → gate 'id != 0' : >>> BLOCKED <<<
```

FC가 내보내는 배터리 값 자체는 정상이었다:

```
SYS_STATUS      24125 mV / 56 cA / 95%
BATTERY_STATUS  24.125V / 0.54A / 249mAh 소모 / 94%
```

## 조사 중 배제된 가설

기록해 둔다 — 같은 증상에서 헛다리 짚기 쉬운 지점들이다.

| 가설 | 배제 근거 |
|---|---|
| `MAV_2_CONFIG=101`이 `MAV_0_CONFIG=101`과 충돌해 스트림이 반쪽만 나감 | `RADIO_STATUS`가 90.9Hz로 수신됨 → TELEM1 MAVLink 인스턴스 정상 기동 중. 중복이지만 무해 |
| `BATTERY_STATUS` 0.5Hz 저레이트 때문에 EdgeTX가 stale 처리 | 노트북 QGC에서는 같은 0.5Hz로 정상 표시됨. `SET_MESSAGE_INTERVAL`로 5.1Hz까지 올려봐도 조종기 화면은 변화 없음 |
| `RC_CRSF_PRT_CFG=0`이라 PX4가 CRSF 배터리 프레임을 안 만듦 | 이 경로로 고치면 MAVLink over ELRS가 끊겨 **노트북 QGC 링크가 죽는다**. 운용 중인 구성을 깨는 방식이라 채택 불가 |
| RX 펌웨어(3.5.6)와 TX(4.1.0) 버전 비호환 | **플래시 전에는 바인딩이 정상 동작했다** → 버전 조합 자체는 호환. 원인이 될 수 없음 |

마지막 항목이 특히 중요하다. **"펌웨어 교체 전에는 잘 됐다"는 사실 하나로 변경되지 않은 모든 구성요소를 용의선상에서 제외할 수 있다.**

## 패치

`ExpressLRS/src/lib/MAVLink/MAVLink.cpp` — 첫 수신 배터리 인스턴스를 기억해 그것만 통과시킨다.

```diff
                 mavlink_msg_battery_status_decode(&msg, &battery_status);
-                if (battery_status.id != 0) {
+                // Accept the first battery instance we see and stick to it.
+                // DroneCAN power modules report the node ID as the battery id
+                // (e.g. 124), so a hardcoded 0 would drop them entirely.
+                static uint8_t primary_batt_id = 0xFF;
+                if (primary_batt_id == 0xFF) {
+                    primary_batt_id = battery_status.id;
+                }
+                if (battery_status.id != primary_batt_id) {
                     break;
                 }
```

**게이트를 통째로 지우지 않은 이유**: 배터리가 2개 이상인 기체에서 값이 교대로 덮어써지는 것을 막기 위함. 이 방식은 DroneCAN(124)·아날로그(0) 양쪽에서 동작하므로 나중에 파워모듈을 바꿔도 유효하다.

> 상류(upstream) 이슈로 제기할 가치가 있는 버그다. DroneCAN 파워모듈 사용자 전원이 겪는 문제이며, ELRS 4.1.0 시점에도 수정되지 않았다.

## 빌드

```bash
cd ~/ExpressLRS/src
pio run -e Unified_ESP32_2400_TX_via_WIFI
# 산출물: .pio/build/Unified_ESP32_2400_TX_via_WIFI/firmware.bin
```

| 항목 | 값 |
|---|---|
| ELRS 소스 | 4.1.0 (`5909f771`, master) |
| 빌드 타겟 | `Unified_ESP32_2400_TX_via_WIFI` |
| 산출물 | `firmware.bin` 1,622,288 bytes |
| md5 | `d6d7b8e2dbe0f60dadee9183c8feeb34` |
| Flash | 82.0% (1,613,001 / 1,966,080 bytes) |
| RAM | 21.6% (70,768 / 327,680 bytes) |
| 빌드 시간 | 64.5초 |

**패치 반영 검증** — 심볼 테이블에 static 변수 존재 확인:

```bash
xtensa-esp32-elf-nm firmware.elf | grep primary_batt
# 3ffbe358 d _ZZ29convert_mavlink_to_crsf_telem11crsf_addr_ePhhE15primary_batt_id
```

`.data` 섹션(`d`)에 배치 = 초기값 `0xFF`로 정상 컴파일됨.

### PlatformIO 설치 (이 PC 기준)

`~/.platformio`에 패키지 캐시(`framework-arduinoespressif32`, `toolchain-xtensa-esp32`, `tool-esptoolpy`, `tool-scons`)는 있었으나 **실행 파일이 없어** 재설치가 필요했다.

```bash
/home/ku/venv-ardupilot/bin/pip install platformio    # 6.1.19
/home/ku/venv-ardupilot/bin/pio run -e Unified_ESP32_2400_TX_via_WIFI
```

## 플래시

Boxer WiFi 웹UI 경유:

1. Boxer ELRS Lua → **WiFi Connectivity** → **Enable WiFi**
2. PC를 `ExpressLRS TX` AP에 접속 (비번 `expresslrs`)
3. 브라우저 `http://10.0.0.1` → **Update Firmware** → `.bin` 업로드
4. 재부팅

⚠️ 업로드 중 전원이 끊기지 않도록 조종기 배터리 잔량을 먼저 확인할 것.

**되돌리기**: ELRS Configurator로 공식 4.1.0 재플래시, 또는 같은 웹UI에 공식 펌웨어 업로드.

## ⚠️ 플래시 후 바인딩 재설정 필요

CLI 비대화형 빌드는 **바인딩 문구가 비어 있는(bare) 펌웨어**를 만든다. 빌드 로그에 명시된다:

```
Not running in an interactive shell, leaving the firmware "bare".
You will be able to configure the hardware via the web UI on the device.
```

공식 ELRS Configurator는 바인딩 문구를 **컴파일 타임에 펌웨어에 박아 넣지만**, CLI 빌드에는 그 단계가 없다. 따라서 플래시 직후 TX는 바인딩 정보를 잃고 **RX와 자동으로 붙지 않는다.**

**RX는 건드릴 필요 없다** — Binding storage가 `Persistent`라 UID를 유지하고 있다.

### 복구 방법

TX 웹UI(`http://10.0.0.1`)의 Binding Phrase 섹션에서 **RX의 Bound UID를 직접 입력**한다.

```
Bound UID: 45,5,9,157,112,199
```

이 값은 RX 웹UI 하단 `Bound` 배지 아래에 표시된다 ([webui-rx-binding-storage.jpg](../../receivers/radiomaster-rp4td-m/images/webui-rx-binding-storage.jpg)).

> 📌 **UID를 문서에 기록해 둔 이유** — 바인딩은 phrase 방식으로 설정했으나 phrase 문자열을 어디에도 남기지 않았다. 커스텀 펌웨어를 다시 빌드·플래시할 때마다 이 복구 절차가 필요하므로 UID를 명시해 둔다. phrase를 알고 있다면 `-DMY_BINDING_PHRASE="..."`를 빌드에 넣어 이 단계를 생략할 수 있다.

## 결과

✅ **조종기 화면과 QGC 양쪽에서 배터리 정상 표시** (2026-08-22 확인).

`RxBt` `Curr` `Capa` `Bat%` 4개 센서가 모두 살아났고, 노트북 QGC 링크도 영향 없이 유지된다.

## 유지보수 주의

- **ELRS 공식 업데이트 시마다 재패치 필요.** 커스텀 빌드이므로 Configurator로 공식 펌웨어를 올리면 수정이 사라진다.
- **RX는 이 패치와 무관.** 변환은 TX에서만 일어난다 — `tx_main.cpp:1544`가 `convert_mavlink_to_crsf_telem()`의 유일한 호출부이며, `rx_main.cpp`에는 해당 코드가 없다. RX 펌웨어는 공식 3.5.6 그대로 두면 된다.
- 재플래시할 때마다 위 **바인딩 재설정**이 반복된다.

## 🔶 확인 필요

- **바인딩 phrase 문자열 미기록** — UID로 복구는 가능하나, phrase를 알면 빌드에 박아 넣어 재설정 자체를 없앨 수 있다.
- **상류 이슈 미제기** — ELRS 저장소에 DroneCAN 배터리 ID 문제를 보고하면 이후 공식 펌웨어에서 해결될 수 있다.
- **`MAV_2_CONFIG=101` 중복 미정리** — `MAV_0_CONFIG`와 같은 TELEM1을 가리킨다. 현재 무해하나 의도된 설정인지 불명. 노트북 2대 운용 구성과 관련 있는지 확인 후 정리 검토.
