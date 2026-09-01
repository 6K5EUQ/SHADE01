# 박서 텔레메트리 화면 — `shade.lua`

[Boxer](README.md) 화면에 SHADE 비행값을 한 판에 띄우는 EdgeTX 텔레메트리 스크립트. 정본은
이 폴더의 [`shade.lua`](shade.lua) 이고, 카드에는 `SD:/SCRIPTS/TELEMETRY/shade.lua` 로 넣는다.

관련: [Boxer](README.md) · [스위치 매핑](switch-mapping.md) · [ELRS 배터리 텔레메트리 수정](elrs-battery-telemetry-fix.md) · [SHADE01 개요](../../../README.md)

## 화면

```
┌──────────────┬──────────────┐
│    STAB      │      99      │  ← 반전 배너: 비행모드 / 링크품질(LQ)
├──────────────┼──────────────┤
│ Cur     3.4  │ Bat      87  │
│ Spd     1.5  │ Alt      12  │
│ Tmp      31  │ Sat      14  │
└──────────────┴──────────────┘
```

| 칸 | 센서 | 뜻 |
|---|---|---|
| Cur | `Curr` | 현재 전류 (A) |
| Bat | `Bat%` | 배터리 잔량 (%) |
| Spd | `GSpd` | 대지속도 (m/s) |
| Alt | `GAlt` | 고도 (m) |
| Tmp | `Temp` | 온도 (℃) |
| Sat | `Sats` | GPS 위성 수 |
| 배너 좌 | (CH6) | 비행모드 — 텔레메트리가 아니라 **채널값에서 읽는다** |
| 배너 우 | `RQly` | 링크 품질 |

비행모드를 CRSF 텔레메트리(`FM` 센서)가 아니라 CH6 채널값에서 읽는 이유는
[비행모드 6단 구성](../../../README.md) 참조 — S3 6단 로터리가 CH6 에 물려 있고, FC 는
MAVLink 를 쓰기 때문에 채널값이 더 확실하다. 구간 표는 `shade.lua` 상단 `MODES` 테이블.

## ⚠️ 함정 1 — 소수 센서를 정수로 찍으면 0 으로 보인다

**증상**: 전류 칸이 항상 `0`. 센서도 배선도 멀쩡한데 값이 안 뜬다.

**원인**: `MODELS/model00.yml` 의 `telemetrySensors:` 를 보면 아래 센서들이 `prec: 1`,
즉 **소수 1자리 센서**다.

| 센서 | prec | |
|---|---|---|
| `Curr` `GSpd` `Temp` `RxBt` | **1** | 소수 1자리 |
| `Bat%` `GAlt` `Sats` `RQly` `Capa` | 0 | 정수 |

이걸 `string.format("%d", v)` 로 찍으면 지상 대기 상태의 **0.4A 가 `0` 이 된다**. 센서가
죽은 것처럼 보이지만 실제로는 반올림 결과다. EdgeTX 기본 텔레메트리 화면은 소수를 표시하니
거기서는 정상으로 보이는 것도 진단을 어렵게 한다.

**해결**: 값이 작을 때만 소수를 붙인다 (`shade.lua` 의 `fmt()`).

```lua
if v > -10 and v < 10 then return string.format("%.1f", v) end
return whole(v)
```

10 이상에서 소수를 떼는 건 자리 폭 때문이다 — 아래 "폭 예산" 참조.

**덤**: 최신 Lua 는 `%d` 에 비정수를 넣으면 `number has no integer representation` 으로
**죽는다**. EdgeTX 의 Lua 5.2 는 조용히 넘어가지만 펌웨어가 올라가면 터지므로,
`whole()` 에서 `math.floor` 로 반올림한 뒤 포맷한다.

## ⚠️ 함정 2 — `.luac` 을 안 지우면 옛 화면이 나온다

EdgeTX 는 바이트코드를 우선 로드하고, 스크립트를 실행할 때마다 `.lua` 옆에 `.luac` 을
새로 굽는다. `.lua` 만 덮어쓰면 **수정 전 화면이 그대로 뜬다.**

카드에 넣을 때는 항상 짝으로:

```bash
cp shade.lua /media/$USER/<SD>/SCRIPTS/TELEMETRY/shade.lua
rm -f /media/$USER/<SD>/SCRIPTS/TELEMETRY/shade.luac
sync
```

## 화면 제약 — 128×64 흑백

Boxer LCD 는 **128×64 흑백**이다. 컬러 기종이 아니다. 헷갈리면 SD 카드에 `IMAGES/`·`THEMES/`
폴더가 있는지 보면 된다 — 없으면 흑백기다. `RADIO/radio.yml` 의 `backlightColor` 는
백라이트 LED 색이지 화면 색이 아니다.

### 폰트 실측 (폭 × 높이, px)

| 플래그 | 크기 |
|---|---|
| `SMLSIZE` | 5 × 6 |
| (플래그 없음) | 8 × 8 |
| `MIDSIZE` | 8 × 12 |
| `DBLSIZE` | 16 × 16 |

### 폭 예산 — 열 하나가 64px

라벨과 값을 한 줄에 넣으면 64px 안에서 나눠 써야 한다.

| 조합 | 폭 | |
|---|---|---|
| 기본폰트 라벨 3글자 + `MIDSIZE` 값 4자리 | 24 + 32 = 56 | ✅ |
| 기본폰트 라벨 4글자 + `MIDSIZE` 값 4자리 | 32 + 32 = 64 | ❌ 고도 `1234` 와 충돌 |
| 기본폰트 라벨 3글자 + `DBLSIZE` 값 3자리 | 24 + 48 = 72 | ❌ |

**`DBLSIZE` 값과 라벨은 공존할 수 없다.** 라벨을 포기하면 값을 크게 쓸 수 있지만, 그러면
어느 칸이 무슨 값인지 알아볼 수 없다 — 실제로 그 버전을 만들었다가 되돌렸다.

라벨을 3글자로 줄인 것(`Curr`→`Cur`, `GSpd`→`Spd`)도 이 예산 때문이다.

### 값이 예외적으로 길어질 때

고도 `-1500` 처럼 5글자가 되면 값이 라벨을 침범한다. 그 행의 **라벨만** `SMLSIZE` 로
내려서 피한다 (`row()` 안의 분기). 평상시에는 발동하지 않는다.

## 레이아웃 원칙 — 값의 오른쪽 끝을 못박는다

라벨은 왼쪽 고정, 값은 **오른쪽 끝을 고정 x 좌표에 맞춰 우측정렬**한다.

| | 좌측 열 | 우측 열 |
|---|---|---|
| 라벨 시작 x | 1 | 65 |
| 값 끝 x | 61 | 125 |

값+단위를 묶어서 가운데 정렬하면 **자릿수가 바뀔 때마다 통째로 좌우로 흔들린다.**
`18A` → `118A` 로 넘어가는 순간 위치가 밀리는데, 비행 중에는 값이 계속 변하므로 화면이
끊임없이 떨린다. 실제로 그렇게 만들었다가 "조잡하다"고 퇴짜맞았다.

## 검증 — 조종기 없이 화면을 미리 본다

카드에 넣고 조종기에서 확인하는 왕복은 느리다. `lcd` 스텁을 만들어 PC 에서
`drawText` 좌표·폭을 기록하면 잘림과 겹침을 미리 잡을 수 있다.

핵심은 **최악값 케이스**를 같이 돌리는 것:

| 케이스 | 값 |
|---|---|
| 지상 대기 | `Curr=0.4` — 소수 함정이 여기서 드러난다 |
| 호버 | `Curr=3.4` |
| 순항 | `Curr=18.6 GAlt=120` |
| 최악 | `Curr=123.4 GAlt=1234 Capa=19999` — 자리 넘침 |
| 무신호 | 전 센서 nil — 전부 `--` |
| 음수 고도 | `GAlt=-1500` — 5글자, 라벨 침범 |

자릿수를 1 → 2 → 3 으로 바꿔가며 값의 오른쪽 끝 x 좌표가 고정되는지 보면 "흔들림"도
사전에 잡힌다. 문법만 보는 `luac -p shade.lua` 도 같이 돌린다.

## 카드에 넣기

```bash
# 마운트 (자동 마운트 안 될 때)
udisksctl mount -b /dev/sdb1

SD=/media/$USER/<라벨>
cp shade.lua "$SD/SCRIPTS/TELEMETRY/shade.lua"
rm -f "$SD/SCRIPTS/TELEMETRY/shade.luac"   # 필수 — 함정 2
sync
udisksctl unmount -b /dev/sdb1
```

조종기에서 USB 연결 시 **USB Storage (SD)** 모드를 골라야 카드가 붙는다. Joystick/Serial
모드로는 파일이 안 보인다. 카드가 붙으면 `lsusb` 에 `0483:5720 STMicroelectronics Mass
Storage Device` 로 뜬다.

화면은 모델의 텔레메트리 화면 설정에서 `shade` 스크립트를 지정해 띄운다.
