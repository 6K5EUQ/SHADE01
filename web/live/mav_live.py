#!/usr/bin/env python3
"""MAVLink 실시간 상태 수집기 — 라이브 트래킹 페이지의 데이터원.

UDP 로 들어오는 MAVLink 를 디코딩해 "지금 상태" 하나를 들고 있다가, 로컬
HTTP 로 내준다. 로그(.ulg) 재생이 아니라 **현재 프레임**이다.

    ./mav_live.py                       # 14550 에서 듣는다 (백팩·브리지 공용)
    ./mav_live.py --port 14550 --http 4400

🔴 읽기 전용이다. 소켓에 **아무것도 쓰지 않는다.**
   pymavlink 의 mavutil.mavlink_connection() 을 쓰지 않는 이유가 이것이다 —
   그 래퍼는 heartbeat 를 자동으로 되쏘고 param/mission 요청을 보낼 길을 열어
   둔다. 여기서는 socket.recvfrom() 만 하고 sendto() 는 코드에 없다. 브라우저가
   무엇을 하든 FC 로 나가는 바이트는 0 이다 (README "상행이 열려 있다" 참조).

받는 경로는 둘 다 같은 포트로 들어온다:
  - ELRS 백팩   조종기 AP(10.0.0.1) → PC. TELEM1 경유
  - shade-bridge  FC USB → UDP 중계

⚠️ 브리지가 이미 14550 을 쓰고 있으면 여기서 시끄럽게 죽는다. SO_REUSEADDR 을
   켜서 조용히 나눠 갖게 하면 커널이 패킷을 둘 중 하나에만 주므로, QGC 와
   이 페이지가 서로 프레임을 훔쳐 간다. 그때는 --port 로 비켜라
   (브리지의 고정 대상에 127.0.0.1:14551 을 추가하는 방식).
"""

import argparse
import errno
import json
import math
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

try:
    from pymavlink import mavutil
    from pymavlink.dialects.v20 import common as mavlink2
except ImportError:
    sys.exit("pymavlink 이 없다. .venv/bin/python 으로 돌려라 "
             "(PROCEDURE.md '분석 PC 준비').")

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(HERE, 'public')

# 궤적 보관 상한. 5Hz 로 들어와도 40분치다. 넘으면 앞을 버린다 —
# 브라우저가 늦게 붙어도 지금까지의 항적을 다 받아야 지도가 맞다.
TRACK_MAX = 12000

# 이 시간 동안 프레임이 없으면 링크가 끊긴 것으로 본다. ELRS 백팩은
# 대역폭이 좁아(615 B/s) 하트비트 간격이 벌어지므로 넉넉히 잡는다.
LINK_TIMEOUT = 3.0

# 항적에 점을 찍는 최소 간격(m). GPS 노이즈로 제자리에서 점이 쌓이는 것을 막는다.
TRACK_MIN_MOVE = 0.4

# PX4 custom_mode 해석 — ArduPilot 과 다르다. pymavlink 의 mode_mapping 은
# APM 용이라 PX4 에 쓰면 엉뚱한 이름이 나온다. PX4 는 상위 바이트에
# main_mode, 그 위 바이트에 sub_mode 를 넣는다 (px4_custom_mode.h).
PX4_MAIN = {
    1: 'MANUAL', 2: 'ALTCTL', 3: 'POSCTL', 4: 'AUTO', 5: 'ACRO',
    6: 'OFFBOARD', 7: 'STABILIZED', 8: 'RATTITUDE', 9: 'SIMPLE', 10: 'TERMINATION',
}
PX4_SUB = {
    1: 'READY', 2: 'TAKEOFF', 3: 'LOITER', 4: 'MISSION',
    5: 'RTL', 6: 'LAND', 7: 'RTGS', 8: 'FOLLOW', 9: 'PRECLAND', 10: 'VTOL_TAKEOFF',
}


def decode_px4_mode(custom_mode, base_mode):
    """custom_mode → 사람이 읽는 모드 이름."""
    if not custom_mode:
        # 커스텀 모드가 안 켜져 있으면 base_mode 밖에 볼 것이 없다.
        if base_mode & mavlink2.MAV_MODE_FLAG_MANUAL_INPUT_ENABLED:
            return 'MANUAL'
        return '?'
    main = (custom_mode >> 16) & 0xFF
    sub = (custom_mode >> 24) & 0xFF
    name = PX4_MAIN.get(main, 'MODE%d' % main)
    if main == 4:                                    # AUTO 일 때만 sub 가 의미 있다
        return 'AUTO.' + PX4_SUB.get(sub, str(sub))
    return name


# VTOL 상태. 쿼드 전용 운용이므로 FW 로 넘어가면 화면에서 눈에 띄어야 한다.
VTOL_STATE = {
    0: '', 1: 'TRANSITION→FW', 2: 'TRANSITION→MC', 3: 'MC', 4: 'FW',
}

# EKF(추정기) 상태 플래그 중 "이것이 죽으면 곤란한" 것만 고른다.
#
# ⚠️ PX4 는 ESTIMATOR_STATUS 를 보낸다. ArduPilot 의 EKF_STATUS_REPORT 가 아니다
#    (근거: PX4-Autopilot/src/modules/mavlink/streams/ESTIMATOR_STATUS.hpp).
#    이름이 비슷해 헷갈리기 쉬운데 pymavlink common 에는 EKF_* 상수 자체가 없다.
EKF_FLAGS = [
    ('attitude', mavlink2.ESTIMATOR_ATTITUDE),
    ('vel_horiz', mavlink2.ESTIMATOR_VELOCITY_HORIZ),
    ('pos_horiz', mavlink2.ESTIMATOR_POS_HORIZ_REL),
    ('pos_abs', mavlink2.ESTIMATOR_POS_HORIZ_ABS),
    ('alt', mavlink2.ESTIMATOR_POS_VERT_ABS),
]

# MAV_SEVERITY 0-7. STATUSTEXT 를 화면에 띄울 때 색을 정한다.
SEVERITY = ['EMERG', 'ALERT', 'CRIT', 'ERROR', 'WARN', 'NOTICE', 'INFO', 'DEBUG']

MAX_MESSAGES = 200


def _finite(o):
    """NaN·Infinity 를 None 으로 바꾼다. 중첩 dict/list 까지 훑는다.

    🔴 이것이 없으면 화면 전체가 죽는다. 파이썬 json 은 NaN 을 **그대로**
       `NaN` 이라 적는데 그건 유효한 JSON 이 아니다. 브라우저의 JSON.parse 는
       필드 하나 때문에 응답 전체를 거부하므로, EKF 비율 하나가 NaN 인 순간
       고도·전압·모드까지 같이 사라지고 페이지는 "서버 없음" 을 띄운다.
       (2026-09-05 실기에서 발생: ESTIMATOR_STATUS 의 vel/pos 비율이 NaN.
        FC 가 EKF 를 아직 초기화하지 않았을 때 그렇게 온다.)

       curl 로는 안 보인다 — 파싱을 안 하니까. 반드시 파서를 거쳐 확인하라.
    """
    if isinstance(o, float):
        return None if o != o or o in (float('inf'), float('-inf')) else o
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_finite(v) for v in o]
    return o


def dumps_json(obj):
    """브라우저가 반드시 파싱할 수 있는 JSON. allow_nan=False 로 이중 방어한다."""
    return json.dumps(_finite(obj), ensure_ascii=False, allow_nan=False)


class State:
    """지금 기체 상태 하나. 락으로 감싼다 — 수신 스레드와 HTTP 스레드가 함께 본다."""

    def __init__(self):
        self.lock = threading.Lock()
        self.seen = 0.0            # 마지막 프레임 수신 시각 (monotonic)
        self.boot = time.time()
        self.packets = 0
        self.bytes = 0
        self.src = None            # 마지막으로 보내온 (ip, port)
        self.sysid = None
        self.compid = None

        self.d = {}                # 화면에 그대로 나가는 값들
        self.track = []            # [[lat, lon, alt_rel], ...]
        self.messages = []         # STATUSTEXT 최근 것
        self.home = None           # [lat, lon]
        self.mission = []          # [[lat, lon, seq, cmd], ...]
        self._last_pt = None
        self._seq = 0              # 프론트가 증분을 알아채는 카운터

        # 항적에 **지금까지 쌓은 총 개수**. TRACK_MAX 로 앞을 버려도 계속 는다.
        # 클라이언트는 이 값으로 "어디까지 받았나"를 말한다 — 리스트 인덱스로
        # 주고받으면 앞이 잘리는 순간 같은 인덱스가 다른 점을 가리켜, 긴 비행에서
        # 항적이 조용히 빠지거나 겹친다.
        self.track_total = 0

    def touch(self, addr, nbytes):
        # 수신 스레드만 쓰지만 snapshot() 이 락 안에서 읽으므로 여기서도 잠근다.
        with self.lock:
            self.seen = time.monotonic()
            self.packets += 1
            self.bytes += nbytes
            self.src = addr

    def snapshot(self, since=None, want_track=True):
        """HTTP 로 나갈 형태. since(총 개수 기준) 이후의 항적만 잘라 보낸다.

        want_track=False 면 항적을 빼고 개수만 알린다.
        """
        with self.lock:
            live = (time.monotonic() - self.seen) < LINK_TIMEOUT if self.seen else False
            n = len(self.track)
            dropped = self.track_total - n        # 앞에서 버려진 개수
            if since is None or since < dropped:
                # 처음 붙었거나, 못 받는 사이에 앞이 잘렸다 → 가진 것을 통째로.
                start = 0
            else:
                start = min(since - dropped, n)
            return {
                'live': live,
                'seq': self._seq,
                'age': round(time.monotonic() - self.seen, 2) if self.seen else None,
                'packets': self.packets,
                'bytes': self.bytes,
                'src': '%s:%d' % self.src if self.src else None,
                'link': _link_kind(self.src),
                'sysid': self.sysid,
                'uptime': round(time.time() - self.boot),
                'd': dict(self.d),
                'home': self.home,
                'mission': self.mission,
                'track_n': self.track_total,
                # 이 응답의 첫 점이 전체에서 몇 번째인가. 0 이면 "처음부터 다시".
                'track_from': dropped + start,
                'track': self.track[start:] if want_track else [],
                'messages': self.messages[-40:],
            }


def _link_kind(src):
    """이 프레임이 어느 경로로 왔나 — 'ELRS' 또는 'USB'.

    보낸 쪽 주소로 가른다. 둘은 대역폭도 갱신 주기도 달라서(실측: 백팩
    285 B/s·자세 1.6Hz vs USB 직결 28.4 KB/s) 지금 무엇을 보고 있는지가
    화면에 드러나야 한다.

      10.0.0.x   조종기 ELRS 백팩 AP → 'ELRS'
      그 외      shade-bridge 가 FC USB 를 중계 → 'USB'

    ⚠️ 브리지는 자기 Tailscale 주소(100.x)나 127.0.0.1 로 보낸다. 백팩만
       10.0.0.0/24 를 쓰므로 그것만 보면 갈린다.
    """
    if not src:
        return None
    ip = src[0]
    return 'ELRS' if ip.startswith('10.0.0.') else 'USB'


def handle(msg, st):
    """MAVLink 메시지 하나를 상태에 반영한다."""
    t = msg.get_type()
    d = st.d

    if t == 'HEARTBEAT':
        # 컴패니언(Pi)·GCS 도 하트비트를 낸다. 기체(autopilot != INVALID)만 본다.
        if msg.autopilot == mavlink2.MAV_AUTOPILOT_INVALID:
            return
        st.sysid = msg.get_srcSystem()
        st.compid = msg.get_srcComponent()
        d['armed'] = bool(msg.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED)
        d['mode'] = decode_px4_mode(msg.custom_mode, msg.base_mode)
        d['mav_type'] = msg.type
        d['system_status'] = msg.system_status

    elif t == 'GLOBAL_POSITION_INT':
        lat, lon = msg.lat / 1e7, msg.lon / 1e7
        d['lat'], d['lon'] = lat, lon
        d['alt_msl'] = msg.alt / 1000.0
        d['alt'] = msg.relative_alt / 1000.0          # 홈 기준 상대고도
        d['vx'], d['vy'], d['vz'] = msg.vx / 100.0, msg.vy / 100.0, msg.vz / 100.0
        d['groundspeed'] = math.hypot(msg.vx, msg.vy) / 100.0
        d['climb'] = -msg.vz / 100.0
        d['hdg'] = msg.hdg / 100.0 if msg.hdg != 65535 else None

        # 유효한 좌표일 때만 항적에 쌓는다. fix 전에는 0,0 이 들어온다.
        if lat or lon:
            pt = [round(lat, 7), round(lon, 7), round(d['alt'], 1)]
            if st._last_pt is None or _moved(st._last_pt, pt) > TRACK_MIN_MOVE:
                st.track.append(pt)
                st.track_total += 1          # 앞을 버려도 계속 는다 (증분 전송의 기준)
                st._last_pt = pt
                if len(st.track) > TRACK_MAX:
                    del st.track[:len(st.track) - TRACK_MAX]

    elif t == 'ATTITUDE':
        d['roll'] = math.degrees(msg.roll)
        d['pitch'] = math.degrees(msg.pitch)
        d['yaw'] = math.degrees(msg.yaw) % 360

    elif t == 'VFR_HUD':
        d['airspeed'] = msg.airspeed
        d['groundspeed'] = msg.groundspeed
        d['throttle'] = msg.throttle
        d['climb'] = msg.climb
        if 'alt' not in d:
            d['alt'] = msg.alt

    elif t == 'SYS_STATUS':
        d['volt'] = msg.voltage_battery / 1000.0 if msg.voltage_battery != 65535 else None
        d['cur'] = msg.current_battery / 100.0 if msg.current_battery != -1 else None
        d['batt_pct'] = msg.battery_remaining if msg.battery_remaining != -1 else None
        d['load'] = msg.load / 10.0

    elif t == 'BATTERY_STATUS':
        # PM08 DroneCAN 이 여기로 온다. SYS_STATUS 보다 정확하다.
        if msg.current_battery != -1:
            d['cur'] = msg.current_battery / 100.0

        # voltages[] 는 셀 전압일 수도, "총 전압을 쪼갠 것" 일 수도 있다.
        # PX4 는 셀 전압을 모르면(PM08 이 그렇다) 총 전압을 첫 칸에 넣고,
        # 65535 를 넘으면 65534 짜리 덩어리로 쪼개 담는다.
        #   미사용 = 65535(UINT16_MAX),  실제 덩어리 = 65534
        # 65534 까지 걸러내면 65.5V 를 통째로 잃는다. 65535 만 뺀다.
        # 근거: PX4-Autopilot/src/modules/mavlink/streams/BATTERY_STATUS.hpp
        cells = [x for x in msg.voltages if x != 65535]
        ext = [x for x in getattr(msg, 'voltages_ext', []) or [] if x not in (0, 65535)]
        if cells:
            d['volt'] = round((sum(cells) + sum(ext)) / 1000.0, 2)
            d['cells'] = len(cells) + len(ext)
        if msg.battery_remaining != -1:
            d['batt_pct'] = msg.battery_remaining
        if msg.current_consumed != -1:
            d['mah'] = msg.current_consumed

    elif t == 'GPS_RAW_INT':
        d['fix'] = msg.fix_type
        d['sats'] = msg.satellites_visible
        d['eph'] = msg.eph / 100.0 if msg.eph != 65535 else None

    elif t == 'VIBRATION':
        d['vibe'] = [round(msg.vibration_x, 2), round(msg.vibration_y, 2),
                     round(msg.vibration_z, 2)]

    elif t == 'ESTIMATOR_STATUS':
        d['ekf'] = {k: bool(msg.flags & f) for k, f in EKF_FLAGS}
        # 비율(ratio) 이다. 1.0 을 넘으면 그 센서의 혁신 검사가 깨지고 있다는 뜻 —
        # 분산이 아니므로 "낮을수록 좋다"가 아니라 "1 을 넘으면 나쁘다"로 읽는다.
        d['ekf_ratio'] = {
            'vel': round(msg.vel_ratio, 2),
            'pos': round(msg.pos_horiz_ratio, 2),
            'alt': round(msg.pos_vert_ratio, 2),
            'mag': round(msg.mag_ratio, 2),
        }
        d['eph_ekf'] = round(msg.pos_horiz_accuracy, 2)

    elif t == 'EXTENDED_SYS_STATE':
        d['vtol'] = VTOL_STATE.get(msg.vtol_state, '')
        d['landed'] = msg.landed_state          # 1=지상 2=공중

    elif t == 'SERVO_OUTPUT_RAW':
        # 모터별 추력. PX4 는 PWM us 를 보낸다 — % 로 바꾼다.
        #
        # ⚠️ ACTUATOR_OUTPUT_STATUS 가 아니다. PX4 의 스트림 설정은
        #    SERVO_OUTPUT_RAW_0 만 켠다 (mavlink_main.cpp) — 전자를 기다리면
        #    영원히 안 온다 (실측 2026-09-05).
        #
        # 🔴 이 기체 배치에 묶인 값이다 (README 「출력 배치」):
        #    MAIN3/4/6/7 = VTOL 우후/우전/좌후/좌전. 인덱스는 0부터라 2,3,5,6.
        #    MAIN1/2 는 에일러론 서보(100Hz), MAIN8 은 크루즈, MAIN5 는 UBEC —
        #    서보를 추력으로 그리면 거짓말이 된다.
        # PWM 1000~2000us 를 0~100% 로 편다. 안 도는 채널(<900)은 None.
        out = {}
        for name, i in (('RB', 3), ('RF', 4), ('LB', 6), ('LF', 7)):
            v = getattr(msg, 'servo%d_raw' % i, 0)
            out[name] = None if (v is None or v < 900) else \
                round(max(0.0, min(100.0, (v - 1000.0) / 10.0)), 1)
        if any(v is not None for v in out.values()):
            d['motors'] = out

    elif t == 'RC_CHANNELS':
        d['rssi'] = msg.rssi if msg.rssi != 255 else None
        # 8 로 자르면 CH9(KILL)·CH10 이 화면에서 사라진다 — 링크는 16 까지 온다.
        # chancount 가 실제로 몇 개가 유효한지 말해 준다.
        n = min(getattr(msg, 'chancount', 8) or 8, 18)
        d['rc_chan'] = [getattr(msg, 'chan%d_raw' % i) for i in range(1, n + 1)]
        d['rc_count'] = n

    elif t == 'RADIO_STATUS':
        d['radio_rssi'] = msg.rssi
        d['radio_remrssi'] = msg.remrssi
        d['radio_noise'] = msg.noise

    elif t == 'HOME_POSITION':
        st.home = [round(msg.latitude / 1e7, 7), round(msg.longitude / 1e7, 7)]

    elif t == 'NAV_CONTROLLER_OUTPUT':
        d['wp_dist'] = msg.wp_dist
        d['xtrack'] = round(msg.xtrack_error, 1)

    elif t == 'MISSION_CURRENT':
        d['wp_seq'] = msg.seq

    elif t == 'STATUSTEXT':
        text = msg.text.decode() if isinstance(msg.text, bytes) else msg.text
        sev = SEVERITY[msg.severity] if msg.severity < len(SEVERITY) else '?'
        st.messages.append({'t': round(time.time()), 'sev': sev, 'text': text.strip()})
        if len(st.messages) > MAX_MESSAGES:
            del st.messages[:len(st.messages) - MAX_MESSAGES]

    else:
        return

    st._seq += 1


def _moved(a, b):
    """두 좌표 사이 대략 거리(m). 짧은 거리라 평면 근사로 충분하다."""
    dlat = (b[0] - a[0]) * 111320.0
    dlon = (b[1] - a[1]) * 111320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def receiver(sock, st):
    """UDP 수신 루프. 이 함수는 소켓에 쓰지 않는다."""
    # 송신 주소마다 파서를 따로 둔다. 한 파서에 여러 기기의 바이트를 섞어
    # 넣으면 시퀀스가 어긋나 프레임을 통째로 버린다 (기체·Pi·GCS 가 같은
    # UDP 로 들어온다).
    #
    # 주소는 포트까지 포함하므로 GCS 가 재시작할 때마다 새 항목이 생긴다.
    # 안 지우면 며칠 켜 둔 동안 조용히 쌓인다 — 마지막 수신 시각을 같이 들고
    # 오래된 것을 버린다.
    parsers = {}                    # addr -> [MAVLink, 마지막 수신 monotonic]
    last_sweep = time.monotonic()
    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except OSError:
            continue
        if not data:
            continue
        st.touch(addr, len(data))

        now = time.monotonic()
        ent = parsers.get(addr)
        if ent is None:
            mav = mavlink2.MAVLink(None)
            mav.robust_parsing = True
            ent = parsers[addr] = [mav, now]
        else:
            ent[1] = now
        mav = ent[0]

        # 5분 넘게 조용한 송신자의 파서는 버린다.
        if now - last_sweep > 60.0:
            last_sweep = now
            for a in [a for a, e in parsers.items() if now - e[1] > 300.0]:
                del parsers[a]
        try:
            msgs = mav.parse_buffer(data) or []
        except Exception:
            continue
        with st.lock:
            for m in msgs:
                if m.get_type() == 'BAD_DATA':
                    continue
                try:
                    handle(m, st)
                except Exception:
                    pass          # 한 메시지가 이상해도 수집은 계속돼야 한다


class Handler(BaseHTTPRequestHandler):
    st = None

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        query = self.path.split('?')[1] if '?' in self.path else ''

        if path == '/api/state':
            since = 0
            # track=0 이면 항적을 아예 안 보낸다. 차트만 보는 화면(지금의
            # 라이브 페이지)이 40분 비행에서 매 폴 수백 KB 를 받지 않게 한다.
            want_track = True
            for kv in query.split('&'):
                if kv.startswith('since='):
                    try:
                        since = int(kv[6:])
                    except ValueError:
                        pass
                elif kv == 'track=0':
                    want_track = False
            body = dumps_json(self.st.snapshot(since, want_track))
            return self._send(200, body, 'application/json; charset=utf-8')

        # 화면에는 이걸 부르는 버튼이 없다 (지우기 버튼을 뺐다, 2026-09-05).
        # curl 로는 여전히 쓸 수 있어 남겨 둔다 — 긴 지상 테스트 뒤 차트를
        # 비우고 싶을 때 편하다.
        if path == '/api/reset':
            # 항적만 지운다. 새 비행을 같은 창에서 볼 때 쓴다.
            with self.st.lock:
                self.st.track.clear()
                self.st.track_total = 0      # 안 되돌리면 dropped 가 음수가 된다
                self.st._last_pt = None
                self.st.messages.clear()
            return self._send(200, '{"ok":true}', 'application/json')

        rel = 'index.html' if path == '/' else path.lstrip('/')
        full = os.path.normpath(os.path.join(PUBLIC, rel))
        if not full.startswith(PUBLIC):
            return self._send(403, 'no', 'text/plain')
        # 지도 타일·CSS 는 기존 뷰어(web/public)의 것을 그대로 쓴다.
        if not os.path.exists(full):
            alt = os.path.normpath(os.path.join(HERE, '..', 'public', rel))
            if alt.startswith(os.path.normpath(os.path.join(HERE, '..', 'public'))) \
                    and os.path.exists(alt):
                full = alt
        try:
            with open(full, 'rb') as f:
                body = f.read()
        except OSError:
            return self._send(404, 'not found', 'text/plain')
        ext = os.path.splitext(full)[1].lower()
        ctype = {'.html': 'text/html; charset=utf-8',
                 '.js': 'text/javascript; charset=utf-8',
                 '.css': 'text/css; charset=utf-8',
                 '.png': 'image/png', '.svg': 'image/svg+xml'}.get(ext, 'application/octet-stream')
        self._send(200, body, ctype)

    def log_message(self, *a):
        pass          # 접근 로그로 터미널을 덮지 않는다


def main():
    ap = argparse.ArgumentParser(description='MAVLink 실시간 트래킹 (읽기 전용)')
    ap.add_argument('--port', type=int, default=int(os.environ.get('LIVE_UDP', '14550')),
                    help='MAVLink UDP 리슨 포트 (기본 14550)')
    ap.add_argument('--http', type=int, default=int(os.environ.get('LIVE_HTTP', '4400')),
                    help='웹 페이지 포트 (기본 4400)')
    ap.add_argument('--bind', default='0.0.0.0',
                    help='UDP 바인딩 주소. 기본은 전부 — 백팩(10.0.0.x)과 '
                         '브리지(tailscale)가 서로 다른 인터페이스로 들어오기 때문이다')
    args = ap.parse_args()

    st = State()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # SO_REUSEADDR 을 켜지 않는다 — mav_bridge.py 와 같은 이유다. 조용히 포트를
    # 나눠 가지면 커널이 패킷을 한쪽에만 주어, QGC 와 이 페이지가 프레임을
    # 서로 훔쳐 간다. 충돌하면 여기서 시끄럽게 죽는 편이 낫다.
    try:
        sock.bind((args.bind, args.port))
    except OSError as e:
        # 🔴 주소가 사라졌으면 0.0.0.0 으로 물러선다. 죽으면 안 된다.
        #    백팩 경로에서는 WiFi 주소(10.0.0.x)에 못박아 여는데, AP 를 떠나면
        #    그 주소가 없어져 EADDRNOTAVAIL 로 시작조차 못 한다 — 다음 부팅에
        #    화면이 통째로 안 뜬다 (실측 rim3 2026-09-05).
        #    0.0.0.0 으로 열면 최소한 브리지 경로는 살아난다. 포트가 이미
        #    잡혀 있으면 그때는 진짜로 죽는 게 맞다 (아래 EADDRINUSE).
        if args.bind != '0.0.0.0' and e.errno == errno.EADDRNOTAVAIL:
            print('%s 가 없다 — 0.0.0.0 으로 물러선다 (백팩 AP 를 떠났나?)'
                  % args.bind, flush=True)
            args.bind = '0.0.0.0'
            try:
                sock.bind((args.bind, args.port))
            except OSError as e2:
                e = e2
            else:
                e = None
        if e is not None:
            print('UDP %s:%d 를 못 연다 (%s)' % (args.bind, args.port, e), file=sys.stderr)
            print('이미 QGC 나 브리지가 쓰고 있다. 확인:  ss -ulnp | grep %d' % args.port,
                  file=sys.stderr)
            print('다른 포트로 비켜라:  --port 14551', file=sys.stderr)
            sys.exit(1)

    threading.Thread(target=receiver, args=(sock, st), daemon=True).start()

    Handler.st = st
    srv = ThreadingHTTPServer(('127.0.0.1', args.http), Handler)
    srv.daemon_threads = True

    print('MAVLink UDP  %s:%d  (읽기 전용 — FC 로 아무것도 안 보낸다)'
          % (args.bind, args.port))
    print('라이브 페이지  http://127.0.0.1:%d' % args.http)
    print('멈추려면 Ctrl-C')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n종료')


if __name__ == '__main__':
    main()
