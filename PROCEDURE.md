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

```bash
./qgc log logs/2026-08-31/2026-08-31_09_17_02.ulg
```

하루치 요약표:

```bash
for f in logs/2026-08-31/*.ulg; do
  echo "=== $(basename "$f") ==="
  ./qgc log "$f" 2>&1 | sed -n '4,12p'
done
```

## 3. 기록

`flights/<날짜>-<주제>.md` 로 남긴다. **`.ulg` 는 git 에 안 들어가므로
(`.gitignore` 의 `*.ulg`), 수치를 문서에 적는 것이 유일한 영구 기록이다.**

담을 것: 세션 목적 / 파일별 요약표(시간·고도·전류·소모) / 문제와 원인 / 다음 할 일.

## 알려진 함정

### FC 는 한 연결에 파일 하나만 내준다

두 번째 파일부터 `OpenFileRO failed, no sessions available` 로 **0바이트**가 된다.
세션 반납(`ResetSessions`)으로는 안 풀린다 — 실측 확인.
**`fcfetch.py` 는 파일마다 재연결하도록 고쳐 두었다** (2026-09-01). 21개 45MB 를 238초에 받았다.

### 분석기 — 손상된 로그도 읽는다 (2026-09-01 수정)

21개 중 7개가 파싱 실패하던 문제를 고쳤다. **지금은 21/21 이 읽힌다.**

원인은 `qgclog.py` 가 아니라 **pyulog** 였다. ULog 정의 구간에 깨진 바이트가 있어
`A`(0x41) 로 오독되면 pyulog 가 거기서 정의 읽기를 멈추고, 뒤따르는 `F`(포맷) 정의가
유실된다. 나중에 그 토픽을 참조하는 시점에 `message_formats[type_name]` 이 KeyError 로
터진다 — `estimator_*` · `actuator_servos` · `DIS3\x03...` 3종이 **전부 같은 한 줄**이었다.

`_patch_pyulog()` 가 그 KeyError 를 **IndexError 로 바꾼다.** pyulog 는 데이터 구간
손상을 이미 IndexError 로 처리하므로(`_file_corrupt` 만 세우고 계속 읽음), 같은 복구
경로에 태우면 **포맷을 잃은 그 토픽만 빠지고 나머지는 전부 살아난다.**

⚠️ `message_name_filter_list` 로는 못 피한다 — `_parse_format()` 이 필터 검사보다 먼저 돈다.

빈 배열 문제도 함께 고쳤다. arm 구간에 그 토픽 샘플이 하나도 없으면 numpy 집계가
ValueError 를 던지거나 조용히 `nan` 을 리포트에 넣었다. `stat()` 헬퍼로 16곳을 막았다.

⚠️ **알려진 한계** — `_repair()` 의 `_scan_sections()` 는 경계 검사 없이 파일 전체를
훑어서, 데이터 바이트를 가짜 포맷 정의로 잡을 수 있다. 그래서 도너 매칭이 실패할 수
있다. 현재 로그는 이 경로를 타지 않아 손대지 않았다.

### MAVFTP API

`tools/qgclog/FETCHING.md` 에 정리돼 있다. `cmd_list` 는 내부에서 `process_ftp_reply`
를 부르므로 밖에서 또 부르면 안 되고, `cmd_get` 은 반대로 반드시 밖에서 불러야 한다.
