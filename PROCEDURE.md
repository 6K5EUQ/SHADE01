# SHADE01 운용 절차

로그를 받고, 분석하고, 기록으로 남기기까지. **2026-09-01 실측으로 검증한 순서**다.

## 1. 로그 수집

FC 는 raspb1 에 USB 로 붙어 있다. 로그는 **raspb1 에서** 받아 이 PC 로 회수한다.

### 1-1. 준비 (raspb1, 최초 1회)

```bash
ssh raspb1@100.126.161.1
python3 -m venv --without-pip ~/.venv-mav
curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
~/.venv-mav/bin/python /tmp/get-pip.py -q
~/.venv-mav/bin/pip install pymavlink pyserial
rm -f /tmp/get-pip.py
```

### 1-2. 브리지 정지 — 필수

**FC 시리얼 포트는 하나뿐이다.** 브리지가 잡고 있으면 MAVFTP 가 붙지 못한다.

```bash
ssh raspb1@100.126.161.1 'sudo systemctl stop mavlink-bridge.service'
ssh raspb1@100.126.161.1 'fuser -v /dev/ttyACM0'   # 비어 있어야 한다
```

⚠️ 이 동안 **QGC 무선 링크가 끊긴다.** 기체 조작 중이 아닐 때만 한다.

### 1-3. 받기

```bash
scp tools/qgclog/fcfetch.py raspb1@100.126.161.1:/tmp/
ssh raspb1@100.126.161.1 'cd /tmp && ~/.venv-mav/bin/python fcfetch.py ls'
ssh raspb1@100.126.161.1 'cd /tmp && ~/.venv-mav/bin/python fcfetch.py fetch 2026-08-31 /tmp/fclogs'
```

⚠️ **파일명은 UTC.** KST = UTC + 9h. `08_24_28.ulg` = **17시 24분(KST)**.

### 1-4. 브리지 복구 — 잊지 말 것

```bash
ssh raspb1@100.126.161.1 'sudo systemctl start mavlink-bridge.service'
```

### 1-5. 회수

```bash
mkdir -p logs/2026-08-31
scp 'raspb1@100.126.161.1:/tmp/fclogs/*.ulg' logs/2026-08-31/
```

## 2. 분석

### 2-0. 분석 PC 준비 (새 PC 최초 1회)

`./qgc` 는 `pyulog` + `numpy` 가 있는 인터프리터를 찾는다. 없으면
**"pyulog/numpy 를 가진 python 을 못 찾았다"** 로 멈춘다. **리포 안 `.venv/`** 에 만든다
— 런처가 `$QGCLOG_PYTHON` 다음으로 보는 경로이고, `.gitignore` 로 제외돼 있다.

⚠️ Ubuntu 기본 python 은 `ensurepip` 가 빠져 있어 `python3 -m venv` 가 pip 없이 끝난다.
raspb1 과 **같은 우회**를 쓴다:

```bash
python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
.venv/bin/python /tmp/get-pip.py -q
rm -f /tmp/get-pip.py
.venv/bin/pip install pyulog numpy pymavlink pyserial
```

> 홈에 `~/venv-ardupilot` 이 이미 있는 PC(`ku`, `rim3`)는 그대로 둬도 된다 —
> 런처가 `.venv` 다음 후보로 계속 찾는다. 이름만 남은 잔재이고 ArduPilot 과는 무관하다.

확인: `./qgc log list` 가 표를 뿌리면 된다.
다른 경로에 있으면 `QGCLOG_PYTHON=/path/to/python` 으로 지정한다.

```bash
./qgc log list                                  # 번호로 나열
./qgc log 1                                     # 번호로 분석
./qgc log logs/2026-08-31/2026-08-31_09_17_02.ulg
```

> 🔴 **`pyulog` 를 직접 부르지 마라.** 잘린 메시지 하나에서 읽기를 포기해 로그 대부분을
> 조용히 잃는다. 에러도 경고도 없이 **짧은 비행처럼 보일 뿐이다.** 반드시 `./qgc` 나
> `qgclog._load()` 를 거쳐라 — [원인](#분석기--잘린-메시지에서-멈추지-않는다-2026-09-01-수정).

하루치 요약표:

```bash
for f in logs/2026-08-31/*.ulg; do
  echo "=== $(basename "$f") ==="
  ./qgc log "$f" 2>&1 | sed -n '4,12p'
done
```

### 파싱이 제대로 됐는지 확인

새 PC 에서 처음 돌릴 때, 또는 결과가 조종자 기억과 다를 때. **파일 크기 대비 비행시간이
말이 되는지** 부터 본다 — 23MB 로그가 27초일 수는 없다.

```bash
for f in logs/2026-08-31/*.ulg; do
  printf "%-34s %6s  %s\n" "$(basename "$f")" "$(du -h "$f" | cut -f1)" \
    "$(./qgc log "$f" 2>/dev/null | grep 비행시간 | grep -oE '[0-9]+초')"
done
```

디코딩률을 숫자로 재려면 `tools/qgclog/decode_rate.py` 를 쓴다:

```bash
.venv/bin/python tools/qgclog/decode_rate.py logs/2026-08-31
```

**기준치 — 2026-08-31 자 21개 실측(2026-09-01): DATA 99.36%, 실패 0개.**
15개가 100%. 이보다 크게 낮으면 패치가 안 걸린 것이다.

## 3. 기록

`flights/<날짜>-<주제>.md` 로 남긴다. **`.ulg` 는 git 에 안 들어가므로
(`.gitignore` 의 `*.ulg`), 수치를 문서에 적는 것이 유일한 영구 기록이다.**

담을 것: 세션 목적 / 파일별 요약표(시간·고도·전류·소모) / 문제와 원인 / 다음 할 일.

## 알려진 함정

### FC 는 한 연결에 파일 하나만 내준다

두 번째 파일부터 `OpenFileRO failed, no sessions available` 로 **0바이트**가 된다.
세션 반납(`ResetSessions`)으로는 안 풀린다 — 실측 확인.
**`fcfetch.py` 는 파일마다 재연결하도록 고쳐 두었다** (2026-09-01). 21개 45MB 를 238초에 받았다.

### 분석기 — 잘린 메시지에서 멈추지 않는다 (2026-09-01 수정)

**증상**: 3분 넘게 난 비행이 로그에는 27초로 찍혔다. "SD 카드 손상" 으로 오해했으나
**파일은 멀쩡했고 파싱이 조기 종료된 것**이었다.

`pyulog` 의 읽기 루프는 메시지 종류마다 파서를 부르는데, 그 파서들이 `struct.unpack` 을
길이 검사 없이 호출한다. 본문이 잘린 메시지를 만나면 `struct.error` 가 나고, 이 예외는
루프 **안쪽**의 `except IndexError` 에 안 걸린 채 **바깥**의 `except struct.error: pass`
까지 올라간다. 거기서 루프가 끝난다 — 파일에 데이터가 20MB 더 남아 있어도 버려진다.

`_patch_pyulog()` 가 메시지 클래스들의 `struct.error` 를 `IndexError` 로 바꿔,
pyulog 가 이미 가진 손상 처리 경로(그 메시지만 버리고 계속)에 태운다.
헤더 파서(`_MessageHeader`)는 제외한다 — 거기서 나는 struct.error 는 진짜 EOF 다.

`09_38_28.ulg` (23MB) 실측:

| 상태 | 읽은 지점 | DATA 디코딩 | 비행시간 |
|---|---|---|---|
| 수정 전 | 1.5 MB | 6.1% | 27초 (거짓) |
| DATA 만 | 9.9 MB | 42.7% | 194초 |
| **전 메시지** | **22.97 MB (끝)** | **100%** | **453초 (실제)** |

같은 패치가 **포맷 정의 유실**도 처리한다. 정의 구간의 깨진 바이트가 `A`(0x41) 로
오독되면 pyulog 가 정의 읽기를 멈춰, 뒤에 오는 토픽 참조가 KeyError 로 터진다
(`estimator_*` · `actuator_servos` · 쓰레기 이름 — 전부 같은 한 줄에서 난다).
⚠️ `message_name_filter_list` 로는 못 피한다 — `_parse_format()` 이 필터 검사보다 먼저 돈다.

빈 배열도 함께 막았다. arm 구간에 그 토픽 샘플이 하나도 없으면 numpy 집계가 ValueError 를
던지거나 조용히 `nan` 을 리포트에 넣었다. `stat()` 헬퍼로 16곳을 처리했다.

> 🔴 **낡은 분석 문서를 의심하라.** 이 버그가 고쳐지기 전에 쓰인 기록은 비행시간·고도·
> 전류·소모량이 전부 축소돼 있을 수 있다. 파싱이 멈춘 지점까지만 본 값이기 때문이다.

### MAVFTP API

`tools/qgclog/FETCHING.md` 에 정리돼 있다. `cmd_list` 는 내부에서 `process_ftp_reply`
를 부르므로 밖에서 또 부르면 안 되고, `cmd_get` 은 반대로 반드시 밖에서 불러야 한다.
