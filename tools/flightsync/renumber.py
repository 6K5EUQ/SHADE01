#!/usr/bin/env python3
"""랩서버의 로그를 FC 비행번호 이름으로 통일한다. **서버에서 돈다.**

    renumber.py <entries.json> <logdir> [--dry]

`fclist.py --map --apply` 와 다른 점은 **충돌을 해소한다**는 것이다.

## 🔴 충돌은 오류가 아니라 중복이다

번호를 붙이려는 이름이 이미 있으면, 그 비행은 **이미 번호가 붙어 서버에 있다.**
지금 이름을 바꾸려는 쪽은 같은 비행을 한 번 더 받아 온 사본이다. `fclist` 는
이때 **전체를 취소**하는데 (반쯤 하다 멈추는 것보다 낫다는 판단), 그러면 나머지
로그도 영영 번호를 못 받는다 — 실측으로 그 상태에 갇혔다.

여기서는 **번호가 없는 쪽을 지운다.** 이미 번호가 붙은 것이 정본이다.

⚠️ 지운 것은 부르는 쪽이 삭제 기록에 남겨야 한다. 안 그러면 다음 sync 가 또
   받아 온다. 그래서 지운 이름을 `DELETED\\t<이름>` 으로 출력한다.

## 이름이 안 붙는 것

- **`REF_*`** — 웹에서 비교용으로 받은 참조 로그. FC 엔트리가 없다. 그대로 둔다
- 크기가 어느 엔트리와도 안 맞는 것 — 시각만 맞는 짝은 **믿지 않는다**.
  틀린 번호는 없는 번호보다 나쁘다

🔴 짝짓기는 `fclist.match()` 를 그대로 쓴다 — 크기 우선이다. 기준을 새로 세우면
   `fclist` 와 다른 번호를 붙이게 된다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(HERE, '..', 'qgclog'),
             os.path.expanduser('~/SHADE01/tools/qgclog')):
    if os.path.isdir(cand):
        sys.path.insert(0, os.path.abspath(cand))

import fclist                                              # noqa: E402
import lognum as LN                                        # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if a != '--dry']
    dry = '--dry' in sys.argv[1:]
    if len(args) < 2:
        sys.exit('사용법: renumber.py <entries.json> <logdir> [--dry]')
    import json
    with open(args[0]) as fh:
        entries = json.load(fh)
    d = args[1]

    facts = LN.scan(d)
    hit = fclist.match(entries, facts, log_dir=d)

    renames, dups, unmatched = [], [], []
    for f in facts:
        n = f['name']
        if n.startswith('REF_'):
            continue                       # 웹 참조 로그 — 우리 기체가 아니다
        if n not in hit or not f['end']:
            # 이미 번호가 붙어 있으면 문제가 아니다 — 크기가 어긋나는 것은
            # 손으로 고친 사본(파싱을 다시 살린 것)이라 그렇다.
            if not LN.QGC_NAME.match(n):
                unmatched.append((n, '엔트리와 안 맞음'))
            continue
        num, why = hit[n]
        # 🔴 번호가 이미 맞으면 그대로 둔다. 이름 속 시각이 1~2초 달라도
        #    건드리지 않는다 — QGC 가 붙인 종료시각과 우리가 계산한 값이
        #    반올림에서 갈리는데, 그것 때문에 매번 개명하면 파일 이름이
        #    돌 때마다 흔들린다 (실측: 안정된 로그 9개가 매 실행 대상이 됐다).
        m = LN.QGC_NAME.match(n)
        if m and int(m.group(1)) == num:
            continue
        if why != 'size':
            # 크기까지 안 맞으면 붙이지 않는다. 같은 크기의 다른 로그와 헷갈릴
            # 수 있고, 틀린 번호는 없는 번호보다 나쁘다.
            unmatched.append((n, '시각만 일치(%d)' % num))
            continue
        new = LN.qgc_name(num, f['end'])
        if new == n:
            continue                       # 이미 맞는 이름
        if os.path.exists(os.path.join(d, new)):
            # 🔴 이미 그 번호가 있다 = 같은 비행을 또 받았다. 번호 없는 쪽을 버린다.
            dups.append((n, new))
            continue
        renames.append((n, new, num))

    for old, new in dups:
        print('DUP\t%s\t(= %s)' % (old, new))
        if not dry:
            try:
                os.unlink(os.path.join(d, old))
                print('DELETED\t%s' % old)
            except OSError as e:
                print('ERR\t%s\t%s' % (old, e))

    # 자리바꿈이 섞이므로 임시 이름을 거친다 (log_77→78, log_78→79 같은 경우).
    if renames and not dry:
        for old, _new, _num in renames:
            os.rename(os.path.join(d, old), os.path.join(d, old + '.tmpmv'))
        for old, new, _num in renames:
            os.rename(os.path.join(d, old + '.tmpmv'), os.path.join(d, new))
    for old, new, _num in renames:
        print('RENAME\t%s\t%s' % (old, new))

    for n, why in unmatched:
        print('SKIP\t%s\t%s' % (n, why))

    print('요약\t개명 %d\t중복삭제 %d\t미매칭 %d%s'
          % (len(renames), len(dups), len(unmatched), '  [dry]' if dry else ''))


if __name__ == '__main__':
    main()
