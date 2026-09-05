#!/usr/bin/env python3
"""로그에 **FC 엔트리 번호**를 붙인다 — 추측이 아니라 로그 안의 증거로.

QGC 가 MAVFTP 로 받은 로그는 `log_129_2026-8-31-18-46-02.ulg` 처럼 이름에
FC 세션 번호를 달고 온다. 그 번호가 이 기체의 비행을 세는 통번호다.
우리 도구(`fcfetch.py`)로 받은 것은 그 번호가 없다 — MAVFTP 디렉토리를
훑을 뿐이라 엔트리 ID 를 안 보기 때문이다.

    from lognum import scan, plan
    facts = scan('logs')          # 파일마다 SD 경로·번호를 읽는다
    for mv in plan(facts): ...    # 확정된 것만 개명 계획을 낸다

## 번호를 무엇으로 확정하나

🔴 **로그 안에 FC 가 SD 경로를 적어 둔다** — `/fs/microsd/log/<날짜>/<HH_MM_SS>.ulg`.
   `INFO` 메시지로 남으므로 파일명이 무엇이든 읽어낼 수 있다. 이것이 같은 비행을
   가리키는 가장 단단한 증거다 (`web/extract.py` 의 `flight_key` 도 같은 것을 쓴다).

**엔트리 번호는 SD 카드 전체 로그의 시간순 일련번호다** — 날짜 폴더를 가로질러
이어진다. 정본 25개에서 확인했다: 번호가 연속인 구간은 SD 시각 순서도 정확히
연속이다 (`77→78→79`, `176→177→178`).

그래서 **번호를 아는 로그 둘 사이에 우리가 가진 로그 수가 번호 간격과 같으면**,
그 사이 로그의 번호가 하나로 정해진다. 예:

    log_92 (SD 10_10_31)  ← 안다
      ?    (SD 10_10_40)  ← 사이에 우리 로그가 1개, 번호 간격도 1 → **93 확정**
    log_94 (SD 10_11_12)  ← 안다

⚠️ 간격이 남으면 (FC 가 발급했는데 우리가 못 받은 로그가 있으면) **확정하지
   않는다.** 예: 94→127 은 번호 간격 33 인데 우리 보유는 23 — 어느 자리가
   비었는지 알 수 없으므로 그 구간은 손대지 않는다. 거짓 번호를 만드는 것보다
   두 이름 체계가 남는 편이 낫다.

## 개명하는 이유

표시만 통일하면 세 곳(`web/live`·`web/server.js`·`qgclog`)이 각자 추론을 돌려야
하고, 규칙이 갈리면 같은 로그가 다른 번호로 뜬다. 파일명이 정본이면 그런 일이
없다.

⚠️ 개명해도 웹 카탈로그는 안 깨진다 — 키가 **파일 내용 해시**(`idOf`)이고
   중복 접기는 **로그 안의 FC 경로**(`flight_key`)로 하기 때문이다. 파일명은
   표시에만 쓴다. `_repair()` 도 같은 디렉토리의 `*.ulg` 를 훑을 뿐 이름을
   보지 않는다.
"""

import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# QGC 가 붙인 이름. 월·일에 0 패딩이 없다.
QGC_NAME = re.compile(r'^log_(\d+)_(\d{4})-(\d{1,2})-(\d{1,2})'
                      r'-(\d{1,2})-(\d{1,2})-(\d{1,2})\.ulg$')
# 로그 안의 FC SD 경로.
SD_PATH = re.compile(r'/log/(\d{4})-(\d{2})-(\d{2})/(\d{2})_(\d{2})_(\d{2})\.ulg')

KST = datetime.timezone(datetime.timedelta(hours=9))


def sd_path(ulog):
    """로그 안에 FC 가 적은 SD 경로. 없으면 None.

    짧게 끊긴 로그에는 이 메시지가 안 실린다 — 그때는 번호를 확정할 수 없다.
    """
    for m in getattr(ulog, 'logged_messages', []) or []:
        if '/fs/microsd' in m.message:
            return m.message.split()[-1]
    return None


def sd_time(path):
    """SD 경로 → UTC 시각(naive). FC 는 SD 에 **UTC** 로 적는다."""
    m = SD_PATH.search(path or '')
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    return datetime.datetime(y, mo, d, h, mi, s)


def end_kst(ulog):
    """로그가 끝난 시각(KST). QGC 이름이 쓰는 바로 그 시각이다."""
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


def qgc_name(num, end):
    """번호와 종료시각(KST)으로 QGC 형식 이름."""
    return 'log_%d_%d-%d-%d-%02d-%02d-%02d.ulg' % (
        num, end.year, end.month, end.day, end.hour, end.minute, end.second)


def scan(log_dir, names=None, verbose=False):
    """디렉토리의 로그마다 사실을 읽는다.

    반환: [{'name','num','sd','sd_t','end','recovered'}]
      num  파일명에 이미 있는 FC 번호 (없으면 None)
      sd_t SD 경로의 시각 — 순서를 정하는 기준
    """
    import qgclog as Q
    if names is None:
        names = sorted(n for n in os.listdir(log_dir) if n.endswith('.ulg'))
    out = []
    for n in names:
        p = os.path.join(log_dir, n)
        try:
            ulog, _ = Q._load(p)
        except Exception as exc:
            if verbose:
                print('  못 읽음 %s: %s' % (n, exc), file=sys.stderr)
            out.append({'name': n, 'num': None, 'sd': None, 'sd_t': None,
                        'end': None, 'recovered': n.startswith('RECOVERED')})
            continue
        m = QGC_NAME.match(n)
        sd = sd_path(ulog)
        out.append({
            'name': n,
            'num': int(m.group(1)) if m else None,
            'sd': sd,
            'sd_t': sd_time(sd),
            'end': end_kst(ulog),
            'recovered': n.startswith('RECOVERED'),
        })
    return out


def infer(facts):
    """SD 순서로 번호를 확정한다. {이름: (번호, 'known'|'derived')}.

    확정 못 한 것은 딕셔너리에 안 넣는다 — **모르는 것은 비워 둔다.**
    """
    # 순서를 매길 기준. SD 시각이 가장 단단하지만, 짧게 끊긴 로그에는 그
    # 메시지가 안 실린다 — 그때는 종료시각(KST)을 UTC 로 되돌려 같은 자에
    # 올린다. 둘은 정확히 9시간 차이다.
    #
    # 🔴 이것이 없으면 SD 경로 없는 로그가 순서에서 통째로 빠져, 그 앞뒤
    #    앵커 사이의 간격이 실제보다 커 보여 확정이 안 된다 (실측: 9/2 의
    #    log_179·log_180 이 빠져 그날 10개가 전부 미확정이었다).
    def order_key(f):
        if f['sd_t']:
            return f['sd_t']
        if f['end']:
            return f['end'] - datetime.timedelta(hours=9)
        return None

    seq = sorted([f for f in facts if order_key(f)], key=order_key)
    out = {}
    for f in seq:
        if f['num'] is not None:
            out[f['name']] = (f['num'], 'known')

    # 번호를 아는 것들의 위치.
    anchors = [(i, f) for i, f in enumerate(seq) if f['num'] is not None]
    for k in range(len(anchors) - 1):
        (ia, a), (ib, b) = anchors[k], anchors[k + 1]
        between = seq[ia + 1:ib]
        if not between:
            continue
        # 🔴 번호 간격과 사이 로그 수가 정확히 맞을 때만 확정한다. 남으면
        #    FC 가 발급했는데 우리가 못 받은 로그가 있다는 뜻이고, 어느 자리가
        #    비었는지 알 수 없다.
        if b['num'] - a['num'] - 1 != len(between):
            continue
        for j, f in enumerate(between):
            out[f['name']] = (a['num'] + 1 + j, 'derived')
    return out


def plan(facts, nums=None):
    """개명 계획. [(옛이름, 새이름, 번호, 출처)]. 바꿀 게 없으면 안 넣는다.

    복구본은 **원본과 같은 번호**를 받되 이름 끝에 `_R<n>` 을 붙인다 — 같은
    비행이라 나란히 서야 하지만 파일은 둘이므로 이름이 겹치면 안 된다.
    """
    if nums is None:
        nums = infer(facts)
    by_name = {f['name']: f for f in facts}

    # 복구본을 원본에 붙인다. 짝은 SD 경로로 찾는다 — 이름의 시각 조각만으로는
    # 날짜를 모른다.
    by_sd = {}
    for f in facts:
        if f['sd'] and f['name'] in nums:
            by_sd.setdefault(f['sd'], f['name'])

    out = []
    taken = set()
    for f in facts:
        n = f['name']
        # 🔴 이미 QGC 이름인 것은 **건드리지 않는다.** 그 이름이 이 규칙의
        #    기준이다 — 우리가 잰 종료시각과 1~2초 어긋나도 QGC 쪽이 정답이다
        #    (FC 가 엔트리 목록에서 준 시각이고, 우리는 마지막 표본으로
        #    되짚은 값이라 표본 주기만큼 차이가 난다). 고치려 들면 정본을
        #    추정치로 덮게 된다.
        if QGC_NAME.match(n):
            taken.add(n)
            continue
        num_src = nums.get(n)
        if num_src is None and f['recovered'] and f['sd']:
            mate = by_sd.get(f['sd'])
            if mate:
                num_src = nums.get(mate)
        if num_src is None or f['end'] is None:
            continue                      # 확정 못 했다 — 그대로 둔다
        num, src = num_src
        new = qgc_name(num, f['end'])
        if f['recovered']:
            # 복구본은 원본과 구분돼야 한다. 같은 번호에 표식만 붙인다.
            k = 1
            base = new[:-4]
            while ('%s_R%d.ulg' % (base, k)) in taken:
                k += 1
            new = '%s_R%d.ulg' % (base, k)
        if new == n:
            taken.add(new)
            continue
        taken.add(new)
        out.append((n, new, num, src))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description='로그 파일명에 FC 엔트리 번호를 붙인다 (SD 경로로 확정)')
    ap.add_argument('dir', nargs='?', default=None, help='로그 디렉토리')
    ap.add_argument('--apply', action='store_true',
                    help='실제로 개명한다 (기본은 계획만 보여 준다)')
    a = ap.parse_args()

    import qgclog as Q
    d = Q.find_log_dir(a.dir)
    print('%s 를 훑는다…' % d, flush=True)
    facts = scan(d, verbose=True)
    nums = infer(facts)
    moves = plan(facts, nums)

    known = sum(1 for v in nums.values() if v[1] == 'known')
    derived = sum(1 for v in nums.values() if v[1] == 'derived')
    print('\n로그 %d개 · 번호 아는 것 %d · SD 순서로 확정 %d · 미확정 %d'
          % (len(facts), known, derived, len(facts) - known - derived))

    if not moves:
        print('바꿀 이름이 없다.')
        return
    print('\n개명 계획 %d건:' % len(moves))
    for old, new, num, src in moves:
        print('  %-40s → %-40s (%s)' % (old, new, src))

    if not a.apply:
        print('\n계획만 보여 줬다. 실제로 바꾸려면 --apply')
        return

    # 🔴 먼저 충돌을 전부 확인한다. 반쯤 하다 멈추면 어느 이름이 무엇인지
    #    모르는 상태가 된다.
    for _old, new, _n, _s in moves:
        if os.path.exists(os.path.join(d, new)):
            sys.exit('이미 있는 이름이다: %s — 아무것도 안 바꿨다' % new)
    for old, new, _n, _s in moves:
        os.rename(os.path.join(d, old), os.path.join(d, new))
    print('\n%d개 개명했다.' % len(moves))


if __name__ == '__main__':
    main()
