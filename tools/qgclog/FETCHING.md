# 비행 로그 가져오기 — 검증된 절차

FC 내장 SD 에서 **QGC 없이 USB 만으로** 로그를 받는다. 2026-08-25 실측 검증.

> **왜 이 문서가 있나**: 처음에 MAVLink `LOG_REQUEST_DATA` 로 순차 요청하는 방식을 썼다가
> 7.6MB 에 10분 이상 걸려 중단했다. **MAVFTP 버스트 읽기로 바꾸니 18초**가 됐다.
> 같은 실수를 반복하지 않도록 성공한 방법만 남긴다.

## 속도 실측

| 방식 | 7.6MB 소요 |
|---|---|
| `LOG_REQUEST_DATA` 순차 (90바이트씩) | **10분+** — 쓰지 마라 |
| **MAVFTP 버스트** | **18초** |
| 하루치 6개(19.8MB) 일괄 | **42초** |

## 🔴 로그는 `SHADE01/logs/` 에 모은다

**회수한 `.ulg` 는 전부 리포의 `logs/` 로 가져온다.** 어느 PC 에서 받든, FC SD 에서
직접 받든 마찬가지다.

`~/SHADE01/QGroundControl/Logs` 는 **QGC 가 자기 용도로 쓰는 폴더일 뿐이다.** 분석·리포트·
비교는 리포 안에서 넓게 한다. QGC 폴더에 있는 로그는 `logs/` 로 옮겨서 본다.

```bash
mv ~/SHADE01/QGroundControl/Logs/*.ulg <SHADE01>/logs/
```

`qgclog` 는 `logs/` 를 **1순위 기본 디렉토리**로 찾는다 (`DEFAULT_DIRS`).
`*.ulg` 는 `.gitignore` 되어 있어 리포에 커밋되지 않는다 — 경로만 공유되고 파일은 안 간다.

구독 섹션 유실 복구가 **같은 디렉토리의 다른 로그를 도너로 쓰기 때문에**, 한 곳에
모아 두는 것이 복구 성공률도 올린다.

## 준비 — pymavlink (sudo 없이)

Ubuntu 24.04 는 `python3-venv` 가 없어 `python3 -m venv` 가 실패한다.
`--without-pip` + `get-pip` 부트스트랩으로 우회한다. **시스템 패키지를 건드리지 않는다.**

```bash
python3 -m venv --without-pip ~/.venv-mav
curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
~/.venv-mav/bin/python /tmp/get-pip.py -q
~/.venv-mav/bin/pip install pymavlink pyserial
rm -f /tmp/get-pip.py
~/.venv-mav/bin/python -c "import pymavlink;print(pymavlink.__version__)"
```

## 절차

### 1. 포트 점유 해제 — 필수

**QGC 가 떠 있으면 MAVFTP 가 붙지 못한다.** 먼저 확인한다.

```bash
fuser -v /dev/ttyACM0        # 점유 프로세스
ps -eo pid,cmd | grep -i qground | grep -v grep
```

QGC 가 잡고 있으면 종료한다. ⚠️ **사용자가 보고 있는 창일 수 있으니 임의로 죽이지 말고 물어볼 것.**

### 2. 로그 목록

```bash
~/.venv-mav/bin/python fcfetch.py ls                        # 날짜 폴더
~/.venv-mav/bin/python fcfetch.py ls /fs/microsd/log/2026-08-24
```

⚠️ **파일명은 UTC 다.** KST = UTC + 9시간.
`10_11_12.ulg` = **19시 11분(KST)**. 19시 비행을 찾는다면 `10_*` 을 봐야 한다.

### 3. 받기

**받는 곳은 리포의 `logs/` 다** — `/tmp` 로 받고 나중에 옮기지 마라. 잊는다.

```bash
# 하루치 전부 (이미 받은 것은 크기 비교 후 건너뜀)
~/.venv-mav/bin/python fcfetch.py fetch 2026-08-24 <SHADE01>/logs

# 하나만
~/.venv-mav/bin/python fcfetch.py get /fs/microsd/log/2026-08-24/10_11_12.ulg <SHADE01>/logs/log_94.ulg
```

### 4. 원격 PC 라면 회수

**받는 곳은 언제나 리포의 `logs/` 다.**

```bash
scp -o BatchMode=yes -o ConnectTimeout=200 \
    'rim3@100.117.47.105:~/SHADE01/logs/*.ulg' <SHADE01>/logs/
```

원격 PC 에 아직 회수 전이면 그쪽에서도 `~/SHADE01/logs/` 로 받게 한다.

⚠️ rim3 는 Tailscale relay 경유라 RTT 가 수백 ms~1.6초다.
`ConnectTimeout` 을 **200초 이상**으로 잡아야 붙는다.

### 5. 분석

```bash
./qgc log list
./qgc log 1
```

## MAVFTP API 함정 — 여기서 시간을 많이 썼다

`pymavlink.mavftp` 는 메서드마다 동작이 다르다. 소스를 봐야 안다.

| 메서드 | 동작 | 올바른 사용 |
|---|---|---|
| `cmd_list` | **내부에서** `process_ftp_reply` 호출 | 그냥 호출하고 `ftp.list_result` 를 읽는다. **밖에서 또 부르면 두 번째가 빈 응답을 받아 `error_code=1`** 이 된다 |
| `cmd_get` | **요청만 보내고 즉시 반환** | 호출 후 **반드시** `process_ftp_reply('OpenFileRO', timeout=900)` 을 돌려야 실제로 전송된다. 안 그러면 0바이트 파일이 생긴다 |

`progress_callback` 은 **인자 1개(비율)** 를 받고, **완료 시 `None`** 이 온다.

```python
def prog(frac):
    if frac is None:      # 이 가드가 없으면 TypeError
        return
    ...
```

`process_ftp_reply(timeout=...)` 는 `timeout > ftp_settings.idle_detection_time` 이어야 한다
(기본 0.1). 작게 주면 `AssertionError`.

`burst_read_size` 는 **239 가 최대**. 이게 속도를 결정한다.

## pymavlink 2.4.49 버그 우회

`recv_match` 가 간헐적으로 터진다:

```
TypeError: 'NoneType' object does not support item assignment
  mavutil.py:98  messages[mtype]._instances[instance_value] = msg
```

인스턴스 필드가 있는 메시지에서 발생한다. **`try/except TypeError` 로 감싸고 다음 패킷으로 넘어가면** 된다.

```python
try:
    msg = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
except TypeError:
    continue
```

## 로그가 안 읽힐 때

`qgclog` 가 원인을 구분해 알려준다.

| 메시지 | 뜻 | 조치 |
|---|---|---|
| `구독 섹션 유실` | A(구독) 메시지가 통째로 없다. 데이터는 살아 있다 | **자동 복구됨** — 같은 포맷(F 136개 완전 일치)의 정상 로그에서 A 블록을 이식한다 |
| `데이터 깨짐 — N% 지점` | 그 지점에서 메시지 헤더가 붕괴 | 복구 불가. 그 앞까지만 유효 |
| `ULog 헤더 아님` | 파일이 ULog 가 아니거나 전송 실패 | md5 로 원본과 대조 |

### 구독 섹션 유실 복구 원리

PX4 는 로그 앞에 `F`(포맷) → `P`(파라미터) → `A`(구독) 순으로 정의를 쓴다.
`A` 가 없으면 pyulog 가 `D`(데이터)를 어느 토픽에 넣을지 몰라 **토픽 0개**가 된다.

`qgclog` 는 같은 디렉토리에서 **포맷 정의(F)가 완전히 같은** 로그를 찾아
`A` 블록만 잘라 마지막 `P` 뒤에 끼워 넣는다. 삽입 위치가 틀리면 pyulog 가 무시한다.

⚠️ **msg_id 매핑을 빌려오는 것이므로 검증이 필요하다.** 복구 후 물리적 정합성을 확인했다
(가속도 크기 9.98 m/s², 쿼터니언 norm 1.0000, 6S 전압 범위, 한국 좌표, 모터 0~1) — 5/5 통과.
같은 펌웨어·같은 설정이면 PX4 가 같은 순서로 id 를 부여하므로 성립한다.
**펌웨어가 다른 로그를 도너로 쓰면 안 된다** — 그래서 F 완전 일치를 조건으로 건다.

## 파일명 시각 주의

`boot_time_utc_us` 는 **부팅 시각**이라 같은 세션의 로그가 전부 같은 값이 된다.
`qgclog` 는 **파일명에서 시각을 뽑는다**. 파일명 형식이 바뀌면 이 부분을 고쳐야 한다.
