#!/usr/bin/env python3
"""이번에 받은 파일에만 FC 엔트리 번호를 붙인다.

    number_new.py <entries.json> <logdir> <파일이름> [...]
    number_new.py fce.json logs 2026-09-05_09_24_04.ulg

`fclist.py --map DIR --apply` 는 **디렉토리 전체**를 개명한다. 그러면 두 가지가
깨진다:

1. **서버 이름과 어긋난다.** 정본 보관소는 예전 이름을 그대로 갖고 있는데
   로컬만 바뀌면, 이름으로 대조하는 증분·정리 로직이 전부 헛돈다.
2. **중복쌍에서 충돌한다.** 같은 비행이 두 이름으로 있는 경우
   (`2026-08-25_09_29_03.ulg` = `log_108_…`), 한쪽을 개명하려 하면 상대 이름이
   이미 있어 `fclist` 가 **전체를 취소한다** — 실측으로 물렸다.

그래서 여기서는 **이번에 새로 받은 파일만** 건드린다. 그 파일들은 아직 어디에도
안 올라갔으므로 이름을 바꿔도 어긋날 상대가 없다.

🔴 판정은 `fclist.match()` 를 그대로 쓴다 — 크기 우선 대조다. 기준을 새로
   세우면 `fclist` 와 다른 번호를 붙이게 된다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'qgclog'))

import fclist                                              # noqa: E402
import lognum as LN                                        # noqa: E402


def main():
    # --out FILE 을 주면 **최종 이름**을 한 줄씩 쓴다 (개명됐든 아니든).
    # 부르는 쪽이 뒤에서 그 파일들을 다시 찾아야 하기 때문이다 — 옛 이름으로
    # 찾으면 "판정할 파일이 없다" 가 된다 (실측으로 물렸다).
    args = sys.argv[1:]
    out_path = None
    if '--out' in args:
        i = args.index('--out')
        out_path = args[i + 1]
        del args[i:i + 2]
    if len(args) < 3:
        sys.exit('사용법: number_new.py [--out FILE] <entries.json> <logdir> <파일이름> [...]')
    import json
    with open(args[0]) as fh:
        entries = json.load(fh)
    d = args[1]
    targets = [os.path.basename(x) for x in args[2:]]
    targets = [t for t in targets if os.path.exists(os.path.join(d, t))]
    if not targets:
        print('번호를 붙일 파일이 없다.')
        return

    # 대조는 디렉토리 전체를 놓고 한다 — 크기가 같은 다른 로그가 있으면
    # `match()` 가 그것도 보고 판단해야 옳은 짝을 고른다.
    facts = LN.scan(d)
    hit = fclist.match(entries, facts, log_dir=d)

    moves = []
    for f in facts:
        n = f['name']
        if n not in targets or n not in hit or not f['end']:
            continue
        num, why = hit[n]
        if why != 'size':
            # 🔴 크기까지 안 맞으면 개명하지 않는다. 시각만으로는 같은 크기의
            #    다른 로그와 헷갈릴 수 있고, 틀린 번호는 없는 번호보다 나쁘다.
            print('  ? %-34s 시각만 일치(%d) — 그대로 둔다' % (n, num))
            continue
        new = LN.qgc_name(num, f['end'])
        if new == n:
            continue
        if os.path.exists(os.path.join(d, new)):
            print('  ? %-34s → %s 가 이미 있다 — 그대로 둔다' % (n, new))
            continue
        moves.append((n, new, num))

    final = {t: t for t in targets}
    for old, new, num in moves:
        os.rename(os.path.join(d, old), os.path.join(d, new))
        final[old] = new
        print('  %-34s → %s' % (old, new))
    print('바꿀 이름이 없다.' if not moves else '%d개에 번호를 붙였다.' % len(moves))
    if out_path:
        with open(out_path, 'w') as fh:
            for t in targets:
                fh.write(final[t] + '\n')


if __name__ == '__main__':
    main()
