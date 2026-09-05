#!/usr/bin/env python3
"""FC 가 가진 로그 중 **랩서버에 없는 것**을 고른다.

    since.py pick <서버목록> <삭제기록> < FC목록     →  받을 것만 낸다
    since.py utc  < 이름들                          →  이름별 UTC 시각 (점검용)

FC 목록은 `이름<TAB>MB<TAB>UTC폴더` 한 줄씩 (flightsync 가 만드는 형식).
서버목록·삭제기록은 파일 경로다. 없으면 빈 것으로 본다.

## 🔴 왜 "마지막 로그 이후" 가 아니라 "없는 것" 인가

시각 cutoff 는 **구멍을 못 본다.** 중간의 한 편이 어떤 이유로 빠졌으면
(업로드 실패, 손으로 지움) 영영 안 올라간다. 집합 차이는 그것을 잡는다.

## 🔴 지운 것은 다시 안 가져온다

`--prune` 이 야외 비행이 아니라고 판정해 지운 로그는 **삭제 기록**에 남는다.
그것이 없으면 다음 sync 가 "서버에 없네" 하고 다시 받아오고, prune 이 다시
지우는 일이 무한히 반복된다.

**번호는 그대로 둔다 — 지운 자리를 메우지 않는다.** 번호는 FC 가 매기는
비행 일련번호라 우리가 채울 수 있는 것도 아니고, 구멍이 있는 편이 정직하다.

## 🔴 같은 로그를 어떻게 알아보나

이름이 세 형식이라 이름만으로는 못 맞춘다:

| 형식 | 시간대 | 예 |
|---|---|---|
| `YYYY-MM-DD_HH_MM_SS.ulg` | **UTC** — FC 에서 그대로 | `2026-09-05_09_24_04.ulg` |
| `log_<n>_YYYY-M-D-H-M-S.ulg` | **KST** — 번호가 붙은 뒤 | `log_244_2026-9-5-18-31-28.ulg` |
| 그 밖 (`RECOVERED*` 등) | — | 손으로 만든 것 |

그래서 **UTC 시각**으로 맞춘다. FC 이름은 그대로, QGC 이름은 9시간을 빼서.

⚠️ **QGC 이름의 시각은 로그가 _끝난_ 때**이고 FC 폴더의 이름은 _시작_ 때다.
   그래서 같은 로그라도 몇 초~몇 분 어긋난다. 창을 두고 맞춘다
   (`_MATCH_WINDOW_S`). 비행이 그보다 촘촘히 이어지는 일은 없다 —
   FC 가 로그를 닫고 다시 여는 데도 시간이 걸린다.
"""
import datetime as dt
import os
import re
import sys

KST_OFFSET = dt.timedelta(hours=9)

# FC SD 에서 그대로 가져온 이름 — UTC, 로그 **시작** 시각
_FC = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})_(\d{2})_(\d{2})\.ulg$")
# 번호가 붙은 이름 — KST, 로그 **종료** 시각
_QGC = re.compile(r"^log_(\d+)_(\d{4})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})\.ulg$")

# 시작시각과 종료시각의 차이를 흡수하는 창. 실측된 가장 긴 비행이 443초이므로
# 그보다 넉넉히 잡되, 비행 사이 간격(가장 짧았던 것이 약 14초)보다는 짧아야
# 다른 로그를 잘못 물지 않는다 — 그 둘 사이에서 고른다.
#
# ⚠️ 창을 넓히면 이웃 로그를 같은 것으로 오인해 **새 비행을 안 받는다.**
#    좁히면 이미 있는 것을 또 받는다 (그쪽이 덜 나쁘다).
_MATCH_WINDOW_S = 900


def parse(name):
    """(UTC datetime, 번호 or None). 못 읽으면 (None, None)."""
    n = name.strip()
    m = _FC.match(n)
    if m:
        try:
            return dt.datetime(*(int(x) for x in m.groups())), None
        except ValueError:
            return None, None
    m = _QGC.match(n)
    if m:
        g = m.groups()
        try:
            return dt.datetime(*(int(x) for x in g[1:])) - KST_OFFSET, int(g[0])
        except ValueError:
            return None, None
    return None, None


def load_names(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as fh:
        return [l.strip() for l in fh if l.strip()]


def known_times(names):
    """이미 아는 로그들의 UTC 시각 목록. 못 읽는 이름은 버린다.

    ⚠️ 못 읽는 이름(`RECOVERED*`)을 버리는 쪽이 맞다 — 그것 때문에 FC 의 새
       로그를 "이미 있다" 고 오인하는 것보다, 한 번 더 받는 편이 낫다.
    """
    out = []
    for n in names:
        t, _num = parse(n)
        if t:
            out.append(t)
    return out


def cmd_pick(server_file, pruned_file, lines):
    known = known_times(load_names(server_file)) + known_times(load_names(pruned_file))
    for line in lines:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, _mb, d = parts[0], parts[1], parts[2]
        t, _ = parse("%s_%s" % (d, name))
        if t is None:
            # 🔴 읽을 수 없으면 **받는다.** 새 비행을 조용히 놓치는 것이
            #    이 도구의 가장 나쁜 실패다.
            print(line)
            continue
        if any(abs((t - k).total_seconds()) <= _MATCH_WINDOW_S for k in known):
            continue                      # 서버에 있거나, 판정 끝나 지운 것
        print(line)


def cmd_utc(lines):
    for n in lines:
        if not n.strip():
            continue
        t, num = parse(n)
        print("%s\t%s\t%s" % (n.strip(), t.isoformat() if t else "-",
                              num if num is not None else "-"))


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("pick", "utc"):
        sys.exit("사용법: since.py pick <서버목록> <삭제기록> | since.py utc")
    lines = sys.stdin.read().splitlines()
    if sys.argv[1] == "utc":
        cmd_utc(lines)
    else:
        cmd_pick(sys.argv[2] if len(sys.argv) > 2 else "",
                 sys.argv[3] if len(sys.argv) > 3 else "",
                 lines)


if __name__ == "__main__":
    main()
