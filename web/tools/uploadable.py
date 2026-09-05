#!/usr/bin/env python3
"""정본 서버에 올릴 값이 있는 로그인지 가른다.

    uploadable.py <path.ulg> [...]        →  <판정><TAB><사유><TAB><경로>

판정은 `skip` 또는 `keep` 이다. 한 줄에 하나씩, 인자 순서대로 낸다.

## 무엇을 막나

| 사유 | 뜻 |
|---|---|
| `unreadable` | 서버가 이 파일을 렌더하지 못한다 — 목록에 회색 줄만 남는다 |
| `abort` | arm 하자마자 disarm (`classify()` 기준 6초 이하) |
| `indoor` | GPS 가 붙어 있는데 **한 번도 측위를 못 했다** — 실내다 |

`ground`·`hover`·`noarm`·`unknown` 은 **올린다.** 지상 시험도 진동·전류 점검에
쓰이고, 나중에 되돌아볼 수 있어야 한다.

## 🔴 판정은 서버가 실제로 도는 경로를 그대로 태운다

`summarize()` 만 불러 보고 통과시키면 안 된다. 서버는 `extract.py full` 을 돌리고,
**요약이 멀쩡해도 `build_track()` 에서 터지는 로그가 있다** (실측 2026-09-05:
`SP` 미정의로 6개가 회색 행이 됐는데 `row` 모드로는 전부 정상으로 보였다).
여기서 같은 함수들을 같은 순서로 부르는 이유가 그것이다.

🔴 `pyulog` 를 직접 부르지 않는다 — 잘린 메시지에서 조용히 멈춘다
   (PROCEDURE.md "분석기 — 잘린 메시지에서 멈추지 않는다").
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'web'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'qgclog'))

import extract                                            # noqa: E402
import qgclog                                             # noqa: E402

# 이 배지가 붙으면 올리지 않는다. extract.classify() 가 내는 값이다.
SKIP_BADGES = {'abort'}

# GPS fix_type 은 0~8 이다 (MAVLink GPS_FIX_TYPE). 그 밖의 값은 깨진 바이트다 —
# 실측: log_182 는 1584샘플이 4(RTK)인데 한 샘플만 215 였다. 유효값만 본다.
_FIX_MAX_VALID = 8

# 3D fix. 이것을 한 번도 못 잡았으면 하늘이 안 보이는 곳에 있었다는 뜻이다.
_FIX_3D = 3

# PX4 는 펌웨어에 따라 토픽 이름이 다르다. 둘 다 봐야 한다 —
# `sensor_gps` 만 보면 9/2 의 실제 야외 비행(log_182·log_186)이 "GPS 없음"으로
# 잡힌다. 실측으로 확인했다.
_GPS_TOPICS = ('sensor_gps', 'vehicle_gps_position')


def gps_verdict(ulog):
    """(실내인가, 사유). 판단할 근거가 없으면 (False, 사유) 로 둔다."""
    data = {x.name: x for x in ulog.data_list}
    g = None
    for name in _GPS_TOPICS:
        if name in data:
            g = data[name]
            break
    if g is None or 'fix_type' not in g.data:
        # GPS 토픽이 아예 없다. **실내라고 단정하지 않는다** — 너무 짧아
        # 한 번도 발행되지 않았을 수 있다 (실측: 9/5 야외 세션의 1.5초 로그).
        return False, 'gps 근거 없음'
    fix = np.asarray(g.data['fix_type'])
    fix = fix[(fix >= 0) & (fix <= _FIX_MAX_VALID)]
    if fix.size == 0:
        return False, 'gps 값이 전부 깨짐'
    if int(fix.max()) < _FIX_3D:
        return True, 'indoor: fix 최대 %d (3D 못 잡음)' % int(fix.max())
    return False, 'fix %d' % int(fix.max())


def verdict(path):
    """(skip|keep, 사유). 판정에 실패하면 올리는 쪽으로 기운다."""
    try:
        rep, _ = extract.summarize(path)
    except qgclog.LogUnreadable as exc:
        return 'skip', 'unreadable: %s' % exc
    except Exception as exc:                              # noqa: BLE001
        return 'skip', 'unreadable: %s: %s' % (type(exc).__name__, exc)

    # 서버가 도는 나머지 절반. 여기서 터지면 목록에 회색 줄이 된다.
    try:
        ulog, _ = qgclog._load(path)
        t0, t1, _armed = extract.armed_window(ulog)
        extract.flight_key(ulog, t0, t1)
        extract.decoded_points(ulog)
        extract.build_track(ulog, t0, t1)
    except Exception as exc:                              # noqa: BLE001
        return 'skip', 'unreadable(full): %s: %s' % (type(exc).__name__, exc)

    try:
        indoor, why = gps_verdict(ulog)
    except Exception as exc:                              # noqa: BLE001
        indoor, why = False, 'gps 판정 실패(%s)' % type(exc).__name__
    if indoor:
        return 'skip', why

    # classify() 는 row 를 받는다 — 판정에 쓰는 네 값만 채워 준다.
    row = {
        'armed': rep.get('armed'),
        'duration': rep.get('duration'),
        'alt_max': rep.get('alt_max'),
        'speed_max': rep.get('speed_max'),
    }
    try:
        badge = extract.classify(row)
    except Exception as exc:                              # noqa: BLE001
        # 🔴 판정이 터지면 **올린다.** 막는 쪽으로 기울면 멀쩡한 비행이
        #    조용히 사라진다 — 서버가 정본 보관소다.
        return 'keep', 'classify 실패(%s) — 올린다' % type(exc).__name__
    if badge in SKIP_BADGES:
        return 'skip', badge
    return 'keep', badge


def main():
    if len(sys.argv) < 2:
        sys.exit('사용법: uploadable.py <path.ulg> [...]')
    for path in sys.argv[1:]:
        try:
            v, why = verdict(path)
        except Exception as exc:                          # noqa: BLE001
            v, why = 'keep', '판정 불가(%s) — 올린다' % type(exc).__name__
        print('%s\t%s\t%s' % (v, why, path), flush=True)


if __name__ == '__main__':
    main()
