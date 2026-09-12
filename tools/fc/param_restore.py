#!/usr/bin/env python3
"""QGC `.params` 파일을 FC 에 되돌려 쓴다.

    param_restore.py params/px4_params_20260912-171950-preflash.params
    param_restore.py <파일> --dry        # 무엇을 쓸지만 본다

🔴 **FC 안의 값을 바꾼다.** `FC_CHANGELOG.md` 에 반드시 기록하라.

## 왜 필요한가 (2026-09-12)

펌웨어를 플래시하면 파라미터가 전부 날아간다. QGC 의 Tools → Load from file
로도 되지만, 그러려면 사람이 창을 열어야 하고 무엇이 실패했는지 목록으로
남지 않는다. 이 스크립트는 **쓴 뒤 되읽어 대조**하고 어긋난 것만 찍는다.

## 안 쓰는 것

- 🔴 **ARM 상태면 거부한다.** 모터가 돌 수 있다.
- **읽기 전용 값은 건너뛴다** — `_HASH_CHECK` 는 PX4 가 스스로 계산한다.
- **새 펌웨어에 없는 파라미터는 조용히 무시된다** (PX4 가 거부). 그것이 정상이고,
  무엇이 무시됐는지 끝에 목록으로 찍는다.

🔴 **int 파라미터는 float 비트로 오간다.** 타입을 그대로 실어 보내야 한다 —
`MAV_PARAM_TYPE_INT32` 로 보내지 않으면 `7` 이 `9.8e-45` 로 들어간다.
"""

import os
import struct
import sys
import time

INT_TYPES = {1, 2, 3, 4, 5, 6, 7, 8}

# PX4 가 스스로 계산하는 값 — 써도 의미가 없다.
SKIP = {'_HASH_CHECK'}


def load(path):
    """[(이름, 값, 타입)] — QGC .params 형식을 읽는다."""
    out = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            if line.startswith('#') or not line.strip():
                continue
            f = line.rstrip('\n').split('\t')
            if len(f) < 5:
                continue
            name, raw, ptype = f[2], f[3], int(f[4])
            if name in SKIP:
                continue
            if ptype in INT_TYPES:
                # 정수 표기를 float 비트로 되돌린다 (백업이 저장한 방식의 역).
                val = struct.unpack('<f', struct.pack('<i', int(raw)))[0]
            else:
                val = float(raw)
            out.append((name, val, ptype))
    return out


def fmt(value, ptype):
    if ptype in INT_TYPES:
        return str(struct.unpack('<i', struct.pack('<f', value))[0])
    return '%.6g' % value


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry' in sys.argv
    if not args:
        raise SystemExit(__doc__.split('\n')[2].strip())
    path = args[0]
    items = load(path)
    print('%s — %d개' % (path, len(items)), file=sys.stderr)
    if dry:
        for n, v, t in items[:20]:
            print('  %-18s %s' % (n, fmt(v, t)))
        print('  ... (--dry 라 쓰지 않았다)')
        return 0

    from pymavlink import mavutil
    conn = os.environ.get('FC_CONN', 'udpout:100.117.47.105:14550')
    m = mavutil.mavlink_connection(conn, source_system=250, source_component=190)
    for _ in range(5):
        m.mav.heartbeat_send(6, 8, 0, 0, 0)
        time.sleep(0.3)
    hb = m.wait_heartbeat(timeout=15)
    if hb is None:
        raise SystemExit('HEARTBEAT 가 없다 — 브리지·USB 를 확인하라')
    if hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
        raise SystemExit('🔴 ARMED 상태다 — 쓰지 않는다')
    tgt, tcomp = m.target_system, m.target_component

    wrote = {}
    for i, (name, val, ptype) in enumerate(items):
        m.mav.param_set_send(tgt, tcomp, name.encode(), val, ptype)
        wrote[name] = (val, ptype)
        if (i + 1) % 100 == 0:
            print('  %d / %d' % (i + 1, len(items)), file=sys.stderr)
            time.sleep(0.4)          # FC 의 파라미터 큐가 넘치지 않게 쉰다
        else:
            time.sleep(0.012)

    print('저장한다 (PREFLIGHT_STORAGE)', file=sys.stderr)
    m.mav.command_long_send(
        tgt, tcomp, mavutil.mavlink.MAV_CMD_PREFLIGHT_STORAGE, 0,
        1, 0, 0, 0, 0, 0, 0)
    t0 = time.time()
    while time.time() - t0 < 10:
        msg = m.recv_match(type='COMMAND_ACK', blocking=True, timeout=1)
        m.mav.heartbeat_send(6, 8, 0, 0, 0)
        if msg and msg.command == mavutil.mavlink.MAV_CMD_PREFLIGHT_STORAGE:
            print('  저장 %s' % ('ACCEPTED' if msg.result == 0 else
                                 'result=%d 🔴' % msg.result), file=sys.stderr)
            break

    # 되읽어 대조한다 — 쓴 것이 실제로 들어갔는지 본다.
    print('되읽어 대조한다', file=sys.stderr)
    m.mav.param_request_list_send(tgt, tcomp)
    got = {}
    t0 = t_last = time.time()
    while time.time() - t0 < 90:
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg is None:
            m.mav.heartbeat_send(6, 8, 0, 0, 0)
            if time.time() - t_last > 3:
                break
            continue
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode('ascii', 'replace')
        got[pid.strip('\x00')] = msg.param_value
        t_last = time.time()

    missing, bad = [], []
    for name, (val, ptype) in wrote.items():
        if name not in got:
            missing.append(name)
        elif fmt(got[name], ptype) != fmt(val, ptype):
            bad.append((name, fmt(val, ptype), fmt(got[name], ptype)))

    print()
    print('되읽음 %d개 / 쓴 것 %d개' % (len(got), len(wrote)))
    if missing:
        print('\n무시된 파라미터 %d개 (새 펌웨어에 없다 — 정상일 수 있다):' % len(missing))
        for n in missing:
            print('   ', n)
    if bad:
        print('\n🔴 값이 다른 것 %d개:' % len(bad))
        for n, want, have in bad:
            print('    %-18s 기대 %s  실제 %s' % (n, want, have))
    if not missing and not bad:
        print('✅ 전부 일치한다')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
