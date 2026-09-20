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
import json
import math
import os
import subprocess
import sys
import time

# ── 이 기체의 기대값. 바꿀 때는 FC_CHANGELOG.md 근거를 같이 남겨라. ──────────
#
# (기대값, 판정등급, 왜)  — 등급: 'blk' 진행불가 / 'warn' 확인필요
EXPECT = {
    # 🟡 천이 — 수동만 열려 있다 (2026-09-17). SD 스위치(CH7)로 조종자가 건다.
    #    🔴 자동 천이를 막는 것은 이 값이 아니라 **미션 이착륙 22/21** 이다
    #       (84 는 스위치를 안 거친다 — 아래 미션 점검 참조).
    'RC_MAP_TRANS_SW': (7, 'warn', 'SD 스위치(CH7) 천이. 0 이면 수동 천이가 막힌 것이다'),
    'VT_ELEV_MC_LOCK': (1, 'blk', 'MC 구간에서 제어면이 안 잠기면 천이 자세가 섞인다'),
    # 🔴 영점이 미판정이라(정지 중 2.86 m/s) 문턱을 10 → 14 로 올려 뒀다.
    #    야외 무풍에서 영점을 재보면 10 으로 되돌린다 (FC_CHANGELOG 2026-09-17).
    'VT_ARSP_TRANS':   (14, 'warn', '영점 오차 흡수분. 실속 7 m/s 대비 여유 4.1 m/s'),

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
    'MAV_0_RATE':      (1400, 'warn', 'MAV_0_FORWARD=0 으로 "Sensor lost" 를 잡은 뒤 재배분 (9/9 14:20)'),
    'MAV_0_FORWARD':   (0, 'warn', '1 이면 USB 브리지 트래픽이 조종기 링크로 넘어가 센서가 죽는다 (9/9 13:10)'),
    'COM_RC_LOSS_T':   (1.0, 'warn', 'RC 상실 판정 1초 (config/SETTINGS.md)'),

    # 🔴 배터리 저전압 대응. 이 값들이 어긋나면 "알아서 돌아온다" 가 거짓이 된다.
    #    근거: config/SETTINGS.md 「전원」·docs/emergency/03-emergency.md
    'COM_LOW_BAT_ACT': (3, 'blk', '저전압 시 RTL 이어야 한다. 0 이면 경고만 하고 계속 난다'),
    'BAT_LOW_THR':     (0.15, 'warn', '잔량 15% 경고 (SETTINGS.md 전원)'),
    'BAT_CRIT_THR':    (0.07, 'warn', '잔량 7% 위험'),
    'BAT_EMERGEN_THR': (0.05, 'warn', '잔량 5% 비상 — 즉시 착륙'),
    'BAT1_CAPACITY':   (16000, 'warn', '16000 mAh. 틀리면 잔량 %가 통째로 어긋난다'),
    'BAT1_V_CHARGED':  (4.2, 'warn', '셀 만충 전압'),
    'BAT1_V_EMPTY':    (3.6, 'warn', '셀 공전압'),
    'CBRK_SUPPLY_CHK': (0, 'warn', '0 = 공급 검사 켜짐 (SETTINGS.md). 풀면 전원 이상을 못 잡는다'),

    # 착륙·arm. 지상 시험용으로 바꿔 둔 것이 남아 있기 쉬운 자리다.
    'COM_DISARM_LAND': (2.0, 'warn', '착륙 2초 뒤 자동 disarm (SETTINGS.md)'),
    'COM_ARM_MAG_ANG': (60, 'warn', '지자기 편차 허용각 60° (SETTINGS.md)'),
    'SENS_BOARD_ROT':  (0, 'blk', 'FC 장착 방향. 틀리면 자세가 통째로 뒤집힌다'),

    # 쿼드 기동 한계. 넘으면 이 기체가 실측으로 겪어 본 적 없는 영역이다.
    'MPC_XY_VEL_MAX':  (8.0, 'warn', '수평 최대 8 m/s'),
    'MPC_Z_VEL_MAX_UP': (3.0, 'warn', '상승 최대 3 m/s'),
    'MPC_TILTMAX_AIR': (45.0, 'warn', '최대 기울기 45°'),
}

# 🔴 값을 보여 주되 **판정하지 않는** 것. 리포에 근거가 없어서다.
#    근거 없이 등급을 매기면 "왜 NO-GO 인지" 를 아무도 못 쫓는다 —
#    임계값을 정하려면 FC_CHANGELOG.md 에 근거부터 남겨라 (CLAUDE.md).
CBRK_OPEN = {
    # PX4 의 "회로차단기" 는 매직 넘버를 넣으면 그 검사를 통째로 끈다.
    # 설명은 **그것이 꺼지면 무슨 일이 생기는지**를 적는다.
    'CBRK_FLIGHTTERM': (121212, '기체가 스스로 비행을 중단하는 최후 안전장치다. '
                                '꺼져 있으면 치명적 고장이 나도 스스로 멈추지 않는다.'),
    'CBRK_IO_SAFETY':  (22027, '기체의 안전 스위치를 건너뛴다. '
                               '스위치를 안 눌러도 모터가 돌 수 있다.'),
    'CBRK_USB_CHK':    (197848, 'USB 가 꽂힌 채로도 시동(arm)을 허용한다. '
                                '정비 중 모터가 도는 사고로 이어질 수 있다.'),
    'CBRK_AIRSPD_CHK': (162128, '대기속도계 이상 검사를 건너뛴다. '
                                '피토관이 막혀도 경고가 안 뜬다.'),
}

# 스위치는 "매핑되어 있기만" 하면 된다. 채널 번호는 조종기 구성에 따라 바뀐다.
MUST_BE_MAPPED = {
    'RC_MAP_KILL_SW': ('blk', 'KILL 스위치가 매핑돼 있어야 한다'),
}

# 값을 보여만 주고 판정하지 않는 것. 맥락이 있어야 읽히는 값들이다.
INFORM = {
    'SENS_DPRES_OFF':  '피토관 영점 — 현재 -3.0643, 미판정 (실내 조회로 판정 금지)',
    'COM_RC_IN_MODE':  '0=RC only, 1=MAVLink, 3=둘 다',
    'COM_ARM_WO_GPS':  '1 이어도 Position·Mission 은 자체 검사가 막는다',
    'MIS_TAKEOFF_ALT': '미션 이륙 고도',
    'NAV_FORCE_VT':    '기체가 이미 FW 일 때만 동작한다 — 84 를 막지 못한다',
    'COM_DISARM_PRFLT': '🟡 arm 후 이륙 안 하면 자동 disarm 까지의 초. '
                        'SETTINGS.md 가 지상테스트용 변경분으로 표시해 둔 값이다',
    'COM_PREARM_MODE': '🟡 동상 — SETTINGS.md 원복 확인 대상',
    'SDLOG_MODE':      '로깅 시점. 0=arm 부터 / -1=끔 / 1=부팅부터. '
                       '이 리포는 로그가 유일한 영구 기록이다',
    'SDLOG_PROFILE':   '로그에 담는 항목 묶음',
    'RTL_TYPE':        'RTL 경로 방식',
    'NAV_MC_ALT_RAD':  '고도 도달 판정 반경',
    'MC_AIRMODE':      '0 = 저스로틀에서 자세제어 약화 (쿼드 기본)',
    'EKF2_HGT_REF':    '고도 기준 센서. 0=기압 1=GPS 2=거리계',
    'FD_FAIL_P':       '자세 실패 감지 피치 한계(°)',
    'FD_FAIL_R':       '자세 실패 감지 롤 한계(°)',
    'MIS_DIST_1WP':    '첫 웨이포인트까지 허용 거리 — 넘으면 미션을 거부한다',
}

FLTMODE_PARAMS = ['COM_FLTMODE%d' % i for i in range(1, 7)]

# PX4 비행모드 번호 → 이름. 고정익 모드가 슬롯에 있으면 진입 경로가 열린 것이다.
# 🔴 정본은 이 기체 펌웨어의 빌드 산출물이다 —
#    PX4-Autopilot/build/px4_fmu-v6c_default/parameters.json (COM_FLTMODE1 values).
#    3 = Mission, 4 = Hold 를 뒤바꿔 적은 탓에 2026-09-06~09 사이 미션이 안 걸렸다.
FLTMODE = {
    -1: '없음', 0: 'Manual', 1: 'Altitude', 2: 'Position', 3: 'Mission',
    4: 'Hold', 5: 'Return', 6: 'Acro', 7: 'Offboard', 8: 'Stabilized',
    9: 'Position Slow', 10: 'Takeoff', 11: 'Land', 12: 'Follow Me',
    13: 'Precision Land', 16: 'Altitude Cruise',
}
MISSION_MODE = 3

# 미션 이착륙 명령. 🔴 84(VTOL_TAKEOFF)는 이름과 달리 "떠서 **고정익으로 전환**하라"다 —
# mission.cpp 가 상승 후 set_vtol_transition_item(FW) 를 부른다. 스위치를 거치지 않으므로
# RC_MAP_TRANS_SW=0 으로도 못 막는다. 쿼드 전용이면 22/21 이어야 한다 (9/5 16:45 규명).
CMD_NAME = {16: 'WAYPOINT', 20: 'RTL', 21: 'LAND', 22: 'TAKEOFF',
            84: 'VTOL_TAKEOFF', 85: 'VTOL_LAND', 189: 'DO_LAND_START'}
FW_MISSION_CMDS = {84: 'VTOL_TAKEOFF', 85: 'VTOL_LAND', 3000: 'DO_VTOL_TRANSITION'}

ALL_PARAMS = (list(EXPECT) + list(MUST_BE_MAPPED) + list(INFORM)
              + list(CBRK_OPEN) + FLTMODE_PARAMS)


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
        # 이 PC 에서 브리지가 돌 때 (자기 Tailscale 주소에 바인딩돼 있다).
        ts = tailscale_ip()
        if ts:
            tries.append(('udpout:%s:14550' % ts, '브리지 UDP 경유'))
        tries.append(('udpout:127.0.0.1:14550', '브리지 UDP (로컬)'))
        # 🔴 FC 가 **다른 PC** 에 꽂혀 있어도 점검할 수 있다. 브리지는 상행을
        #    Tailscale 로 흘리므로, 분석 PC(ku)에서 정비 PC(rim3)의 FC 를 그대로
        #    읽는다 — 실측 3.8초, 값이 직접 실행과 같았다. 기체 옆으로 갈 필요가 없다.
        for host, name in bridge_hosts():
            if ts and host == ts:
                continue
            tries.append(('udpout:%s:14550' % host, '%s 의 브리지 경유' % name))

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
        #    안 그러면 하행이 영영 안 온다 (실측: 가만히 기다리면 무응답).
        #
        # 후보당 예산을 짧게 준다. 살아 있는 경로는 첫 왕복(<1초)에 답하므로,
        # 오래 기다려서 얻는 것은 죽은 경로에서 버리는 시간뿐이다 — 후보를
        # 넷 훑던 초기 판이 15.5초였고 대부분이 그 낭비였다.
        t0 = time.time()
        hb = None
        budget = 4.0 if conn.startswith('/dev/') else 1.8
        while time.time() - t0 < budget:
            try:
                m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            except Exception:
                pass
            hb = m.wait_heartbeat(timeout=0.45)
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


# 브리지가 돌 만한 PC. Tailscale 이름으로 찾는다 — IP 를 박으면 주소가 바뀔 때
# 조용히 안 붙는다 (gcs/ACCESS.md 가 이름을 쓰라고 하는 것과 같은 이유).
# raspb1 은 2026-09-10 사망, rim 은 수동 갱신 전용(브리지 안 돌림) — 둘 다 뺐다.
BRIDGE_HOSTS = ('rim3', 'ku-dgs1')


def bridge_hosts():
    """Tailscale 에서 온라인인 후보를 (ip, 이름) 으로 준다."""
    try:
        out = subprocess.run(['tailscale', 'status'], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:
        return []
    found, seen = [], set()
    for line in out.splitlines():
        f = line.split()
        if len(f) < 2:
            continue
        ip, name = f[0], f[1]
        short = name.split('.')[0]
        if 'offline' in line:
            continue
        for want in BRIDGE_HOSTS:
            if short == want or short.startswith(want):
                if ip not in seen:
                    seen.add(ip)
                    found.append((ip, short))
    # BRIDGE_HOSTS 의 순서를 우선순위로 쓴다
    return sorted(found, key=lambda x: next(
        (i for i, w in enumerate(BRIDGE_HOSTS) if x[1].startswith(w)), 99))


def tailscale_ip():
    try:
        out = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True,
                             text=True, timeout=4).stdout.strip().split()
        return out[0] if out else None
    except Exception:
        return None


# ── 수집 ────────────────────────────────────────────────────────────────────
def gather(m, secs, verbose, on_progress=None):
    """파라미터·미션·텔레메트리를 **한 소켓에서 동시에** 걷는다.

    파라미터 응답을 기다리는 시간이 어차피 필요하므로, 그 동안 들어오는
    텔레메트리를 같이 주워 담는다. 따로 하면 시간이 두 배가 된다.

    `on_progress(progress, params, mission, tel, msgs)` 을 주면 걷는 **중간에**
    묶음별 진행률을 흘린다. 🔴 묶음이 끝나는 순서는 정해져 있지 않다 —
    자기 데이터가 먼저 온 것이 먼저 끝난다. 화면도 그 순서로 채워진다."""
    from pymavlink import mavutil

    tgt, tcomp = m.target_system, m.target_component
    params, tel, msgs, dropped = {}, {}, [], []
    mission = {'count': None, 'items': {}, 'requested': set()}

    for n in ALL_PARAMS:
        m.mav.param_request_read_send(tgt, tcomp, n.encode('ascii'), -1)
    m.mav.mission_request_list_send(tgt, tcomp, 0)

    t0 = time.time()
    t_end = t0 + secs
    last_retry = time.time()
    last_emit = 0.0

    def emit(force=False):
        """진행률을 흘린다. 값이 그대로면 보내지 않는다 — 같은 화면을
        다시 그리게 하는 것은 대역만 쓴다."""
        nonlocal last_emit
        if on_progress is None:
            return
        now = time.time()
        if not force and now - last_emit < 0.15:
            return
        last_emit = now
        prog = {}
        for g in GROUP_NEEDS:
            v = group_progress(g, params, mission, tel, now - t0, secs)
            if v is not None:
                prog[g] = v
        on_progress(prog, params, mission, tel, msgs)

    emit(force=True)
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

        emit()

        done = (len(params) == len(ALL_PARAMS)
                and mission['count'] is not None
                and len(mission['items']) == mission['count']
                and {'fix', 'volt', 'roll'} <= set(tel))
        if done and time.time() > t_end - (secs - 3.0):
            break

    emit(force=True)
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

    elif t == 'HIGHRES_IMU':
        # 원시 IMU. 가속도 크기와 자기장 세기를 여기서만 볼 수 있다 —
        # SYS_STATUS 의 건강 비트는 "살아 있다" 만 말하고 값이 맞는지는 모른다.
        import math
        tel['acc'] = (msg.xacc, msg.yacc, msg.zacc)
        tel['acc_mag'] = math.sqrt(msg.xacc ** 2 + msg.yacc ** 2 + msg.zacc ** 2)
        tel['gyro'] = (msg.xgyro, msg.ygyro, msg.zgyro)
        tel['gyro_mag'] = math.sqrt(msg.xgyro ** 2 + msg.ygyro ** 2 + msg.zgyro ** 2)
        tel['mag'] = (msg.xmag, msg.ymag, msg.zmag)
        tel['mag_mag'] = math.sqrt(msg.xmag ** 2 + msg.ymag ** 2 + msg.zmag ** 2)
        tel['imu_temp'] = msg.temperature
        tel['imu_press'] = msg.abs_pressure
        tel['imu_diff_press'] = msg.diff_pressure

    elif t == 'SCALED_PRESSURE':
        # 🔴 HIGHRES_IMU 와 **다른 기압계**다. 둘을 맞대 보면 한쪽이 틀어진 것을
        #    잡는다 — 건강 비트는 둘 다 "정상" 이라고 답한다.
        tel['baro_press'] = msg.press_abs
        tel['baro_temp'] = msg.temperature / 100.0

    elif t == 'ALTITUDE':
        tel['alt_amsl'] = msg.altitude_amsl
        tel['alt_local'] = msg.altitude_local
        tel['alt_terrain'] = msg.altitude_terrain

    elif t == 'SERVO_OUTPUT_RAW':
        # 모터 출력. arm 전에는 전부 idle 이어야 한다.
        tel['servo'] = [getattr(msg, 'servo%d_raw' % i) for i in range(1, 9)]

    elif t == 'SYSTEM_TIME':
        # FC 시계. 로그 시각이 여기서 나온다 — 어긋나면 로그를 맞춰 볼 수 없다.
        tel['fc_unix'] = msg.time_unix_usec / 1e6 if msg.time_unix_usec else None
        tel['fc_boot_s'] = msg.time_boot_ms / 1000.0

    elif t == 'MISSION_CURRENT':
        tel['mission_seq'] = msg.seq
        tel['mission_state'] = getattr(msg, 'mission_state', None)

    elif t == 'LOCAL_POSITION_NED':
        import math
        tel['vel_ned'] = math.sqrt(msg.vx ** 2 + msg.vy ** 2 + msg.vz ** 2)



# ── 판정 ────────────────────────────────────────────────────────────────────
class Report:
    """판정을 모은다. 등급은 셋뿐이다 — 막을 것, 볼 것, 괜찮은 것.

    `seq` 는 항목이 **불린 순서**다. 터미널은 등급으로 묶어 찍지만 웹 화면은
    절차 순서(1. GPS … 2. 기압계 …)로 줄세워야 해서, 순서를 여기서 같이 들고
    간다 — 화면 쪽에서 되짚으면 두 벌이 따로 늙는다.
    """

    def __init__(self):
        self.blk, self.warn, self.ok, self.info = [], [], [], []
        self.rows = []          # 부른 순서대로 (group, level, name, detail, why)
        self.group = '기타'     # check_* 가 절마다 바꿔 준다

    def add(self, level, name, detail, why='', group=None):
        {'blk': self.blk, 'warn': self.warn, 'ok': self.ok, 'info': self.info}[level] \
            .append((name, detail, why))
        self.rows.append((group or self.group, level, name, detail, why))

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

    # 파라미터마다 어느 묶음인지. EXPECT 순서를 화면이 그대로 쓰므로, 여기서
    # 이름을 붙여 두면 절차 목록이 저절로 절 단위로 줄선다.
    G = {
        'RC_MAP_TRANS_SW': '쿼드 전용 잠금', 'VT_ELEV_MC_LOCK': '쿼드 전용 잠금',
        'VT_ARSP_TRANS': '쿼드 전용 잠금',
        'NAV_RCL_ACT': 'failsafe', 'NAV_DLL_ACT': 'failsafe',
        'RTL_RETURN_ALT': 'failsafe', 'RTL_DESCEND_ALT': 'failsafe',
        'RC_MAP_KILL_SW': 'failsafe',
        'GF_ACTION': '지오펜스', 'GF_MAX_HOR_DIST': '지오펜스',
        'GF_MAX_VER_DIST': '지오펜스',
        'NAV_ACC_RAD': '항법·미션', 'MIS_TAKEOFF_ALT': '항법·미션',
        'NAV_FORCE_VT': '항법·미션',
        'BAT1_N_CELLS': '전원', 'MPC_THR_HOVER': '전원',
        'MAV_0_RATE': '링크', 'MAV_0_FORWARD': '링크',
        'COM_RC_IN_MODE': '링크', 'COM_ARM_WO_GPS': '항법·미션',
        'SENS_DPRES_OFF': '센서', 'SENS_BOARD_ROT': '센서',
        'COM_LOW_BAT_ACT': '전원', 'BAT_LOW_THR': '전원', 'BAT_CRIT_THR': '전원',
        'BAT_EMERGEN_THR': '전원', 'BAT1_CAPACITY': '전원',
        'BAT1_V_CHARGED': '전원', 'BAT1_V_EMPTY': '전원', 'CBRK_SUPPLY_CHK': '전원',
        'COM_RC_LOSS_T': 'failsafe', 'COM_DISARM_LAND': 'ARM 조건',
        'COM_ARM_MAG_ANG': 'ARM 조건', 'COM_DISARM_PRFLT': 'ARM 조건',
        'COM_PREARM_MODE': 'ARM 조건',
        'MPC_XY_VEL_MAX': '기동 한계', 'MPC_Z_VEL_MAX_UP': '기동 한계',
        'MPC_TILTMAX_AIR': '기동 한계', 'MC_AIRMODE': '기동 한계',
        'FD_FAIL_P': '기동 한계', 'FD_FAIL_R': '기동 한계',
        'SDLOG_MODE': '기록', 'SDLOG_PROFILE': '기록',
        'RTL_TYPE': 'failsafe', 'NAV_MC_ALT_RAD': '항법·미션',
        'MIS_DIST_1WP': '항법·미션', 'EKF2_HGT_REF': 'GPS·추정',
    }

    # 기대값 대조
    for name, (want, level, why) in EXPECT.items():
        r.group = G.get(name, '파라미터')
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
        r.group = G.get(name, '파라미터')
        if name not in p:
            r.add('warn', name, '읽지 못했다', why)
        elif int(p[name]) == 0:
            r.add(level, name, '미매핑 (0)', why)
        else:
            r.add('ok', name, 'CH%d' % int(p[name]))

    # 🔴 비행모드 6슬롯에 고정익 모드가 있으면 스위치 하나로 천이한다.
    r.group = '쿼드 전용 잠금'
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
        # 🔴 Mission 이 어느 슬롯에도 없으면 조종기로 미션을 걸 방법이 없다.
        #    2026-09-06 에 COM_FLTMODE1 이 4(Hold)로 바뀌어 9/9 까지 이 상태였다.
        elif not any(int(p[n]) == MISSION_MODE for n in FLTMODE_PARAMS if n in p):
            r.add('warn', '비행모드 슬롯', ' '.join(slots),
                  'Mission(3) 이 6슬롯 어디에도 없다 — 조종기로 미션 진입 불가')
        else:
            r.add('ok', '비행모드 슬롯', ' '.join(slots))

    # 🔴 회로차단기 — 열려 있으면 그 검사가 **통째로 꺼진 것**이다.
    #    리포에 왜 열었는지가 없으므로 등급을 매기지 않고 사실만 낸다.
    #    (임계값을 정하려면 FC_CHANGELOG.md 에 근거부터 남겨라 — CLAUDE.md)
    r.group = '회로차단기'
    for name, (magic, what) in CBRK_OPEN.items():
        if name not in p:
            continue
        if int(p[name]) == magic:
            r.add('warn', name, '꺼짐',
                  '%s 이 기체에서 왜 껐는지가 기록에 없다 — 일부러 껐다면 '
                  'FC_CHANGELOG.md 에 이유를 적어 두어라. 그래야 다음 사람이 '
                  '이 줄을 보고 놀라지 않는다' % what)
        else:
            r.add('ok', name, '켜짐', what)

    for name, note in INFORM.items():
        r.group = G.get(name, '파라미터')
        if name in p:
            r.add('info', name, fmtv(p[name]), note)

    r.group = '파라미터'
    if missing:
        r.add('warn', '파라미터 수신', '%d개 못 받음' % len(missing),
              '설정값 일부를 못 읽었다 — 그만큼은 판정하지 못했다는 뜻이다. '
              '링크가 느릴 때 생긴다. 못 받은 것: '
              + ', '.join(missing[:8]) + ('…' if len(missing) > 8 else ''))


def fmtv(v):
    if isinstance(v, float):
        return ('%.4f' % v).rstrip('0').rstrip('.')
    return str(v)


def check_mission(r, mission):
    r.group = '미션'
    n = mission['count']
    if n is None:
        r.add('warn', '미션', '못 받았다',
              '기체에 들어 있는 미션을 못 읽었다. 미션이 있는지 없는지를 모르는 상태다')
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
            r.add('warn', '미션 고도', '%.0f~%.0f m' % (lo, hi),
                  '이 기체가 실제로 올라가 본 최고 고도는 19.9m 다. '
                  '그보다 높은 미션은 겪어 보지 않은 영역이다')
        else:
            r.add('ok', '미션 고도', '%.0f~%.0f m' % (lo, hi))


# 🔴 이 기체의 출력 배치. 정본은 config/SETTINGS.md 「PWM_MAIN_FUNC」 표이고
#    2026-09-11 에 로그(`actuator_outputs`)로 재검증됐다. 번호는 MAVLink
#    기준(1부터)이라 로그의 output[2,3,5,6] 이 여기서 servo3/4/6/7 이다.
#    ⚠️ 다른 기체에 그대로 쓰면 안 된다 — 배치가 기체마다 다르다.
SERVO_ROLE = {
    1: '좌 에일러론', 2: '우 에일러론',
    3: 'VTOL 우후 모터', 4: 'VTOL 우전 모터',
    5: '미사용 (UBEC 급전)',
    6: 'VTOL 좌후 모터', 7: 'VTOL 좌전 모터',
    8: '크루즈 모터',
}
# disarm 중 기대값. 서보는 중립 1500, 모터는 정지 1000, 미사용은 0.
SERVO_DISARM = {1: 1500, 2: 1500, 3: 1000, 4: 1000, 5: None, 6: 1000, 7: 1000, 8: 1000}

# SYS_STATUS 센서 비트. PX4 가 실제로 채우는 것만 본다.
SENSOR_BITS = [
    (1 << 0, '자이로'), (1 << 1, '가속도계'), (1 << 2, '지자기'),
    (1 << 3, '기압계'), (1 << 5, 'GPS'), (1 << 12, 'RC 수신'),
    (1 << 24, '배터리'),
]


def check_live(r, tel, msgs):
    r.group = '기체 상태'
    # ARM 상태 — 점검은 DISARM 에서 해야 안전하다.
    # 🔴 `armed` 가 아예 없으면 "DISARMED" 라고 답하면 안 된다. 하트비트를 못 읽은
    #    것과 무장이 안 된 것은 전혀 다르고, 전자를 후자로 답하면 도구가
    #    모르는 것을 안전하다고 말하는 셈이다 (실측으로 잡은 버그).
    if 'armed' not in tel:
        r.add('blk', 'ARM 상태', '확인 불가',
              '기체가 응답을 안 해 시동이 걸렸는지 아닌지를 모른다. '
              '모르는 채로 만지지 마라 — 연결부터 다시 확인하라')
    elif tel['armed']:
        r.add('blk', 'ARM 상태', '🔴 시동 걸림',
              '지금 모터에 전원이 들어가 있다. 점검 중 프로펠러가 돌 수 있다. '
              '조종기로 시동을 끄고(disarm) 다시 점검하라')
    else:
        r.add('ok', 'ARM 상태', 'DISARMED')

    # GPS
    r.group = 'GPS·추정'
    fix, sats, eph = tel.get('fix'), tel.get('sats'), tel.get('eph')
    if fix is None:
        r.add('warn', 'GPS', '데이터 없음', 'GPS_RAW_INT 가 안 온다')
    else:
        FIXN = {0: '없음', 1: '신호만', 2: '2D', 3: '3D', 4: 'DGPS', 5: 'RTK(부동)', 6: 'RTK(고정)'}
        d = '%s · 위성 %s기%s' % (FIXN.get(fix, fix), sats if sats is not None else '?',
                                 ' · 오차 %.2fm' % eph if eph else '')
        if fix < 3:
            r.add('blk', 'GPS', d,
                  '위치를 못 잡았다. 실내라면 정상이다 — 야외로 나가면 잡힌다. '
                  '이 상태로는 Position·Mission·RTL(자동 복귀)이 전부 안 된다')
        elif sats is not None and sats < 10:
            r.add('warn', 'GPS', d,
                  '잡힌 위성이 적다. 야외에서는 보통 21~32기가 잡힌다. '
                  '건물이나 나무에 가려 있으면 위치가 흔들린다')
        elif eph and eph > 1.0:
            r.add('warn', 'GPS', d,
                  '위치 오차가 크다. 이 기체의 야외 실측은 0.15~0.23m 다. '
                  '하늘이 트인 곳으로 옮겨 다시 보라')
        else:
            r.add('ok', 'GPS', d)

    # 배터리 — 6S 기준
    r.group = '전원'
    v = tel.get('volt')
    if v is None:
        r.add('warn', '배터리', '전압 없음',
              '배터리가 안 꽂혀 있거나 전원 모듈이 값을 못 읽는다. '
              '실내 점검 중이면 정상이다')
    else:
        cell = v / 6.0
        d = '%.2f V · %.2f V/셀' % (v, cell)
        if v < 21.0:
            r.add('blk', '배터리', d,
                  '전압이 너무 낮다 (6S 기준 21.0V 미만). 이대로 띄우면 비행 중 '
                  '전압이 무너져 추락한다. 충전된 배터리로 바꿔라')
        elif v < 22.2:
            r.add('warn', '배터리', d, '만충은 25.2V 다. 짧은 비행만 가능하다')
        else:
            r.add('ok', '배터리', d)

    # 자세 — 지상에서 기울어 있으면 수평 아닌 곳이거나 IMU 가 틀어진 것
    r.group = '기체 상태'
    roll, pitch = tel.get('roll'), tel.get('pitch')
    if roll is not None:
        d = 'roll %+.1f° pitch %+.1f°' % (roll, pitch)
        if abs(roll) > 10 or abs(pitch) > 10:
            r.add('warn', '지상 자세', d,
                  '기체가 10° 넘게 기울어 있다. 바닥이 기울었거나, 평평한데도 '
                  '이렇게 나오면 자세 센서 보정이 틀어진 것이다')
        else:
            r.add('ok', '지상 자세', d)

    # 진동
    r.group = '기체 상태'
    vibe = tel.get('vibe')
    if vibe:
        mx = max(vibe)
        d = 'x %.1f y %.1f z %.1f' % vibe
        if mx == 0.0:
            # 지상 정지에서도 완전한 0 은 잘 안 나온다. 값이 아니라 아직
            # 안 채워진 것으로 보는 편이 안전하다.
            r.add('warn', '진동', d,
                  '값이 전부 0 이다. 측정이 아직 안 된 것일 수 있다 — '
                  '모터를 한 번 돌린 뒤 다시 점검하라')
        elif mx > 30:
            r.add('blk', '진동', d,
                  '진동이 위험 수준이다. 프로펠러 균열·모터 베어링·헐거운 나사를 '
                  '확인하라. 이 상태로는 센서가 자세를 잘못 읽는다')
        elif mx > 10:
            r.add('warn', '진동', d,
                  '진동이 경고선(10)을 넘었다. 프로펠러와 모터 마운트를 살펴보라')
        else:
            r.add('ok', '진동', d)

    # EKF 혁신비 — 1.0 을 넘으면 센서끼리 안 맞는다
    r.group = 'GPS·추정'
    # 🔴 NaN 을 그냥 지나치면 안 된다. `NaN > 1.0` 은 False 라 비교만으로는
    #    조용히 '정상' 이 된다 — 모르는 것을 안전하다고 답하는 그 부류다.
    #    실기에서 EKF 가 아직 안 선 동안 vel·pos 가 NaN 으로 나온다.
    ratios = {k[4:]: tel[k] for k in ('ekf_vel', 'ekf_pos', 'ekf_vrt', 'ekf_mag')
              if tel.get(k) is not None}
    if ratios:
        KO = {'vel': '속도', 'pos': '수평위치', 'vrt': '수직위치', 'mag': '방위'}
        d = ' · '.join('%s %s' % (KO.get(k, k), '미정' if isnan(v) else '%.2f' % v)
                       for k, v in ratios.items())
        nans = [KO.get(k, k) for k, v in ratios.items() if isnan(v)]
        good = [v for v in ratios.values() if not isnan(v)]
        worst = max(good) if good else None
        # 🔴 설명은 **다음에 무엇을 하면 되는지**를 말한다. 용어(혁신비·NaN)만
        #    적어 두면 읽는 사람이 그것을 먼저 찾아봐야 한다.
        if nans:
            r.add('warn', '위치 추정', d,
                  '기체가 아직 자기 위치를 확정하지 못했다. 실내이거나 GPS 를 '
                  '막 켠 직후에 정상으로 나오는 상태다. 야외에서 위성이 잡히면 '
                  '저절로 풀린다. 지금은 Position·Mission 모드로 못 넘어간다')
        elif worst > 1.0:
            r.add('blk', '위치 추정', d,
                  '센서들이 서로 다른 위치를 가리킨다. 이대로 띄우면 기체가 '
                  '엉뚱한 곳으로 튄다. 나침반 보정을 다시 하고 GPS 가 잡힐 때까지 기다려라')
        elif worst > 0.5:
            r.add('warn', '위치 추정', d,
                  '센서끼리 조금 어긋나 있다. 날 수는 있으나 위치가 흔들릴 수 있다')
        else:
            r.add('ok', '위치 추정', d)

    # 센서 건강 비트
    r.group = '센서'
    pres, health = tel.get('sensors_present'), tel.get('sensors_health')
    if pres is not None and health is not None:
        bad = [nm for bit, nm in SENSOR_BITS if (pres & bit) and not (health & bit)]
        if bad:
            r.add('blk', '센서 상태', '이상: ' + ', '.join(bad),
                  'FC 가 이 센서들을 고장으로 보고했다. 배선과 커넥터를 확인하라')
        else:
            r.add('ok', '센서 상태', '보고된 센서 전부 정상')

    # VTOL 상태 — 쿼드 전용
    r.group = '쿼드 전용 잠금'
    vs = tel.get('vtol_state')
    if vs is not None:
        name = {0: '미정', 1: '천이 중(FW로)', 2: '천이 중(MC로)', 3: 'MC', 4: 'FW'}.get(vs, vs)
        if vs == 4:
            r.add('blk', 'VTOL 상태', name,
                  '기체가 고정익 모드로 서 있다. 지금 이 기체는 쿼드(멀티콥터) 전용이라 '
                  '이 상태로 띄우면 안 된다')
        elif vs in (1, 2):
            r.add('warn', 'VTOL 상태', name,
                  '쿼드와 고정익 사이를 넘어가는 중이다. 멈출 때까지 기다려라')
        else:
            r.add('ok', 'VTOL 상태', name)

    # RC
    r.group = '링크'
    rc = tel.get('rc')
    if rc:
        r.add('ok', 'RC 입력', 'CH1~8 %s' % ' '.join(str(x) for x in rc[:8]))
    else:
        r.add('warn', 'RC 입력', '없다',
              '조종기 신호가 안 들어온다. 조종기가 꺼져 있거나, 수신기가 기체에 '
              '안 붙었거나, 바인딩이 풀린 것이다. 조종기를 켜고 다시 점검하라')

    # 에어스피드 — 정지 상태에서 ±2 m/s 안이어야 한다 (2026-09-11 기준 갱신).
    #
    # 🔴 **양수 편향이 음수보다 위험하다.** PX4 는 음수를 보수적으로 다루지만, 양수는
    #    실제보다 빠르다고 착각하게 만들어 실속 판단을 늦춘다 (FW_AIRSPD_STALL=7,
    #    FW_AIRSPD_MIN=10). 그래서 같은 크기라도 양수 쪽을 더 세게 잡는다.
    #
    # 이력: -4.52(고장, -5.0 m/s) → 9/11 낮 -1.8096(-1.3 m/s, 기준 충족)
    #       → 9/11 저녁 -3.0643(+2.21 m/s, 과보정). 되돌릴 값은 -1.8096 이다.
    # ⚠️ 실내에서는 **에어컨 바람**이 그대로 읽힌다 (2026-09-13 실측 +2.2 m/s).
    #    그 값으로 영점을 판정하지 마라 — 한 번 「과보정」이라 오판하고 철회했다.
    #    판정은 야외 무풍 또는 실비행 로그로 한다 (CLAUDE.md 「값을 뽑을 때」).
    r.group = '센서'
    a = tel.get('airspeed')
    if a is not None:
        if a > 1.5:
            r.add('info', '대기속도', '%.1f m/s' % a,
                  '정지 중인데 양수 — 실내면 **바람일 수 있다**(에어컨). '
                  '영점 판정은 야외 무풍이나 실비행 로그로 하라')
        elif a < -2:
            r.add('warn', '대기속도', '%.1f m/s' % a,
                  '음수로 크다 — 영점이 덜 빠졌다 (고장 시절 -5.0). '
                  'SENS_DPRES_OFF 확인')
        else:
            r.add('info', '대기속도', '%.1f m/s' % a,
                  '정지 ±2 m/s 안 — 영점은 정상. 남은 것은 ASPD_SCALE_1 (고정익 비행으로만 학습)')

    # ── 원시 IMU — 건강 비트가 못 보는 것 ─────────────────────────────
    # 🔴 SYS_STATUS 의 건강 비트는 "센서가 응답한다" 만 말한다. 값이 맞는지는
    #    모른다. 정지한 기체에서 가속도 크기는 1G 여야 하고 자이로는 0 이어야
    #    한다 — 아니면 IMU 가 틀어졌거나 기체가 흔들리고 있는 것이다.
    r.group = '센서'
    am = tel.get('acc_mag')
    if am is not None:
        d = '%.2f m/s² (%.3f G)' % (am, am / 9.80665)
        if abs(am - 9.80665) > 0.5:
            r.add('warn', '가속도 크기', d,
                  '정지 중이면 1G(9.81)여야 한다. 벗어나면 IMU 보정이 틀어졌거나 '
                  '기체가 움직이고 있다')
        else:
            r.add('ok', '가속도 크기', d)

    gm = tel.get('gyro_mag')
    if gm is not None:
        d = '%.4f rad/s' % gm
        if gm > 0.05:
            r.add('warn', '자이로 정지값', d, '정지 중인데 각속도가 있다 — 흔들리거나 드리프트다')
        else:
            r.add('ok', '자이로 정지값', d)

    # 지자기 세기. 한국 지자기는 약 0.50 Gauss 다. 크게 벗어나면 근처 금속·전류.
    # 🔴 이 기체는 전류-자기장 상관 −0.91 이 실측돼 있다
    #    (flights/2026-09-05-hover-compass-interference.md).
    mm = tel.get('mag_mag')
    if mm is not None:
        d = '%.3f Gauss' % mm
        if mm < 0.25 or mm > 0.75:
            r.add('warn', '지자기 세기', d,
                  '한국 지자기는 약 0.50 G 다. 벗어나면 근처 금속이나 전류 간섭이다')
        else:
            r.add('ok', '지자기 세기', d)

    tc = tel.get('imu_temp')
    if tc is not None:
        d = '%.1f °C' % tc
        if tc < -10 or tc > 60:
            r.add('warn', 'IMU 온도', d, '보정 범위를 벗어났다 — 자이로 바이어스가 흐른다')
        else:
            r.add('ok', 'IMU 온도', d)

    # 기압계 둘. HIGHRES_IMU 와 SCALED_PRESSURE 는 **다른 센서**이고, 이 기체는
    # 둘이 10.7 hPa 어긋나 있다 (2026-09-20 실측, 실내).
    #
    # 🔴 **판정하지 않는다.** 정상 편차가 얼마인지가 리포에 없다. 둘 중 무엇이
    #    고도의 기준인지는 확인했다 — `HIGHRES_IMU.pressure_alt` 가
    #    `ALTITUDE.altitude_amsl` 와 같은 값을 낸다. 판정을 붙이려면
    #    야외 실비행 로그로 정상 편차부터 재고 FC_CHANGELOG.md 에 남겨라
    #    (CLAUDE.md 「값을 뽑을 때」 — 실내 조회값으로 판정 금지).
    p1, p2 = tel.get('imu_press'), tel.get('baro_press')
    if p1 is not None and p2 is not None:
        gap = abs(p1 - p2)
        r.add('info', '기압계 2중', '%.2f / %.2f hPa (차 %.2f)' % (p1, p2, gap),
              'HIGHRES_IMU 와 SCALED_PRESSURE 는 다른 센서다. 정상 편차가 '
              '얼마인지는 아직 실측이 없다 — 실내 조회값으로 판정하지 마라')

    # ── 액추에이터 출력 ───────────────────────────────────────────────
    # 🔴 **번호마다 기대값이 다르다.** 이 기체는 VTOL(4+1)이라 servo1·2 는
    #    에일러론이고 disarm 중립이 1500 이다 — 모터로 착각하면 정상 기체를
    #    NO-GO 로 만든다 (실제로 한 번 그랬다).
    #
    #    정본은 config/SETTINGS.md 의 출력 배치표다. 2026-09-11 에 로그
    #    (`actuator_outputs`)로 재검증된 표이고, MAVLink 쪽은 번호가 1부터라
    #    로그의 output[2,3,5,6] 이 여기서는 servo3/4/6/7 이 된다.
    r.group = '기체 상태'
    sv = tel.get('servo')
    if sv:
        d = ' '.join(str(v) for v in sv[:8])
        bad = []
        for i, v in enumerate(sv[:8], 1):
            want = SERVO_DISARM.get(i)
            if want is None or v == 0:        # 미사용 핀은 0 으로 온다
                continue
            if abs(v - want) > 60:
                bad.append('%d번 %d (기대 %d, %s)' % (i, v, want, SERVO_ROLE[i]))
        if tel.get('armed') is False and bad:
            # 모터가 도는 것과 서보가 어긋난 것은 다르다 — 모터만 진행 불가다.
            motors = [b for b in bad if '모터' in b]
            r.add('blk' if motors else 'warn', '액추에이터 출력', d,
                  '시동이 꺼져 있는데 출력이 정지값이 아니다: ' + ' · '.join(bad))
        else:
            r.add('ok', '액추에이터 출력', d)

    # 속도 — 지상에 놓인 기체는 0 이어야 한다. EKF 가 흐르면 여기서 보인다.
    v = tel.get('vel_ned')
    if v is not None:
        d = '%.2f m/s' % v
        if v > 0.5:
            r.add('warn', '추정 속도', d,
                  '기체는 가만히 있는데 스스로 움직이고 있다고 판단한다. '
                  '위치 추정이 흐르는 중이다 — GPS 가 잡히면 대개 가라앉는다')
        else:
            r.add('ok', '추정 속도', d)

    # ── FC 시계 — 로그 시각이 여기서 나온다 ──────────────────────────
    r.group = '기록'
    fu = tel.get('fc_unix')
    if fu:
        skew = abs(time.time() - fu)
        d = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(fu))
        if skew > 60:
            r.add('warn', 'FC 시계', '%s (%.0f초 차)' % (d, skew),
                  '기체 시계가 이 PC 와 어긋나 있다. 비행 로그에 찍히는 시각이 '
                  '맞지 않아 나중에 다른 기록과 맞춰 보기 어려워진다')
        else:
            r.add('ok', 'FC 시계', d)
    elif tel.get('fc_boot_s') is not None:
        r.add('warn', 'FC 시계', '시각 없음 (부팅 후 %.0f초)' % tel['fc_boot_s'],
              '기체가 아직 실제 날짜·시각을 모른다. GPS 로 시각을 받아오기 때문에 '
              '실내에서는 정상이다. 로그에는 부팅 후 경과시간만 남는다')

    # 홈 위치
    r.group = 'GPS·추정'
    if tel.get('home') and tel.get('lat'):
        import math
        hlat, hlon = tel['home']
        dlat = (tel['lat'] - hlat) * 111320
        dlon = (tel['lon'] - hlon) * 111320 * math.cos(math.radians(hlat))
        d = math.hypot(dlat, dlon)
        if d > 20:
            r.add('warn', '홈 위치', '기체에서 %.0f m' % d,
                  '복귀 지점이 기체와 멀리 떨어져 있다. 자동 복귀(RTL)를 걸면 '
                  '여기로 날아간다. 지도에서 H 표시가 기체 위에 있는지 확인하라')
        else:
            r.add('ok', '홈 위치', '기체에서 %.0f m' % d)
    else:
        r.add('info', '홈 위치', '아직 없다', '시동을 걸면 그 자리가 복귀 지점이 된다')

    # FC 가 스스로 뱉은 경고 — 임계값 판정보다 맥락이 짙다
    r.group = 'FC 자신의 말'
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
    ('고정익', '금지. 에어스피드 영점(SENS_DPRES_OFF=-3.0643) 미판정 — 실내 조회는 에어컨 바람을 읽는다. '
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


# ── 묶음별로 무엇이 와야 판정이 서는가 ─────────────────────────────────────
#
# 🔴 점검은 **병렬이다.** 파라미터 40개 요청과 미션 요청을 한 번에 던지고,
#    그 응답을 기다리는 동안 같은 소켓에서 텔레메트리를 줍는다. 그래서 묶음이
#    끝나는 순서는 정해져 있지 않다 — 자기 데이터가 먼저 도착한 묶음이 먼저
#    끝난다. 화면도 그 순서대로 채워진다.
#
# 진행률은 여기 적힌 것 중 **몇 개가 도착했나**다. 남은 시간이나 회전 수 같은
# 것을 세지 않는다 — 그건 실제 진행이 아니라 시계를 보여 주는 것이다.
#
# `params` 는 파라미터 이름, `tel` 은 텔레메트리 키, `mission` 은 미션이 다
# 받아졌는지. 없는 값이 하나라도 남아 있으면 그 묶음은 아직 안 끝난 것이다.
GROUP_NEEDS = {
    '쿼드 전용 잠금': {
        'params': ['RC_MAP_TRANS_SW', 'VT_ELEV_MC_LOCK', 'VT_ARSP_TRANS'] + FLTMODE_PARAMS,
        'tel': ['vtol_state'],
    },
    'failsafe': {
        'params': ['NAV_RCL_ACT', 'NAV_DLL_ACT', 'RTL_RETURN_ALT', 'RTL_DESCEND_ALT',
                   'RC_MAP_KILL_SW', 'COM_RC_LOSS_T', 'RTL_TYPE'],
    },
    '지오펜스': {
        'params': ['GF_ACTION', 'GF_MAX_HOR_DIST', 'GF_MAX_VER_DIST'],
    },
    '미션': {'mission': True},
    '항법·미션': {
        'params': ['NAV_ACC_RAD', 'MIS_TAKEOFF_ALT', 'NAV_FORCE_VT', 'COM_ARM_WO_GPS',
                   'NAV_MC_ALT_RAD', 'MIS_DIST_1WP'],
    },
    'GPS·추정': {
        # 홈은 arm 전에는 안 온다 — 기다리면 영영 안 끝난다. 여기 넣지 않는다.
        'params': ['EKF2_HGT_REF'],
        'tel': ['fix', 'sats', 'ekf_vel', 'ekf_pos'],
    },
    '전원': {
        'params': ['BAT1_N_CELLS', 'MPC_THR_HOVER', 'COM_LOW_BAT_ACT',
                   'BAT_LOW_THR', 'BAT_CRIT_THR', 'BAT_EMERGEN_THR',
                   'BAT1_CAPACITY', 'BAT1_V_CHARGED', 'BAT1_V_EMPTY',
                   'CBRK_SUPPLY_CHK'],
        # 배터리를 빼 놓으면 volt 가 None 이다. 키가 **있기만** 하면 된다 —
        # 값이 None 인 것도 판정거리다 ("전압 없음").
        'tel': ['sensors_present'],
    },
    '센서': {
        'params': ['SENS_DPRES_OFF', 'SENS_BOARD_ROT'],
        'tel': ['sensors_health', 'airspeed', 'acc_mag', 'gyro_mag', 'mag_mag',
                'imu_temp', 'baro_press'],
    },
    '기체 상태': {
        'tel': ['armed', 'roll', 'vibe', 'servo', 'vel_ned'],
    },
    '링크': {
        'params': ['MAV_0_RATE', 'MAV_0_FORWARD', 'COM_RC_IN_MODE', 'COM_RC_LOSS_T'],
        'tel': ['rc'],
    },
    'ARM 조건': {
        'params': ['COM_DISARM_LAND', 'COM_ARM_MAG_ANG', 'COM_DISARM_PRFLT',
                   'COM_PREARM_MODE'],
    },
    '기동 한계': {
        'params': ['MPC_XY_VEL_MAX', 'MPC_Z_VEL_MAX_UP', 'MPC_TILTMAX_AIR',
                   'MC_AIRMODE', 'FD_FAIL_P', 'FD_FAIL_R'],
    },
    '회로차단기': {
        'params': list(CBRK_OPEN),
    },
    '기록': {
        'params': ['SDLOG_MODE', 'SDLOG_PROFILE'],
        'tel': ['fc_boot_s'],
    },
    # FC 가 스스로 말할 때까지는 알 수 없다. 수집이 끝나야 끝난 것이다.
    'FC 자신의 말': {'until_end': True},
}

# 🔴 기체 식별. 정본은 OPERATIONS.md 「기체 식별」 표다 — 바꿀 일이 생기면
#    거기부터 고치고 여기를 맞춘다. 화면이 "무엇을 점검하고 있는지" 를
#    말하려면 기체 이름이 필요한데, 그것을 FC 에서 읽어 올 방법이 없다.
AIRFRAME = {
    'callsign': 'SHADE01',
    'type': 'Striver Mini VTOL (4+1)',
    'fc': 'Pixhawk 6C Mini',
    'fw': 'PX4 v1.17.0 커스텀 (37e76b278a)',
    'link': 'FC USB → rim3 브리지',
}

# 화면에 낼 점검 이름. 🔴 판정이 아니라 **무엇을 보고 있는지**를 적는다.
#    줄마다 "…을 점검합니다" 를 붙이지 않는다 — 열 몇 줄이 같은 꼬리를 달면
#    정작 다른 부분(무엇을 보는지)이 묻힌다. 목록이라는 것은 자리가 말한다.
GROUP_LABEL = {
    '쿼드 전용 잠금': '쿼드 전용 잠금',
    'failsafe':      'failsafe 동작',
    '지오펜스':        '지오펜스 설정',
    '미션':           '미션 이착륙 명령',
    '항법·미션':       '항법 파라미터',
    'GPS·추정':       'GPS · 추정기',
    '전원':           '전원 · 배터리',
    '센서':           'FC 센서',
    '기체 상태':       '기체 상태',
    '링크':           '링크 · 조종기',
    'FC 자신의 말':    'FC 경고',
    '파라미터':        '파라미터 수신',
    'ARM 조건':       'ARM 조건',
    '기동 한계':       '기동 한계',
    '회로차단기':      '회로차단기',
    '기록':           '로깅 · FC 시계',
}


def group_progress(name, params, mission, tel, elapsed, secs):
    """묶음 하나가 얼마나 왔나. 0.0~1.0.

    🔴 진짜로 도착한 것만 센다. 시계를 백분율로 바꿔 보여 주면 화면은
       그럴듯한데 실제로는 아무것도 안 온 상태일 수 있다."""
    need = GROUP_NEEDS.get(name)
    if not need:
        return None
    if need.get('until_end'):
        # 언제 올지 모르는 것. 수집 시간이 지나야 끝난 것으로 본다.
        return min(1.0, elapsed / secs) if secs > 0 else 1.0

    have = total = 0
    for n in need.get('params', ()):
        total += 1
        if n in params:
            have += 1
    for k in need.get('tel', ()):
        total += 1
        if k in tel:
            have += 1
    if need.get('mission'):
        total += 1
        if mission['count'] is not None and len(mission['items']) == mission['count']:
            have += 1
    return (have / total) if total else 1.0


# 묶음을 화면에 낼 순서. 여기 없는 이름은 뒤에 붙는다.
# 🔴 순서는 **현장 점검 순서**다 — 먼저 막을 것(쿼드 잠금·failsafe)을 위로 둔다.
GROUP_ORDER = ['쿼드 전용 잠금', 'failsafe', '회로차단기', '지오펜스', '미션',
               '항법·미션', 'ARM 조건', 'GPS·추정', '전원', '센서', '기체 상태',
               '기동 한계', '링크', '기록', '파라미터', 'FC 자신의 말']

# 묶음 하나의 판정 = 그 안에서 가장 나쁜 등급. 등급이 셋뿐이라 규칙도 하나다.
# 🔴 이 계산은 여기에만 있다. 화면(JS)에서 다시 하면 두 벌이 따로 늙는다.
#
# 🔴 **GO 가 아니면 NO GO 다** (2026-09-20 사용자 지정). 안쪽 등급은 셋이지만
#    (`blk` 진행 불가 · `warn` 확인 필요 · `ok` 정상) 줄에 찍는 답은 둘뿐이다 —
#    종합과 같은 기준이라야 "줄은 확인인데 종합은 NO GO" 를 읽는 사람이 겪지
#    않는다. 무엇 때문인지는 항목별 상세가 말한다.
GROUP_VERDICT = {'blk': 'NO GO', 'warn': 'NO GO', 'ok': 'GO', 'info': '참고'}


def judge(params, mission, tel, msgs, dropped=()):
    """지금까지 걷은 것으로 판정을 한 벌 만든다.

    🔴 판정 로직은 `check_*` 하나뿐이다. 중간에 부르든 끝에 부르든 같은
       함수를 돌린다 — 화면용으로 따로 재는 코드를 만들면 그 순간부터
       "화면은 GO 인데 터미널은 NO-GO" 인 날이 온다."""
    r = Report()
    check_params(r, params)
    check_mission(r, mission)
    check_live(r, tel, msgs)
    if dropped:
        r.group = '링크'
        uniq = sorted(set(d.split(':')[0] for d in dropped))
        r.add('warn', '해석 못한 메시지', '%d건 (%s)' % (len(dropped), ', '.join(uniq)),
              dropped[0])
    return r


def group_of(r, name, elapsed=0.0):
    """판정 한 벌에서 묶음 하나만 떼어 낸다. 없으면 None."""
    blob = as_json(r, {'how': None, 'notes': []}, elapsed)
    for g in blob['groups']:
        if g['name'] == name:
            return g
    return None


def stream(m, secs, meta, out):
    """걷는 동안 묶음이 끝나는 대로 한 줄씩 흘린다 (NDJSON).

    🔴 **완료 순서는 정해져 있지 않다.** 자기 데이터가 먼저 온 묶음이 먼저
       나간다. 화면은 도착한 순서대로 채우면 된다 — 번호를 미리 매겨 두고
       그 자리를 기다리면 병렬로 걷는 의미가 없다.

    줄의 종류:
      {"t":"start", groups:[{name,label}...]}   무엇을 볼 것인지
      {"t":"prog",  progress:{name: 0.0~1.0}}   지금까지 몇 개가 왔나
      {"t":"group", group:{...}}                한 묶음이 끝났다 (판정 포함)
      {"t":"done",  ...as_json...}              전부 끝났다
    """
    t0 = time.time()
    sent = set()

    def line(obj):
        json.dump(obj, out, ensure_ascii=False)
        out.write('\n')
        out.flush()

    line({'t': 'start',
          'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
          'how': meta.get('how'),
          'secs': secs,
          'airframe': AIRFRAME,
          'groups': [{'name': g, 'label': GROUP_LABEL.get(g, g)}
                     for g in GROUP_ORDER if g in GROUP_NEEDS]})

    def on_progress(prog, params, mission, tel, msgs):
        line({'t': 'prog', 'progress': {k: round(v, 3) for k, v in prog.items()},
              'elapsed': round(time.time() - t0, 2)})
        # 다 온 묶음은 그 자리에서 판정해 내보낸다. 기다릴 이유가 없다.
        ready = [g for g, v in prog.items() if v >= 1.0 and g not in sent]
        if not ready:
            return
        r = judge(params, mission, tel, msgs)
        for g in ready:
            blob = group_of(r, g, time.time() - t0)
            if blob is None:
                # 판정거리가 아직 하나도 없는 묶음이다 (FC 가 경고를 안 뱉었다).
                # 🔴 그래도 **끝난 것으로 내보낸다.** 안 그러면 화면이 100%
                #    에 멈춘 채로 남아, 다 된 점검이 도는 중으로 보인다.
                blob = {'name': g, 'items': [], 'level': 'ok', 'verdict': 'GO',
                        'counts': {'blk': 0, 'warn': 0, 'ok': 0, 'info': 0}}
            sent.add(g)
            line({'t': 'group', 'group': blob,
                  'elapsed': round(time.time() - t0, 2)})

    params, mission, tel, msgs, dropped = gather(m, secs, False, on_progress)

    # 마지막 한 벌. 중간에 보낸 묶음도 여기 다시 들어간다 — 화면은 이것으로
    # 자기 상태를 맞춘다. 중간 판정은 그때까지 온 것만 보고 낸 것이라,
    # 늦게 도착한 값이 판정을 바꿨을 수 있다.
    r = judge(params, mission, tel, msgs, dropped)
    blob = as_json(r, meta, time.time() - t0)
    blob['t'] = 'done'
    line(blob)
    v = r.verdict()
    return 0 if v == 'GO' else (1 if v == 'NO-GO' else 2)


def as_json(r, meta, elapsed):
    """판정을 기계가 읽는 모양으로. 🔴 판정 자체는 여기서 하지 않는다 —
    check_* 가 이미 내린 것을 묶어서 옮길 뿐이다. 값을 다시 해석하면
    터미널과 웹이 다른 답을 내게 된다."""
    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    groups = {}
    for i, (g, level, name, detail, why) in enumerate(r.rows):
        gr = groups.setdefault(g, {'name': g, 'items': []})
        gr['items'].append({'level': level, 'name': name,
                            'detail': detail, 'why': why, 'seq': i})
    out = []
    for g in sorted(groups, key=lambda g: (order.get(g, 99), g)):
        gr = groups[g]
        lv = {it['level'] for it in gr['items']}
        # 가장 나쁜 것 하나가 묶음을 정한다. 전부 info 면 판정이 아니라 참고다.
        worst = ('blk' if 'blk' in lv else
                 'warn' if 'warn' in lv else
                 'ok' if 'ok' in lv else 'info')
        gr['level'] = worst
        gr['verdict'] = GROUP_VERDICT[worst]
        gr['counts'] = {k: sum(1 for it in gr['items'] if it['level'] == k)
                        for k in ('blk', 'warn', 'ok', 'info')}
        out.append(gr)

    return {
        'ok': True,
        'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'airframe': AIRFRAME,
        'verdict': r.verdict(),
        'exit': 0 if r.verdict() == 'GO' else (1 if r.verdict() == 'NO-GO' else 2),
        'elapsed': round(elapsed, 2),
        'how': meta.get('how'),
        'notes': meta.get('notes') or [],
        'counts': {'blk': len(r.blk), 'warn': len(r.warn),
                   'ok': len(r.ok), 'info': len(r.info)},
        'groups': out,
        # 🔴 매 비행 같은 내용이다. 판정과 섞지 말라고 따로 낸다.
        'standing': [{'name': n, 'text': t} for n, t in STANDING],
    }


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
    ap.add_argument('--json', action='store_true',
                    help='판정을 JSON 으로 낸다 (웹 화면·에이전트용). '
                         '판정 로직은 터미널과 같은 것을 쓴다')
    ap.add_argument('--stream', action='store_true',
                    help='걷는 동안 묶음이 끝나는 대로 NDJSON 으로 흘린다. '
                         '완료 순서는 정해져 있지 않다 — 먼저 온 것이 먼저 나간다')
    a = ap.parse_args()
    machine = a.json or a.stream
    paint(not a.no_color and not machine and sys.stdout.isatty())

    t0 = time.time()
    # 기계용일 때는 verbose 로 모은다. 화면이 정상 항목까지 다 그리기 때문이다.
    verbose = a.verbose or machine
    m, how, hb_s, notes = connect(a.conn, verbose)
    if m is None:
        if machine:
            # 🔴 붙지 못한 것을 "이상 없음" 으로 내지 않는다. 판정 자리에
            #    붙지 못했다는 사실을 그대로 넣는다 — 화면이 GO 를 그리면 안 된다.
            json.dump({
                'ok': False,
                'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'verdict': 'NO-GO',
                'exit': 1,
                'elapsed': round(time.time() - t0, 2),
                'error': 'FC 에 붙지 못했다',
                'notes': notes,
                'hints': ['FC USB 가 그 PC 에 꽂혀 있나 (ls /dev/ttyACM*)',
                          '누가 포트를 쥐고 있나 (fuser -v /dev/ttyACM0)',
                          '브리지가 떠 있나 (pgrep -af mav_bridge)'],
                'groups': [], 'standing': [],
                'counts': {'blk': 1, 'warn': 0, 'ok': 0, 'info': 0},
                # 스트림을 읽는 쪽이 종류로 갈라 보므로 이것도 이름을 붙인다.
                't': 'done',
            }, sys.stdout, ensure_ascii=False)
            sys.stdout.write('\n')
            return 1
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

    meta = {'how': how, 'notes': notes if verbose else []}
    if a.stream:
        return stream(m, a.secs, meta, sys.stdout)

    params, mission, tel, msgs, dropped = gather(m, a.secs, verbose and not machine)
    # 🔴 조용히 버리면 "왜 그 항목이 안 나왔지" 를 아무도 못 쫓는다 — judge 가
    #    dropped 를 '해석 못한 메시지' 로 올린다.
    r = judge(params, mission, tel, msgs, dropped)

    if a.json:
        json.dump(as_json(r, meta, time.time() - t0), sys.stdout, ensure_ascii=False)
        sys.stdout.write('\n')
        v = r.verdict()
        return 0 if v == 'GO' else (1 if v == 'NO-GO' else 2)
    return render(r, meta, time.time() - t0, a.verbose)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n중단됨')
        sys.exit(130)
