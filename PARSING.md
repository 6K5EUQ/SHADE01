# 로그 파싱 절차 — 읽기 전에 손대지 마라

**`.ulg`·`.tlog` 을 읽는 모든 작업은 이 문서가 정본이다.** 로그 분석·목록·웹 표시·
스킬 실행 전에 읽는다. 여기 적힌 방법은 전부 **한 번씩 실패해서 고친 것**이다.

> 🔴 **"파싱이 깨졌다" 는 보고를 받으면 고치기 전에 [§1 진단 순서](#1-진단-순서--깨졌다는-말을-들으면)
> 를 먼저 밟아라.** 지금까지 "깨졌다" 로 보고된 것의 **대부분이 파일 문제가 아니었다** —
> 파일은 멀쩡한데 도구·직렬화·전송이 깨진 것이었다. 파일부터 의심하면 매번 헛다리를 짚는다.

## 이 문서가 있는 이유

같은 부류의 사고가 최소 다섯 번 반복됐다. 매번 원인이 달랐지만 **증상은 똑같이
"읽기 실패"** 였고, 그때마다 파일을 의심하다 시간을 버렸다.

| 날짜 | 증상 | 진짜 원인 | 파일은? |
|---|---|---|---|
| 2026-09-01 | 23MB 로그가 27초로 보임 | pyulog 가 잘린 메시지에서 조기 종료 | **멀쩡** |
| 2026-09-05 | 6개가 회색 행 | `build_track()` 의 `UnboundLocalError` | **멀쩡** |
| 2026-09-06 | 화면 전체가 "서버 없음" | EKF NaN → `JSON.parse` 거부 | **멀쩡** |
| 2026-09-06 | 목록만 "파싱 실패" | `quick_scan()` 이 패치를 안 걸었다 | **멀쩡** |
| 2026-09-09 | 받을 때마다 내용이 다름 | MAVFTP **전송** 손상 (SD 아님) | 멀쩡 |
| 2026-09-10 | `log_11` 읽기 실패 | `mag_corr` NaN → `JSON.parse` 거부 | **멀쩡** |

**여섯 중 다섯이 파일과 무관했다.** 그리고 NaN 만 세 번이다.

---

## 1. 진단 순서 — 깨졌다는 말을 들으면

**이 순서를 건너뛰지 마라.** 위에서부터 하나씩, 결과를 보고 다음으로 간다.

### 1단계 — 파서가 실제로 읽는가

```bash
.venv/bin/python -c "
import sys, warnings; sys.path.insert(0,'tools/qgclog'); warnings.filterwarnings('ignore')
import qgclog
a = qgclog.analyse('<파일경로>')
print('성공. duration=%s alt_max=%s' % (a.get('duration'), a.get('alt_max')))
"
```

- **성공하면 → 파일은 멀쩡하다.** 2단계로. **여기서 파일을 지우면 안 된다.**
- 예외가 나면 → 그 예외 메시지가 진짜 단서다. [§4](#4-파일이-정말-깨졌을-때) 로.

### 2단계 — 웹 경로가 읽는가 (웹에서 실패로 뜰 때만)

파서가 읽는데 웹만 실패하면 **직렬화나 서버 문제**다.

```bash
# 서버에서 CLI 로
ssh ku@ku-labserver 'cd ~/SHADE01 && ~/shade01-venv/bin/python web/extract.py full <서버경로>' \
  > /tmp/out.json; echo "exit=$?"; wc -c /tmp/out.json
```

🔴 **여기서 성공했다고 안심하지 마라.** 파이썬은 자기가 쓴 `NaN` 을 도로 읽는다.
**반드시 3단계를 밟아라.**

### 3단계 — 🔴 JavaScript 기준으로 유효한 JSON 인가

**이것이 가장 많이 놓친 단계다. 파이썬으로 검사하면 통과한다.**

```bash
# 서버에서 (node 는 ~/.local/bin/node20)
ssh ku@ku-labserver 'cd ~/SHADE01/web && ~/.local/bin/node20 -e "
const {execFile}=require(\"child_process\");
execFile(\"/home/ku/shade01-venv/bin/python\",[\"extract.py\",\"full\",\"<경로>\"],
 {timeout:600000, maxBuffer:256*1024*1024},(err,stdout,stderr)=>{
  console.log(\"stdout len:\", stdout.length);
  try{ JSON.parse(stdout); console.log(\"=> JSON OK\"); }
  catch(e){ console.log(\"=> JSON FAIL:\", e.message.slice(0,200)); }
 });
"'
```

가장 흔한 실패:

```
=> JSON FAIL: Unexpected token 'N', ..."mag_corr": NaN, ... is not valid JSON
```

→ [§3 NaN](#3-nan--세-번-물린-자리) 으로.

간단히 문자열로 확인해도 된다 — **`NaN` 이 한 글자라도 있으면 웹이 못 읽는다**:

```bash
grep -c 'NaN' /tmp/out.json      # 0 이어야 한다
```

### 4단계 — 서버 로그를 읽는다

```bash
ssh ku@ku-labserver 'grep -i "<파일명>" ~/shade01-data/server.log | tail -5'
```

서버는 실패 이유를 남긴다. `추출기 출력이 JSON 이 아니다: ...` 는 **파일이 아니라
우리 출력이 문제**라는 뜻이다 — 이 메시지가 파일 탓처럼 읽혀서 여러 번 헛짚었다.

---

## 2. 파싱의 3대 철칙

### 철칙 1 — `pyulog` 를 직접 부르지 마라

```python
# ❌ 절대 금지
from pyulog import ULog
ulog = ULog(path)

# ✅ 반드시 이것
import qgclog
ulog, note = qgclog._load(path)     # 또는 qgclog.analyse(path)
```

**이유** (2026-09-01): `pyulog` 의 읽기 루프는 메시지 파서가 `struct.unpack` 을
길이 검사 없이 부른다. 본문이 잘린 메시지 하나를 만나면 `struct.error` 가 나고,
그 예외가 루프를 통째로 끝낸다. **파일은 멀쩡한데 뒷부분을 통째로 버린다** —
23MB 로그가 27초짜리로 보였다.

`qgclog._patch_pyulog()` 가 그 `struct.error` 를 `IndexError` 로 바꿔 루프가
그 메시지만 건너뛰고 계속 읽게 한다.

⚠️ **새 코드 경로를 만들 때마다 이 패치가 걸리는지 확인하라.** 2026-09-06 에
`quick_scan()` 이 패치를 안 걸어서 **목록만** "파싱 실패" 로 뜬 적이 있다.
`analyse()` 는 멀쩡했기 때문에 목록만 보고는 원인을 못 찾는다.

### 철칙 2 — 고도는 `_agl()` 로 만든다

```python
agl = qgclog._agl(-z, t)      # arm 기준 상대고도
```

`z` 를 그대로 쓰면 EKF 원점 기준이라 **지상 로그가 −7.0 m** 로 나온다.

### 철칙 3 — JSON 으로 내보낼 때는 [§3](#3-nan--세-번-물린-자리) 을 지킨다

---

## 3. NaN — 세 번 물린 자리

**같은 부류로 세 번 사고가 났다.** 2026-09-06(라이브 화면 전체 백지),
2026-09-06(preflight 이 NaN 을 정상으로 판정), 2026-09-10(`log_11` 읽기 실패).

### 왜 계속 새어 나가나

```python
json.dumps(data, default=coerce)     # ❌ NaN 을 못 막는다
```

`default=` 는 json 이 **모르는 타입**에만 불린다. `NaN` 은 그냥 `float` 이고
(numpy float 도 float 서브클래스) json 이 안다고 여겨 **`default=` 를 안 부른다.**
`coerce()` 안에 NaN→None 분기를 써 놔도 **호출되지 않는다.**

실측:

```
python float nan : {"v": NaN}      ← coerce 안 불림
numpy  float nan : {"v": NaN}      ← 마찬가지
```

그리고 **`NaN` 은 JSON 표준에 없다.** 파이썬은 자기가 쓴 걸 도로 읽지만
`JSON.parse` 는 응답 전체를 거부한다. 값 하나가 페이지를 통째로 죽인다.

### 지켜야 할 형태

```python
print(json.dumps(jsonable(out), default=coerce,
                 allow_nan=False, ensure_ascii=False))
```

- **`jsonable()`** — 직렬화 **전에** 재귀로 훑어 NaN/inf 를 `None` 으로 (`web/extract.py`)
- **`allow_nan=False`** — 안전망. 놓친 게 있으면 조용히 나가는 대신 그 자리에서 죽는다

값 하나 때문에 리포트 전체를 죽이지 않는다. 해당 필드만 `null` 이 되고 나머지는 나간다.

### NaN 은 정상일 때도 나온다

**버그가 아니라 상태다.** 없애려 들지 말고 **"모른다"로 표시**하라.

| 값 | 언제 | 무슨 뜻 |
|---|---|---|
| EKF `vel`/`pos` 비율 NaN | 추정기 수렴 전 | 정상. **Position·Mission 이 안 선다** |
| `mag_corr` NaN | 자기장 표준편차 0 → 0/0 | 상관을 못 낸다 |
| 진동 3축 정확히 0.0 | 메시지가 아직 안 참 | **"완벽"이 아니다** |

🔴 **NaN 을 임계값과 비교하지 마라.** `NaN > 1.0` 은 `False` 라서 **모든 비교가
통과로 떨어진다** — 도구가 모르는 값을 안전하다고 말하게 된다 (2026-09-06 실측).

```python
# ❌ NaN 이면 조용히 통과
if ratio > 1.0: warn()

# ✅ 모르는 것과 정상인 것을 가른다
if ratio is None or math.isnan(ratio):
    note('추정기 미수렴 — 이 상태로는 Position·Mission 이 안 선다')
elif ratio > 1.0:
    warn()
```

---

## 4. 파일이 정말 깨졌을 때

§1 의 1단계에서 예외가 났을 때만 해당한다.

### 꼬리 잘림 — 흔하고, 대개 앞부분은 살아 있다

```
파싱 실패: 꼬리 37906바이트 잘림 (전원 급단) — 앞 구간은 정상
```

비행 중 배터리가 빠지거나 커넥터가 순간 떨어지면 마지막 블록이 안 닫힌다.
**앞 구간 데이터는 유효하다.** `qgclog._repair()` 가 같은 디렉토리의 **형제 로그**를
기증자로 써서 정의 구간을 복구한다.

🔴 **그래서 로그는 `logs/` 에 평면으로 쌓는다.** 날짜 하위폴더를 만들면
`_repair()` 가 기증자를 못 찾는다.

### 전송 손상 — SD 카드 탓이 아니다

**받을 때마다 내용이 다르면 MAVFTP 전송 문제다.** 2026-09-06 에 "SD 카드를 교체해야
한다"고 결론 냈는데 **틀렸다** (2026-09-09 정정). FC 가 낸 CRC 는 4회 전부 같았다 —
카드는 일관된 데이터를 낸다. 손상은 512바이트 블록 단위로 전송 중에 생긴다.

```bash
./shade01 sync --verify     # 5회씩 받아 바이트 다수결. 시간 5배
```

서로 다른 4회 시행이 바이트 단위로 같은 결과를 냈고, 복원본 CRC 가 FC 값과 일치했다.

---

## 5. 로그를 지우기 전에

🔴 **`.ulg` 삭제는 되돌릴 수 없다.** `.gitignore` 라 git 에도 없고, 리포의 문서가
유일한 영구 기록이다.

**다음을 전부 확인하기 전에는 지우지 마라:**

1. §1 의 1~4단계를 다 밟았나
2. 파서가 정말 예외를 내나 (JSON 직렬화 실패가 아니라)
3. `--verify` 로 다시 받아 봤나 (전송 손상일 수 있다)
4. 앞 구간이라도 살릴 수 있나 (`_repair`)
5. **사용자가 지우라고 명시했나**

`unreadable` 판정은 **서버가 렌더 못 한다는 뜻**이지 파일이 쓸모없다는 뜻이 아니다.

---

## 6. 스킬·명령을 실행할 때

`shade01-log`·`shade01-sync`·`shade01-live` 는 전부 이 문서의 규칙 위에 있다.

| 하려는 것 | 쓸 것 | 직접 하지 말 것 |
|---|---|---|
| 로그 분석 | `./shade01 log <N>` | `pyulog` 직접 호출 |
| 로그 목록 | `./shade01 log list` | 디렉토리 직접 훑기 |
| 웹 업로드 | `./shade01 sync` | 수동 scp |
| 실시간 | `./shade01 live` | — |
| 비행 전 점검 | `./shade01 test` | 파라미터 하나씩 읽기 |

**도구가 실패하면 도구를 고쳐라.** 우회 스크립트를 새로 짜면 그 스크립트가
`_patch_pyulog()` 를 안 걸어서 §2 철칙 1 을 다시 밟는다 — 실제로 그렇게 물렸다.

---

## 7. 고친 뒤 확인

파싱·직렬화를 건드렸으면 **아래를 전부 통과해야 배포한다.**

```bash
# 1) 대표 로그 몇 개가 여전히 읽히는가 (회귀)
for f in logs/2026-09-09_08_20_57.ulg logs/2026-09-05_09_24_04.ulg; do
  .venv/bin/python web/extract.py row "$f" | python3 -c "
import sys,json; s=sys.stdin.read(); d=json.loads(s)
print('%-34s OK badge=%s NaN없음=%s' % ('$f'.split('/')[-1], d['row'].get('badge'), 'NaN' not in s))"
done

# 2) 서버쪽 자체검사
.venv/bin/python web/live/_selftest.py         # FAIL 0

# 3) 배포 후 실제 웹에서 error 필드가 비었는지
curl -s https://shade01.bewe.co.kr/api/logs | python3 -c "
import sys,json
d=json.load(sys.stdin); rows = d if isinstance(d,list) else d.get('logs',d)
bad=[r['name'] for r in rows if isinstance(r,dict) and r.get('error')]
print('오류 있는 로그:', bad or '없음')"
```

⚠️ **파서를 고치면 캐시 지문이 바뀌어 서버가 전체를 다시 굽는다.** 배포 직후
502 가 잠깐 나는 것은 실패가 아니라 준비 중이다 (실측 로그 67개에 약 7초).

---

## 관련 문서

| 파일 | 무엇 |
|---|---|
| [`PROCEDURE.md`](PROCEDURE.md) | 로그 수집 → 분석 → 기록 전체 절차 |
| [`FLIGHT-SYNC.md`](FLIGHT-SYNC.md) | 전송 손상·`--verify` 상세 |
| [`tools/qgclog/README.md`](tools/qgclog/README.md) | 분석기 임계값과 판정 |
| [`web/README.md`](web/README.md) | 서버 캐시·배포 |
| [`web/live/README.md`](web/live/README.md) | `.tlog` 기록 기준 |
