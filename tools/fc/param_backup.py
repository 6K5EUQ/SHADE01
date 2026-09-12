#!/usr/bin/env python3
"""FC 파라미터를 전량 받아 QGC `.params` 형식으로 저장한다.

    param_backup.py [출력경로]
    param_backup.py params/px4_params_20260912-180000.params

인자를 안 주면 `params/px4_params_<YYYYMMDD-HHMMSS>.params` 로 저장한다.

🔴 **읽기 전용이다.** `PARAM_REQUEST_LIST` 만 보내고 `PARAM_SET` 을 안 보낸다.
   FC 안의 값이 안 바뀌므로 `FC_CHANGELOG.md` 에 적을 것이 없다.

## 왜 필요한가 (2026-09-12)

펌웨어를 플래시하면 **파라미터가 전부 날아간다.** 그때 복원할 정본이 있어야
failsafe·고정익 차단·미션·캘리브레이션을 다시 쌓지 않는다.

QGC 로도 뜰 수 있지만, 그러면 사람이 창을 열어야 하고 파일 이름·위치가
그때그때 다르다. 이 스크립트는 리포의 `params/` 에 같은 규칙으로 남긴다.

## 형식

QGC 가 읽는 그 형식 그대로다 — 복원할 때 QGC 의 Tools → Load from file 로
바로 쓴다.

    # MAV ID  COMPONENT ID  PARAM NAME  VALUE  TYPE
    1  1  ASPD_BETA_GATE  1  6

🔴 **int 파라미터는 float 비트로 오간다.** `RC_MAP_TRANS_SW=7` 을 float 로
읽으면 `9.8e-45` 로 보인다. type 이 정수형(1~8)이면 비트를 되돌려 적는다.
"""

import os
import struct
import sys
import time
import datetime

INT_TYPES = {1, 2, 3, 4, 5, 6, 7, 8}


def fetch(conn, timeout=90):
    """(이름 → (값문자열, 타입)) 전량. 못 받은 것이 있으면 재요청한다."""
    from pymavlink import mavutil

    m = mavutil.mavlink_connection(conn, source_system=250, source_component=190)
    for _ in range(5):
        m.mav.heartbeat_send(6, 8, 0, 0, 0)
        time.sleep(0.3)
    hb = m.wait_heartbeat(timeout=15)
    if hb is None:
        raise SystemExit('HEARTBEAT 가 없다 — 브리지·USB 를 확인하라')
    tgt, tcomp = m.target_system, m.target_component

    m.mav.param_request_list_send(tgt, tcomp)
    got = {}
    total = None
    t_last = time.time()
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg is None:
            m.mav.heartbeat_send(6, 8, 0, 0, 0)
            # 3초 넘게 새 값이 없고 아직 덜 받았으면 다시 요청한다.
            if total and len(got) < total and time.time() - t_last > 3:
                m.mav.param_request_list_send(tgt, tcomp)
                t_last = time.time()
            continue
        total = msg.param_count
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode('ascii', 'replace')
        pid = pid.strip('\x00')
        if pid not in got:
            got[pid] = (msg.param_value, msg.param_type)
            t_last = time.time()
            if len(got) % 200 == 0:
                print('  %d / %s' % (len(got), total), file=sys.stderr)
        if total and len(got) >= total:
            break
    return got, total


def fmt(value, ptype):
    """QGC 가 읽는 값 표기. int 형은 float 비트를 되돌린다."""
    if ptype in INT_TYPES:
        return str(struct.unpack('<i', struct.pack('<f', value))[0])
    return repr(float(value))


def main():
    conn = os.environ.get('FC_CONN', 'udpout:100.117.47.105:14550')
    if len(sys.argv) > 1:
        out = sys.argv[1]
    else:
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        out = os.path.join('params', 'px4_params_%s.params' % stamp)

    print('FC 파라미터를 받는다 (%s)' % conn, file=sys.stderr)
    got, total = fetch(conn)
    if not got:
        raise SystemExit('한 개도 못 받았다')
    if total and len(got) < total:
        print('⚠️  %d / %d 만 받았다 — 다시 돌려라' % (len(got), total), file=sys.stderr)

    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write('# Onboard parameters for Vehicle 1\n#\n')
        fh.write('# Stack: PX4\n# Vehicle: VTOL\n# Version: \n')
        fh.write('# Date: %s\n#\n'
                 % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        fh.write('# MAV ID\tCOMPONENT ID\tPARAM NAME\tVALUE\tTYPE\n')
        for name in sorted(got):
            v, t = got[name]
            fh.write('1\t1\t%s\t%s\t%d\n' % (name, fmt(v, t), t))
    print('%s  (%d개)' % (out, len(got)))
    return 0 if (total is None or len(got) >= total) else 1


if __name__ == '__main__':
    sys.exit(main())
