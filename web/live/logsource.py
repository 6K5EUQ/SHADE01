#!/usr/bin/env python3
"""로그 목록의 **정본은 labserver 다.**

이 PC 의 `logs/` 는 작업 사본이다. 여기에만 있는 로그가 생기면 그 PC 가
죽을 때 사라진다 — 실제로 gram 에만 있던 20개를 9/6 에 발견했다
(`LOG-INVENTORY.md` 는 "PC 유일본 없음" 이라 적고 있었는데 gram 이 대조에서
빠져 있었다).

그래서 목록은 **항상 labserver 에서 받는다.** 재생할 때만 그 파일 하나를
내려받아 `logs/` 에 캐시한다.

    from logsource import catalog, ensure_local
    items = catalog()                      # labserver 목록 (+ 로컬 보유 표시)
    path = ensure_local('log_129_....ulg') # 없으면 받아 온다

🔴 **읽기 전용이다.** `scp` 로 받기만 한다 — labserver 에 아무것도 안 쓴다.
   정본을 지우거나 고치는 것은 사람이 할 일이다.

⚠️ labserver 가 죽어도 화면은 떠야 한다. 목록을 못 받으면 로컬에 있는 것만
   보여 주고 그 사실을 말한다 (`source: 'local'`).
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools', 'qgclog'))

# 정본 보관소. `web/tools/gather.sh` 가 3대에서 모아 올리는 그 자리다.
REMOTE_HOST = os.environ.get('SHADE_LOG_HOST', 'ku@ku-labserver')
REMOTE_DIR = os.environ.get('SHADE_LOG_DIR', '~/shade01-data/logs')

# 받아 온 로그를 두는 곳. 로컬 `logs/` 와 **같은 디렉토리**다 —
# `_repair()` 가 형제 로그를 기증자로 쓰므로 나눠 두면 복구율이 떨어진다
# (CLAUDE.md 「로그는 logs/ 에 평면으로 쌓는다」).
LOCAL_DIR = os.environ.get(
    'QGC_LOG_DIR', os.path.join(HERE, '..', '..', 'logs'))

# ssh 가 응답 없이 매달리면 페이지 전체가 멎는다. 짧게 끊고 로컬로 물러선다.
SSH_TIMEOUT = 8

_SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=%d' % SSH_TIMEOUT]

# 목록은 자주 바뀌지 않는다. 폴마다 ssh 를 띄우면 목록 열 때마다 수백 ms 가
# 든다 — 짧게 캐시한다.
_CACHE = {'at': 0.0, 'items': None}
CACHE_S = 30.0


def _remote_list():
    """labserver 의 `.ulg` 목록. [(이름, 크기)]. 못 받으면 None."""
    cmd = _SSH + [REMOTE_HOST,
                  'cd %s && stat -c "%%s %%n" *.ulg 2>/dev/null' % REMOTE_DIR]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=SSH_TIMEOUT + 4)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out = []
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[1].endswith('.ulg'):
            try:
                out.append((parts[1], int(parts[0])))
            except ValueError:
                pass
    return out or None


def _local_list():
    d = os.path.abspath(LOCAL_DIR)
    try:
        names = [n for n in os.listdir(d) if n.endswith('.ulg')]
    except OSError:
        return []
    out = []
    for n in names:
        try:
            out.append((n, os.path.getsize(os.path.join(d, n))))
        except OSError:
            pass
    return out


def catalog(force=False):
    """재생 목록. labserver 를 먼저 보고, 안 되면 로컬로 물러선다.

    반환: {'source': 'labserver'|'local', 'items': [...], 'error': str|None}
    각 항목: {'name','disp','num','exact','size','local','recovered','when'}

    - `name`   labserver 에 있는 실제 파일명 (재생할 때 이 이름으로 받는다)
    - `disp`   화면에 뜨는 이름. QGC 형식으로 통일한 것
    - `exact`  True 면 FC 가 준 번호, False 면 빈칸에서 추론한 번호
    - `local`  이 PC 에 이미 받아 둔 것인가
    """
    now = time.monotonic()
    if not force and _CACHE['items'] and now - _CACHE['at'] < CACHE_S:
        return _CACHE['items']

    import lognames as L

    err = None
    rows = _remote_list()
    source = 'labserver'
    if rows is None:
        source, err = 'local', 'labserver 에 못 붙었다 — 이 PC 의 사본만 보인다'
        rows = _local_list()

    have = {n for n, _ in _local_list()}
    local_dir = os.path.abspath(LOCAL_DIR)

    # 종료시각은 로그를 열어야 안다. **로컬에 있는 것만** 잰다 — 목록을 띄우려고
    # 80개를 내려받을 수는 없다. 없는 것은 파일명의 시각으로 대신한다.
    def end_of(name):
        p = os.path.join(local_dir, name)
        if not os.path.exists(p):
            return None
        return L.end_time(p)

    names = [n for n, _ in rows]
    tbl = L.assign(names, end_of=end_of)
    sizes = dict(rows)

    items = []
    for n in names:
        disp, num, exact = tbl[n]
        _num, t, kind = L.parse(n)
        # 표시이름에서 시각을 다시 뽑는다 — 정렬은 이것으로 한다.
        _n2, t2, _k2 = L.parse(disp)
        when = t2 or t
        items.append({
            'name': n,
            'disp': disp,
            'num': num,
            'exact': bool(exact),
            'size': sizes.get(n, 0),
            'local': n in have,
            'recovered': kind == 'recovered',
            'when': when.strftime('%Y-%m-%d %H:%M') if when else None,
            '_sort': when.timestamp() if when else 0,
        })
    # 최신 먼저. 번호가 곧 순서지만, 번호를 못 받은 것(복구본·참조본)이 섞이므로
    # 시각으로 세운다.
    items.sort(key=lambda x: x['_sort'], reverse=True)
    for it in items:
        del it['_sort']

    res = {'source': source, 'items': items, 'error': err,
           'remote': '%s:%s' % (REMOTE_HOST, REMOTE_DIR)}
    _CACHE['at'] = now
    _CACHE['items'] = res
    return res


def ensure_local(name):
    """그 로그를 이 PC 에 확보한다. 이미 있으면 그대로, 없으면 받아 온다.

    반환: 로컬 경로. 실패하면 예외.

    🔴 이름은 **파일명만** 받는다. 경로가 섞이면 `scp` 가 엉뚱한 곳을 긁는다.
    """
    if not name or '/' in name or '\\' in name or not name.endswith('.ulg'):
        raise ValueError('이름이 이상하다: %r' % name)
    d = os.path.abspath(LOCAL_DIR)
    p = os.path.join(d, name)
    if os.path.exists(p):
        return p
    os.makedirs(d, exist_ok=True)
    # 받는 중에 죽으면 잘린 파일이 남는다 — 임시 이름으로 받고 다 되면 옮긴다.
    # `_repair()` 가 잘린 파일을 기증자로 삼으면 복구가 더 나빠진다.
    tmp = p + '.part'
    cmd = ['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=%d' % SSH_TIMEOUT,
           '%s:%s/%s' % (REMOTE_HOST, REMOTE_DIR, name), tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError('labserver 에서 못 받았다: %s' % e)
    if r.returncode != 0 or not os.path.exists(tmp):
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise RuntimeError('labserver 에서 못 받았다: %s'
                           % (r.stderr.strip()[:200] or 'scp 실패'))
    os.replace(tmp, p)
    return p


if __name__ == '__main__':
    c = catalog(force=True)
    print('원천: %s  (%s)' % (c['source'], c['remote']))
    if c['error']:
        print('⚠️ ', c['error'])
    for it in c['items']:
        print('%s %-42s %8.1fMB %s%s' % (
            ' ' if it['exact'] else '~', it['disp'], it['size'] / 1e6,
            '' if it['local'] else '(원격) ',
            '복구본' if it['recovered'] else ''))
    print('\n총 %d개' % len(c['items']))
