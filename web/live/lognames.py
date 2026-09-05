#!/usr/bin/env python3
"""로그 파일에 **QGC 와 같은 이름**을 매긴다.

목록에 두 이름 체계가 섞여 있었다. QGC 가 MAVFTP 로 받은 것은
`log_129_2026-8-31-18-46-02.ulg` 이고, 우리 도구가 받은 것은
`2026-08-31_09_38_28.ulg` 다. 같은 비행이 두 얼굴로 뜨니 목록에서 순서도
번호도 읽히지 않았다.

**QGC 이름이 정답이다.** 그쪽이 FC 가 발급한 세션 번호를 들고 있고, 그
번호가 이 기체의 비행을 세는 유일한 통번호다.

    from lognames import assign
    tbl = assign(['log_129_2026-8-31-18-46-02.ulg', '2026-08-25_09_07_09.ulg'])
    tbl['2026-08-25_09_07_09.ulg']      # ('log_95_2026-8-25-18-08-07.ulg', 95, True)

## QGC 규칙 (소스가 없어 정본 30개에서 역산했다 — 2026-09-06)

```
log_<엔트리ID>_<종료시각 KST>.ulg
     └ 0패딩 없음   └ %d-%d-%d-%02d-%02d-%02d
```

🔴 **시각은 로그가 _끝난_ 때다.** 시작이 아니다. 정본 10개에서 로그 마지막
   표본의 UTC 를 KST 로 옮긴 값과 ±2초로 일치했다. 시작 시각으로 잘못 짚으면
   번호 배정이 구간마다 한 칸씩 밀려 어긋난다 (실제로 그렇게 겪었다).

🔴 **`.ulg` 안에는 세션 번호가 없다.** `msg_info_dict` 를 다 뒤져도 없다 —
   번호는 FC SD 의 파일명에만 있고, QGC 를 거치지 않고 받은 로그는 그것을
   영영 잃었다. 그래서 아래처럼 **추론**한다.

## 번호를 모르는 로그에 번호를 주는 법

정본 30개에서 확인했다: **번호는 종료시각 순서와 단조 일치한다** (77→187 이
8/22→9/2 순서 그대로). 그러므로 번호를 아는 로그 사이의 빈 번호에, 번호를
모르는 로그를 종료시각 순으로 끼우면 된다.

빈칸이 모자라면 그 구간에는 지상 테스트나 중복이 섞여 있다는 뜻이다 —
실제로 그렇게 해서 지상 로그 9개와 중복 2쌍을 찾아냈다 (2026-09-06).
그래도 모자라면 소숫점을 붙인다 (`log_94.1`). 거짓 번호를 만들지 않는다.

⚠️ **추론한 번호는 `exact=False` 로 표시된다.** FC 가 실제로 준 번호와 같다는
   보장이 없다 — 그 구간에서 FC 가 발급했으나 우리가 못 받은 로그가 있으면
   한 칸씩 밀린다. 화면은 이것을 흐리게 그려 사실대로 말한다.
"""

import datetime
import os
import re

# QGC 가 붙인 이름. 월·일·시각에 0 패딩이 없다 (`2026-8-31-18-46-02`).
QGC_NAME = re.compile(
    r'^log_(\d+)_(\d{4})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})\.ulg$')

# 우리 도구(`qgclog` 회수)가 붙인 이름. **UTC** 다 — QGC 이름이 KST 인 것과
# 9시간 어긋난다. 이 차이를 안 맞추면 번호가 통째로 밀린다.
UTC_NAME = re.compile(r'^(\d{4})-(\d{2})-(\d{2})_(\d{2})_(\d{2})_(\d{2})\.ulg$')

# `_repair()` 가 살려낸 것. 원본 이름을 잃어 시각 조각만 남았다.
RECOVERED = re.compile(r'^RECOVERED(\d*)_(\d{2})_(\d{2})_(\d{2})\.ulg$')

KST = datetime.timezone(datetime.timedelta(hours=9))


def qgc_name(num, end_kst, suffix=''):
    """번호와 종료시각(KST, naive)으로 QGC 형식 이름을 만든다."""
    return 'log_%s%s_%d-%d-%d-%02d-%02d-%02d.ulg' % (
        num, suffix, end_kst.year, end_kst.month, end_kst.day,
        end_kst.hour, end_kst.minute, end_kst.second)


def parse(name):
    """파일명 → (번호 또는 None, 종료시각 KST 또는 None, 종류).

    종류는 'qgc' | 'utc' | 'recovered' | '?'.

    ⚠️ `utc` 이름의 시각은 **시작** 시각이다. QGC 이름의 **종료** 시각과 직접
       비교하면 안 된다 — 로그를 열어 실제 종료 시각을 재야 한다
       (`end_time()`). 여기서 돌려주는 값은 로그를 못 열 때의 차선책이다.
    """
    m = QGC_NAME.match(name)
    if m:
        num = int(m.group(1))
        y, mo, d, h, mi, s = (int(x) for x in m.groups()[1:])
        return num, datetime.datetime(y, mo, d, h, mi, s), 'qgc'
    m = UTC_NAME.match(name)
    if m:
        y, mo, d, h, mi, s = (int(x) for x in m.groups())
        u = datetime.datetime(y, mo, d, h, mi, s, tzinfo=datetime.timezone.utc)
        return None, u.astimezone(KST).replace(tzinfo=None), 'utc'
    if RECOVERED.match(name):
        return None, None, 'recovered'
    return None, None, '?'


def end_time(path):
    """로그를 열어 **끝난 시각**(KST, naive)을 잰다. 못 재면 None.

    QGC 이름이 쓰는 바로 그 시각이다. `boot_time_utc_us` 에 마지막 표본의
    상대 timestamp 를 더하면 절대 UTC 가 나온다.

    🔴 `pyulog` 를 직접 부르지 않는다 — `qgclog._load()` 를 거친다 (잘린
       로그에서 조용히 멈춘다. CLAUDE.md 「pyulog 를 직접 부르지 마라」).
    """
    import qgclog as Q
    try:
        ulog, _ = Q._load(path)
    except Exception:
        return None
    bt = ulog.msg_info_dict.get('boot_time_utc_us')
    if not bt:
        return None
    last = None
    for d in ulog.data_list:
        ts = d.data.get('timestamp')
        if ts is not None and len(ts):
            last = ts[-1] if last is None else max(last, ts[-1])
    if last is None:
        return None
    utc = datetime.datetime.fromtimestamp((bt + last) / 1e6, datetime.timezone.utc)
    return utc.astimezone(KST).replace(tzinfo=None)


def assign(names, end_of=None):
    """이름 목록 → {원래이름: (표시이름, 번호, exact)}.

    `end_of(name)` 은 그 로그의 실제 종료시각을 주는 함수다. 없으면 파일명에서
    읽은 시각을 쓴다 — `utc` 이름은 시작 시각이라 부정확하지만, 로그를 열지
    않고도 목록이 뜨는 것이 우선인 자리가 있다.

    exact=True 면 FC 가 준 번호, False 면 빈칸에서 추론한 번호다.
    """
    known, unknown, odd = [], [], []
    for n in names:
        num, t, kind = parse(n)
        if kind == 'qgc':
            known.append((t, num, n))
        elif kind == 'utc':
            unknown.append((n, t))
        else:
            odd.append(n)

    # 종료시각을 실제로 잴 수 있으면 그것으로 바꾼다. QGC 이름의 시각은 이미
    # 종료시각이므로 건드리지 않는다 — 그쪽이 이 규칙의 기준이다.
    if end_of is not None:
        unknown = [(n, end_of(n) or t) for n, t in unknown]

    known.sort(key=lambda x: (x[0] is None, x[0]))
    unknown.sort(key=lambda x: (x[1] is None, x[1]))
    used = {k[1] for k in known}

    out = {}
    for t, num, n in known:
        out[n] = (n, num, True)          # 이미 정답이다. 그대로 둔다.

    # 구간마다 빈 번호를 시각순으로 나눠 준다.
    buckets = {}
    for n, t in unknown:
        if t is None:
            odd.append(n)
            continue
        before = [k for k in known if k[0] and k[0] <= t]
        after = [k for k in known if k[0] and k[0] > t]
        lo = before[-1][1] if before else 0
        hi = after[0][1] if after else None
        buckets.setdefault((lo, hi), []).append((t, n))

    for (lo, hi), items in buckets.items():
        items.sort()
        top = hi if hi is not None else lo + len(items) + 1
        free = [i for i in range(lo + 1, top) if i not in used]
        for k, (t, n) in enumerate(items):
            if k < len(free):
                out[n] = (qgc_name(free[k], t), free[k], False)
            else:
                # 빈칸이 모자라다. 앞 번호에 소숫점을 붙여 **번호를 지어내지
                # 않는다** — 이 자리에 FC 번호가 무엇이었는지는 알 수 없다.
                base = free[-1] if free else lo
                out[n] = (qgc_name(base, t, '.%d' % (k - len(free) + 1)), base, False)

    # 복구본은 **원본과 같은 이름**을 받는다. `_repair()` 가 살려낸 같은
    # 비행이므로 목록에서 나란히 서야 한다 — 복구본이라는 사실은 이름이
    # 아니라 배지로 말한다 (사용자 지시 2026-09-06).
    #
    # 짝은 종료시각으로 찾는다. 이름의 `09_09_49` 는 원본 시각의 조각이지만
    # 그것만으로는 날짜를 모른다 — 로그를 열어 잰 종료시각이 유일한 근거다.
    ends = {}
    for n, res in out.items():
        t = None
        if end_of is not None:
            t = end_of(n)
        if t is None:
            _, t, _k = parse(n)
        if t is not None:
            ends.setdefault(t.replace(microsecond=0), res)

    for n in odd:
        t = end_of(n) if end_of is not None else None
        mate = ends.get(t.replace(microsecond=0)) if t else None
        if mate:
            # 원본과 같은 표시이름·번호. exact 는 원본을 따른다.
            out[n] = (mate[0], mate[1], mate[2])
        else:
            # 짝을 못 찾았다. 이름을 지어내지 않는다.
            out[n] = (n, None, False)
    return out


if __name__ == '__main__':
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else 'logs'
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    '..', '..', 'tools', 'qgclog'))
    names = sorted(n for n in os.listdir(d) if n.endswith('.ulg'))
    tbl = assign(names, end_of=lambda n: end_time(os.path.join(d, n)))
    for n in names:
        disp, num, exact = tbl[n]
        mark = ' ' if exact else '~'
        print('%s %-40s %s' % (mark, n, disp if disp != n else ''))
