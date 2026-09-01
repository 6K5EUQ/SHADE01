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
mkdir -p SHADE01/logs/2026-08-31
scp 'raspb1@100.126.161.1:/tmp/fclogs/*.ulg' SHADE01/logs/2026-08-31/
```

## 2. 분석

```bash
./qgc log SHADE01/logs/2026-08-31/2026-08-31_09_17_02.ulg
```

하루치 요약표:

```bash
for f in SHADE01/logs/2026-08-31/*.ulg; do
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

### 분석기가 일부 로그에서 죽는다

2026-08-31 자 21개 중 **7개가 파싱 실패**했다. 원인 세 갈래:

| 증상 | 뜻 |
|---|---|
| `ValueError: zero-size array` | 고도 데이터가 아예 없음 — 부팅 직후 짧은 로그 |
| `KeyError: 'estimator_*'` / `'actuator_servos'` | 그 토픽이 로그에 없음 |
| `KeyError: 'DIS3\x03...'` | 로그 파일 자체 손상 |

`qgclog.py` 가 이 경우를 방어하지 않는다. **고칠 값어치가 있는 개선점이다.**

### MAVFTP API

`tools/qgclog/FETCHING.md` 에 정리돼 있다. `cmd_list` 는 내부에서 `process_ftp_reply`
를 부르므로 밖에서 또 부르면 안 되고, `cmd_get` 은 반대로 반드시 밖에서 불러야 한다.
