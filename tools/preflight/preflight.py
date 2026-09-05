#!/usr/bin/env python3
"""SHADE01 비행 전 점검 — 한 번 붙어서 한 번에 끝낸다.

🔴 **읽기 전용이다.** `PARAM_SET`·`COMMAND_LONG`·미션 업로드를 절대 보내지 않는다.
   보내는 것은 GCS 하트비트(브리지가 우리를 peer 로 등록해야 하행이 온다)와
   `PARAM_REQUEST_READ`·`MISSION_REQUEST_LIST` 뿐이다. FC 안의 값은 안 바뀌므로
   `FC_CHANGELOG.md` 에 적을 일이 없다.

## 왜 이 도구가 있나

같은 점검을 대화로 하면 왕복이 수십 번이다 — 파라미터 하나 읽고, 판정 묻고,
다음 것 읽고. 실측 결과 그 방식은 수 분이 걸렸다. 여기서는

  ① 한 번 연결한다 (시리얼이 비었으면 직결, 아니면 브리지 UDP)
  ② 필요한 파라미터 **약 40개만** 한꺼번에 요청한다 (전량 1354개를 받지 않는다)
  ③ 그 응답을 기다리는 **동안** 텔레메트리를 같은 소켓에서 주워 담는다
  ④ 미션을 받아 이착륙 명령을 확인한다
  ⑤ 판정표를 한 장 찍는다

전부 한 패스라 실측 **10초 안쪽**이다.

## 판정 기준의 출처

임계값은 이 기체에 묶여 있다. 근거는 전부 리포 안에 있다 —
`FC_CHANGELOG.md`(파라미터가 왜 그 값인지), `flights/`(실측 이력),
`README.md`(현재 제한). 다른 기체에 그대로 쓰면 안 된다.
"""

import argparse
import math
import os
import subprocess
import sys
import time

# ── 이 기체의 기대값. 바꿀 때는 FC_CHANGELOG.md 근거를 같이 남겨라. ──────────
#
# (기대값, 판정등급, 왜)  — 등급: 'blk' 진행불가 / 'warn' 확인필요
EXPECT = {
    # 🔴 쿼드 전용 잠금 (2026-09-04~05). 하나라도 열리면 의도치 않게 천이한다.
    'RC_MAP_TRANS_SW': (0, 'blk', '천이 스위치가 매핑되면 조종기로 고정익 전환이 걸린다'),
    'VT_ELEV_MC_LOCK': (1, 'blk', 'MC 구간에서 제어면이 안 잠기면 천이 자세가 섞인다'),

    # 🔴 failsafe. 이 값들이 비면 링크가 끊겼을 때 기체가 아무것도 안 한다.
    'NAV_RCL_ACT':     (2, 'blk', 'RC 상실 시 RTL 이어야 한다'),
    'NAV_DLL_ACT':     (2, 'blk', '데이터링크 두절 시 RTL (2026-09-05 14:16)'),
    'RTL_RETURN_ALT':  (20, 'warn', '순항 5m 인데 60m 로 솟던 것을 내렸다 (9/5 17:15)'),
    'RTL_DESCEND_ALT': (10, 'warn', '직선 복귀라 너무 낮으면 장애물 위험'),

    # 지오펜스는 **꺼 둔 것이 정상이다** (9/5 14:16). Hold 가 #184 조종 불능의
    # 직접 원인이었고 참조 함대 18대 전원이 안 쓴다. 켜져 있으면 그게 이상이다.
    'GF_ACTION':       (0, 'warn', '지오펜스는 꺼 둔 상태가 정상 — 2 는 조종권을 뺏는다'),
    'GF_MAX_HOR_DIST': (0, 'warn', '펜스 해제 상태 (거리 관리는 조종자 몫)'),
    'GF_MAX_VER_DIST': (0, 'warn', '펜스 해제 상태'),

    # 항법·미션
    'NAV_ACC_RAD':     (3, 'warn', 'RTK eph 0.14m 실측 — 10m 는 과했다 (9/5 16:45)'),

    # 전원. 6S 는 하드웨어 사실이다.
    'BAT1_N_CELLS':    (6, 'blk', '셀 수가 틀리면 저전압 판정이 통째로 어긋난다'),
    'MPC_THR_HOVER':   (0.65, 'warn', 'FC 자체 추정과 30% 어긋나 있던 것을 맞췄다 (9/5 17:15)'),

    # 링크
    'MAV_0_RATE':      (490, 'warn', '300 으로 조였다가 되돌린 값 (9/5 17:22)'),
}

# 스위치는 "매핑되어 있기만" 하면 된다. 채널 번호는 조종기 구성에 따라 바뀐다.
MUST_BE_MAPPED = {
    'RC_MAP_KILL_SW': ('blk', 'KILL 스위치가 매핑돼 있어야 한다'),
}

# 값을 보여만 주고 판정하지 않는 것. 맥락이 있어야 읽히는 값들이다.
INFORM = {
    'SENS_DPRES_OFF':  '피토관 영점 — 고장 상태의 지표다 (-4.52 근처면 그대로)',
    'COM_RC_IN_MODE':  '0=RC only, 1=MAVLink, 3=둘 다',
    'COM_ARM_WO_GPS':  '1 이어도 Position·Mission 은 자체 검사가 막는다',
    'MIS_TAKEOFF_ALT': '미션 이륙 고도',
    'NAV_FORCE_VT':    '기체가 이미 FW 일 때만 동작한다 — 84 를 막지 못한다',
}

FLTMODE_PARAMS = ['COM_FLTMODE%d' % i for i in range(1, 7)]

# PX4 비행모드 번호 → 이름. 고정익 모드가 슬롯에 있으면 진입 경로가 열린 것이다.
# (PX4 commander_params.c 의 COM_FLTMODE1 열거)
FLTMODE = {
    -1: '없음', 0: 'Manual', 1: 'Altitude', 2: 'Position', 3: 'Mission',
    4: 'Hold', 5: 'Return', 6: 'Acro', 7: 'Offboard', 8: 'Stabilized',
    9: 'Rattitude', 10: 'Takeoff', 11: 'Land', 12: 'Follow Me', 13: 'Precision Land',
}

# 미션 이착륙 명령. 🔴 84(VTOL_TAKEOFF)는 이름과 달리 "떠서 **고정익으로 전환**하라"다 —
# mission.cpp 가 상승 후 set_vtol_transition_item(FW) 를 부른다. 스위치를 거치지 않으므로
# RC_MAP_TRANS_SW=0 으로도 못 막는다. 쿼드 전용이면 22/21 이어야 한다 (9/5 16:45 규명).
CMD_NAME = {16: 'WAYPOINT', 20: 'RTL', 21: 'LAND', 22: 'TAKEOFF',
            84: 'VTOL_TAKEOFF', 85: 'VTOL_LAND', 189: 'DO_LAND_START'}
FW_MISSION_CMDS = {84: 'VTOL_TAKEOFF', 85: 'VTOL_LAND', 3000: 'DO_VTOL_TRANSITION'}

ALL_PARAMS = (list(EXPECT) + list(MUST_BE_MAPPED) + list(INFORM) + FLTMODE_PARAMS)


def i32(v):
    """PX4 int 파라미터는 float 비트로 오간다. RC_MAP_TRANS_SW=7 을 float 로 읽으면
    9.8e-45 로 보인다 — 되돌리지 않으면 판정이 통째로 틀린다 (CLAUDE.md)."""
    import struct
    return struct.unpack('<i', struct.pack('<f', v))[0]


def pval(msg):
    """PARAM_VALUE 하나를 사람이 쓰는 값으로. type 을 보고 int/float 를 가른다."""
    t = msg.param_type
    # MAV_PARAM_TYPE: 1..8 이 정수 계열, 9=REAL32, 10=REAL64
    if t in (1, 2, 3, 4, 5, 6, 7, 8):
        try:
            return i32(msg.param_value)
        except Exception:
            return int(msg.param_value)
    return float(msg.param_value)


# ── 연결 ────────────────────────────────────────────────────────────────────
def serial_busy(dev):
    """시리얼을 누가 쥐고 있나. 쥐고 있으면 (pid, cmd) 를 준다.

    🔴 이걸 먼저 보는 이유: 브리지나 fcfetch 가 물고 있는데 열려고 하면
       'device reports readiness to read but returned no data' 로 죽는다.
       원인이 안 보이는 오류라 여기서 미리 이름을 대 준다."""
    try:
        out = subprocess.run(['fuser', dev], capture_output=True, text=True, timeout=4)
        pid = out.stdout.strip().split()
        if not pid:
            return None
        pid = pid[0]
        cmd = subprocess.run(['ps', '-o', 'cmd=', '-p', pid],
                             capture_output=True, text=True, timeout=4).stdout.strip()
        return (pid, cmd)
    except Exception:
        return None


def find_serial():
    for d in ('/dev/ttyACM0', '/dev/ttyACM1'):
        if os.path.exists(d):
            return d
    return None


def connect(explicit, verbose):
    """시리얼이 비었으면 직결, 아니면 브리지 UDP. 실패 사유를 사람 말로 남긴다."""
    from pymavlink import mavutil

    tries = []
    if explicit:
        tries.append((explicit, '지정'))
    else:
        dev = find_serial()
        if dev:
            busy = serial_busy(dev)
            if busy:
                tries.append((None, '%s 는 PID %s 가 쥐고 있다: %s'
                              % (dev, busy[0], busy[1][:60])))
            else:
                tries.append((dev, 'FC USB 직결'))
        # 브리지 경유. 자기 Tailscale 주소로 보내야 브리지의 허용목록을 통과한다.
        ts = tailscale_ip()
        if ts:
            tries.append(('udpout:%s:14550' % ts, '브리지 UDP 경유'))
        tries.append(('udpout:127.0.0.1:14550', '브리지 UDP (로컬)'))

    notes = []
    for conn, why in tries:
        if conn is None:
            notes.append(why)
            continue
        try:
            baud = 921600 if conn.startswith('/dev/') else None
            m = (mavutil.mavlink_connection(conn, baud=baud, source_system=250,
                                            source_component=190)
                 if baud else
                 mavutil.mavlink_connection(conn, source_system=250, source_component=190))
        except Exception as e:
            notes.append('%s: %s' % (why, e))
            continue

        # 🔴 udpout 은 우리가 먼저 말을 걸어야 브리지가 peer 로 등록한다.
        #    안 그러면 하행이 영영 안 온다 (실측: 15초 기다려도 무응답).
        t0 = time.time()
        hb = None
        for _ in range(6):
            try:
                m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            except Exception:
                pass
            hb = m.wait_heartbeat(timeout=1)
            if hb:
                break
        if hb:
            return m, why, time.time() - t0, notes
        notes.append('%s: 하트비트 없음' % why)
        try:
            m.close()
        except Exception:
            pass
    return None, None, 0, notes


def tailscale_ip():
    try:
        out = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True,
                             text=True, timeout=4).stdout.strip().split()
        return out[0] if out else None
    except Exception:
        return None


# ── 수집 ────────────────────────────────────────────────────────────────────
def gather(m, secs, verbose):
    """파라미터·미션·텔레메트리를 **한 소켓에서 동시에** 걷는다.

    파라미터 응답을 기다리는 시간이 어차피 필요하므로, 그 동안 들어오는
    텔레메트리를 같이 주워 담는다. 따로 하면 시간이 두 배가 된다."""
    from pymavlink import mavutil

    tgt, tcomp = m.target_system, m.target_component
    params, tel, msgs, dropped = {}, {}, [], []
    mission = {'count': None, 'items': {}, 'requested': set()}

    for n in ALL_PARAMS:
        m.mav.param_request_read_send(tgt, tcomp, n.encode('ascii'), -1)
    m.mav.mission_request_list_send(tgt, tcomp, 0)

    t_end = time.time() + secs
    last_retry = time.time()
    while time.time() < t_end:
        msg = m.recv_match(blocking=True, timeout=0.3)
        if msg is None:
            continue
        t = msg.get_type()
        try:
            _absorb(m, msg, t, tgt, tcomp, params, mission, tel, msgs)
        except Exception as e:
            # 🔴 메시지 하나가 예상과 달라도 점검은 끝까지 간다. 비행 전에
            #    "도구가 죽었다" 는 답을 받는 것이 제일 나쁘다 — 무엇이
            #    빠졌는지는 아래 '파라미터 수신' · 각 항목의 '데이터 없음' 이 말한다.
            dropped.append('%s: %s' % (t, e))
            if verbose:
                print('  (무시한 %s: %s)' % (t, e))
            continue

        # 못 받은 것만 한 번 더 조른다. UDP 는 조용히 흘린다.
        if time.time() - last_retry > 1.5:
            last_retry = time.time()
            miss = [n for n in ALL_PARAMS if n not in params]
            for n in miss[:25]:
                m.mav.param_request_read_send(tgt, tcomp, n.encode('ascii'), -1)
            if mission['count'] is not None:
                for i in range(mission['count']):
                    if i not in mission['items']:
                        m.mav.mission_request_int_send(tgt, tcomp, i, 0)

        done = (len(params) == len(ALL_PARAMS)
                and mission['count'] is not None
                and len(mission['items']) == mission['count']
                and {'fix', 'volt', 'roll'} <= set(tel))
        if done and time.time() > t_end - (secs - 3.0):
            break

    return params, mission, tel, msgs, dropped


MAV_MODE_FLAG_SAFETY_ARMED = 128        # MAVLink 표준. import 스코프에 안 기댄다.


def _absorb(m, msg, t, tgt, tcomp, params, mission, tel, msgs):
    """메시지 하나를 갈무리한다. 예외는 호출자가 삼킨다."""
    if t == 'PARAM_VALUE':
        nm = msg.param_id.strip('\x00')
        if nm in ALL_PARAMS and nm not in params:
            params[nm] = pval(msg)

    elif t == 'MISSION_COUNT':
        if mission['count'] is None:
            mission['count'] = msg.count
            for i in range(msg.count):
                m.mav.mission_request_int_send(tgt, tcomp, i, 0)
                mission['requested'].add(i)

    elif t in ('MISSION_ITEM_INT', 'MISSION_ITEM'):
        mission['items'][msg.seq] = msg

    elif t == 'STATUSTEXT':
        txt = msg.text.strip('\x00') if isinstance(msg.text, str) else str(msg.text)
        sev = msg.severity
        if sev <= 4:                      # EMERG..WARNING 만 (INFO 는 소음)
            msgs.append((sev, txt))

    elif t == 'HEARTBEAT' and msg.get_srcSystem() == tgt:
        tel['base_mode'] = msg.base_mode
        tel['custom_mode'] = msg.custom_mode
        tel['armed'] = bool(msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED)
        tel['mav_type'] = msg.type

    elif t == 'GPS_RAW_INT':
        tel['fix'] = msg.fix_type
        tel['sats'] = msg.satellites_visible
        tel['eph'] = msg.eph / 100.0 if msg.eph not in (0, 65535) else None

    elif t == 'SYS_STATUS':
        tel['volt'] = msg.voltage_battery / 1000.0 if msg.voltage_battery not in (0, 65535) else None
        tel['cur'] = msg.current_battery / 100.0 if msg.current_battery != -1 else None
        tel['batt_pct'] = msg.battery_remaining if msg.battery_remaining != -1 else None
        tel['sensors_present'] = msg.onboard_control_sensors_present
        tel['sensors_enabled'] = msg.onboard_control_sensors_enabled
        tel['sensors_health'] = msg.onboard_control_sensors_health

    elif t == 'ATTITUDE':
        import math
        tel['roll'] = math.degrees(msg.roll)
        tel['pitch'] = math.degrees(msg.pitch)
        tel['yaw'] = math.degrees(msg.yaw)

    elif t == 'VIBRATION':
        tel['vibe'] = (msg.vibration_x, msg.vibration_y, msg.vibration_z)
        tel['clip'] = (msg.clipping_0, msg.clipping_1, msg.clipping_2)

    elif t == 'ESTIMATOR_STATUS':
        tel['ekf_flags'] = msg.flags
        tel['ekf_vel'] = msg.vel_ratio
        tel['ekf_pos'] = msg.pos_horiz_ratio
        tel['ekf_vrt'] = msg.pos_vert_ratio
        tel['ekf_mag'] = msg.mag_ratio

    elif t == 'EXTENDED_SYS_STATE':
        tel['vtol_state'] = msg.vtol_state
        tel['landed_state'] = msg.landed_state

    elif t == 'VFR_HUD':
        tel['airspeed'] = msg.airspeed
        tel['groundspeed'] = msg.groundspeed
        tel['alt_msl'] = msg.alt

    elif t == 'RC_CHANNELS':
        tel['rc_rssi'] = msg.rssi
        tel['rc_count'] = msg.chancount
        tel['rc'] = [getattr(msg, 'chan%d_raw' % i) for i in range(1, 9)]

    elif t == 'HOME_POSITION':
        tel['home'] = (msg.latitude / 1e7, msg.longitude / 1e7)

    elif t == 'GLOBAL_POSITION_INT':
        tel['lat'] = msg.lat / 1e7
        tel['lon'] = msg.lon / 1e7
        tel['alt_rel'] = msg.relative_alt / 1000.0



# ── 판정 ────────────────────────────────────────────────────────────────────
class Report:
    """판정을 모은다. 등급은 셋뿐이다 — 막을 것, 볼 것, 괜찮은 것."""

    def __init__(self):
        self.blk, self.warn, self.ok, self.info = [], [], [], []

    def add(self, level, name, detail, why=''):
        {'blk': self.blk, 'warn': self.warn, 'ok': self.ok, 'info': self.info}[level] \
            .append((name, detail, why))

    def verdict(self):
        return 'NO-GO' if self.blk else ('확인 후 판단' if self.warn else 'GO')


def isnan(v):
    try:
        return math.isnan(float(v))
    except Exception:
        return False


def near(a, b, tol=1e-3):
    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


def check_params(r, p):
    missing = [n for n in ALL_PARAMS if n not in p]

    # 기대값 대조
    for name, (want, level, why) in EXPECT.items():
        if name not in p:
            r.add('warn', name, '읽지 못했다', '값을 모르면 판정도 못 한다')
            continue
        got = p[name]
        if near(got, want, 0.001 if isinstance(want, float) else 0.5):
            r.add('ok', name, '%s' % fmtv(got))
        else:
            r.add(level, name, '%s  (기대 %s)' % (fmtv(got), fmtv(want)), why)

    # 매핑만 확인하면 되는 것
    for name, (level, why) in MUST_BE_MAPPED.items():
        if name not in p:
            r.add('warn', name, '읽지 못했다', why)
        elif int(p[name]) == 0:
            r.add(level, name, '미매핑 (0)', why)
        else:
            r.add('ok', name, 'CH%d' % int(p[name]))

    # 🔴 비행모드 6슬롯에 고정익 모드가 있으면 스위치 하나로 천이한다.
    slots, fw_slots = [], []
    for i, name in enumerate(FLTMODE_PARAMS, 1):
        if name not in p:
            continue
        v = int(p[name])
        slots.append('%d:%s' % (i, FLTMODE.get(v, str(v))))
        # PX4 의 6슬롯에는 FW 전용 모드가 애초에 없다. 있으면 펌웨어가 다른 것이다.
        if v in (6,):                       # Acro — 쿼드 곡예. 운용상 쓰지 않는다
            fw_slots.append('%d:%s' % (i, FLTMODE.get(v, v)))
    if slots:
        if fw_slots:
            r.add('warn', '비행모드 슬롯', ' '.join(slots),
                  '곡예/비운용 모드가 슬롯에 있다: ' + ', '.join(fw_slots))
        else:
            r.add('ok', '비행모드 슬롯', ' '.join(slots))

    for name, note in INFORM.items():
        if name in p:
            r.add('info', name, fmtv(p[name]), note)

    if missing:
        r.add('warn', '파라미터 수신', '%d개 못 받음' % len(missing),
              ', '.join(missing[:8]) + ('…' if len(missing) > 8 else ''))


def fmtv(v):
    if isinstance(v, float):
        return ('%.4f' % v).rstrip('0').rstrip('.')
    return str(v)


def check_mission(r, mission):
    n = mission['count']
    if n is None:
        r.add('warn', '미션', '못 받았다', 'FC 가 MISSION_COUNT 를 안 줬다')
        return
    if n == 0:
        r.add('info', '미션', '없음 (0항목)', '수동 비행이면 정상이다')
        return

    items = [mission['items'][i] for i in sorted(mission['items'])]
    if len(items) != n:
        r.add('warn', '미션', '%d/%d 항목만 받았다' % (len(items), n), '')

    fw = [(it.seq, FW_MISSION_CMDS[it.command]) for it in items
          if it.command in FW_MISSION_CMDS]
    alts = [it.z for it in items if it.command in (16, 22)]
    desc = ' '.join('%d:%s' % (it.seq, CMD_NAME.get(it.command, it.command))
                    for it in items)

    if fw:
        r.add('blk', '미션 이착륙', desc,
              '🔴 %s — 이름과 달리 상승 후 **고정익 전환**을 건다. '
              '스위치를 안 거치므로 RC_MAP_TRANS_SW=0 으로도 못 막는다. '
              '쿼드 전용이면 22/21 이어야 한다 (FC_CHANGELOG 9/5 16:45)'
              % ', '.join('seq%d %s' % f for f in fw))
    else:
        r.add('ok', '미션 %d항목' % n, desc)

    if alts:
        lo, hi = min(alts), max(alts)
        if hi > 30:
            r.add('warn', '미션 고도', '%.0f~%.0f m' % (lo, hi), '이 기체 실측 최고 19.9m')
        else:
            r.add('ok', '미션 고도', '%.0f~%.0f m' % (lo, hi))


# SYS_STATUS 센서 비트. PX4 가 실제로 채우는 것만 본다.
SENSOR_BITS = [
    (1 << 0, '자이로'), (1 << 1, '가속도계'), (1 << 2, '지자기'),
    (1 << 3, '기압계'), (1 << 5, 'GPS'), (1 << 12, 'RC 수신'),
    (1 << 24, '배터리'),
]


def check_live(r, tel, msgs):
    # ARM 상태 — 점검은 DISARM 에서 해야 안전하다.
    # 🔴 `armed` 가 아예 없으면 "DISARMED" 라고 답하면 안 된다. 하트비트를 못 읽은
    #    것과 무장이 안 된 것은 전혀 다르고, 전자를 후자로 답하면 도구가
    #    모르는 것을 안전하다고 말하는 셈이다 (실측으로 잡은 버그).
    if 'armed' not in tel:
        r.add('blk', 'ARM 상태', '확인 불가', '하트비트를 못 읽었다 — 무장 여부를 모른 채로 날리지 마라')
    elif tel['armed']:
        r.add('blk', 'ARM 상태', '🔴 ARMED', '점검 중 모터가 돌 수 있다. DISARM 하고 다시 하라')
    else:
        r.add('ok', 'ARM 상태', 'DISARMED')

    # GPS
    fix, sats, eph = tel.get('fix'), tel.get('sats'), tel.get('eph')
    if fix is None:
        r.add('warn', 'GPS', '데이터 없음', 'GPS_RAW_INT 가 안 온다')
    else:
        d = 'fix %d · %s기%s' % (fix, sats if sats is not None else '?',
                                 ' · eph %.2fm' % eph if eph else '')
        if fix < 3:
            r.add('blk', 'GPS', d, '3D fix 가 없으면 Position·Mission·RTL 이 안 선다')
        elif sats is not None and sats < 10:
            r.add('warn', 'GPS', d, '위성이 적다 (야외 실측은 21~32기)')
        elif eph and eph > 1.0:
            r.add('warn', 'GPS', d, 'eph 가 크다 (실측 0.15~0.23m)')
        else:
            r.add('ok', 'GPS', d)

    # 배터리 — 6S 기준
    v = tel.get('volt')
    if v is None:
        r.add('warn', '배터리', '전압 없음', '')
    else:
        cell = v / 6.0
        d = '%.2f V · %.2f V/셀' % (v, cell)
        if v < 21.0:
            r.add('blk', '배터리', d, '6S 21.0V 미만 — 날리면 안 된다')
        elif v < 22.2:
            r.add('warn', '배터리', d, '충전 권장 (만충 25.2V)')
        else:
            r.add('ok', '배터리', d)

    # 자세 — 지상에서 기울어 있으면 수평 아닌 곳이거나 IMU 가 틀어진 것
    roll, pitch = tel.get('roll'), tel.get('pitch')
    if roll is not None:
        d = 'roll %+.1f° pitch %+.1f°' % (roll, pitch)
        if abs(roll) > 10 or abs(pitch) > 10:
            r.add('warn', '지상 자세', d, '기체가 기울어 있거나 IMU 가 틀어졌다')
        else:
            r.add('ok', '지상 자세', d)

    # 진동
    vibe = tel.get('vibe')
    if vibe:
        mx = max(vibe)
        d = 'x %.1f y %.1f z %.1f' % vibe
        if mx == 0.0:
            # 지상 정지에서도 완전한 0 은 잘 안 나온다. 값이 아니라 아직
            # 안 채워진 것으로 보는 편이 안전하다.
            r.add('warn', '진동', d, '전부 0 — 아직 값이 안 온 것일 수 있다. 모터를 돌려 다시 보라')
        elif mx > 30:
            r.add('blk', '진동', d, '위험 수준')
        elif mx > 10:
            r.add('warn', '진동', d, '경고선 10 초과')
        else:
            r.add('ok', '진동', d)

    # EKF 혁신비 — 1.0 을 넘으면 센서끼리 안 맞는다
    # 🔴 NaN 을 그냥 지나치면 안 된다. `NaN > 1.0` 은 False 라 비교만으로는
    #    조용히 '정상' 이 된다 — 모르는 것을 안전하다고 답하는 그 부류다.
    #    실기에서 EKF 가 아직 안 선 동안 vel·pos 가 NaN 으로 나온다.
    ratios = {k[4:]: tel[k] for k in ('ekf_vel', 'ekf_pos', 'ekf_vrt', 'ekf_mag')
              if tel.get(k) is not None}
    if ratios:
        d = ' '.join('%s %s' % (k, 'nan' if isnan(v) else '%.2f' % v)
                     for k, v in ratios.items())
        nans = [k for k, v in ratios.items() if isnan(v)]
        good = [v for v in ratios.values() if not isnan(v)]
        worst = max(good) if good else None
        if nans:
            r.add('warn', 'EKF 혁신비', d,
                  '%s 가 NaN — 추정기가 아직 안 섰다. GPS·자세가 잡히면 사라진다. '
                  '이 상태로는 Position·Mission 이 안 선다' % ', '.join(nans))
        elif worst > 1.0:
            r.add('blk', 'EKF 혁신비', d, '센서 불일치 — 뜨면 위치가 튄다')
        elif worst > 0.5:
            r.add('warn', 'EKF 혁신비', d, '여유가 적다')
        else:
            r.add('ok', 'EKF 혁신비', d)

    # 센서 건강 비트
    pres, health = tel.get('sensors_present'), tel.get('sensors_health')
    if pres is not None and health is not None:
        bad = [nm for bit, nm in SENSOR_BITS if (pres & bit) and not (health & bit)]
        if bad:
            r.add('blk', '센서 상태', '이상: ' + ', '.join(bad), 'SYS_STATUS 건강 비트')
        else:
            r.add('ok', '센서 상태', '보고된 센서 전부 정상')

    # VTOL 상태 — 쿼드 전용
    vs = tel.get('vtol_state')
    if vs is not None:
        name = {0: '미정', 1: '천이 중(FW로)', 2: '천이 중(MC로)', 3: 'MC', 4: 'FW'}.get(vs, vs)
        if vs == 4:
            r.add('blk', 'VTOL 상태', name, '🔴 고정익 상태다 — 이 기체는 쿼드 전용이다')
        elif vs in (1, 2):
            r.add('warn', 'VTOL 상태', name, '천이 중이다')
        else:
            r.add('ok', 'VTOL 상태', name)

    # RC
    rc = tel.get('rc')
    if rc:
        r.add('ok', 'RC 입력', 'CH1~8 %s' % ' '.join(str(x) for x in rc[:8]))
    else:
        r.add('warn', 'RC 입력', '없다', '조종기가 꺼져 있거나 수신기가 안 붙었다')

    # 에어스피드 — 고장이 **정상 상태**다. 값이 바뀌면 알려 준다.
    a = tel.get('airspeed')
    if a is not None:
        if a < -2:
            r.add('info', '대기속도', '%.1f m/s' % a,
                  '고장 상태 그대로 (SENS_DPRES_OFF=-4.52). 고정익 금지의 근거다')
        else:
            r.add('warn', '대기속도', '%.1f m/s' % a,
                  '고장값(-4.7~-5.0)에서 벗어났다 — 영점을 다시 확인하라')

    # 홈 위치
    if tel.get('home') and tel.get('lat'):
        import math
        hlat, hlon = tel['home']
        dlat = (tel['lat'] - hlat) * 111320
        dlon = (tel['lon'] - hlon) * 111320 * math.cos(math.radians(hlat))
        d = math.hypot(dlat, dlon)
        if d > 20:
            r.add('warn', '홈 위치', '기체에서 %.0f m' % d,
                  'RTL 이 그리로 간다. arm 후 QGC 에서 H 아이콘이 기체 위인지 확인하라')
        else:
            r.add('ok', '홈 위치', '기체에서 %.0f m' % d)
    else:
        r.add('info', '홈 위치', '아직 없다', 'arm 하면 잡힌다')

    # FC 가 스스로 뱉은 경고 — 임계값 판정보다 맥락이 짙다
    seen, out = set(), []
    for sev, txt in msgs:
        if txt not in seen:
            seen.add(txt)
            out.append((sev, txt))
    SEVN = {0: 'EMERG', 1: 'ALERT', 2: 'CRIT', 3: 'ERROR', 4: 'WARN'}
    for sev, txt in out[-8:]:
        lvl = 'blk' if (sev <= 3 and 'Preflight Fail' in txt) else 'warn'
        r.add(lvl, 'FC: ' + SEVN.get(sev, str(sev)), txt, '')


# ── 출력 ────────────────────────────────────────────────────────────────────
# 매 비행 기억할 것. 🔴 **판정에 넣지 않는다** — 늘 켜지는 경고는 무시하는 법을
# 가르쳐서, 정작 그날 생긴 이상이 같은 줄에 섞여 안 보이게 된다.
STANDING = [
    ('전류', '2026-09-05 최대 90.2A · 평균 45.9A — XT90 연속 정격 45A 의 2배. '
             '착륙 후 커넥터를 손으로 만져 발열을 본다'),
    ('나침반', '전류-자기장 상관 −0.91 실측 — Position 에서 기수가 흐른다 '
               '(flights/2026-09-05-hover-compass-interference.md)'),
    ('고정익', '금지. 에어스피드 영점(SENS_DPRES_OFF=-4.52) 미해결 — '
               '푸는 순서는 영점 먼저, 그 다음 미션 84/85'),
    ('지오펜스', '꺼져 있다 (의도한 것). 거리 관리는 전적으로 조종자 몫이다'),
    ('홈', 'arm 뒤 QGC 지도에서 H 가 기체 위인지 눈으로 본다 — RTL 이 그리로 간다'),
]

C = {'r': '\033[31m', 'y': '\033[33m', 'g': '\033[32m', 'd': '\033[2m',
     'b': '\033[1m', '0': '\033[0m'}


def paint(on):
    if not on:
        for k in C:
            C[k] = ''


def render(r, meta, elapsed, verbose):
    W = 78
    print()
    print('%s%s%s   %s' % (C['b'], 'SHADE01 비행 전 점검', C['0'],
                           time.strftime('%Y-%m-%d %H:%M:%S KST')))
    print('%s%s%s' % (C['d'], '─' * W, C['0']))
    print('경로: %s%s%s   %s   %s%.1f초%s'
          % (C['b'], meta['how'], C['0'], meta.get('fw', ''),
             C['d'], elapsed, C['0']))
    if meta.get('notes'):
        for n in meta['notes']:
            print('  %s· %s%s' % (C['d'], n, C['0']))
    print()

    def block(title, rows, col, mark):
        if not rows:
            return
        print('%s%s%s (%d)' % (col + C['b'], title, C['0'], len(rows)))
        for name, detail, why in rows:
            print('  %s%s%s %-18s %s' % (col, mark, C['0'], name, detail))
            if why:
                # 왜 막혔는지가 다음 행동을 정한다. 접지 않는다.
                for line in wrap(why, W - 24):
                    print('     %s%s%s' % (C['d'], line, C['0']))
        print()

    block('진행 불가', r.blk, C['r'], '✖')
    block('확인 필요', r.warn, C['y'], '▲')
    if verbose:
        block('정상', r.ok, C['g'], '✔')
        block('참고', r.info, C['d'], '·')
    else:
        if r.ok:
            print('%s✔ 정상 (%d)%s  %s' % (C['g'] + C['b'], len(r.ok), C['0'],
                                          C['d'] + ', '.join(n for n, _, _ in r.ok)[:200] + C['0']))
            print()

    print('%s기억할 것%s  %s(판정과 무관 — 매번 같다)%s'
          % (C['b'], C['0'], C['d'], C['0']))
    for name, txt in STANDING:
        for i, line in enumerate(wrap(txt, W - 12)):
            print('  %s%-8s %s%s' % (C['d'], name if i == 0 else '', line, C['0']))
    print()

    v = r.verdict()
    col = C['r'] if v == 'NO-GO' else (C['y'] if v != 'GO' else C['g'])
    print('%s%s' % (C['d'], '─' * W) + C['0'])
    print('%s판정: %s%s' % (col + C['b'], v, C['0']))
    if not verbose:
        print('%s  (정상·참고 항목까지 보려면 -v)%s' % (C['d'], C['0']))
    print()
    return 0 if v == 'GO' else (1 if v == 'NO-GO' else 2)


def wrap(s, w):
    out, cur = [], ''
    for word in s.split(' '):
        if len(cur) + len(word) + 1 > w and cur:
            out.append(cur)
            cur = word
        else:
            cur = (cur + ' ' + word).strip()
    if cur:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser(
        description='SHADE01 비행 전 점검 (읽기 전용 — FC 값을 바꾸지 않는다)')
    ap.add_argument('--conn', help='mavlink 연결 문자열. 안 주면 시리얼→브리지 순으로 찾는다')
    ap.add_argument('-t', '--secs', type=float, default=6.0,
                    help='텔레메트리 수집 시간 (기본 6초)')
    ap.add_argument('-v', '--verbose', action='store_true', help='정상 항목까지 전부')
    ap.add_argument('--no-color', action='store_true')
    a = ap.parse_args()
    paint(not a.no_color and sys.stdout.isatty())

    t0 = time.time()
    m, how, hb_s, notes = connect(a.conn, a.verbose)
    if m is None:
        print()
        print('%sFC 에 붙지 못했다.%s' % (C['r'] + C['b'], C['0']))
        for n in notes:
            print('  · %s' % n)
        print()
        print('%s확인할 것:%s' % (C['b'], C['0']))
        print('  · FC USB 가 이 PC 에 꽂혀 있나  (ls /dev/ttyACM*)')
        print('  · 누가 포트를 쥐고 있나          (fuser -v /dev/ttyACM0)')
        print('  · 브리지가 떠 있나               (pgrep -af mav_bridge)')
        return 1

    params, mission, tel, msgs, dropped = gather(m, a.secs, a.verbose)

    r = Report()
    check_params(r, params)
    check_mission(r, mission)
    check_live(r, tel, msgs)
    if dropped:
        # 조용히 버리면 "왜 그 항목이 안 나왔지" 를 아무도 못 쫓는다.
        uniq = sorted(set(d.split(':')[0] for d in dropped))
        r.add('warn', '해석 못한 메시지', '%d건 (%s)' % (len(dropped), ', '.join(uniq)),
              dropped[0])

    meta = {'how': how, 'notes': notes if a.verbose else []}
    return render(r, meta, time.time() - t0, a.verbose)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n중단됨')
        sys.exit(130)
