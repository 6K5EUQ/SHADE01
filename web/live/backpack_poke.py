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

# AP 가 없을 때 "올라왔나" 를 다시 묻는 간격.
ASK_RETRY_SEC = 3.0


def _ap_up(host):
    """백팩 AP 에 붙어 있나 — 그 대역 주소가 이 PC 에 있으면 그렇다.

    ping 을 안 쓰는 이유: 3초마다 프로세스를 띄우고 싶지 않고, UDP
    connect() 는 패킷을 안 보내면서 라우팅만 확인해 준다.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 9))
        return s.getsockname()[0].startswith('10.0.0.')
    except OSError:
        return False
    finally:
        s.close()


BACKPACK_HOST = os.environ.get('BACKPACK_IP', '10.0.0.1')


def _ask_listen_port(host, default=14555):
    """백팩에게 '너는 어느 포트로 듣냐' 고 직접 묻는다.

    GET /mavlink → {"ports":{"listen":14555,"send":14550}, ...}
    실패하면 ELRS 기본값 14555.
    """
    try:
        import json as _json
        import urllib.request
        with urllib.request.urlopen('http://%s/mavlink' % host, timeout=3) as r:
            return int(_json.loads(r.read().decode())['ports']['listen'])
    except Exception:
        return default


def parse_hostport(s, default_port):
    if ':' in s:
        h, _, p = s.rpartition(':')
        return (h, int(p))
    return (s, default_port)


def main():
    ap = argparse.ArgumentParser(description='ELRS 백팩 깨우기 (빈 하트비트만 보낸다)')
    ap.add_argument('--backpack', default=os.environ.get('BACKPACK', ''),
                    help='백팩 주소. 비우면 /mavlink 에 물어본다 '
                         '(기본 10.0.0.1:<listen 포트>)')
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

    # 🔴 백팩에 **말을 걸 포트**는 /mavlink 의 `listen` 이다 (`send` 가 아니다).
    #    send=14550 은 백팩이 우리에게 **보내는** 포트고, listen=14555 가
    #    백팩이 **듣는** 포트다. 여기를 헷갈리면 하트비트가 아무도 안 읽는
    #    포트로 가고, 백팩은 GCS 주소를 영영 못 배운다 —
    #    /mavlink 의 ip.gcs 가 "IP UNSET" 인 채로 남는다 (실측 rim3 2026-09-05:
    #    백팩은 93패킷/12초를 만들고 있는데 보낼 곳을 몰라 버리고 있었다).
    # 🔴 포트를 **시작할 때 한 번만** 정하면 안 된다. AP 가 꺼져 있는 동안
    #    켜 두면 _ask_listen_port() 가 실패해 기본값으로 굳고, 나중에 AP 가
    #    올라와도 틀린 포트로 계속 쏜다. 아래 루프가 AP 가 돌아올 때마다
    #    다시 묻는다 (실측 rim3 2026-09-06).
    fixed_bp = parse_hostport(args.backpack, 14555) if args.backpack else None
    bp = fixed_bp                       # None 이면 아직 모른다 — 루프가 정한다
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

    if bp:
        print('백팩 %s:%d 를 깨운다 → 받은 것은 %s:%d 로 넘긴다'
              % (bp[0], bp[1], to[0], to[1]), flush=True)
    else:
        print('백팩 %s 가 올라오기를 기다린다 → 받은 것은 %s:%d 로 넘긴다'
              % (BACKPACK_HOST, to[0], to[1]), flush=True)
    print('보내는 것은 빈 하트비트뿐이다 (명령 아님). Ctrl-C 로 종료.', flush=True)

    last_poke = 0.0
    last_rx = time.monotonic()
    warned = False
    total = 0
    last_ask = 0.0

    while True:
        now = time.monotonic()

        # 포트를 아직 모르면(또는 AP 가 돌아왔으면) 다시 묻는다.
        # 고정 지정(--backpack)이 있으면 그것을 존중하고 안 묻는다.
        if fixed_bp is None and bp is None and now - last_ask >= ASK_RETRY_SEC:
            last_ask = now
            if _ap_up(BACKPACK_HOST):
                bp = (BACKPACK_HOST, _ask_listen_port(BACKPACK_HOST))
                print('백팩 올라왔다 — %s:%d 로 깨운다' % bp, flush=True)
                warned = False

        if bp is not None and now - last_poke >= POKE_SEC:
            last_poke = now
            try:
                sock.sendto(HEARTBEAT, bp)
            except OSError as e:
                # 백팩 AP 에서 떨어지면 여기서 난다. 죽지 않고 계속 시도한다 —
                # WiFi 가 돌아오면 저절로 복구된다.
                if not warned:
                    print('백팩에 못 보낸다 (%s) — AP 를 다시 기다린다' % e, flush=True)
                    warned = True
                # 포트를 다시 묻게 만든다. AP 가 바뀌었을 수도 있다.
                if fixed_bp is None:
                    bp = None

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
