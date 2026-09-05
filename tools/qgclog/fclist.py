#!/usr/bin/env python3
"""FC 에게 **로그 엔트리 목록**을 물어 번호를 받아 온다.

    fclist.py                      기본 경로로 붙어 목록만 본다
    fclist.py --map logs           그 번호를 로컬 로그에 맞춰 개명 계획을 낸다
    fclist.py --map logs --apply   실제로 개명한다

## 왜 필요한가

`fcfetch.py` 는 MAVFTP 로 SD 디렉토리를 훑어 받는다 — 파일은 오지만 **엔트리
번호는 안 온다.** 번호는 다른 프로토콜(`LOG_REQUEST_LIST`)에 있고, QGC 는
그쪽을 써서 `log_129_...` 라는 이름을 만든다.

그래서 QGC 없이 받은 로그는 번호를 잃는다. 시각 순서로 추론할 수는 있지만
(`lognum.py`), 앵커가 없는 구간 — 그날 QGC 로 받은 로그가 하나도 없으면 —
아무것도 확정되지 않는다. 9/5 세션 24개가 그 상태였다.

**FC 에게 직접 물으면 추론이 필요 없다.**

## 무엇을 보내나

🔴 `LOG_REQUEST_LIST` 하나다 — **목록 조회**이고 FC 상태를 바꾸지 않는다.
   파라미터도, 모드도, 미션도 건드리지 않는다. (`fcfetch.py` 가 이미 MAVFTP
   요청을 보내므로 새로운 성질은 아니다. `web/live` 의 읽기 전용 원칙은
   그쪽 프로세스의 것이고 이 도구와 별개다.)

⚠️ **비행 중에는 쓰지 마라.** 로그 목록 조회는 FC 의 SD 접근을 점유한다.

## 번호를 파일에 어떻게 붙이나

FC 가 주는 `LOG_ENTRY` 에는 `id`(엔트리 번호)와 `time_utc`(그 로그의 UTC
시각)가 들어 있다. 로컬 로그의 SD 경로(`/fs/microsd/log/<날짜>/<HH_MM_SS>.ulg`)
또는 종료시각과 맞춰 짝을 짓는다.

⚠️ FC 의 `time_utc` 는 **로그가 끝난** 시각이다 — QGC 파일명이 쓰는 그 값이다.
   SD 경로의 시각(로그 _시작_)과 직접 비교하면 안 된다.
"""

import argparse
import datetime
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

KST = datetime.timezone(datetime.timedelta(hours=9))

# 짝짓기 허용 오차(초). FC 가 준 종료시각과 우리가 로그에서 되짚은 종료시각은
# 표본 주기만큼 어긋난다 — 실측 ±2초였다. 넉넉히 잡되 이웃 로그를 잘못 물지
# 않을 만큼만: 이 기체는 연속 이착륙 간격이 최소 4초였다.
MATCH_TOL_S = 8


def fetch_entries(device, baud=115200, timeout=30):
    """FC 의 로그 엔트리 목록. [{'id','time_utc','size'}].

    🔴 `LOG_REQUEST_LIST` 하나만 보낸다. 상태를 바꾸는 메시지는 없다.
    """
    from pymavlink import mavutil

    m = mavutil.mavlink_connection(device, baud=baud)
    t0 = time.time()
    tgt = None
    while time.time() - t0 < 20:
        try:
            hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
        except TypeError:
            continue          # pymavlink 2.4.49 인스턴스 필드 버그
        if hb:
            h = hb.get_header()
            tgt = (h.srcSystem, h.srcComponent)
            break
    if tgt is None:
        raise RuntimeError('HEARTBEAT 없음 — FC 연결/포트 점유 확인')

    m.mav.log_request_list_send(tgt[0], tgt[1], 0, 0xFFFF)

    entries = {}
    total = None
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = m.recv_match(type='LOG_ENTRY', blocking=True, timeout=2)
        if msg is None:
            # 다 받았으면 끝낸다. 아직이면 한 번 더 조른다.
            if total is not None and len(entries) >= total:
                break
            if entries:
                break
            continue
        total = msg.num_logs
        if msg.num_logs == 0:
            break
        entries[msg.id] = {'id': msg.id, 'time_utc': msg.time_utc,
                           'size': msg.size}
        if len(entries) >= msg.num_logs:
            break
    m.close()
    return [entries[k] for k in sorted(entries)]


def match(entries, facts, log_dir=None):
    """FC 엔트리와 로컬 로그를 짝짓는다. {파일이름: (번호, 근거)}.

    FC 의 `time_utc` 는 로그가 **끝난** 시각(UTC epoch)이다. 로컬 로그의
    종료시각(KST)을 UTC 로 되돌려 견준다.

    🔴 **크기가 최우선 근거다.** FC 가 준 `size` 와 파일 크기가 바이트 단위로
       같으면 그 로그가 맞다 — 시각은 ±2초 어긋나지만 크기는 안 어긋난다.
       실측(2026-09-06): `log_77`·`log_78`·`log_79` 는 **파일명의 번호가
       한 칸씩 밀려 있었다** (QGC 가 잘못 붙였다). 크기로 대조하니
       `log_77` 의 1,735,227 B 가 FC 엔트리 78번의 크기와 정확히 같았다.
       시각만 봤으면 이 오류를 그대로 물려받았을 것이다.

    근거는 'size'(크기 일치) 또는 'time'(시각만 일치)이다. 'time' 인 것은
    같은 크기의 다른 로그가 있을 수 있어 확실성이 한 단계 낮다.
    """
    # time_utc 가 0 인 엔트리가 있다 — FC 가 GPS 시각을 못 얻은 채 쓴 로그다.
    ents = [e for e in entries if e['time_utc']]
    out = {}
    used = set()

    def size_of(f):
        if log_dir is None:
            return None
        try:
            return os.path.getsize(os.path.join(log_dir, f['name']))
        except OSError:
            return None

    # 1단계: 크기 + 시각이 둘 다 맞는 것부터. 가장 단단하다.
    for f in facts:
        if not f['end']:
            continue
        sz = size_of(f)
        if sz is None:
            continue
        end_utc = f['end'].replace(tzinfo=KST).timestamp()
        for e in ents:
            if e['id'] in used or e['size'] != sz:
                continue
            if abs(e['time_utc'] - end_utc) <= MATCH_TOL_S:
                out[f['name']] = (e['id'], 'size')
                used.add(e['id'])
                break

    # 2단계: 남은 것은 시각으로. 크기가 안 맞는 이유는 여럿이다 —
    # `_repair()` 로 고친 사본, 전송 중 잘린 파일.
    for f in facts:
        if f['name'] in out or not f['end']:
            continue
        end_utc = f['end'].replace(tzinfo=KST).timestamp()
        best, bestd = None, None
        for e in ents:
            if e['id'] in used:
                continue
            d = abs(e['time_utc'] - end_utc)
            if bestd is None or d < bestd:
                best, bestd = e, d
        if best is not None and bestd <= MATCH_TOL_S:
            out[f['name']] = (best['id'], 'time')
            used.add(best['id'])
    return out


def main():
    ap = argparse.ArgumentParser(
        description='FC 에게 로그 엔트리 번호를 물어 파일명에 붙인다')
    ap.add_argument('--device', default=os.environ.get('FC_DEVICE', '/dev/ttyACM0'),
                    help='FC 시리얼 (기본 /dev/ttyACM0). udp:127.0.0.1:14550 도 된다')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--map', metavar='DIR', default=None,
                    help='이 디렉토리의 로그에 번호를 맞춘다')
    ap.add_argument('--apply', action='store_true', help='실제로 개명한다')
    ap.add_argument('--save', metavar='FILE', default=None,
                    help='엔트리 목록을 JSON 으로 저장한다')
    ap.add_argument('--load', metavar='FILE', default=None,
                    help='FC 대신 저장해 둔 목록을 읽는다. FC 가 붙은 PC 와 '
                         '로그가 있는 PC 가 다를 때 쓴다 (rim3 에 FC, gram 에 로그)')
    a = ap.parse_args()

    if a.load:
        import json
        with open(a.load) as fh:
            entries = json.load(fh)
        print('저장해 둔 목록 %d개 (%s)' % (len(entries), a.load))
    else:
        print('FC 에 붙는다: %s' % a.device, flush=True)
        entries = fetch_entries(a.device, a.baud)
        if a.save:
            import json
            with open(a.save, 'w') as fh:
                json.dump(entries, fh)
            print('저장했다: %s' % a.save)
    print('엔트리 %d개' % len(entries))
    for e in ([] if a.map else entries):
        t = (datetime.datetime.fromtimestamp(e['time_utc'], datetime.timezone.utc)
             .astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')) if e['time_utc'] else '(시각 없음)'
        print('  %4d  %-21s %8.2fMB' % (e['id'], t, e['size'] / 1e6))

    if not a.map:
        return

    import lognum as LN
    import qgclog as Q
    d = Q.find_log_dir(a.map)
    print('\n%s 와 맞춘다…' % d, flush=True)
    facts = LN.scan(d)
    hit = match(entries, facts, log_dir=d)
    bysz = sum(1 for v in hit.values() if v[1] == 'size')
    print('짝지어진 로그 %d개 (크기까지 일치 %d, 시각만 %d)'
          % (len(hit), bysz, len(hit) - bysz))

    # 🔴 이미 QGC 이름인 것으로 **매칭이 맞는지 검산한다.** 파일명의 번호와
    #    FC 가 말하는 번호가 다르면 둘 중 하나가 틀린 것이므로 드러내야 한다.
    #    실측(2026-09-06): log_77·78·79 는 QGC 가 번호를 한 칸씩 밀려 붙였고,
    #    크기 대조로 FC 쪽이 맞다는 것이 확인됐다.
    conflicts = []
    for f in facts:
        m = LN.QGC_NAME.match(f['name'])
        if not m or f['name'] not in hit:
            continue
        want, (got, why) = int(m.group(1)), hit[f['name']]
        if want != got:
            conflicts.append((f['name'], want, got, why))
    if conflicts:
        print('\n⚠️ 파일명의 번호와 FC 가 말하는 번호가 다르다 %d건:' % len(conflicts))
        for n, want, got, why in conflicts:
            print('   %-40s 파일명 %d ≠ FC %d (%s)' % (n, want, got, why))
        print('   크기까지 일치(size)면 FC 쪽이 맞다 — 파일명이 잘못 붙은 것이다.')

    moves = []
    for f in facts:
        n = f['name']
        if n not in hit or not f['end']:
            continue
        num, why = hit[n]
        m = LN.QGC_NAME.match(n)
        if m and int(m.group(1)) == num:
            continue                      # 이미 맞는 이름이다
        if m and why != 'size':
            # 이름이 이미 있는데 근거가 시각뿐이면 건드리지 않는다 — 바꿀
            # 만큼 확실하지 않다.
            continue
        new = LN.qgc_name(num, f['end'])
        if new != n:
            moves.append((n, new, why))
    if not moves:
        print('바꿀 이름이 없다.')
        return
    print('\n개명 계획 %d건:' % len(moves))
    for old, new, why in moves:
        print('  %-40s → %-40s (%s)' % (old, new, why))
    if not a.apply:
        print('\n계획만 보여 줬다. 실제로 바꾸려면 --apply')
        return
    # 🔴 충돌을 먼저 전부 확인한다. 반쯤 하다 멈추면 어느 이름이 무엇인지
    #    모르는 상태가 된다. 개명 대상 자기들끼리 자리를 바꾸는 경우가 있어
    #    (log_77→78, log_78→79) 계획에 든 이름은 충돌로 치지 않는다.
    moving = {o for o, _n, _w in moves}
    for _o, new, _w in moves:
        if os.path.exists(os.path.join(d, new)) and new not in moving:
            sys.exit('이미 있는 이름이다: %s — 아무것도 안 바꿨다' % new)
    # 🔴 되돌릴 수 있게 매핑표를 **먼저** 남긴다. 개명 뒤에 쓰려다 실패하면
    #    무엇이 무엇이었는지 알 길이 없다.
    import json
    mapfile = os.path.join(d, 'RENAME-MAP.json')
    prev = []
    if os.path.exists(mapfile):
        try:
            with open(mapfile) as fh:
                prev = json.load(fh)
        except (OSError, ValueError):
            prev = []
    prev.append({
        'when': datetime.datetime.now().isoformat(timespec='seconds'),
        'source': 'fclist (FC 엔트리 목록)',
        'moves': [{'from': o, 'to': n, 'why': w} for o, n, w in moves],
    })
    with open(mapfile + '.tmp', 'w') as fh:
        json.dump(prev, fh, ensure_ascii=False, indent=1)
    os.replace(mapfile + '.tmp', mapfile)
    print('매핑표: %s' % mapfile)

    # 자리바꿈이 섞이므로 임시 이름을 거친다.
    for old, _new, _w in moves:
        os.rename(os.path.join(d, old), os.path.join(d, old + '.tmpmv'))
    for old, new, _w in moves:
        os.rename(os.path.join(d, old + '.tmpmv'), os.path.join(d, new))
    print('\n%d개 개명했다.' % len(moves))


if __name__ == '__main__':
    main()
