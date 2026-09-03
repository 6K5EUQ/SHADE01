# SHADE01 운용 절차

로그를 받고, 분석하고, 기록으로 남기기까지. **2026-09-01 실측으로 검증한 순서**다.

> PC 별 Tailscale 주소·사용자명·리포 경로는 [gcs/ACCESS.md](gcs/ACCESS.md) 에 있다.

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

**받는 곳은 언제나 리포의 `logs/` 다 — 평면으로 쌓는다. 날짜별 하위 폴더를 만들지 마라.**
파일명에 이미 날짜가 들어 있고, `./qgc log list` 가 한 번에 전부 보여준다.

```bash
scp 'raspb1@100.126.161.1:/tmp/fclogs/*.ulg' logs/
```

`~/SHADE01/QGroundControl/Logs` 는 **QGC 자신이 쓰는 폴더일 뿐이다.** 거기 쌓인 로그도 옮겨 온다 —
분석·비교·리포트는 전부 리포 안에서 한다.

```bash
mv ~/SHADE01/QGroundControl/Logs/*.ulg logs/
```

`qgclog` 는 `logs/` 를 **1순위 기본 디렉토리**로 찾는다. `*.ulg` 는 `.gitignore` 되어
커밋되지 않으므로, 한곳에 모아도 리포가 무거워지지 않는다. 구독 섹션 유실 복구가
**같은 디렉토리의 다른 로그를 도너로 쓰기 때문에**, 모아 두는 편이 복구 성공률도 높다.

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

> 리포에 `venv-ardupilot/` 이 이미 있는 PC(`ku`, `rim3`)는 그대로 둬도 된다 —
> 런처가 `.venv` 다음 후보로 계속 찾는다. 이름만 남은 잔재이고 ArduPilot 과는 무관하다.

확인: `./qgc log list` 가 표를 뿌리면 된다.
다른 경로에 있으면 `QGCLOG_PYTHON=/path/to/python` 으로 지정한다.

```bash
./qgc log list                                  # 번호로 나열
./qgc log 1                                     # 번호로 분석
./qgc log logs/2026-08-31_09_17_02.ulg   # 경로 직접 지정
```

> 🔴 **`pyulog` 를 직접 부르지 마라.** 잘린 메시지 하나에서 읽기를 포기해 로그 대부분을
> 조용히 잃는다. 에러도 경고도 없이 **짧은 비행처럼 보일 뿐이다.** 반드시 `./qgc` 나
> `qgclog._load()` 를 거쳐라 — [원인](#분석기--잘린-메시지에서-멈추지-않는다-2026-09-01-수정).

하루치 요약표:

```bash
for f in logs/2026-08-31_*.ulg; do
  echo "=== $(basename "$f") ==="
  ./qgc log "$f" 2>&1 | sed -n '4,12p'
done
```

### 파싱이 제대로 됐는지 확인

새 PC 에서 처음 돌릴 때, 또는 결과가 조종자 기억과 다를 때. **파일 크기 대비 비행시간이
말이 되는지** 부터 본다 — 23MB 로그가 27초일 수는 없다.

```bash
for f in logs/2026-08-31_*.ulg; do
  printf "%-34s %6s  %s\n" "$(basename "$f")" "$(du -h "$f" | cut -f1)" \
    "$(./qgc log "$f" 2>/dev/null | grep 비행시간 | grep -oE '[0-9]+초')"
done
```

디코딩률을 숫자로 재려면 `tools/qgclog/decode_rate.py` 를 쓴다:

```bash
.venv/bin/python tools/qgclog/decode_rate.py logs
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

### 목록의 "파싱 실패" 를 믿지 마라 (2026-09-03 수정)

**증상**: `qgclog list` 가 15개 중 4개를 "파싱 실패" 로 찍었다. 실제로는 4개 전부
읽혔다. 게다가 읽히던 로그들의 **비행시간도 틀려 있었다** — log_184 는 72초로
찍혔지만 실제 200초, log_183 은 1초가 아니라 61초, log_177 은 13초가 아니라 102초였다.

원인 세 가지. 전부 `tools/qgclog/qgclog.py` 에서 고쳤다.

**1. `quick_scan()` 이 패치를 안 걸었다.** 목록 표시용 경로만 순정 pyulog 를 쓰고
있었다. 그래서 `analyse()` 로는 멀쩡히 읽히는 로그가 목록에서는 실패로 보였고,
읽히는 것도 조기 종료된 시간을 보여줬다. 이제 `_patch_pyulog()` 를 먼저 부른다.

**2. 가짜 FLAGS_BITS 하나가 로그 전체를 버렸다.** 정의 구간이 손상되면 pyulog 는
바이트를 밀며 재동기화하는데, 그때 쓰레기가 `B`(FLAGS_BITS) 로 오독된다. pyulog 는
`FLAGS_BITS message must be first message` 를 찍어 **스스로 가짜인 걸 알면서도**
그 난수 바이트를 incompat_flags 로 믿고 `ValueError` 를 던져 파일을 포기한다.
실측: `log_180` offset 164234 에서 incompat `[225, 43, 70, 65, 49, 187, 56, 50]` 로
읽혀 1.0MB 전체가 버려졌다. 진짜 첫 FLAGS_BITS(offset 16)는 정상이었다.
첫 메시지가 아니거나 incompat 이 말이 안 되면 `IndexError` 로 바꿔 손상 처리
경로에 태운다.

**3. `_repair()` 의 기증자 판정이 너무 빡셌다.** 포맷 정의가 **완전히 같아야** 이식을
허용했는데, 손상된 로그에는 데이터 구간의 임의 바이트가 `F` 로 오독된 가짜 포맷이
섞인다. `log_180` 은 가짜 2개(offset 525526, 607069) 때문에 기증자를 하나도 못
찾았다 — 진짜 포맷은 하나도 빠지지 않았는데도. 이제 이름이 ASCII 식별자가 아닌
포맷은 버리고, 기증자가 내 포맷을 **전부 포함**하면 통과시킨다(기증자에만 있는
토픽은 무해하다 — 내 D 메시지가 참조하지 않는다).

**꼬리 잘림은 손상이 아니다.** `_why_broken()` 이 마지막 메시지 하나가 잘린 것을
"99% 지점에서 메시지 구조 붕괴" 로 찍어 손상으로 오해하게 했다. 전원이 갑자기
끊기면 항상 꼬리가 잘린다 — 앞 데이터는 멀쩡하다. 실측 꼬리 크기는 5.4K / 36K /
39K 였다. 256KB 이하면 "전원 급단" 으로 구분해 표시한다.

> ⚠️ **2026-09-03 이전에 "파싱 실패" 로 넘긴 로그를 다시 열어봐라.** 대부분 읽힌다.
> 그때 적어 둔 비행시간도 축소돼 있을 수 있다.

**남은 실패 1개** — `RECOVERED_09_09_49.ulg` 는 손으로 복구하던 중간 산물이다.
구독 블록은 있으나 자기 데이터와 안 맞는다(토픽 29개, msg id 0·1·3·6 미매칭).
같은 원본을 제대로 복구한 `RECOVERED2_09_09_49.ulg` 가 97초로 잘 읽히므로 이쪽을 쓴다.

### 깨진 float 한 샘플이 최고고도를 5.03e14 m 로 만든다 (2026-09-03 수정)

`log_182` 의 최고고도가 **503002175635456.0 m** 로 찍혔다. `vehicle_local_position`
의 `z` 1758개 중 **한 샘플**의 float32 비트가 손상돼 지수부가 튄 것이다.

`z_valid` 플래그로는 못 거른다 — EKF 가 낸 값이 아니라 파일이 깨진 것이라
플래그는 `True` 로 남는다. 물리적으로 불가능한 크기만 버린다
(`_SANE_ALT_M = 10000`, `_SANE_SPEED_MS = 200`). 걸러낸 뒤 3.2 m 로 정상화됐다.

목록과 `qgclog <N>` 이 **같은 필터**를 쓰므로 두 값은 항상 일치한다.

### 목록 표에 고도·속도가 들어간다 (2026-09-03)

`qgclog list` 의 열: `# / 파일 / 시간(KST) / 최대고도 / 최대속도 / 비행시간 / 파일크기`.

고도·속도는 `vehicle_local_position` 을 arm 구간으로 잘라 낸 값이라
`qgclog <N>` 의 "최고고도 / 최대속도" 와 같다. 그 토픽이 없으면 `-` 로 비운다
(0 으로 채우면 '고도 0m 로 날았다' 로 읽힌다).

한글 헤더가 2칸 폭이라 `%-Ns` 로는 표가 어긋난다. `_pad()` 가
`unicodedata.east_asian_width` 로 표시폭을 세어 채운다.

### 목록에 복구 표시가 붙는다 (2026-09-03)

`qgclog list` 의 파일크기 뒤 `⚠복구` 는 **구독 섹션이 유실돼 다른 로그의 정의를
이식해 읽었다**는 뜻이다. `qgclog <N>` 은 원래 이 경고를 냈지만 목록에는 없어,
표만 보고 수치를 정본으로 착각할 수 있었다.

2026-09-02 자 로그 중 `log_180`·`log_179` 둘이 여기 해당한다.

### 목록에 복구 표시가 붙는다 (2026-09-03)

`qgclog list` 의 파일크기 뒤 `⚠복구` 는 **구독 섹션이 유실돼 다른 로그의 정의를
이식해 읽었다**는 뜻이다. `qgclog <N>` 은 원래 이 경고를 냈지만 목록에는 없어,
표만 보고 수치를 정본으로 착각할 수 있었다.

2026-09-02 자 로그 중 `log_180`·`log_179` 둘이 여기 해당한다.

### 최고고도는 arm 기준 상대고도다 (2026-09-03 수정)

`vehicle_local_position` 의 `z` 는 **EKF 원점 기준**이라 이륙 지점과 무관하다.
그대로 최고고도로 내면 지상에 있던 로그가 `-7.0 m`, 뜬 로그가 `27.2 m` 로 찍혀
**표에서 "떴는지" 를 눈으로 못 가른다.**

`_agl()` 이 arm 직후 `_GROUND_WINDOW_S`(1초)의 z 중앙값을 지면으로 잡아 뺀다.
첫 샘플 하나가 아니라 중앙값을 쓰는 이유는 튐에 강해서다 (실측 차이는 0.05 m 안쪽).

바뀐 값 — 같은 로그, 같은 데이터:

| 로그 | 원점 기준(전) | arm 기준(후) |
|---|---|---|
| `log_184` | 27.2 m | **33.5 m** |
| `log_187` | 1.9 m | **4.1 m** |
| `log_179` | **-7.0 m** | **0.0 m** (안 떴다) |
| `log_178` | -6.9 m | **0.0 m** (안 떴다) |

목록과 `qgclog <N>` 이 같은 `_agl()` 을 쓰므로 두 값은 항상 일치한다.
**직접 파싱할 때는 이 보정이 안 걸린다** — `z` 를 그대로 읽지 말고 직접 빼라.

### MAVFTP API

`tools/qgclog/FETCHING.md` 에 정리돼 있다. `cmd_list` 는 내부에서 `process_ftp_reply`
를 부르므로 밖에서 또 부르면 안 되고, `cmd_get` 은 반대로 반드시 밖에서 불러야 한다.
