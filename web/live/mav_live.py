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
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
# playback.py 는 이 폴더에 있다. systemd 는 임의의 cwd 로 띄우므로 경로를 박는다.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

# 실시간 기록물이 쌓이는 곳. `.ulg` 와 섞이지 않게 하위 폴더를 쓴다 —
# qgclog 의 `_repair()` 가 형제 로그를 기증자로 찾으므로 `logs/` 평면에
# tlog 를 끼워 넣으면 안 된다 (PROCEDURE.md "평면으로 쌓는다").
LIVE_DIR = os.environ.get(
    'LIVE_TLOG_DIR', os.path.join(HERE, '..', '..', 'logs', 'live'))

# disarm 뒤 이만큼 더 받아 적고 닫는다. 착륙 직후의 경고·마지막 자세가
# 잘리지 않게 한다 — 9/5 세션에서 Kill 이후 5초 안에 진단이 나왔다.
REC_TAIL_S = 10.0


class Recorder:
    """ARM 구간을 원시 MAVLink(.tlog)로 받아 적는다.

    QGC 표준 tlog 형식이다 — 프레임마다 **8바이트 빅엔디안 마이크로초 UTC**를
    앞에 붙인 것. 그래서 QGC 로 바로 열리고 pymavlink 로도 재파싱된다.

    🔴 읽기 전용 원칙은 그대로다. 이 클래스는 **디스크에만** 쓴다. 소켓으로
       나가는 바이트는 여전히 0 이다.

    왜 원시 바이트인가: 파싱에 실패한 프레임도 원본이 남는다. 화면에 안 나가는
    필드도 나중에 다시 뽑을 수 있다 — 무엇이 필요할지는 사고가 난 뒤에 안다.
    """

    def __init__(self, dirpath, enabled=True):
        self.dir = os.path.abspath(dirpath)
        self.enabled = enabled
        self.f = None
        self.path = None
        self.started = None        # 이 파일이 열린 시각 (time.time)
        self.frames = 0
        self.bytes = 0
        self._closing_at = None    # disarm 후 닫을 시각 (monotonic)
        self.last = None           # 마지막으로 닫은 파일 (화면 표시용)
        self.error = None          # 디스크 문제를 화면에 드러낸다

    def _open(self):
        try:
            os.makedirs(self.dir, exist_ok=True)
            # 파일명은 **KST 로컬시각**이다. `.ulg` 가 UTC 라 헷갈리는 것을
            # 문서가 반복해 경고하는데(PROCEDURE §1-3), 이 파일은 사람이
            # 고르라고 있는 것이므로 조종자의 시계에 맞춘다. 안이 UTC 인 것과
            # 무관하다 — 그래서 이름에 KST 를 박아 둔다.
            name = time.strftime('%Y-%m-%d_%H-%M-%S_KST.tlog', time.localtime())
            path = os.path.join(self.dir, name)
            self.f = open(path, 'ab')
            self.path = path
            self.started = time.time()
            self.frames = self.bytes = 0
            self.error = None
            print('기록 시작  %s' % path, flush=True)
        except OSError as e:
            # 디스크가 차거나 권한이 없어도 **트래킹은 계속돼야 한다.**
            self.f = self.path = None
            self.error = str(e)
            print('기록 못 함: %s' % e, file=sys.stderr, flush=True)

    def _close(self):
        if self.f is None:
            self.path = None
            return
        try:
            self.f.close()
        except OSError:
            pass
        if self.path:
            dur = time.time() - self.started if self.started else 0
            self.last = {'name': os.path.basename(self.path),
                         'frames': self.frames, 'bytes': self.bytes,
                         'dur': round(dur, 1)}
            print('기록 종료  %s  (%d프레임 %.1fMB %.0f초)'
                  % (self.path, self.frames, self.bytes / 1e6, dur), flush=True)
        self.f = self.path = self.started = None
        self._closing_at = None

    def on_arm(self, armed):
        """armed 가 **바뀐** 순간에만 불린다."""
        if not self.enabled:
            return
        if armed:
            self._closing_at = None       # 꼬리 대기 중에 다시 떴으면 이어 쓴다
            if self.f is None:
                self._open()
        elif self.f is not None:
            # 바로 닫지 않는다. REC_TAIL_S 동안 더 받아 적는다.
            self._closing_at = time.monotonic() + REC_TAIL_S

    def write(self, data):
        """수신한 UDP 페이로드 그대로. 락 밖에서 부르지 마라 (st.lock 안)."""
        if self.f is None:
            return
        if self._closing_at is not None and time.monotonic() >= self._closing_at:
            self._close()
            return
        try:
            # 8바이트 빅엔디안 마이크로초 — QGC tlog 규약.
            self.f.write(int(time.time() * 1e6).to_bytes(8, 'big'))
            self.f.write(data)
            self.frames += 1
            self.bytes += len(data) + 8
        except OSError as e:
            self.error = str(e)
            print('기록 중단: %s' % e, file=sys.stderr, flush=True)
            self._close()

    def tick(self):
        """프레임이 안 들어와도 꼬리 시간이 지나면 닫아야 한다."""
        if self.f is not None and self._closing_at is not None \
                and time.monotonic() >= self._closing_at:
            self._close()

    def status(self):
        return {
            'on': self.enabled,
            'rec': self.f is not None,
            'name': os.path.basename(self.path) if self.path else None,
            'frames': self.frames,
            'bytes': self.bytes,
            'dur': round(time.time() - self.started, 1) if self.started else None,
            'last': self.last,
            'error': self.error,
        }


def read_tlog(path):
    """tlog 를 [(t_us, bytes), ...] 로 읽는다. 형식이 깨진 지점에서 멈춘다.

    QGC tlog = [8바이트 빅엔디안 us][MAVLink 프레임] 반복. 프레임 길이는
    헤더에서 읽는다 (v2: 0xFD, payload len 은 두 번째 바이트).

    ⚠️ 전원이 급단되면 마지막 프레임이 잘린다 — `.ulg` 와 같은 성질이다
       (PROCEDURE "꼬리 잘림은 손상이 아니다"). 그 앞까지 읽고 조용히 끝낸다.
    """
    out = []
    with open(path, 'rb') as f:
        buf = f.read()
    i, n = 0, len(buf)
    while i + 8 <= n:
        t_us = int.from_bytes(buf[i:i + 8], 'big')
        i += 8
        if i >= n:
            break
        magic = buf[i]
        if magic == 0xFD:                      # MAVLink v2
            if i + 3 > n:
                break
            plen = buf[i + 1]
            incompat = buf[i + 2]
            flen = 12 + plen + (13 if incompat & 0x01 else 0)
        elif magic == 0xFE:                    # MAVLink v1
            if i + 2 > n:
                break
            flen = 8 + buf[i + 1]
        else:
            break                              # 동기 상실 — 여기까지가 유효하다
        if i + flen > n:
            break
        out.append((t_us, buf[i:i + flen]))
        i += flen
    return out


class Player:
    """녹화된 tlog 를 시간축에 맞춰 State 에 흘려 넣는다.

    재생도 **실시간과 같은 handle() 을 통과한다.** 그래서 화면에 나오는 값이
    실시간과 한 글자도 다르지 않다 — 재생 전용 경로를 따로 만들면 두 그림이
    조용히 갈라진다.
    """

    def __init__(self, st):
        self.st = st
        self.frames = []
        self.name = None
        self.i = 0
        self.speed = 1.0
        self.playing = False
        self.t0 = None             # 프레임 기준 시각(us)
        self.wall = None           # 재생을 시작한 monotonic
        self.base = 0.0            # 시작 시점의 재생 위치(초)
        self.dur = 0.0
        self.thread = None
        self.stop = False

    def load(self, path):
        frames = read_tlog(path)
        if not frames:
            raise ValueError('읽을 프레임이 없다')
        with self.st.lock:
            self.frames = frames
            self.name = os.path.basename(path)
            self.t0 = frames[0][0]
            self.dur = (frames[-1][0] - self.t0) / 1e6
            self.i = 0
            self.base = 0.0
            self.playing = False
            self._reset_state()
        return {'name': self.name, 'frames': len(frames), 'dur': round(self.dur, 1)}

    def _reset_state(self):
        """st.lock 을 잡은 채로 부른다."""
        st = self.st
        st.d.clear()
        st.track.clear()
        st.track_total = 0
        st._last_pt = None
        st.messages.clear()
        st.home = None
        st.mission = []
        st._seq += 1

    def pos(self):
        """지금 재생 위치(초)."""
        if self.playing and self.wall is not None:
            return min(self.base + (time.monotonic() - self.wall) * self.speed, self.dur)
        return self.base

    def _apply_upto(self, target_s):
        """target_s 까지의 프레임을 State 에 먹인다. st.lock 안에서."""
        mav = mavlink2.MAVLink(None)
        mav.robust_parsing = True
        while self.i < len(self.frames):
            t_us, data = self.frames[self.i]
            if (t_us - self.t0) / 1e6 > target_s:
                break
            try:
                for m in mav.parse_buffer(data) or []:
                    if m.get_type() == 'BAD_DATA':
                        continue
                    try:
                        handle(m, self.st)
                    except Exception:
                        pass
            except Exception:
                pass
            self.i += 1
        # 재생 중에는 링크가 살아 있는 것처럼 보여야 한다 — 화면의 '끊김'
        # 표시는 실시간 전용 판정이다.
        self.st.seen = time.monotonic()

    def seek(self, sec):
        sec = max(0.0, min(sec, self.dur))
        with self.st.lock:
            # 뒤로 갈 때는 상태를 지우고 처음부터 다시 먹인다. MAVLink 는
            # 증분이라 되감기가 없다 — 앞 프레임을 안 먹으면 값이 남는다.
            if sec < self.pos():
                self._reset_state()
                self.i = 0
            self.base = sec
            self.wall = time.monotonic()
            self._apply_upto(sec)

    def _run(self):
        while not self.stop and self.playing:
            with self.st.lock:
                p = self.pos()
                self._apply_upto(p)
                if p >= self.dur:
                    self.playing = False
                    self.base = self.dur
                    break
            time.sleep(0.05)

    def play(self):
        with self.st.lock:
            if not self.frames or self.playing:
                return
            if self.base >= self.dur:        # 끝에서 다시 누르면 처음부터
                self._reset_state()
                self.i = 0
                self.base = 0.0
            self.playing = True
            self.wall = time.monotonic()
        self.stop = False
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def pause(self):
        with self.st.lock:
            if self.playing:
                self.base = self.pos()
                self.playing = False

    def set_speed(self, v):
        with self.st.lock:
            if self.playing:
                self.base = self.pos()
                self.wall = time.monotonic()
            self.speed = max(0.1, min(v, 50.0))

    def unload(self):
        self.pause()
        with self.st.lock:
            self.frames = []
            self.name = None
            self.i = 0
            self.base = self.dur = 0.0
            self._reset_state()

    def status(self):
        if not self.frames:
            return None
        return {'name': self.name, 'playing': self.playing,
                'pos': round(self.pos(), 2), 'dur': round(self.dur, 2),
                'speed': self.speed, 'frames': len(self.frames)}


def list_recordings(dirpath):
    """logs/live/ 의 .tlog 목록. 최신 먼저."""
    try:
        names = [n for n in os.listdir(dirpath) if n.endswith('.tlog')]
    except OSError:
        return []
    out = []
    for n in names:
        p = os.path.join(dirpath, n)
        try:
            stt = os.stat(p)
        except OSError:
            continue
        out.append({'name': n, 'size': stt.st_size,
                    'mtime': int(stt.st_mtime)})
    out.sort(key=lambda x: x['mtime'], reverse=True)
    return out


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


def _qs(query, key):
    """쿼리스트링에서 값 하나.

    ⚠️ parse_qs 가 이미 퍼센트 인코딩을 푼다. 여기서 또 unquote 하면
       파일명에 '%' 나 '+' 가 든 로그를 못 연다.
    """
    from urllib.parse import parse_qs
    vals = parse_qs(query).get(key)
    return vals[0] if vals else None


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

        self.rec = None            # Recorder. main() 이 꽂는다
        self.player = None         # Player. main() 이 꽂는다
        # 🔴 기록기가 보는 arm 상태는 d['armed'] 와 **따로** 둔다. 재생 중에는
        #    d 가 과거 프레임의 값으로 덮이므로, 그것을 기준으로 삼으면 실제
        #    기체가 arm 해도 파일이 안 갈린다.
        self._rec_armed = None
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
                'rec': self.rec.status() if self.rec else None,
                'play': self.player.status() if self.player else None,
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
        armed = bool(msg.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED)
        # 바뀐 순간에만 기록기를 건드린다. 하트비트는 1Hz 로 계속 오므로
        # 매번 부르면 파일을 여닫는 판정이 초마다 돈다.
        # 재생 중이면 이 경로로 오는 것은 과거 프레임이다 — 기록기는 위쪽
        # 수신 루프가 실기 하트비트로 따로 몬다.
        replaying = st.player is not None and st.player.frames
        if st.rec is not None and not replaying and armed != st._rec_armed:
            st.rec.on_arm(armed)
            st._rec_armed = armed
        d['armed'] = armed
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
    # 🔴 블로킹으로 두면 링크가 끊긴 순간 이 루프가 영영 멈춘다. 그러면
    #    disarm 뒤 꼬리 시간이 지나도 파일이 안 닫혀 열린 채 남는다.
    #    1초마다 깨어나 rec.tick() 을 돌린다.
    sock.settimeout(1.0)
    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            if st.rec is not None:
                with st.lock:
                    st.rec.tick()
            continue
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
            # 🔴 재생 중에는 들어오는 프레임을 화면에 반영하지 않는다. 섞으면
            #    과거와 현재가 한 화면에서 엎치락뒤치락한다. 기록은 계속한다 —
            #    재생을 보는 사이에도 실제 비행이 벌어질 수 있다.
            replaying = st.player is not None and st.player.frames
            if not replaying:
                for m in msgs:
                    if m.get_type() == 'BAD_DATA':
                        continue
                    try:
                        handle(m, st)
                    except Exception:
                        pass      # 한 메시지가 이상해도 수집은 계속돼야 한다
            else:
                # 화면에는 안 넣더라도 arm 전환은 봐야 기록 파일이 갈린다.
                for m in msgs:
                    if m.get_type() != 'HEARTBEAT':
                        continue
                    if m.autopilot == mavlink2.MAV_AUTOPILOT_INVALID:
                        continue
                    a = bool(m.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED)
                    if st.rec is not None and a != st._rec_armed:
                        st.rec.on_arm(a)
                    st._rec_armed = a
            # handle() 뒤에 쓴다 — HEARTBEAT 이 파일을 여는 순간의 그 패킷도
            # 기록에 들어가야 arm 시점이 파일 첫 프레임이 된다.
            if st.rec is not None:
                st.rec.write(data)


class Playback:
    """열어 둔 로그 하나. 프레임은 미리 구워 두고 인덱스만 옮긴다.

    🔴 재생은 **서버가 아니라 브라우저가** 시각을 정한다. 서버는 "이 시각의
       프레임을 달라" 는 요청에 답할 뿐 스스로 시간을 흘리지 않는다 — 그래야
       탭을 여러 개 열어도 서로 다른 지점을 볼 수 있고, 일시정지·스크럽이
       서버 상태를 건드리지 않는다.

    한 번에 하나만 연다. 40분 로그가 12000 프레임이라 여러 개를 물고 있으면
    메모리가 는다.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.fl = None            # load_flight() 결과
        self.err = None
        self.loading = None       # 로딩 중인 파일 이름

    def open(self, path):
        """로그를 연다. 오래 걸리므로(대형 로그 수십 초) 호출자가 스레드로 돌린다."""
        import playback
        with self.lock:
            self.loading = os.path.basename(path)
            self.err = None
            self.fl = None
        try:
            fl = playback.load_flight(path)
        except Exception as exc:
            with self.lock:
                self.err = str(exc)
                self.loading = None
            return
        with self.lock:
            self.fl = fl
            self.loading = None

    def close(self):
        with self.lock:
            self.fl = None
            self.err = None
            self.loading = None

    def info(self):
        """지금 무엇이 열려 있나. 프레임은 빼고 요약만."""
        with self.lock:
            if self.loading:
                return {'state': 'loading', 'name': self.loading}
            if self.err:
                return {'state': 'error', 'error': self.err}
            if not self.fl:
                return {'state': 'idle'}
            f = self.fl
            return {'state': 'ready', 'name': f['name'], 'dur': f['dur'],
                    'utc': f['utc'], 'hz': f['hz'], 'frames': len(f['frames']),
                    'repaired': f['repaired'], 'home': f['home'],
                    'track_n': len(f['track']), 'messages_n': len(f['messages'])}

    def series(self):
        """차트가 쓸 전량 시계열. 화면의 `trk` 와 **같은 채널 이름**으로 낸다.

        라이브는 폴 한 번이 격자 한 칸이지만 재생은 되감을 수 있어야 하므로,
        열 때 한 번 통째로 주고 브라우저는 커서만 옮긴다.
        """
        with self.lock:
            if not self.fl:
                return None
            frames = self.fl['frames']
            cols = {k: [] for k in ('alt', 'climb', 'spd', 'aspd', 'roll', 'pitch',
                                    'cur', 'volt', 'sats', 'eph',
                                    'ekf_vel', 'ekf_pos', 'ekf_alt', 'ekf_mag')}
            modes = []
            last_mode = None
            for fr in frames:
                d = fr['d']
                cols['alt'].append(d.get('alt'))
                cols['climb'].append(d.get('climb'))
                cols['spd'].append(d.get('groundspeed'))
                cols['aspd'].append(d.get('airspeed'))
                cols['roll'].append(d.get('roll'))
                cols['pitch'].append(d.get('pitch'))
                cols['cur'].append(d.get('cur'))
                cols['volt'].append(d.get('volt'))
                cols['sats'].append(d.get('sats'))
                cols['eph'].append(d.get('eph'))
                r = d.get('ekf_ratio') or {}
                cols['ekf_vel'].append(r.get('vel'))
                cols['ekf_pos'].append(r.get('pos'))
                cols['ekf_alt'].append(r.get('alt'))
                cols['ekf_mag'].append(r.get('mag'))
                m = d.get('mode')
                if m and m != last_mode:
                    modes.append({'t': fr['t'], 'name': m})
                    last_mode = m
            # 진동은 로그에 vibration 토픽이 없다 — 채널을 아예 안 만든다.
            # 화면은 없는 채널을 비워 두는 쪽이 0 을 그리는 것보다 정직하다.
            return {'hz': self.fl['hz'], 'n': len(frames),
                    'dur': self.fl['dur'], 'cols': cols, 'modes': modes,
                    'messages': self.fl['messages']}

    def at(self, ts):
        """재생 시각 ts(초) 의 상태를 라이브와 **같은 모양**으로 만든다.

        화면 코드가 라이브인지 재생인지 몰라도 되게 하는 것이 요점이다 —
        `d`·`messages`·`home` 이 전부 같은 자리에 온다.
        """
        with self.lock:
            if not self.fl:
                return None
            f = self.fl
            frames = f['frames']
            if not frames:
                return None
            i = int(round(ts * f['hz']))
            i = max(0, min(len(frames) - 1, i))
            fr = frames[i]
            # 지난 메시지만 보여준다 — 아직 안 온 경고를 미리 띄우면 재생이 아니다.
            msgs = [m for m in f['messages'] if m['t'] <= fr['t']][-40:]
            return {
                'live': True,          # 화면의 프리즈 오버레이를 켜지 않는다
                'playback': True,
                'name': f['name'],
                'dur': f['dur'],
                'utc': f['utc'],
                'pos': fr['t'],
                'i': i,
                'n': len(frames),
                'seq': i,
                'age': 0,
                'packets': i,
                'link': 'LOG',
                'src': f['name'],
                'sysid': 1,
                'uptime': round(fr['t']),
                'd': fr['d'],
                'home': f['home'],
                'mission': [],
                'track_n': 0,
                'track_from': 0,
                'track': [],
                'messages': msgs,
            }


class Handler(BaseHTTPRequestHandler):
    st = None
    rec_dir = None
    pb = None

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

        # ── 로그 재생 ──────────────────────────────────────────────
        # 🔴 전부 GET 이다. POST 를 열지 않는다 — "HTTP 는 do_GET 만 있다" 가
        #    이 서버의 읽기 전용 보장 중 하나다 (README 「상행이 없다」).
        #    재생은 로컬 파일을 읽을 뿐 FC 와 아무 관계가 없지만, 보장을
        #    깨뜨리지 않는 편이 검증하기 쉽다.
        if path == '/api/logs':
            import playback
            try:
                items = playback.list_logs()
            except SystemExit as exc:      # find_log_dir 이 못 찾으면 exit 한다
                return self._send(200, dumps_json({'logs': [], 'error': str(exc)}),
                                  'application/json; charset=utf-8')
            return self._send(200, dumps_json({'logs': items}),
                              'application/json; charset=utf-8')

        if path == '/api/playback/open':
            name = _qs(query, 'name')
            if not name:
                return self._send(400, '{"error":"name 이 없다"}', 'application/json')
            import playback
            # 🔴 목록에 있는 파일만 연다. 이름을 그대로 경로로 쓰면
            #    ?name=../../etc/passwd 로 아무 파일이나 열린다.
            try:
                allowed = {e['name']: e['path'] for e in playback.list_logs()}
            except SystemExit as exc:
                return self._send(500, dumps_json({'error': str(exc)}), 'application/json')
            full = allowed.get(name)
            if not full:
                return self._send(404, '{"error":"그런 로그가 없다"}', 'application/json')
            threading.Thread(target=self.pb.open, args=(full,), daemon=True).start()
            return self._send(200, dumps_json({'ok': True, 'name': name}),
                              'application/json; charset=utf-8')

        if path == '/api/playback/close':
            self.pb.close()
            return self._send(200, '{"ok":true}', 'application/json')

        if path == '/api/playback/info':
            return self._send(200, dumps_json(self.pb.info()),
                              'application/json; charset=utf-8')

        if path == '/api/playback/series':
            # 차트용 전량 시계열. 재생은 되감기가 있으므로 폴마다 한 칸씩
            # 쌓는 라이브 방식으로는 뒤로 감을 때 그림이 사라진다 — 열 때
            # 한 번 통째로 받아 두고 커서만 옮긴다.
            body = self.pb.series()
            if body is None:
                return self._send(409, dumps_json(self.pb.info()),
                                  'application/json; charset=utf-8')
            return self._send(200, dumps_json(body),
                              'application/json; charset=utf-8')

        if path == '/api/playback/state':
            try:
                ts = float(_qs(query, 't') or 0.0)
            except ValueError:
                ts = 0.0
            snap = self.pb.at(ts)
            if snap is None:
                return self._send(409, dumps_json(self.pb.info()),
                                  'application/json; charset=utf-8')
            return self._send(200, dumps_json(snap),
                              'application/json; charset=utf-8')

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

        # ── 재생 ──────────────────────────────────────────────────
        # 기록된 .tlog 를 같은 화면에 흘린다. 프론트는 /api/state 하나만
        # 보므로, 서버가 State 를 과거 값으로 채우면 그림이 그대로 나온다.
        if path == '/api/recordings':
            body = dumps_json({'dir': os.path.abspath(self.rec_dir),
                               'items': list_recordings(self.rec_dir)})
            return self._send(200, body, 'application/json; charset=utf-8')

        if path.startswith('/api/play'):
            pl = self.st.player
            q = dict(kv.split('=', 1) for kv in query.split('&') if '=' in kv)
            act = path[len('/api/play'):].lstrip('/')
            try:
                if act == 'load':
                    name = unquote(q.get('name', ''))
                    # 🔴 경로 탈출 방지 — 파일명만 받는다.
                    if not name or '/' in name or '\\' in name or not name.endswith('.tlog'):
                        return self._send(400, '{"error":"이름이 이상하다"}',
                                          'application/json')
                    full = os.path.join(self.rec_dir, name)
                    if not os.path.isfile(full):
                        return self._send(404, '{"error":"없는 파일"}',
                                          'application/json')
                    info = pl.load(full)
                    return self._send(200, dumps_json({'ok': True, **info}),
                                      'application/json; charset=utf-8')
                if act == 'play':
                    pl.play()
                elif act == 'pause':
                    pl.pause()
                elif act == 'seek':
                    pl.seek(float(q.get('t', 0)))
                elif act == 'speed':
                    pl.set_speed(float(q.get('v', 1)))
                elif act == 'unload':
                    pl.unload()
                else:
                    return self._send(404, '{"error":"모르는 동작"}', 'application/json')
            except (ValueError, OSError) as e:
                return self._send(400, dumps_json({'error': str(e)}),
                                  'application/json; charset=utf-8')
            return self._send(200, dumps_json({'ok': True, 'play': pl.status()}),
                              'application/json; charset=utf-8')

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
    ap.add_argument('--rec-dir', default=LIVE_DIR,
                    help='실시간 기록(.tlog) 폴더. 기본은 리포의 logs/live/ '
                         '— 이 PC 안에만 쓴다')
    ap.add_argument('--no-record', action='store_true',
                    help='ARM 구간 .tlog 기록을 끈다 (기본은 켜짐)')
    args = ap.parse_args()

    st = State()
    st.rec = Recorder(args.rec_dir, enabled=not args.no_record)
    st.player = Player(st)

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
    Handler.rec_dir = os.path.abspath(args.rec_dir)
    Handler.pb = Playback()
    srv = ThreadingHTTPServer(('127.0.0.1', args.http), Handler)
    srv.daemon_threads = True

    print('MAVLink UDP  %s:%d  (읽기 전용 — FC 로 아무것도 안 보낸다)'
          % (args.bind, args.port))
    print('라이브 페이지  http://127.0.0.1:%d' % args.http)
    if st.rec.enabled:
        print('기록          %s  (ARM 마다 새 .tlog)' % os.path.abspath(args.rec_dir))
    else:
        print('기록          꺼짐 (--no-record)')
    print('멈추려면 Ctrl-C')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n종료')
    finally:
        # 🔴 Ctrl-C 로 죽어도 파일을 닫는다. 안 닫으면 마지막 몇 프레임이
        #    OS 버퍼에 남은 채 사라진다.
        with st.lock:
            st.rec._close()


if __name__ == '__main__':
    main()
