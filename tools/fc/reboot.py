#!/usr/bin/env python3
"""FC 재부팅 — extras.txt 는 부팅 때만 읽힌다. DISARM 확인 후에만 보낸다."""
import sys, time
from pymavlink import mavutil
from fcport import NO_PORT, find_port, wait_fc_heartbeat

# 🔴 ttyACM0 을 박지 마라 — 다른 기체 FC 가 꽂혀 있으면 그것이 재부팅된다.
#    by-id 링크를 쓰고, 하트비트로 이 기체인지 한 번 더 본다.
PORT = sys.argv[1] if len(sys.argv) > 1 else find_port()
if PORT is None:
    sys.exit(NO_PORT)
m = mavutil.mavlink_connection(PORT, baud=115200)
# HEARTBEAT 하나를 받는다 — 다른 FC 면 NotThisFC 로 여기서 끝난다.
# ⚠️ pymavlink 2.4.49 는 인스턴스 필드가 있는 메시지에서 산발적으로
#    `TypeError: 'NoneType' object does not support item assignment` 로 죽는다
#    (mavutil.py:98). wait_fc_heartbeat 가 다음 패킷으로 넘긴다 — FETCHING.md 의
#    알려진 버그다. 2026-09-11 재부팅 때 실제로 여기서 걸렸다.
hb_wait = wait_fc_heartbeat


print('하트비트 대기...', flush=True)
hb = hb_wait(m, 30)
if hb is None:
    sys.exit('하트비트 없음')
armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
print('sys %d  ARM: %s' % (m.target_system, '🔴 ARMED' if armed else 'disarmed'))
if armed:
    sys.exit('🔴 ARM 상태 — 재부팅 중단')

print('재부팅 명령 전송...', flush=True)
m.mav.command_long_send(
    m.target_system, m.target_component,
    mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0,
    1, 0, 0, 0, 0, 0, 0)          # param1=1 : autopilot reboot
ack = m.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
print('ACK: %s' % (ack if ack else '(없음 — 재부팅이 먼저 끊는 것이 정상)'))

print('부팅 대기...', flush=True)
m.close()
time.sleep(8)
for attempt in range(1, 13):
    try:
        m2 = mavutil.mavlink_connection(PORT, baud=115200)
        if hb_wait(m2, 10) is not None:
            print('✅ 돌아왔다 (%d차) sys %d' % (attempt, m2.target_system))
            sys.exit(0)
        m2.close()
    except Exception as e:
        print('  %d차: %s' % (attempt, e), flush=True)
    time.sleep(4)
sys.exit('🔴 FC 가 안 돌아온다 — 직접 확인 필요')
