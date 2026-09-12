# 펌웨어 빌드 — SHADE01 전용 v1.17.0

**`.px4` 바이너리는 git 에 안 들어간다** (`.gitignore`). 이 문서가 정본이고,
여기 적힌 대로 하면 같은 것이 다시 나온다.

## 왜 커스텀 빌드인가

두 가지 때문이다.

**① dataman 미션 실패** — 2026-09-11 야외에서 미션 3회 전부 실패했다.
`dataman_client timeout after 5000 ms!` 로 미션 항목을 못 읽었다.
분석은 [`flights/2026-09-11-mission-failure.md`](../../flights/2026-09-11-mission-failure.md).

**② 플래시 98.3%** — 안 쓰는 모듈이 기본으로 켜져 있었다.

## 결과

| | 표준 v1.17.0 | **SHADE01** |
|---|---|---|
| 플래시 | 1926272 B (97.98%) | **1763632 B (89.70%)** |
| 여유 | 33 KB | **156 KB** |
| dataman 수정 | 없음 | **2개 적용** |

## 환경 (rim3, sudo 없이 홈에 설치)

`sudo` 에 비밀번호가 걸려 있어 시스템 패키지를 못 깐다. 전부 `~/opt` 에 넣었다 —
`rm -rf ~/opt ~/PX4-Autopilot` 로 깨끗이 되돌아간다.

```bash
# ARM 툴체인 13.2.Rel1  🔴 디렉토리명이 Rel1 (대문자 R) 이다
curl -fL -o ~/opt/arm-toolchain.tar.xz \
  https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-x86_64-arm-none-eabi.tar.xz
cd ~/opt && xz -t arm-toolchain.tar.xz && tar xf arm-toolchain.tar.xz

# ninja
curl -fsSL -o /tmp/ninja.zip \
  https://github.com/ninja-build/ninja/releases/download/v1.11.1/ninja-linux.zip
unzip -oq /tmp/ninja.zip -d ~/opt/bin && chmod +x ~/opt/bin/ninja

# 빌드 전용 venv — 🔴 SHADE01 의 .venv 를 쓰지 마라
#    PX4 는 numpy·pandas·sympy 를 끌고 온다. 파싱 도구가 쓰는 .venv 와 섞으면 안 된다.
#    python3-venv 가 없어 ensurepip 이 안 돈다 → --without-pip 로 우회한다.
python3 -m venv --without-pip ~/opt/px4-venv
curl -fsSL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
~/opt/px4-venv/bin/python /tmp/get-pip.py
~/opt/px4-venv/bin/pip install -r ~/PX4-Autopilot/Tools/setup/requirements.txt
~/opt/px4-venv/bin/pip install "setuptools<81"   # pkg_resources — 아래 함정 참조
```

환경 스크립트 `~/opt/px4env.sh`:

```bash
export PATH="$HOME/opt/arm-gnu-toolchain-13.2.Rel1-x86_64-arm-none-eabi/bin:$HOME/opt/bin:$PATH"
export PATH="$HOME/opt/px4-venv/bin:$PATH"
```

## 소스

```bash
git clone --recursive https://github.com/PX4/PX4-Autopilot.git ~/PX4-Autopilot
cd ~/PX4-Autopilot
git checkout v1.17.0
git submodule update --init --recursive     # 🔴 이걸 빼먹지 마라 (아래 함정)
```

🔴 **우리가 쓰던 펌웨어 커밋 `d6f12ad1c4f7` 은 `v1.17.0` 태그 그 자체다.**
`git describe --tags d6f12ad1c4f7` 이 `v1.17.0` 을 낸다 — **소스 개조가 없었다.**
"커스텀" 이라 불린 것은 보드 설정에 `crsf_rc` 를 얹은 것뿐이었다.

## 적용한 수정 2개

브랜치 `shade01-v1.17.0-dataman` (v1.17.0 기준):

| 커밋 | 내용 | 방법 |
|---|---|---|
| [`5fd7fed8d8`](https://github.com/PX4/PX4-Autopilot/commit/5fd7fed8d8) | 큐에 남은 응답 제거 | `git cherry-pick -x` 성공 |
| [`e9c1c83e35`](https://github.com/PX4/PX4-Autopilot/commit/e9c1c83e35) | dataman 스택 1420 → 2000 | **손으로 적용** |

**스택 수정을 손으로 한 이유:** upstream 은 `#ifdef CONFIG_FS_LITTLEFS` 조건문을
지우는 변경인데 v1.17.0 에는 그 조건문이 없다. 그래서 체리픽이 충돌한다.
결과값(2000)은 같다.

`5fd7fed8d8` 의 주석이 우리 증상을 그대로 서술한다:

> Drain queued replies first so a response from an aborted or **timed-out**
> operation cannot be matched to the next request.

우리 로그의 `5000ms → 500ms` 연쇄 타임아웃이 이 패턴이다.

**넣지 않은 것:** [`bd0b15d434`](https://github.com/PX4/PX4-Autopilot/commit/bd0b15d434)
(DO_JUMP 를 저장 실패로 오보하지 않음). 우리 미션은 이륙·호버·착륙 3항목이라
DO_JUMP 가 없다. 변경을 최소로 둔다.

## 보드 설정 — `boards/px4/fmu-v6c/shade01.px4board`

뺀 것은 **전부 파라미터로 "안 쓴다" 를 확인한 것만**이다. 짐작으로 뺀 것이 없다.

| 모듈 | 크기 | 확인한 값 |
|---|---|---|
| uXRCE-DDS (ROS2) | 63.3 KB | `UXRCE_DDS_CFG=0` |
| SIH 시뮬레이터 | 22.1 KB | `SYS_HITL=0` — 실기 전용 |
| 온도보상 | 20.9 KB | `TC_A_ENABLE=TC_B_ENABLE=TC_G_ENABLE=0` |
| Gimbal | 15.5 KB | `MNT_MODE_IN=-1` |
| Septentrio GNSS | — | 일반 GPS 를 쓴다 |
| `crsf_rc` | — | `RC_CRSF_PRT_CFG=0`·`RC_CRSF_TEL_EN=0`, 전 경로 MAVLink |

### 🔴 PX4IO 도 빼지 마라 — AUX 서보 3개가 여기 달려 있다

한 번 뺐다가 되돌렸다. `SYS_USE_IO` 파라미터가 없어서 "v6c 는 IO 보드가 없다" 고
판단했는데 **틀렸다.** PX4IO 드라이버가 **AUX 출력 자체를 제공**한다.

빼면 `PWM_AUX_*` **52개가 통째로 사라진다.** 실제로 쓰고 있다:

```
PWM_AUX_FUNC1=204  PWM_AUX_FUNC2=205(러더)  PWM_AUX_FUNC3=203
PWM_AUX_DIS2=1500     러더 arm 튐을 잡은 값 (FC_CHANGELOG 9/5 15:12)
PWM_AUX_TIM0~2=100    아날로그 서보용 (FC_CHANGELOG 9/5 15:50)
```

**파라미터가 "없다" 는 것은 "안 쓴다" 의 근거가 못 된다.** 다른 이름으로 있을 수
있다. 빌드 산출물 ↔ 백업 diff (아래 「플래시 전 관문」) 가 이걸 잡아냈다.

### 🔴 UAVCAN 은 빼지 마라 — 170.6 KB 지만 필수다

가장 큰 모듈이라 눈에 띄지만 **전원 모니터 PM08 이 DroneCAN 이다.**
빼면 배터리 전압·전류가 안 들어온다.

```
UAVCAN_ENABLE=2   BAT1_SOURCE=1
```

실기 `uavcan status` 로 동작을 확인했다 (TX 63513 프레임).

## 빌드

```bash
source ~/opt/px4env.sh
cd ~/PX4-Autopilot
git checkout shade01-v1.17.0-dataman
make px4_fmu-v6c_shade01
```

산출물: `build/px4_fmu-v6c_shade01/px4_fmu-v6c_shade01.px4` (1.6 MB)

## 🔴 빌드 함정 — 전부 한 번씩 물렸다

### ① 설정을 지우면 되살아난다

```
✗ CONFIG_MODULES_GIMBAL=y  줄을 삭제      → Kconfig 가 default y 로 복원
✅ # CONFIG_MODULES_GIMBAL is not set     → 실제로 꺼진다
```

첫 빌드가 **97.99% 로 하나도 안 줄었다.** 줄을 지웠더니 기본값이 다시 채워졌고
`libmodules__uxrce_dds_client.a` 가 그대로 링크됐다. 설정을 바꾸면
**`build/px4_fmu-v6c_shade01` 을 지우고 다시 빌드해야** 반영된다.

### ② 서브모듈이 main 기준으로 받아진다

`git clone --recursive` 를 먼저 돌리고 나중에 `git checkout v1.17.0` 을 하면
서브모듈은 여전히 main(v1.18.0-beta1) 것이다. **NuttX 가 12.12.0 으로 잡힌다** —
v1.17.0 이 요구하는 것은 `nuttx-8.2-10680` 계열이다. 그대로 빌드하면
**다른 커널이 들어간 펌웨어**가 나온다.

```bash
git submodule update --init --recursive     # 체크아웃 뒤에 반드시
git submodule status --recursive | grep -c '^[+-]'   # 0 이어야 한다
```

### ③ `pkg_resources` 없음

setuptools 81 부터 빠졌다. `dsdl compiler` 단계에서 죽는다.

```bash
~/opt/px4-venv/bin/pip install "setuptools<81"
```

### ④ 툴체인 디렉토리명

받는 파일은 `13.2.rel1` 인데 **풀리는 디렉토리는 `13.2.Rel1`** 이다 (대문자 R).

## 검증 — 빌드 후 반드시 본다

```bash
source ~/opt/px4env.sh
cd ~/PX4-Autopilot/build/px4_fmu-v6c_shade01

# 뺀 것이 정말 빠졌나
arm-none-eabi-nm px4_fmu-v6c_shade01.elf | grep -ci uxrce     # 0 이어야 한다

# 남아야 할 것이 남았나
for m in uavcan dataman navigator ekf2 mavlink; do
  echo "$m $(arm-none-eabi-nm px4_fmu-v6c_shade01.elf | grep -ci $m)"
done

# dataman 수정이 들어갔나
arm-none-eabi-nm px4_fmu-v6c_shade01.elf | grep -c clearPendingResponse   # 1
```

실측 (2026-09-12):

```
uxrce      0        ✅ 제거됨
uavcan     2150     ✅
dataman      36     ✅
navigator   105     ✅
ekf2        129     ✅
mavlink    1205     ✅
px4io      107      ✅
clearPendingResponse 1  ✅
```

## 🔴 플래시 전 관문 — 파라미터 diff 를 반드시 밟아라

빌드가 정의하는 파라미터와 실기 백업을 대조한다. **이 검사가 PX4IO 실수를 잡았다.**

```bash
cd ~/SHADE01
~/opt/px4-venv/bin/python - <<'EOF'
import json, io
meta = json.load(io.open(
  '/home/rim3/PX4-Autopilot/build/px4_fmu-v6c_shade01/parameters.json'))
std = {p['name'] for p in meta['parameters'] if p.get('name')}
have = set()
for line in io.open('params/px4_params_20260912-final.params', encoding='utf-8'):
    if line.startswith('#'): continue
    f = line.rstrip('\n').split('\t')
    if len(f) >= 4: have.add(f[2])
lost = sorted(have - std)
print('사라지는 파라미터: %d개' % len(lost))
for n in lost: print('  ', n)
EOF
```

**사라지는 것이 나오면 그 하나하나가 현재 "꺼짐" 값인지 확인해야 한다.**
켜져 있는 것이 사라지면 기능이 죽는다.

실측 (2026-09-12) — 10개, 전부 꺼짐이라 안전:

| 파라미터 | 값 | |
|---|---|---|
| `MNT_MODE_IN` | -1 | gimbal 안 씀 |
| `RC_CRSF_PRT_CFG` | 0 | CRSF 안 씀 |
| `SEP_PORT1/2_CFG` | 0 | Septentrio 안 씀 |
| `TC_A/B/G/M_ENABLE` | 0 | 온도보상 안 씀 |
| `UXRCE_DDS_CFG` | 0 | ROS2 안 씀 |
| `_HASH_CHECK` | — | PX4 자동 계산 |

⚠️ **`gimbal` 은 100개가 남는다 — 정상이다.** MAVLink 메시지 정의와 uORB 토픽
심볼이라 모듈과 무관하다. `libdrivers__gimbal.a` 가 링크되지 않은 것을 확인했다.

## 플래시 — 아직 안 했다

플래시 절차와 복원은 [`FLASHING.md`](FLASHING.md) 에 따로 있다.
🔴 **플래시는 파라미터를 전부 날린다.** 복원 정본은
`params/px4_params_20260912-final.params` (1353개) 다.
