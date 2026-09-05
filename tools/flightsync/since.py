#!/usr/bin/env python3
"""서버가 가진 마지막 로그 시각(UTC)을 구하고, FC 목록을 그 뒤로 자른다.

    since.py cutoff  < 서버파일명들          →  YYYY-MM-DD HH:MM:SS  (UTC)
    since.py pick <cutoff> < FC목록          →  받을 것만 걸러 낸다

FC 목록은 `이름<TAB>MB<TAB>UTC폴더` 한 줄씩 (flightsync 가 만드는 형식).

## 🔴 시간대가 형식마다 다르다

파일명이 두 가지고 **기준 시간대가 서로 다르다** — 섞어 읽으면 같은 비행이
9시간 어긋난 두 줄이 된다 (`qgclog._time_from_name` 이 같은 함정을 다룬다):

| 형식 | 시간대 | 예 |
|---|---|---|
| `YYYY-MM-DD_HH_MM_SS.ulg` | **UTC** — FC SD 에서 그대로 | `2026-09-05_09_24_04.ulg` |
| `log_<n>_YYYY-M-D-H-M-S.ulg` | **KST** — QGC 가 붙인 이름 | `log_184_2026-9-2-17-57-06.ulg` |

FC 안은 `/fs/microsd/log/<UTC날짜>/<UTC시각>.ulg` 이므로 **전부 UTC 로 맞춰**
비교한다. QGC 형식은 9시간을 빼서 UTC 로 만든다.

⚠️ 서버 API 의 `utc` 필드는 이름과 달리 **KST** 다. 그래서 API 대신 **파일명**을
쓴다 — 파일명이 FC 경로와 같은 기준이라 변환이 한 번뿐이다.
"""
import datetime as dt
import re
import sys

KST_OFFSET = dt.timedelta(hours=9)

# FC SD 에서 그대로 가져온 이름 — UTC
_FC = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})_(\d{2})_(\d{2})\.ulg$")
# QGC 가 붙인 이름 — KST
_QGC = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})")


def utc_of(name):
    """파일명에서 UTC datetime 을 뽑는다. 못 읽으면 None."""
    m = _FC.match(name.strip())
    if m:
        try:
            return dt.datetime(*(int(x) for x in m.groups()))
        except ValueError:
            return None
    m = _QGC.search(name)
    if m:
        try:
            return dt.datetime(*(int(x) for x in m.groups())) - KST_OFFSET
        except ValueError:
            return None
    return None


def cmd_cutoff(lines):
    stamps = [t for t in (utc_of(n) for n in lines if n.strip()) if t]
    if not stamps:
        # 서버가 비어 있으면 자르지 않는다 — 전부 후보다.
        print("")
        return
    print(max(stamps).strftime("%Y-%m-%d %H:%M:%S"))


def cmd_pick(cutoff_s, lines):
    """FC 목록에서 cutoff 보다 **뒤**인 것만 낸다. 형식은 그대로 유지한다."""
    cutoff = None
    if cutoff_s.strip():
        cutoff = dt.datetime.strptime(cutoff_s.strip(), "%Y-%m-%d %H:%M:%S")
    for line in lines:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, _mb, d = parts[0], parts[1], parts[2]
        # FC 안의 이름은 `HH_MM_SS.ulg`, 폴더가 날짜다. 합쳐서 판정한다.
        t = utc_of("%s_%s" % (d, name))
        if t is None:
            # 읽을 수 없으면 **버리지 않는다.** 새 비행을 조용히 놓치는 것이
            # 이 도구의 가장 나쁜 실패다.
            print(line)
            continue
        if cutoff is None or t > cutoff:
            print(line)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("cutoff", "pick"):
        sys.exit("사용법: since.py cutoff | since.py pick <YYYY-MM-DD HH:MM:SS>")
    lines = sys.stdin.read().splitlines()
    if sys.argv[1] == "cutoff":
        cmd_cutoff(lines)
    else:
        cmd_pick(sys.argv[2] if len(sys.argv) > 2 else "", lines)


if __name__ == "__main__":
    main()
