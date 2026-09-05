#!/usr/bin/env python3
"""ELRS 백팩을 깨워 텔레메트리를 흐르게 한다.

백팩(10.0.0.1:14550)은 **먼저 말을 걸어온 곳에만** 텔레메트리를 보낸다.
QGC 의 백팩 링크가 `host0=10.0.0.1` 로 잡혀 있는 이유가 이것이다 —
QGC 는 자기가 먼저 쏘고, 그 응답을 받는다.

라이브 트래커(mav_live.py)는 **읽기 전용이라 소켓에 쓰지 않는다.** 그래서
혼자서는 백팩을 못 깨운다. 그 한 가지 일만 여기서 한다:

    [백팩 10.0.0.1:14550] ←빈 HEARTBEAT─ [이 스크립트]
                          ─텔레메트리→   [이 스크립트] ─그대로→ [트래커 UDP]

🔴 FC 로 나가는 것은 **빈 하트비트뿐이다.** 명령이 아니다 — MAV_TYPE_GCS /
   MAV_STATE_UNINIT 로, ARM·모드변경·파라미터 어느 것도 아니다. 받은 것은
   해석하지 않고 트래커에게 그대로 넘긴다 (해석은 트래커가 한다).

   트래커 본체에 sendto() 를 넣지 않은 이유가 이 분리다. 트래커는 여전히
   "소켓에 쓰는 코드가 한 줄도 없다" 를 유지한다.

    ./backpack_poke.py                    # 10.0.0.1:14550 → 127.0.0.1:14550
    ./backpack_poke.py --to 127.0.0.1:14552
"""

import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

try:
    from pymavlink.dialects.v20 import common as mavlink2
except ImportError:
    sys.exit("pymavlink 이 없다. .venv/bin/python 으로 돌려라.")

# 백팩이 조용해지지 않게 이 간격으로 계속 깨운다. QGC 도 하트비트를 1Hz 로 낸다.
POKE_SEC = 1.0

# 이 시간 동안 아무것도 안 오면 백팩이 없는 것으로 보고 조용히 계속 시도한다.
QUIET_WARN = 10.0


def parse_hostport(s, default_port):
    if ':' in s:
        h, _, p = s.rpartition(':')
        return (h, int(p))
    return (s, default_port)


def main():
    ap = argparse.ArgumentParser(description='ELRS 백팩 깨우기 (빈 하트비트만 보낸다)')
    ap.add_argument('--backpack', default=os.environ.get('BACKPACK', '10.0.0.1:14550'),
                    help='백팩 주소 (기본 10.0.0.1:14550)')
    # 🔴 기본값은 트래커가 실제로 듣는 포트를 따라간다. 여기만 14550 으로
    #    박아 두면 14551 로 비켜 앉은 PC(rim3·rim)에서는 poker 가 아무도 안
    #    듣는 포트로 부어 넣어 패킷 0 이 된다 — 유닛이 EnvironmentFile 로
    #    LIVE_UDP 를 이미 들고 있으므로 그것을 쓴다.
    ap.add_argument('--to',
                    default=os.environ.get(
                        'POKE_TO',
                        '127.0.0.1:' + os.environ.get('LIVE_UDP', '14550')),
                    help='받은 텔레메트리를 넘길 곳 = 트래커 '
                         '(기본 127.0.0.1:$LIVE_UDP, 없으면 14550)')
    args = ap.parse_args()

    bp = parse_hostport(args.backpack, 14550)
    to = parse_hostport(args.to, 14550)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.2)

    # 빈 하트비트 한 벌을 미리 만들어 둔다. 매번 새로 만들 이유가 없다.
    # MAV_TYPE_GCS + MAV_STATE_UNINIT = "나는 지상국이고 아무 상태도 주장하지
    # 않는다". FC 는 이것으로 아무 동작도 하지 않는다.
    buf = []

    class _Out:
        def write(self, b):
            buf.append(b)

    mav = mavlink2.MAVLink(_Out(), srcSystem=255, srcComponent=190)
    mav.heartbeat_send(mavlink2.MAV_TYPE_GCS, mavlink2.MAV_AUTOPILOT_INVALID,
                       0, 0, mavlink2.MAV_STATE_UNINIT)
    HEARTBEAT = b''.join(buf)

    print('백팩 %s:%d 를 깨운다 → 받은 것은 %s:%d 로 넘긴다'
          % (bp[0], bp[1], to[0], to[1]), flush=True)
    print('보내는 것은 빈 하트비트뿐이다 (명령 아님). Ctrl-C 로 종료.', flush=True)

    last_poke = 0.0
    last_rx = time.monotonic()
    warned = False
    total = 0

    while True:
        now = time.monotonic()
        if now - last_poke >= POKE_SEC:
            last_poke = now
            try:
                sock.sendto(HEARTBEAT, bp)
            except OSError as e:
                # 백팩 AP 에서 떨어지면 여기서 난다. 죽지 않고 계속 시도한다 —
                # WiFi 가 돌아오면 저절로 복구된다.
                if not warned:
                    print('백팩에 못 보낸다 (%s) — 계속 시도한다' % e, flush=True)
                    warned = True

        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            data = None
        except OSError:
            data = None

        if data:
            last_rx = now
            total += len(data)
            if warned:
                print('백팩 응답 복구', flush=True)
                warned = False
            try:
                sock.sendto(data, to)          # 해석하지 않고 그대로 넘긴다
            except OSError:
                pass
        elif now - last_rx > QUIET_WARN and not warned:
            print('%.0f초째 백팩 응답 없음 — AP 에 붙어 있나? (nmcli con show --active)'
                  % (now - last_rx), flush=True)
            warned = True


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n종료')
