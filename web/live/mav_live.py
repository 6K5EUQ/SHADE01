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

받는 경로는 둘이다. **둘을 동시에 듣는다** — 갈아타는 데 재시작이 필요 없다:
  - ELRS 백팩   조종기 AP(10.0.0.1) → PC. TELEM1 경유
  - shade-bridge  FC USB → UDP 중계

둘 다 살아 있으면 **USB 를 쓴다** (`LINK_PRIORITY`). 28.4 KB/s 대 285 B/s 라
같은 화면이면 USB 쪽이 언제나 낫다. 우선 경로가 조용해지면
`LINK_FALLBACK_AFTER` 초 뒤 아래 경로가 이어받는다.

    ./mav_live.py --listen 14550 --listen 10.0.0.100:14550

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
import re
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

# 두 경로가 동시에 들어올 때 무엇을 화면에 쓸지 — 앞이 강하다.
# USB 직결/브리지가 28.4 KB/s 로 백팩(285 B/s)보다 두 자릿수 빠르고 자세
# 갱신도 촘촘해서, 둘 다 살아 있으면 USB 쪽이 언제나 더 나은 그림이다.
LINK_PRIORITY = ('USB', 'ELRS')

# 우선 경로가 이만큼 조용하면 아래 경로로 넘긴다. LINK_TIMEOUT 보다 짧게 잡는다
# — 링크가 죽었다고 화면에 뜨기 **전에** 살아 있는 쪽으로 갈아타야, 갈아타는
# 동안 계기가 빈다는 인상이 안 생긴다.
LINK_FALLBACK_AFTER = 2.0

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

# ── 야외 판정 ──────────────────────────────────────────────────────────
# 🔴 GPS 로 가른다 — 3D fix 이고 위성 6기 이상. 실내에서는 fix 가 2 이하로
#    머물거나 위성이 서너 개에서 멎으므로 자연히 걸러진다. `qgclog.py` 가
#    지난 로그를 실내로 판정하는 기준과 같은 성질이다.
REC_MIN_FIX = 3
REC_MIN_SATS = 6

# ── 남길 것을 고르는 기준 (2026-09-06) ────────────────────────────────
# 🔴 **일단 다 적고, 닫을 때 판정해서 지운다.** 예전에는 야외 판정을
#    통과해야 파일을 열었는데, 그러면 fix 가 늦게 잡힌 비행의 **앞부분이
#    통째로 없다** — 이륙 순간이 가장 보고 싶은 구간인데 그게 빠졌다.
#    지금은 arm 하면 무조건 적기 시작하고, 닫을 때 아래 둘을 본다:
#
#      1. 비행 중 한 번이라도 야외(fix≥3, 위성≥6)였나
#      2. 파일이 REC_MIN_KEEP_BYTES 이상인가
#
#    둘 다 맞아야 남는다. 하나라도 아니면 지운다 — 실내 벤치 arm 과
#    즉시 disarm 이 목록을 덮는 것을 막는 것이 원래 목적이고, 그 목적은
#    파일을 **안 여는 것**이 아니라 **안 남기는 것**으로 달성된다.
#    🔴 문턱은 **링크마다 다르다** (2026-09-09 실측으로 물렸다).
#    1MB 하나를 두 경로에 똑같이 걸었더니, 그 값이 "비행의 가치" 가 아니라
#    "링크 대역폭" 을 재고 있었다. 그날 야외 실비행 9편이 전부 버려졌다:
#
#      지상시험  22초  USB   1.17MB  → 남음
#      실비행   388초  ELRS  0.50MB  → 버려짐   ← 6.5분을 날고도
#
#    ELRS 백팩은 USB 의 1/5 도 안 되는 속도로 흐른다(실측 아래). 그래서
#    백팩으로 나간 비행은 **아무리 길어도 1MB 를 못 넘긴다** — 구조적으로
#    절대 안 남는 경로였다.
#
#    ELRS 실측 (2026-09-09 야외, 전부 fix≥3·위성≥6 통과):
#       92초 0.1MB · 124초 0.1MB · 136초 0.2MB
#      223초 0.3MB · 271초 0.3MB · 388초 0.5MB
#    같은 날 실내·미연결 ELRS 는 19~40초에 0.0MB 였다 — 백팩이 안 붙으면
#    바이트가 아예 안 쌓이므로, 낮은 문턱으로도 지상 arm 은 그대로 걸러진다.
#
#    야외 판정(fix≥3, 위성≥6)이 이미 실내를 막고 있으므로, 크기 문턱은
#    "링크가 실제로 흐르고 있었나" 만 보면 된다.
REC_MIN_KEEP_BYTES = {
    'FC':   1_000_000,    # USB 직결 — 1MB. 22초 지상시험이 1.17MB 다
    'ELRS': 50_000,       # 백팩 — 50KB. 실비행 최소가 92초 0.1MB 였다
}
REC_MIN_KEEP_DEFAULT = 1_000_000      # 모르는 경로는 보수적으로

# 오래된 기록은 지운다. 몇 달을 켜 두면 ARM 마다 파일이 생기는데 아무도 안
# 지운다 — git 에도 안 올라가니(.gitignore) 조용히 디스크만 먹는다.
# 정본은 shade01.bewe.co.kr 이고 이것은 이 PC 의 사본이므로 넉넉히 잡아도 된다.
REC_KEEP_DAYS = 90


def _outdoor(d):
    """지금 값이 야외인가. `State.d` 를 그대로 받는다."""
    fix = d.get('fix')
    sats = d.get('sats')
    if fix is None or sats is None:
        return False
    return fix >= REC_MIN_FIX and sats >= REC_MIN_SATS


class _Sink:
    """한 수신 경로의 파일 하나. 열고·쓰고·닫는 것만 안다."""

    def __init__(self, dirpath, kind):
        self.dir = dirpath
        self.kind = kind           # 'ELRS' | 'FC'
        self.f = None
        self.path = None
        self.started = None
        self.frames = 0
        self.bytes = 0
        self.error = None
        # 이 파일이 사는 동안 **한 번이라도** 야외 GPS 를 봤나. 닫을 때
        # 남길지 지울지의 판정 절반이다 (나머지 절반은 크기).
        self.outdoor = False

    def open(self, stamp):
        """stamp 는 이 **비행 세션**의 시작 시각 (time.time). 경로가 달라도
        같은 비행이면 같은 stamp 를 받아 파일명 앞부분이 같아진다 — 목록에서
        두 파일을 한 비행으로 묶는 근거가 이 이름이다."""
        try:
            os.makedirs(self.dir, exist_ok=True)
            # 파일명은 **KST 로컬시각**이다. `.ulg` 가 UTC 라 헷갈리는 것을
            # 문서가 반복해 경고하는데(PROCEDURE §1-3), 이 파일은 사람이
            # 고르라고 있는 것이므로 조종자의 시계에 맞춘다. 안이 UTC 인 것과
            # 무관하다 — 그래서 이름에 KST 를 박아 둔다.
            #
            # 🔴 뒤의 `_KST_<경로>` 두 토막이 규약이다. `list_recordings()` 가
            #    앞의 시각으로 비행을 묶고 뒤의 경로로 줄을 가른다.
            name = '%s_KST_%s.tlog' % (
                time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(stamp)), self.kind)
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

    def write(self, data):
        if self.f is None:
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
            self.close()

    def close(self):
        """닫고, 남길 값어치가 있으면 요약을 준다. 지웠거나 안 열렸으면 None.

        🔴 판정은 **여기서** 한다 — 적는 동안이 아니라. 그래야 fix 가 늦게
           잡힌 비행도 앞부분이 남는다 (REC_MIN_KEEP_BYTES 주석 참조).
        """
        if self.f is None:
            self.path = None
            return None
        try:
            self.f.close()
        except OSError:
            pass
        info = None
        path, dur = self.path, (time.time() - self.started if self.started else 0)
        if path:
            why = self._discard_reason()
            if why is None:
                info = {'name': os.path.basename(path), 'kind': self.kind,
                        'frames': self.frames, 'bytes': self.bytes,
                        'dur': round(dur, 1)}
                print('기록 종료  %s  (%d프레임 %.1fMB %.0f초)'
                      % (path, self.frames, self.bytes / 1e6, dur), flush=True)
            else:
                # 남길 값어치가 없다 — 지운다. 실패해도 트래킹은 계속돼야 하므로
                # 조용히 넘어가되, 왜 지웠는지는 반드시 찍는다.
                try:
                    os.remove(path)
                    print('기록 버림  %s  (%s — %.1fMB %.0f초)'
                          % (os.path.basename(path), why, self.bytes / 1e6, dur),
                          flush=True)
                except OSError as e:
                    print('기록 못 지움 %s: %s' % (path, e), file=sys.stderr, flush=True)
        self.f = self.path = self.started = None
        return info

    def _discard_reason(self):
        """버릴 이유. 남길 것이면 None."""
        if not self.outdoor:
            return '실내 — GPS 야외 판정을 한 번도 못 넘었다'
        # 문턱은 링크마다 다르다 — REC_MIN_KEEP_BYTES 주석 참조.
        floor = REC_MIN_KEEP_BYTES.get(self.kind, REC_MIN_KEEP_DEFAULT)
        if self.bytes < floor:
            return '%.2fMB < %.2fMB(%s)' % (self.bytes / 1e6, floor / 1e6, self.kind)
        return None


class Recorder:
    """야외 ARM 구간을 원시 MAVLink(.tlog)로 받아 적는다.

    QGC 표준 tlog 형식이다 — 프레임마다 **8바이트 빅엔디안 마이크로초 UTC**를
    앞에 붙인 것. 그래서 QGC 로 바로 열리고 pymavlink 로도 재파싱된다.

    🔴 읽기 전용 원칙은 그대로다. 이 클래스는 **디스크에만** 쓴다. 소켓으로
       나가는 바이트는 여전히 0 이다.

    왜 원시 바이트인가: 파싱에 실패한 프레임도 원본이 남는다. 화면에 안 나가는
    필드도 나중에 다시 뽑을 수 있다 — 무엇이 필요할지는 사고가 난 뒤에 안다.

    🔴 **수신 경로마다 파일을 따로 연다** (ELRS 백팩 / FC USB 브리지). 둘은
       대역폭도 갱신 주기도 다르고(실측: 백팩 285 B/s·자세 1.6Hz vs USB
       28.4 KB/s), 한 파일에 섞으면 어느 링크가 무엇을 놓쳤는지 못 가린다 —
       링크 비교가 이 기체의 반복 과제라 섞으면 안 된다.

       같은 비행의 파일들은 **같은 세션 시각**을 이름에 달고 나온다. 목록이
       그 시각으로 묶어 한 줄로 보여 준다.
    """

    def __init__(self, dirpath, enabled=True):
        self.dir = os.path.abspath(dirpath)
        self.enabled = enabled
        self.sinks = {}            # 'ELRS'|'FC' -> _Sink (열려 있는 것만)
        self.stamp = None          # 이 비행 세션의 시작 시각 (time.time)
        self.armed = False         # 기체가 지금 arm 인가
        self._closing_at = None    # disarm 후 닫을 시각 (monotonic)
        self.last = None           # 마지막으로 닫은 비행 (화면 표시용)
        self.error = None          # 디스크 문제를 화면에 드러낸다
        # arm 은 했는데 아직 야외가 아니라 못 적고 있는 상태. 화면에 드러낸다 —
        # "왜 안 찍히나" 를 조종자가 바로 알아야 한다.
        self.waiting = False

    # ── 세션 ──────────────────────────────────────────────────────
    def _closeall(self):
        infos = [s.close() for s in self.sinks.values()]
        infos = [i for i in infos if i]
        if infos:
            self.last = {'when': self.stamp, 'files': infos,
                         'dur': max(i['dur'] for i in infos)}
        self.sinks = {}
        self.stamp = None
        self._closing_at = None
        self.waiting = False

    def on_arm(self, armed):
        """armed 가 **바뀐** 순간에만 불린다."""
        if not self.enabled:
            return
        self.armed = armed
        if armed:
            self._closing_at = None       # 꼬리 대기 중에 다시 떴으면 이어 쓴다
            # 파일은 여기서 열지 않는다. 야외 판정을 통과한 첫 프레임에서
            # `write()` 가 연다 — arm 시점에 fix 가 아직 없을 수 있다.
        elif self.sinks:
            # 바로 닫지 않는다. REC_TAIL_S 동안 더 받아 적는다.
            self._closing_at = time.monotonic() + REC_TAIL_S
        else:
            self.waiting = False          # 못 적은 채 끝난 arm

    def write(self, data, kind, d):
        """수신한 UDP 페이로드 그대로. 락 밖에서 부르지 마라 (st.lock 안).

        kind 는 `_link_kind()` 결과('ELRS'/'USB'), d 는 지금 `State.d` 다.
        """
        if not self.enabled:
            return
        if self._closing_at is not None and time.monotonic() >= self._closing_at:
            self._closeall()
            return
        if not self.armed and self._closing_at is None:
            return
        # 파일명에 쓰는 이름. 'USB' 는 사람이 읽을 때 'FC' 가 분명하다 —
        # 그 경로는 FC 를 USB 로 직결한 브리지다.
        k = 'FC' if kind != 'ELRS' else 'ELRS'
        sink = self.sinks.get(k)
        if sink is None:
            # 꼬리 시간에 처음 보는 경로가 나타나면 새로 열지 않는다 —
            # disarm 뒤 10초짜리 조각 파일이 목록을 어지럽힌다.
            if self._closing_at is not None:
                return
            # 🔴 야외인지 **묻지 않고 연다.** 판정은 닫을 때 한다 — 그래야
            #    fix 가 늦게 잡힌 비행도 이륙 순간이 남는다.
            if self.stamp is None:
                self.stamp = time.time()
            sink = self.sinks[k] = _Sink(self.dir, k)
            sink.open(self.stamp)
            if sink.error:
                self.error = sink.error
        # 이 비행이 야외였다는 사실은 **한 번 참이면 계속 참**이다. 착륙 후
        # fix 를 잃어도 이미 야외 비행이었던 것은 변하지 않는다.
        if not sink.outdoor and _outdoor(d):
            sink.outdoor = True
        # 화면의 「실내대기」는 이제 "안 적는 중" 이 아니라 "적고는 있는데
        # 아직 야외를 못 봤다(=이대로 끝나면 버려진다)" 는 뜻이다.
        self.waiting = not any(sk.outdoor for sk in self.sinks.values())
        sink.write(data)
        if sink.error:
            self.error = sink.error

    def tick(self):
        """프레임이 안 들어와도 꼬리 시간이 지나면 닫아야 한다."""
        if self.sinks and self._closing_at is not None \
                and time.monotonic() >= self._closing_at:
            self._closeall()

    def _close(self):
        """종료 경로용. main() 이 Ctrl-C 에서 부른다."""
        self._closeall()

    def status(self):
        files = [{'kind': s.kind, 'name': os.path.basename(s.path) if s.path else None,
                  'frames': s.frames, 'bytes': s.bytes}
                 for s in self.sinks.values() if s.path]
        started = min((s.started for s in self.sinks.values() if s.started),
                      default=None)
        return {
            'on': self.enabled,
            'rec': bool(files),
            # 지금 적고 있는 경로들. 화면이 'ELRS+FC' 처럼 보여 준다.
            'kinds': sorted(f['kind'] for f in files),
            'files': files,
            'frames': sum(f['frames'] for f in files),
            'bytes': sum(f['bytes'] for f in files),
            'dur': round(time.time() - started, 1) if started else None,
            # arm 했는데 GPS 를 기다리는 중 — 화면이 "실내" 라고 말한다.
            'waiting': self.waiting,
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


# 파일명 규약: `YYYY-MM-DD_HH-MM-SS_KST_<경로>.tlog`. `_Sink.open()` 이 만든다.
# 경로가 없는 옛 파일(`..._KST.tlog`)도 읽는다 — 9/5 이전 기록이 그 이름이다.
_REC_NAME = re.compile(
    r'^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_KST(?:_(ELRS|FC))?\.tlog$')

# 같은 비행으로 묶는 시각 허용치(초). 두 경로의 첫 프레임이 정확히 같은 순간에
# 오지는 않는다 — 한 세션에서 같은 stamp 로 열므로 보통 0 이지만, 옛 파일과
# 서버 재시작을 건너뛰지 않으려면 여유가 필요하다.
#
# ⚠️ 너무 크게 잡으면 연달아 띄운 두 비행이 한 줄로 뭉친다. 이 기체는 배터리
#    교체에 수 분이 걸리므로 90초면 겹칠 일이 없다.
REC_GROUP_S = 90.0


def _rec_stamp(name):
    """파일명 → (epoch 초, 경로). 규약에서 벗어난 이름은 None."""
    m = _REC_NAME.match(name)
    if not m:
        return None
    date, hh, mm, ss, kind = m.groups()
    try:
        # 파일명은 KST 로컬시각이다 — 로컬 타임존으로 되돌린다.
        tm = time.strptime('%s %s:%s:%s' % (date, hh, mm, ss), '%Y-%m-%d %H:%M:%S')
        epoch = time.mktime(tm)
    except (ValueError, OverflowError):
        return None
    return epoch, (kind or 'FC')


def prune_recordings(dirpath, days=REC_KEEP_DAYS):
    """REC_KEEP_DAYS 보다 오래된 .tlog 를 지운다. 지운 개수를 돌려준다.

    🔴 실패해도 조용히 넘어간다 — 청소가 트래킹을 막으면 안 된다.
    """
    cutoff = time.time() - days * 86400
    n = 0
    try:
        names = os.listdir(dirpath)
    except OSError:
        return 0
    for name in names:
        if not name.endswith('.tlog'):
            continue
        path = os.path.join(dirpath, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                n += 1
        except OSError:
            pass
    if n:
        print('오래된 기록 %d개 지움 (%d일 지난 것)' % (n, days), flush=True)
    return n


def list_recordings(dirpath):
    """logs/live/ 의 .tlog 를 **비행 단위로 묶어** 돌려준다. 최신 먼저.

    한 비행에서 ELRS 백팩과 FC USB 브리지 양쪽으로 받으면 파일이 둘 나온다.
    둘은 같은 시각을 이름에 달고 열리므로(`_Sink.open()`), 시각이
    REC_GROUP_S 안이면 한 줄로 묶는다.

    반환: [{'when': epoch, 'label': '2026-09-05 09:24',
            'files': [{'name','kind','size','mtime'}, ...],
            'size': 합계, 'kinds': ['ELRS','FC']}, ...]
    """
    try:
        names = [n for n in os.listdir(dirpath) if n.endswith('.tlog')]
    except OSError:
        return []
    items = []
    for n in names:
        p = os.path.join(dirpath, n)
        try:
            stt = os.stat(p)
        except OSError:
            continue
        parsed = _rec_stamp(n)
        # 이름이 규약을 벗어나면 파일 mtime 을 시각으로 쓴다. 묶이지 않고
        # 혼자 한 줄이 되겠지만 **목록에서 사라지지는 않는다.**
        when, kind = parsed if parsed else (stt.st_mtime, 'FC')
        items.append({'name': n, 'kind': kind, 'size': stt.st_size,
                      'mtime': int(stt.st_mtime), 'when': when})

    items.sort(key=lambda x: x['when'], reverse=True)

    groups = []
    for it in items:
        g = groups[-1] if groups else None
        # 같은 경로가 이미 그 그룹에 있으면 다른 비행이다 — 한 비행에서 같은
        # 경로로 두 파일이 나오지 않는다. 안 가르면 연속 비행이 통째로 뭉친다.
        if g is not None and abs(g['when'] - it['when']) <= REC_GROUP_S \
                and not any(f['kind'] == it['kind'] for f in g['files']):
            g['files'].append(it)
            g['when'] = max(g['when'], it['when'])
        else:
            groups.append({'when': it['when'], 'files': [it]})

    out = []
    for g in groups:
        fs = sorted(g['files'], key=lambda f: f['kind'])
        out.append({
            'when': int(g['when']),
            'label': time.strftime('%Y-%m-%d %H:%M', time.localtime(g['when'])),
            'files': [{'name': f['name'], 'kind': f['kind'],
                       'size': f['size'], 'mtime': f['mtime']} for f in fs],
            'size': sum(f['size'] for f in fs),
            'kinds': [f['kind'] for f in fs],
        })
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
        self.src = None            # 화면에 반영 중인 경로의 마지막 (ip, port)
        self.sysid = None
        self.compid = None

        # 경로별 마지막 수신 시각(monotonic). 두 경로를 동시에 듣기 때문에
        # "지금 어느 쪽이 살아 있나" 를 링크 종류별로 따로 들고 있어야 한다.
        #   {'USB': monotonic, 'ELRS': monotonic}
        self.link_seen = {}

        # 조종자가 화면에서 고정한 경로. None 이면 자동(LINK_PRIORITY).
        self.pin = None

        self.rec = None            # Recorder. main() 이 꽂는다
        self.player = None         # Player. main() 이 꽂는다
        # 🔴 기록기가 보는 arm 상태는 d['armed'] 와 **따로** 둔다. 재생 중에는
        #    d 가 과거 프레임의 값으로 덮이므로, 그것을 기준으로 삼으면 실제
        #    기체가 arm 해도 파일이 안 갈린다.
        self._rec_armed = None
        # 🔴 기록기의 야외 판정이 보는 GPS 도 d 와 **따로** 둔다. 같은 이유다 —
        #    재생 중에는 d 의 fix/sats 가 로그의 값이라, 실내에서 arm 해도
        #    지난 비행의 위성 12기가 보여 파일이 열려 버린다.
        self.rec_gps = {}
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

    def touch(self, addr, nbytes, kind=None):
        # 수신 스레드만 쓰지만 snapshot() 이 락 안에서 읽으므로 여기서도 잠근다.
        with self.lock:
            now = time.monotonic()
            if kind:
                self.link_seen[kind] = now
            self.packets += 1
            self.bytes += nbytes
            # `seen`·`src` 는 **화면에 쓰는 경로**의 것이다. 아래 경로의 프레임까지
            # 여기 찍으면, 우선 경로가 죽었는데도 링크가 붙어 있는 것처럼 보인다.
            if kind is None or kind == self._active_locked(now):
                self.seen = now
                self.src = addr

    def _active_locked(self, now=None):
        """지금 화면에 쓸 경로. 락을 **이미 쥔 채** 부른다.

        LINK_PRIORITY 순서로 훑어 살아 있는 첫 경로를 고른다. 우선 경로가
        LINK_FALLBACK_AFTER 보다 오래 조용하면 다음 경로로 내려간다.

        조종자가 경로를 고정해 두었으면 그것을 먼저 따른다. USB 가 붙어 있으면
        ELRS 는 영영 화면에 안 나오는데, 정작 비행 중에 봐야 하는 것은 기체가
        실제로 쓰는 ELRS 쪽이다 — 그 링크로 무엇이 몇 Hz 로 오는지는 USB 로는
        볼 수 없다. 고정한 경로가 죽어 있어도 유지한다: 조용하다는 사실 자체가
        보려던 정보이고, 말없이 다른 경로로 넘어가면 그것을 못 본다.
        """
        now = time.monotonic() if now is None else now
        if self.pin in LINK_PRIORITY:
            return self.pin
        for kind in LINK_PRIORITY:
            t = self.link_seen.get(kind)
            if t is not None and now - t < LINK_FALLBACK_AFTER:
                return kind
        # 전부 조용하다 — 가장 최근에 말한 쪽을 유지한다. 화면 값이 어느 경로의
        # 마지막 값인지는 여전히 알려 줘야 한다.
        if not self.link_seen:
            return None
        return max(self.link_seen, key=self.link_seen.get)

    def active_link(self):
        with self.lock:
            return self._active_locked()

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
                'link': self._active_locked(),
                # 지금 붙어 있는 경로 전부. 둘 다 살아 있으면 둘 다 true 다 —
                # 화면은 `link` 를 쓰지만, 어느 쪽이 더 붙어 있는지 진단할 때
                # 이것을 본다.
                'links': {
                    k: round(time.monotonic() - t, 2)
                    for k, t in self.link_seen.items()
                },
                # 고정된 경로. None 이면 자동. 화면이 이 값으로 배지를 칠한다.
                'pin': self.pin,
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
        d['alt_src'] = 'gps'
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
        # 🔴 GLOBAL_POSITION_INT 가 오기 전까지의 자리표시다 — VFR_HUD.alt 는
        #    **기압 AMSL** 이지 홈 기준 상대고도가 아니다. 예전에는 첫 값만 잡고
        #    굳혔는데(`if 'alt' not in d`), GPS fix 가 없는 지상에서는 GPI 가
        #    영영 안 와서 뷰어마다 **자기가 켜진 순간의 기압고도**를 들고 있었다.
        #    실측 2026-09-06: rim3 54.56 / ku 120.56 → ku 재시작 뒤 58.85 —
        #    같은 FC, 같은 브리지, 값만 셋. 웹은 rim3 것을 그대로 받아 54.56.
        #    GPI 를 한 번이라도 본 뒤에는 건드리지 않는다.
        if d.get('alt_src') != 'gps':
            d['alt'] = msg.alt
            d['alt_src'] = 'baro'

    elif t == 'SYS_STATUS':
        d['volt'] = msg.voltage_battery / 1000.0 if msg.voltage_battery != 65535 else None
        d['cur'] = msg.current_battery / 100.0 if msg.current_battery != -1 else None
        # 🔴 잔량은 BATTERY_STATUS 가 이겨야 한다 — 아래 참조. 조건 없이 대입하던
        #    때는 두 메시지가 이 칸을 번갈아 덮어써서, 웹의 % 가 조종기 화면과
        #    어긋나 보였다. 조종기(ELRS)는 BATTERY_STATUS 만 읽는다.
        if d.get('batt_pct_src') != 'battery_status':
            d['batt_pct'] = msg.battery_remaining if msg.battery_remaining != -1 else None
            d['batt_pct_src'] = 'sys_status'
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
        # 잔량은 두 메시지가 다른 것을 센다. BATTERY_STATUS 는 PM08 인스턴스를
        # 그대로 보고하고(PX4 가 DroneCAN 노드 ID 124 를 배터리 id 로 쓴다),
        # SYS_STATUS 는 FC 가 고른 주 배터리 요약이라 값도 갱신 시점도 다르다.
        # 여기 값이 실측이고 PX4 의 SoC 융합(전류적산 + 전압)을 거친 것이라
        # 한 번이라도 오면 이쪽으로 굳힌다. 링크가 끊겨 SYS_STATUS 만 남아도
        # 마지막 값이 남지 낡은 소스로 되돌아가지는 않는다.
        if msg.battery_remaining != -1:
            d['batt_pct'] = msg.battery_remaining
            d['batt_pct_src'] = 'battery_status'
        if msg.current_consumed != -1:
            d['mah'] = msg.current_consumed
        # PM08 이 주는 배터리 온도. cdegC(1/100 도) 이고 32767 이 "모름" 이다.
        # ESC·모터 온도는 없다 — ESC 텔레메트리가 FC 로 안 올라온다(실측 ESC_STATUS 0회).
        if msg.temperature != 32767:
            d['batt_temp'] = round(msg.temperature / 100.0, 1)

    elif t == 'GPS_RAW_INT':
        d['fix'] = msg.fix_type
        d['sats'] = msg.satellites_visible
        # 기록기의 야외 판정용 사본. d 는 재생이 덮으므로 따로 둔다.
        st.rec_gps['fix'] = msg.fix_type
        st.rec_gps['sats'] = msg.satellites_visible
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


def _sniff_gps(msgs, st):
    """재생 중에도 **실기의** GPS 만 골라 `st.rec_gps` 를 갱신한다.

    재생 중에는 `handle()` 이 안 돌아 rec_gps 가 멎는다. 그 사이 실제로 arm
    하면 야외 판정이 옛 값(또는 빈 값)으로 굳어 기록이 안 열리거나 잘못 열린다.
    화면에는 아무것도 넣지 않는다 — 이 함수는 판정용 두 숫자만 만진다.
    """
    for m in msgs:
        if m.get_type() == 'GPS_RAW_INT':
            st.rec_gps['fix'] = m.fix_type
            st.rec_gps['sats'] = m.satellites_visible


def receiver(sock, st, alive=None):
    """UDP 수신 루프. 이 함수는 소켓에 쓰지 않는다.

    alive 가 주어지면 그것이 False 를 돌려주는 순간 루프를 끝낸다 — 백팩
    소켓처럼 도중에 은퇴하는 것을 위해서다.

    🔴 닫힌 소켓에서 `continue` 로 버티면 안 된다. 스레드가 소켓 객체를
       계속 붙들고 있어 **포트가 안 풀린다** — 다음에 같은 자리를 열려고 할
       때 EADDRINUSE 로 실패한다. AP 를 껐다 켰다 하면 두 번째부터 영영
       안 붙었다 (실측 2026-09-06, 200회 토글 시험에서 199회 실패).
    """
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
            if alive is not None and not alive():
                return
            if st.rec is not None:
                with st.lock:
                    st.rec.tick()
            continue
        except OSError:
            # 소켓이 닫혔다(은퇴) — 스레드도 같이 끝난다. 그래야 fd 가 풀린다.
            return
        if not data:
            continue
        kind = _link_kind(addr)
        st.touch(addr, len(data), kind)

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
            # 🔴 두 경로를 동시에 듣는다. 화면(`st.d`)에 쓰는 것은 **우선 경로
            #    하나뿐**이다 — 둘의 프레임을 같은 d 에 섞으면 갱신 주기가 다른
            #    두 링크가 서로 덮어써 고도·자세가 튄다 (백팩 1.6Hz vs USB 수십Hz).
            #    아래 경로의 프레임도 버리지는 않는다: 기록기가 경로별로 따로
            #    적고(`_ELRS`/`_FC`), link_seen 도 이미 찍혔으므로 우선 경로가
            #    죽는 순간 곧바로 이어받는다.
            passive = kind is not None and kind != st._active_locked()
            if not replaying and not passive:
                for m in msgs:
                    if m.get_type() == 'BAD_DATA':
                        continue
                    try:
                        handle(m, st)
                    except Exception:
                        pass      # 한 메시지가 이상해도 수집은 계속돼야 한다
            else:
                # 화면에는 안 넣더라도 arm 전환은 봐야 기록 파일이 갈린다.
                # 재생 중이든 아래 경로든 마찬가지다.
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
            #
            # 🔴 야외 판정은 `st.rec_gps` 로 한다 — `st.d` 가 아니다. 재생 중에는
            #    d 가 과거 프레임의 GPS 로 덮이므로, 지난 비행을 돌려 보는 동안
            #    실내 arm 이 야외로 오인돼 파일이 열린다. rec_gps 는 실기 프레임만
            #    본다 (`handle()` 이 재생 경로에서는 안 돌고, 아래가 원본 바이트를
            #    따로 훑기 때문이다).
            if st.rec is not None:
                # 아래 경로의 프레임도 야외 판정 GPS 는 스스로 챙겨야 한다 —
                # handle() 을 안 거쳤으므로 rec_gps 가 안 채워진다.
                if replaying or passive:
                    _sniff_gps(msgs, st)
                st.rec.write(data, kind, st.rec_gps)


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
        self.note = None          # 「받는 중」처럼 지금 무엇을 하는지

    def begin(self, name, note=None):
        """열기를 시작했다고 표시한다. **파일을 받기 전에** 부른다.

        labserver 에서 내려받는 동안에도 화면이 「여는 중」을 보여야 한다 —
        안 그러면 큰 로그를 받는 수십 초 동안 아무 일도 안 일어난 것처럼 보인다.
        """
        with self.lock:
            self.loading = name
            self.note = note
            self.err = None
            self.fl = None

    def fail(self, msg):
        """열기 실패. 내려받기가 깨졌을 때 호출자가 부른다."""
        with self.lock:
            self.err = msg
            self.loading = None
            self.note = None

    def open(self, path):
        """로그를 연다. 오래 걸리므로(대형 로그 수십 초) 호출자가 스레드로 돌린다."""
        import playback
        with self.lock:
            self.loading = os.path.basename(path)
            self.note = None
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
            self.note = None

    def info(self):
        """지금 무엇이 열려 있나. 프레임은 빼고 요약만."""
        with self.lock:
            if self.loading:
                return {'state': 'loading', 'name': self.loading,
                        'note': self.note}
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
                                    'cur', 'volt', 'vib', 'sats', 'eph',
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
                # 화면의 `vib` 채널은 축별 최대값이다 (pushSample 과 같은 식).
                vb = d.get('vibe')
                cols['vib'].append(max(vb) if vb else None)
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

        # 화면에 쓸 수신 경로를 고정한다. FC 로 나가는 바이트는 여전히 0 이다 —
        # 이미 듣고 있는 두 스트림 중 무엇을 그릴지만 고른다.
        if path == '/api/link':
            want = _qs(query, 'pin')
            if want in ('auto', ''):
                self.st.pin = None
            elif want in LINK_PRIORITY:
                self.st.pin = want
            else:
                return self._send(400, dumps_json(
                    {'error': 'pin 은 %s 또는 auto 여야 한다'
                              % ' / '.join(LINK_PRIORITY)}),
                    'application/json; charset=utf-8')
            return self._send(200, dumps_json(
                {'pin': self.st.pin, 'link': self.st.active_link()}),
                'application/json; charset=utf-8')

        # ── 로그 재생 ──────────────────────────────────────────────
        # 🔴 전부 GET 이다. POST 를 열지 않는다 — "HTTP 는 do_GET 만 있다" 가
        #    이 서버의 읽기 전용 보장 중 하나다 (README 「상행이 없다」).
        #    재생은 로컬 파일을 읽을 뿐 FC 와 아무 관계가 없지만, 보장을
        #    깨뜨리지 않는 편이 검증하기 쉽다.
        if path == '/api/logs':
            # 🔴 목록의 정본은 **labserver** 다. 이 PC 의 logs/ 는 작업 사본이라
            #    여기에만 있는 로그가 생기면 그 PC 가 죽을 때 사라진다 —
            #    gram 에만 있던 20개를 9/6 에 발견했다. 재생할 때 그 파일
            #    하나만 받아 온다 (logsource.ensure_local).
            import logsource
            try:
                c = logsource.catalog(force=_qs(query, 'refresh') == '1')
            except Exception as exc:
                return self._send(200, dumps_json({'logs': [], 'error': str(exc)}),
                                  'application/json; charset=utf-8')
            return self._send(200, dumps_json(
                {'logs': c['items'], 'source': c['source'],
                 'remote': c['remote'], 'error': c['error']}),
                'application/json; charset=utf-8')

        if path == '/api/playback/open':
            name = _qs(query, 'name')
            if not name:
                return self._send(400, '{"error":"name 이 없다"}', 'application/json')
            import logsource
            # 🔴 목록에 있는 파일만 연다. 이름을 그대로 경로로 쓰면
            #    ?name=../../etc/passwd 로 아무 파일이나 열린다.
            try:
                allowed = {e['name'] for e in logsource.catalog()['items']}
            except Exception as exc:
                return self._send(500, dumps_json({'error': str(exc)}), 'application/json')
            if name not in allowed:
                return self._send(404, '{"error":"그런 로그가 없다"}', 'application/json')

            # 이 PC 에 없으면 labserver 에서 받아 온다. 큰 로그는 수십 초 걸리므로
            # 굽는 것과 함께 **딴 스레드**에서 한다 — 프론트는 /api/playback/info
            # 를 폴하며 기다린다 (state='opening').
            self.pb.begin(name, 'labserver 에서 받는 중')

            def _open():
                try:
                    full = logsource.ensure_local(name)
                except Exception as exc:
                    self.pb.fail(str(exc))
                    return
                self.pb.open(full)
            threading.Thread(target=_open, daemon=True).start()
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

        # ⚠️ `/api/play` 로 시작만 보면 **`/api/playback/*` 까지 삼킨다.**
        #    ulg 재생(위 /api/playback/…)과 tlog 재생이 한 서버에 같이 살므로
        #    접두사를 `/api/play/` 로 못박는다. 위 라우트가 먼저라 지금도
        #    동작은 하지만, 순서에 기대는 코드는 다음 편집에서 깨진다.
        if path == '/api/play' or path.startswith('/api/play/'):
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


def parse_listen(spec, default_port):
    """'10.0.0.100:14550' · ':14551' · '14551' → (주소, 포트)."""
    spec = spec.strip()
    if not spec:
        raise ValueError('빈 값')
    if ':' in spec:
        host, _, port = spec.rpartition(':')
        host = host or '0.0.0.0'
    else:
        # 숫자뿐이면 포트, 아니면 주소.
        if spec.isdigit():
            host, port = '0.0.0.0', spec
        else:
            host, port = spec, str(default_port)
    try:
        port = int(port)
    except ValueError:
        raise ValueError('포트가 숫자가 아니다: %r' % port)
    if not 1 <= port <= 65535:
        raise ValueError('포트 범위를 벗어났다: %d' % port)
    return (host, port)


def bind_udp(addr, port):
    """UDP 소켓 하나를 연다. 못 열면 이유를 말하고 None.

    🔴 SO_REUSEADDR 을 켜지 않는다 — mav_bridge.py 와 같은 이유다. 조용히
       포트를 나눠 가지면 커널이 패킷을 한쪽에만 주어, QGC 와 이 페이지가
       프레임을 서로 훔쳐 간다.

    여기서 죽지 않고 None 을 돌려주는 이유: 경로를 여럿 듣기 때문이다. 백팩
    AP 를 떠나면 10.0.0.x 가 사라져 EADDRNOTAVAIL 이 나는데(실측 rim3
    2026-09-05), 그것 때문에 브리지 경로까지 같이 잃으면 안 된다. 하나도
    못 열었을 때만 main() 이 죽는다.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((addr, port))
    except OSError as e:
        sock.close()
        if e.errno == errno.EADDRNOTAVAIL:
            print('%s:%d — 그 주소가 이 PC 에 없다 (AP 를 떠났나?). 건너뛴다'
                  % (addr, port), flush=True)
        elif e.errno == errno.EADDRINUSE:
            print('%s:%d — 이미 누가 쓰고 있다. 건너뛴다' % (addr, port), flush=True)
        else:
            print('%s:%d — 못 연다 (%s). 건너뛴다' % (addr, port, e), flush=True)
        return None
    return sock


# ── 백팩 자동 감지 ────────────────────────────────────────────────────
# 백팩 AP 는 켜졌다 꺼졌다 한다. 그때마다 `./qgc live on` 을 치게 하지 않으려면
# **트래커가 스스로** 붙었는지 보고 소켓을 열고 닫아야 한다.
BACKPACK_IP = os.environ.get('BACKPACK_IP', '10.0.0.1')
BACKPACK_NET = '10.0.0.'          # 이 대역의 주소가 생기면 AP 에 붙은 것이다
WATCH_SEC = 3.0                   # 감시 주기


def _local_backpack_addr():
    """이 PC 에 붙은 백팩 대역(10.0.0.x) 주소. 없으면 None.

    소켓 하나로 물어본다 — `ip` 를 부르지 않는 이유는 3초마다 프로세스를
    띄우고 싶지 않아서다. UDP connect() 는 패킷을 안 보낸다(라우팅만 본다).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((BACKPACK_IP, 9))
        ip = s.getsockname()[0]
        return ip if ip.startswith(BACKPACK_NET) else None
    except OSError:
        return None
    finally:
        s.close()


def _backpack_send_port(host, default=14550):
    """백팩이 **보내는** 포트. 우리가 들어야 할 쪽이다.

    GET /mavlink → {"ports":{"listen":14555,"send":14550}, ...}
    """
    try:
        import json as _json
        import urllib.request
        with urllib.request.urlopen('http://%s/mavlink' % host, timeout=3) as r:
            return int(_json.loads(r.read().decode())['ports']['send'])
    except Exception:
        return default


class Listeners:
    """열려 있는 UDP 소켓들을 관리한다. 백팩은 붙고 떨어지는 대로 따라간다.

    🔴 이 클래스가 있는 이유: 예전에는 소켓을 시작할 때 한 번만 열었다. 그래서
       백팩 AP 에 나중에 붙으면 `./qgc live on` 을 다시 쳐야 했고, 안 치면
       조용했다. 이제 감시 스레드가 3초마다 보고 알아서 연다/닫는다.

    🔴 **여는 데 실패해도 절대 죽지 않는다.** 유닛에 StartLimitBurst=3/60s 가
       걸려 있어서, 프로세스가 죽고 되살아나기를 1분에 세 번 하면 systemd 가
       영영 포기한다 — WiFi 를 껐다 켰다 하는 운용에서 언젠가 반드시 밟는다.
       그래서 실패는 다음 주기에 다시 시도할 뿐이다.
    """

    def __init__(self, st, fixed):
        self.st = st
        self.fixed = list(fixed)      # [(addr, port)] — 항상 열어 두려는 것
        self.socks = {}               # (addr, port) -> socket
        self.threads = {}             # (addr, port) -> 그 소켓의 수신 스레드
        self.lock = threading.Lock()
        self.bp_key = None            # 지금 열려 있는 백팩 소켓의 (addr, port)

    def _open(self, addr, port):
        if (addr, port) in self.socks:
            return True
        sock = bind_udp(addr, port)
        if sock is None:
            return False
        self.socks[(addr, port)] = sock
        th = threading.Thread(target=receiver, args=(sock, self.st), daemon=True)
        self.threads[(addr, port)] = th
        th.start()
        return True

    def _close(self, key):
        sock = self.socks.pop(key, None)
        th = self.threads.pop(key, None)
        if sock is None:
            return
        # 소켓을 닫으면 그 수신 스레드의 recvfrom 이 OSError 로 끝난다.
        try:
            sock.close()
        except OSError:
            pass
        # 🔴 스레드가 끝날 때까지 기다린다. 안 기다리면 그 스레드가 소켓
        #    객체를 붙들고 있는 동안 **포트가 안 풀려서**, 같은 자리를 다시
        #    열 때 EADDRINUSE 로 실패한다 — AP 를 두 번째 켤 때부터 영영
        #    안 붙는다 (실측 2026-09-06: 200회 토글 중 199회 실패).
        #    recvfrom 타임아웃이 1초라 그보다 넉넉히 준다.
        if th is not None and th.is_alive():
            th.join(timeout=2.5)
            if th.is_alive():
                print('경고: %s:%d 수신 스레드가 안 끝났다' % key,
                      file=sys.stderr, flush=True)
        print('닫음  %s:%d (백팩 AP 를 떠났다)' % key, flush=True)

    def start(self):
        """고정 소켓을 연다. 하나도 못 열면 False — main() 이 그때만 죽는다."""
        with self.lock:
            for addr, port in self.fixed:
                self._open(addr, port)
            return bool(self.socks)

    def _tick(self):
        addr = _local_backpack_addr()
        with self.lock:
            # 고정 소켓 중 아직 못 연 것이 있으면 계속 시도한다 — 부팅 때
            # 브리지보다 먼저 떠서 포트를 놓쳤을 수 있다.
            for a, p in self.fixed:
                if (a, p) not in self.socks:
                    self._open(a, p)

            if addr is None:
                # AP 를 떠났다. 백팩 소켓은 주소가 사라졌으므로 닫는다.
                if self.bp_key is not None:
                    self._close(self.bp_key)
                    self.bp_key = None
                return

            # AP 에 붙어 있다. 이미 맞는 소켓이 열려 있으면 할 일이 없다.
            if self.bp_key is not None and self.bp_key[0] == addr:
                return
            if self.bp_key is not None:
                self._close(self.bp_key)      # 주소가 바뀌었다 (재접속)
                self.bp_key = None

        # 포트를 묻는 동안은 락을 놓는다 — HTTP 3초 타임아웃이 걸릴 수 있다.
        port = _backpack_send_port(BACKPACK_IP)
        with self.lock:
            if self.bp_key is not None:
                return
            # 고정 소켓이 이미 그 자리를 쥐고 있으면 새로 열 필요가 없다.
            if (addr, port) in self.socks:
                return
            if self._open(addr, port):
                self.bp_key = (addr, port)
                print('열림  %s:%d (백팩 AP 에 붙었다)' % (addr, port), flush=True)

    def run(self):
        last_prune = time.monotonic()
        while True:
            try:
                self._tick()
                # 하루에 한 번 오래된 기록을 치운다. 몇 달 켜 두는 것이
                # 전제이므로 시작할 때 한 번으로는 부족하다.
                if time.monotonic() - last_prune > 86400:
                    last_prune = time.monotonic()
                    if self.st.rec is not None and self.st.rec.enabled:
                        prune_recordings(self.st.rec.dir)
            except Exception as e:
                # 🔴 어떤 예외도 이 스레드를 끝내면 안 된다. 끝나면 그 뒤로
                #    백팩이 영영 안 잡히는데, 아무도 눈치채지 못한다.
                print('리스너 감시 오류(계속한다): %s' % e, file=sys.stderr, flush=True)
            time.sleep(WATCH_SEC)


def main():
    ap = argparse.ArgumentParser(description='MAVLink 실시간 트래킹 (읽기 전용)')
    ap.add_argument('--port', type=int, default=int(os.environ.get('LIVE_UDP', '14550')),
                    help='MAVLink UDP 리슨 포트 (기본 14550)')
    ap.add_argument('--http', type=int, default=int(os.environ.get('LIVE_HTTP', '4400')),
                    help='웹 페이지 포트 (기본 4400)')
    ap.add_argument('--bind', default='0.0.0.0',
                    help='UDP 바인딩 주소. 기본은 전부 — 백팩(10.0.0.x)과 '
                         '브리지(tailscale)가 서로 다른 인터페이스로 들어오기 때문이다')
    ap.add_argument('--listen', action='append', metavar='[주소:]포트',
                    default=[x for x in os.environ.get('LIVE_LISTEN', '').split(',') if x.strip()],
                    help='들을 곳. 여러 번 줄 수 있다 — 두 경로를 **동시에** 듣고 '
                         '살아 있는 쪽을 쓴다 (USB 우선). 예: '
                         "--listen 14550 --listen 10.0.0.100:14550. "
                         '주면 --bind/--port 대신 이것을 쓴다')
    ap.add_argument('--rec-dir', default=LIVE_DIR,
                    help='실시간 기록(.tlog) 폴더. 기본은 리포의 logs/live/ '
                         '— 이 PC 안에만 쓴다')
    ap.add_argument('--no-record', action='store_true',
                    help='ARM 구간 .tlog 기록을 끈다 (기본은 켜짐)')
    args = ap.parse_args()

    st = State()
    st.rec = Recorder(args.rec_dir, enabled=not args.no_record)
    st.player = Player(st)
    if st.rec.enabled:
        prune_recordings(st.rec.dir)

    # 들을 곳을 정한다. --listen 이 있으면 그대로, 없으면 --bind/--port 하나.
    wanted = []
    for spec in (args.listen or []):
        try:
            wanted.append(parse_listen(spec, args.port))
        except ValueError as e:
            print('--listen %s: %s' % (spec, e), file=sys.stderr)
            sys.exit(2)
    if not wanted:
        wanted = [(args.bind, args.port)]
    # 같은 (주소, 포트) 를 두 번 열지 않는다 — 두 번째가 EADDRINUSE 로 죽는다.
    wanted = list(dict.fromkeys(wanted))

    lst = Listeners(st, wanted)
    # 🔴 고정 소켓이 하나라도 열렸으면 산다. 백팩은 감시 스레드가 나중에
    #    열어 주므로, 지금 AP 에 안 붙어 있다고 죽을 이유가 없다.
    if not lst.start():
        print('들을 수 있는 UDP 소켓이 하나도 없다:', file=sys.stderr)
        for addr, port in wanted:
            print('  %s:%d' % (addr, port), file=sys.stderr)
        print('이미 QGC 나 브리지가 쓰고 있다. 확인:  ss -ulnp | grep 1455',
              file=sys.stderr)
        print('다른 포트로 비켜라:  --port 14551', file=sys.stderr)
        sys.exit(1)

    socks = [(sk, a, p) for (a, p), sk in lst.socks.items()]
    threading.Thread(target=lst.run, daemon=True).start()

    Handler.st = st
    Handler.rec_dir = os.path.abspath(args.rec_dir)
    Handler.pb = Playback()
    srv = ThreadingHTTPServer(('127.0.0.1', args.http), Handler)
    srv.daemon_threads = True

    for i, (_, addr, port) in enumerate(socks):
        label = 'MAVLink UDP ' if i == 0 else '            '
        print('%s %s:%-6d %s' % (label, addr, port,
                                 '(읽기 전용 — FC 로 아무것도 안 보낸다)'
                                 if i == 0 else ''))
    print('             백팩 AP 는 붙는 대로 알아서 연다 (%.0f초마다 확인)'
          % WATCH_SEC)
    print('             둘 다 들어오면 %s 를 쓴다' % LINK_PRIORITY[0])
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
