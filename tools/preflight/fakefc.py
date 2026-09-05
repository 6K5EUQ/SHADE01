#!/usr/bin/env python3
"""점검 도구를 시험하려고 FC 인 척한다. 기체도 비행도 필요 없다.

왜 필요한가: `preflight.py` 의 판정 대부분은 **뭔가 잘못됐을 때** 도는 코드다.
멀쩡한 실기에서는 NO-GO 경로가 한 줄도 안 돌아 본 채로 남는다 — 정작 필요한
날에 처음 실행되는 코드가 된다. 여기서 그 경로를 전부 밟는다.

    fakefc.py [프로필] [--port 14550]

프로필:
    good   전부 정상 — GO 가 나와야 한다
    fw     미션이 VTOL_TAKEOFF(84) · RC_MAP_TRANS_SW=7 — 쿼드 전용 위반
    nogps  fix 1 · 위성 3기
    batt   전압 20.4V (6S 21.0 미만)
    armed  ARMED 상태
    vibe   진동 35 · EKF 혁신비 1.4
"""
import argparse
import math
import socket
import struct
import time

from pymavlink.dialects.v20 import common as mav

PROFILES = {
    'good': {}, 'fw': {}, 'nogps': {}, 'batt': {}, 'armed': {}, 'vibe': {},
}

# 실기에서 읽은 값을 기본으로 둔다 (FC_CHANGELOG 기준 2026-09-05 시점).
BASE_PARAMS = {
    'RC_MAP_TRANS_SW': (0, 6), 'VT_ELEV_MC_LOCK': (1, 6),
    'NAV_RCL_ACT': (2, 6), 'NAV_DLL_ACT': (2, 6),
    'RTL_RETURN_ALT': (20.0, 9), 'RTL_DESCEND_ALT': (10.0, 9),
    'GF_ACTION': (0, 6), 'GF_MAX_HOR_DIST': (0.0, 9), 'GF_MAX_VER_DIST': (0.0, 9),
    'NAV_ACC_RAD': (3.0, 9), 'BAT1_N_CELLS': (6, 6), 'MPC_THR_HOVER': (0.65, 9),
    'MAV_0_RATE': (490, 6), 'RC_MAP_KILL_SW': (8, 6),
    'SENS_DPRES_OFF': (-4.52, 9), 'COM_RC_IN_MODE': (3, 6),
    'COM_ARM_WO_GPS': (1, 6), 'MIS_TAKEOFF_ALT': (5.0, 9),
    'NAV_FORCE_VT': (1, 6),
    'COM_FLTMODE1': (8, 6), 'COM_FLTMODE2': (1, 6), 'COM_FLTMODE3': (2, 6),
    'COM_FLTMODE4': (2, 6), 'COM_FLTMODE5': (3, 6), 'COM_FLTMODE6': (5, 6),
}

MISSION_GOOD = [(22, 5.0), (16, 5.0), (16, 5.0), (16, 5.0), (16, 5.0), (21, 0.0)]
MISSION_FW = [(84, 5.0), (16, 5.0), (16, 5.0), (16, 5.0), (16, 5.0), (85, 0.0)]


def f_from_i(i):
    """int 파라미터를 float 비트에 실어 보낸다 — PX4 가 그렇게 한다."""
    return struct.unpack('<f', struct.pack('<i', int(i)))[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('profile', nargs='?', default='good', choices=sorted(PROFILES))
    ap.add_argument('--port', type=int, default=14550)
    ap.add_argument('--secs', type=float, default=25.0)
    a = ap.parse_args()
    P = a.profile

    params = dict(BASE_PARAMS)
    mission = list(MISSION_GOOD)
    if P == 'fw':
        params['RC_MAP_TRANS_SW'] = (7, 6)
        params['VT_ELEV_MC_LOCK'] = (0, 6)
        mission = list(MISSION_FW)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', a.port))
    sock.settimeout(0.05)
    m = mav.MAVLink(None, srcSystem=1, srcComponent=1)
    peer = [None]

    def send(msg):
        if peer[0]:
            try:
                sock.sendto(msg.pack(m), peer[0])
            except Exception:
                pass

    t0 = time.time()
    last = 0.0
    print('fakefc: 프로필 %s · 127.0.0.1:%d 에서 대기' % (P, a.port), flush=True)

    while time.time() - t0 < a.secs:
        try:
            data, addr = sock.recvfrom(2048)
            peer[0] = addr
            for msg in (m.parse_buffer(data) or []):
                t = msg.get_type()
                if t == 'PARAM_REQUEST_READ':
                    nm = msg.param_id
                    nm = nm.decode() if isinstance(nm, bytes) else nm
                    nm = nm.strip('\x00')
                    if nm in params:
                        v, ty = params[nm]
                        raw = f_from_i(v) if ty != 9 else float(v)
                        send(mav.MAVLink_param_value_message(
                            nm.encode().ljust(16, b'\0'), raw, ty, len(params), 0))
                elif t == 'MISSION_REQUEST_LIST':
                    send(mav.MAVLink_mission_count_message(255, 190, len(mission), 0))
                elif t in ('MISSION_REQUEST_INT', 'MISSION_REQUEST'):
                    i = msg.seq
                    if 0 <= i < len(mission):
                        cmd, alt = mission[i]
                        send(mav.MAVLink_mission_item_int_message(
                            255, 190, i, 6, cmd, 0, 1, 0, 0, 0, 0,
                            375000000, 1270000000, alt, 0))
        except socket.timeout:
            pass
        except Exception:
            pass

        now = time.time()
        if now - last < 0.2:
            continue
        last = now
        el = now - t0

        armed = 128 if P == 'armed' else 0
        send(mav.MAVLink_heartbeat_message(2, 12, 81 | armed, 393216, 3, 3))
        fix, sats, eph = (1, 3, 900) if P == 'nogps' else (4, 27, 19)
        send(mav.MAVLink_gps_raw_int_message(
            int(el * 1e6), fix, 375000000, 1270000000, 50000, eph, 20, 0, 0, sats,
            0, 0, 0, 0, 0, 0))
        volt = 20400 if P == 'batt' else 24100
        send(mav.MAVLink_sys_status_message(
            0x3F | (1 << 5) | (1 << 12), 0x3F | (1 << 5) | (1 << 12),
            0x3F | (1 << 5) | (1 << 12), 250, volt, 3000, 63, 0, 0, 0, 0, 0, 0))
        send(mav.MAVLink_attitude_message(
            int(el * 1000), math.radians(1.2), math.radians(-0.6), 0.5, 0, 0, 0))
        vb = 35.0 if P == 'vibe' else 3.1
        send(mav.MAVLink_vibration_message(int(el * 1e6), vb, vb * .9, vb * 1.1, 0, 0, 0))
        rt = 1.4 if P == 'vibe' else 0.28
        send(mav.MAVLink_estimator_status_message(
            int(el * 1e6), 0xFFFF, rt, rt, rt, rt, 0.2, 0.1, 0.1, 0.1))
        send(mav.MAVLink_extended_sys_state_message(3, 1))
        send(mav.MAVLink_vfr_hud_message(-4.9, 0.1, 0, 12, 50.0, 0.0))
        send(mav.MAVLink_rc_channels_message(
            int(el * 1000), 8, 1500, 1500, 1000, 1500, 1000, 1275, 1500, 1000,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 200))
        send(mav.MAVLink_home_position_message(
            375000000, 1270000000, 50000, 0.0, 0.0, 0.0, [1.0, 0.0, 0.0, 0.0],
            0.0, 0.0, 0.0, 0))
        send(mav.MAVLink_global_position_int_message(
            int(el * 1000), 375000000, 1270000000, 50000, 1000, 0, 0, 0, 0))
        if P == 'fw' and int(el) % 5 == 2:
            send(mav.MAVLink_statustext_message(
                3, b'Preflight Fail: VTOL transition armed'.ljust(50, b'\0'), 0, 0))
    print('fakefc: 끝', flush=True)


if __name__ == '__main__':
    main()
