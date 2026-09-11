#!/usr/bin/env python3
"""QGC `.plan` 을 FC 의 미션으로 올리고, 되읽어 대조한다.

    backup  — FC 의 현재 미션을 .plan 으로 내려받는다 (아무것도 안 쓴다)
    verify  — 올릴 .plan 을 펌웨어 규칙으로 검사한다 (연결 안 함)
    push    — 미션을 올린다 (되읽어 항목별로 대조)

🔴 push 만 FC 에 쓴다. backup/verify 는 읽기 전용이다.

extras.txt 와 달리 미션은 MAVFTP 가 아니라 **MISSION 프로토콜**로 오간다
(MISSION_COUNT → MISSION_REQUEST_INT → MISSION_ITEM_INT → MISSION_ACK).
그래서 CRC 가 없다. 대신 올린 뒤 **전량을 되읽어 항목마다 비교**한다.

🔴 이 기체는 쿼드 전용이다 (2026-09-04, 에어스피드 영점 미해결).
   84(VTOL_TAKEOFF)·85(VTOL_LAND)·3000(DO_VTOL_TRANSITION) 은 고정익 전환을
   건다. NAV_FORCE_VT=1 로도 안 막힌다 — 기체가 이미 FW 일 때만 동작한다.
   verify 가 이 셋을 발견하면 거부한다.
"""
import argparse
import collections
import json
import sys
import time

from pymavlink import mavutil

# 🔴 pymavlink 우회. mavutil.add_message() 는 인스턴스 필드가 있는 메시지를
#    저장할 때 messages[mtype]._instances 가 None 이면 터진다:
#
#      TypeError: 'NoneType' object does not support item assignment
#      (mavutil.py:98)
#
#    같은 타입이 인스턴스 없이 먼저 들어온 뒤 인스턴스 버전이 오면 그렇게 된다.
#    이 기체에서는 실제로 발생한다 — 미션을 읽는 도중 터져서 받다 만다.
#    라이브러리를 고치지 않고 여기서 막는다 (venv 는 되돌려지는 자리다).
_orig_add_message = mavutil.add_message


def _safe_add_message(messages, mtype, msg):
    try:
        return _orig_add_message(messages, mtype, msg)
    except TypeError:
        # _instances 가 비어 있으면 만들어 주고 한 번만 다시 시도한다.
        cur = messages.get(mtype)
        if cur is not None and getattr(cur, '_instances', None) is None:
            cur._instances = {}
            return _orig_add_message(messages, mtype, msg)
        messages[mtype] = msg
        return None


mavutil.add_message = _safe_add_message

# 쿼드 전용인 동안 미션에 들어오면 안 되는 명령.
FORBIDDEN = {
    84: 'VTOL_TAKEOFF — 고정익 전환을 건다',
    85: 'VTOL_LAND — 고정익 전환을 건다',
    3000: 'DO_VTOL_TRANSITION — 고정익 전환을 건다',
}

NAME = {16: 'WAYPOINT', 17: 'LOITER_UNLIM', 18: 'LOITER_TURNS', 19: 'LOITER_TIME',
        20: 'RTL', 21: 'LAND', 22: 'TAKEOFF', 84: 'VTOL_TAKEOFF', 85: 'VTOL_LAND',
        177: 'DO_JUMP', 178: 'DO_CHANGE_SPEED', 189: 'DO_LAND_START',
        3000: 'DO_VTOL_TRANSITION'}

# MISSION_ITEM_INT 는 위경도를 1e7 배 정수로 싣는다.
SCALE = 1e7


def load_plan(path):
    d = json.load(open(path))
    if d.get('fileType') != 'Plan':
        sys.exit('%s: QGC .plan 이 아니다' % path)
    return d['mission']['items']


def check(items):
    """펌웨어가 거부할 구성을 미리 잡는다. 통과하면 True.

    근거는 PX4 FeasibilityChecker.cpp — 아래 주석에 함수명을 적어 둔다.
    """
    ok = True
    if not items:
        print('  🔴 항목이 없다')
        return False

    for i, it in enumerate(items):
        c = it['command']
        if c in FORBIDDEN:
            print('  🔴 %d번 항목: %s' % (i, FORBIDDEN[c]))
            ok = False

    # checkLandPatternValidity(): 착륙으로 시작하면 거부한다.
    if items[0]['command'] in (21, 85):
        print('  🔴 미션이 착륙으로 시작한다')
        ok = False

    # checkTakeoffLandAvailable(), MIS_TKO_LAND_REQ=2 → 착륙이 있어야 한다.
    has_land = any(it['command'] in (21, 85) for it in items)
    if not has_land:
        print('  🟡 착륙 항목이 없다 — MIS_TKO_LAND_REQ=2 면 FC 가 거부한다')
        ok = False

    print('  이륙 %s / 착륙 %s / 항목 %d개'
          % ('있음' if items[0]['command'] in (22, 84) else '없음',
             '있음' if has_land else '없음', len(items)))
    return ok


def describe(items):
    for i, it in enumerate(items):
        p = it['params']
        extra = ''
        if it['command'] == 19:
            extra = '  체류 %.0fs' % (p[0] or 0)
        print('  %d  %-12s(%4d)  alt=%-6s %.7f,%.7f%s'
              % (i, NAME.get(it['command'], '?'), it['command'], p[6],
                 p[4] or 0, p[5] or 0, extra))


def connect(dev, baud):
    m = mavutil.mavlink_connection(dev, baud=baud)
    print('하트비트 대기...', flush=True)
    if not m.wait_heartbeat(timeout=30):
        sys.exit('하트비트 없음 — FC 가 안 붙었거나 포트를 다른 게 쥐고 있다')
    print('연결: sys %d comp %d' % (m.target_system, m.target_component), flush=True)
    # 🔴 ARM 이면 아무것도 안 한다.
    hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=10)
    armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    print('ARM 상태: %s' % ('🔴 ARMED' if armed else 'disarmed'), flush=True)
    if armed:
        sys.exit('🔴 ARM 상태다. 중단한다.')
    return m


def download(m):
    """FC 의 현재 미션을 전량 받는다. 읽기 전용."""
    m.mav.mission_request_list_send(m.target_system, m.target_component,
                                    mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    cnt = m.recv_match(type='MISSION_COUNT', blocking=True, timeout=10)
    if cnt is None:
        sys.exit('MISSION_COUNT 가 안 온다')
    n = cnt.count
    print('FC 미션 항목: %d개' % n)
    out = []
    for i in range(n):
        m.mav.mission_request_int_send(m.target_system, m.target_component, i,
                                       mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
        it = m.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=10)
        if it is None:
            sys.exit('%d번 항목이 안 온다' % i)
        out.append(it)
    if n:
        m.mav.mission_ack_send(m.target_system, m.target_component,
                               mavutil.mavlink.MAV_MISSION_ACCEPTED,
                               mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    return out


def to_plan(items):
    """받은 MISSION_ITEM_INT 를 .plan 모양으로 되돌린다 (백업용)."""
    out = []
    for i, it in enumerate(items):
        out.append(collections.OrderedDict([
            ("autoContinue", bool(it.seq is not None and it.autocontinue)),
            ("command", it.command),
            ("doJumpId", i + 1),
            ("frame", it.frame),
            ("params", [it.param1, it.param2, it.param3, it.param4,
                        it.x / SCALE, it.y / SCALE, it.z]),
            ("type", "SimpleItem"),
        ]))
    return collections.OrderedDict([
        ("fileType", "Plan"),
        ("geoFence", collections.OrderedDict([("circles", []), ("polygons", []), ("version", 2)])),
        ("groundStation", "QGroundControl"),
        ("mission", collections.OrderedDict([
            ("cruiseSpeed", 15), ("firmwareType", 12), ("globalPlanAltitudeMode", 1),
            ("hoverSpeed", 5), ("items", out),
            ("plannedHomePosition", [out[0]['params'][4], out[0]['params'][5],
                                     out[0]['params'][6]] if out else [0, 0, 0]),
            ("vehicleType", 20), ("version", 2),
        ])),
        ("rallyPoints", collections.OrderedDict([("points", []), ("version", 2)])),
        ("version", 1),
    ])


def upload(m, items):
    """.plan 항목을 FC 로 올린다. 🔴 여기서만 FC 에 쓴다."""
    n = len(items)
    m.mav.mission_count_send(m.target_system, m.target_component, n,
                             mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    sent = set()
    deadline = time.time() + 60
    while len(sent) < n and time.time() < deadline:
        req = m.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT',
                                 'MISSION_ACK'], blocking=True, timeout=10)
        if req is None:
            sys.exit('FC 가 항목을 요청하지 않는다')
        if req.get_type() == 'MISSION_ACK':
            sys.exit('FC 가 중간에 ACK 를 보냈다: type=%d' % req.type)
        i = req.seq
        it = items[i]
        p = it['params']
        # None 은 "지정 안 함" 이다. MAVLink 로는 NaN 이 아니라 0 으로 보낸다 —
        # QGC 도 그렇게 보내고, NaN 을 넣으면 FC 가 항목을 거부한다.
        f = lambda v: 0.0 if v is None else float(v)
        m.mav.mission_item_int_send(
            m.target_system, m.target_component, i, it['frame'], it['command'],
            1 if i == 0 else 0, 1 if it.get('autoContinue', True) else 0,
            f(p[0]), f(p[1]), f(p[2]), f(p[3]),
            int(round(f(p[4]) * SCALE)), int(round(f(p[5]) * SCALE)), f(p[6]),
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
        sent.add(i)
    ack = m.recv_match(type='MISSION_ACK', blocking=True, timeout=20)
    if ack is None:
        sys.exit('MISSION_ACK 가 안 온다 — 올라갔는지 확실하지 않다. backup 으로 확인해라')
    if ack.type != mavutil.mavlink.MAV_MISSION_ACCEPTED:
        sys.exit('🔴 FC 가 거부했다: MAV_MISSION_ACK type=%d' % ack.type)
    print('FC ACCEPTED')


def compare(sent, got):
    """올린 것과 되읽은 것을 항목마다 대조한다. CRC 가 없으니 이것이 유일한 확인이다."""
    if len(sent) != len(got):
        print('🔴 개수가 다르다: 보낸 %d, 받은 %d' % (len(sent), len(got)))
        return False
    ok = True
    for i, (s, g) in enumerate(zip(sent, got)):
        p = s['params']
        f = lambda v: 0.0 if v is None else float(v)
        checks = [
            ('command', s['command'], g.command),
            ('frame', s['frame'], g.frame),
            ('param1', round(f(p[0]), 3), round(g.param1, 3)),
            ('lat', int(round(f(p[4]) * SCALE)), g.x),
            ('lon', int(round(f(p[5]) * SCALE)), g.y),
            ('alt', round(f(p[6]), 2), round(g.z, 2)),
        ]
        for name, a, b in checks:
            if a != b:
                print('  🔴 %d번 %s: 보낸 %s ≠ 받은 %s' % (i, name, a, b))
                ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('backup', 'verify', 'push'))
    ap.add_argument('--dev', default='/dev/ttyACM0')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--backup', default=None, help='백업을 쓸 .plan 경로')
    ap.add_argument('--new', default=None, help='올릴 .plan')
    a = ap.parse_args()

    if a.mode == 'verify':
        if not a.new:
            sys.exit('--new 가 필요하다')
        items = load_plan(a.new)
        print('%s:' % a.new)
        describe(items)
        print('검사:')
        if not check(items):
            sys.exit('🔴 검사 실패 — 올리지 마라')
        print('  ✅ 통과')
        return

    m = connect(a.dev, a.baud)

    if a.mode == 'backup':
        got = download(m)
        if not got:
            print('FC 에 미션이 없다 — 백업할 것이 없다')
            if a.backup:
                open(a.backup, 'w').write(json.dumps(to_plan([]), indent=4) + '\n')
                print('빈 미션으로 기록: %s' % a.backup)
            return
        for i, g in enumerate(got):
            print('  %d  %-12s(%4d)  alt=%-6s %.7f,%.7f'
                  % (i, NAME.get(g.command, '?'), g.command, g.z,
                     g.x / SCALE, g.y / SCALE))
        if a.backup:
            open(a.backup, 'w').write(json.dumps(to_plan(got), indent=4) + '\n')
            print('저장: %s' % a.backup)
        return

    # push
    if not a.new:
        sys.exit('--new 가 필요하다')
    items = load_plan(a.new)
    print('올릴 것:')
    describe(items)
    print('검사:')
    if not check(items):
        sys.exit('🔴 검사 실패 — 올리지 않는다')
    print('  ✅ 통과')

    print('올리는 중...')
    upload(m, items)

    # 🔴 되읽어 대조한다. ACCEPTED 는 "받았다" 일 뿐 "같다" 가 아니다.
    print('되읽어 대조...')
    got = download(m)
    if compare(items, got):
        print('✅ 올린 것과 FC 의 미션이 같다')
    else:
        sys.exit('🔴 대조 실패 — FC 의 미션을 믿지 마라')


if __name__ == '__main__':
    main()
