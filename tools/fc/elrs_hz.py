#!/usr/bin/env python3
"""ELRS 백팩 경로로 실제 무엇이 몇 Hz 로 오는지 센다. 읽기 전용.

백팩 AP(10.0.0.1:14555)가 보내는 것을 받으려면 우리가 먼저 한 번 찔러야 한다
(backpack_poke.py 가 1초마다 하는 일과 같다). 소켓은 새로 열고, FC 로는
아무것도 안 보낸다 — 백팩을 깨우는 UDP 만 나간다.
"""
import socket, sys, time, collections
from pymavlink import mavutil

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
BP = ('10.0.0.1', 14555)
# 🔴 백팩은 자기를 마지막으로 찌른 클라이언트에게 보낸다. 14550 을 받아야
#    하므로 shade-live 를 먼저 멈춰야 한다 — MEASURING.md 참조.
BIND = '10.0.0.100'

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((BIND, 14550))
s.settimeout(1.0)
print('로컬 포트 %d 에서 듣는다. 백팩을 깨운다...' % s.getsockname()[1], flush=True)

mav = mavutil.mavlink.MAVLink(None)
mav.robust_parsing = True

hb = mavutil.mavlink.MAVLink_heartbeat_message(
    mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0, 3)
mav.srcSystem, mav.srcComponent = 255, 190
poke = hb.pack(mav)

cnt = collections.Counter()
byts = collections.Counter()
first, last = {}, {}
gaps = collections.defaultdict(float)
total_b = 0
t0 = time.time()
next_poke = 0.0
bad = 0

while time.time() - t0 < SECS:
    now = time.time()
    if now >= next_poke:
        try:
            s.sendto(poke, BP)
        except Exception as e:
            print('poke 실패:', e)
        next_poke = now + 1.0
    try:
        data, addr = s.recvfrom(4096)
    except socket.timeout:
        continue
    total_b += len(data)
    try:
        msgs = mav.parse_buffer(data) or []
    except Exception:
        bad += 1
        continue
    for m in msgs:
        t = m.get_type()
        if t == 'BAD_DATA':
            bad += 1
            continue
        now2 = time.time()
        cnt[t] += 1
        byts[t] += len(m.get_msgbuf())
        if t in last:
            gaps[t] = max(gaps[t], now2 - last[t])
        else:
            first[t] = now2
        last[t] = now2

el = time.time() - t0
print()
print('=== ELRS 백팩 실측  %.1f초  (%s) ===' % (el, time.strftime('%H:%M:%S')))
print('총 %d 패킷 / %d B  →  %.0f B/s' % (sum(cnt.values()), total_b, total_b / el))
print('BAD_DATA %d' % bad)
print()
print('%-26s %6s %8s %8s %8s' % ('message', 'n', 'Hz', 'max gap', 'B/s'))
for t, n in cnt.most_common():
    print('%-26s %6d %8.2f %8.2f %8.0f'
          % (t, n, n / el, gaps[t], byts[t] / el))
