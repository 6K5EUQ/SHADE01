#!/usr/bin/env python3
"""정본 서버에 올릴 값이 있는 로그인지 가른다.

    uploadable.py <path.ulg> [...]        →  <판정><TAB><사유><TAB><경로>

판정은 `skip` 또는 `keep` 이다. 한 줄에 하나씩, 인자 순서대로 낸다.

## 무엇을 막나

두 가지다 — 둘 다 **서버에 올려 봐야 볼 것이 없는** 파일이다.

| 사유 | 뜻 |
|---|---|
| `unreadable` | 파싱이 안 된다. 목록에 회색 줄만 남는다 |
| `abort` | arm 하자마자 disarm (`classify()` 기준 6초 이하) |

`ground`·`hover`·`noarm`·`unknown` 은 **올린다.** 지상 시험도 진동·전류 점검에
쓰이고, 나중에 되돌아볼 수 있어야 한다.

## 왜 web/extract.py 의 판정을 그대로 쓰나

서버 목록의 배지가 그 함수로 만들어진다. 여기서 기준을 새로 세우면 "목록에
`abort` 로 보이는데 올라와 있는" 어긋남이 생긴다. 판정은 한 곳에만 둔다.

🔴 `pyulog` 를 직접 부르지 않는다 — 잘린 메시지에서 조용히 멈춘다
   (PROCEDURE.md "분석기 — 잘린 메시지에서 멈추지 않는다").
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'web'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'qgclog'))

import extract                                            # noqa: E402
import qgclog                                             # noqa: E402

# 이 배지가 붙으면 올리지 않는다. extract.classify() 가 내는 값이다.
SKIP_BADGES = {'abort'}


def verdict(path):
    """(skip|keep, 사유) 를 낸다. 판정에 실패하면 올리는 쪽으로 기운다."""
    try:
        rep, _ = extract.summarize(path)
    except qgclog.LogUnreadable as exc:
        return 'skip', 'unreadable: %s' % exc
    except Exception as exc:                              # noqa: BLE001
        return 'skip', 'unreadable: %s: %s' % (type(exc).__name__, exc)

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
