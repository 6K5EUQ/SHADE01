"""이 기체(SHADE01) FC 만 연다 — 모든 FC 도구가 이것을 거친다.

🔴 /dev/ttyACM0 을 그대로 잡지 마라. 다른 기체 FC 가 같은 PC 에 꽂히면 그것이
   ttyACM0 이 된다 — 그 기체에 재부팅·미션·파라미터가 들어간다.
   실측: QGC tlog 에 다른 기체(ArduPilot 쿼드, autopilot=3 type=2)가 sysid 1
   로 같이 남아 있다. sysid 로는 못 가른다.

by-id 링크 **그 자체**를 넘긴다. 풀어서 ttyACMn 으로 넘기면 뽑고 다시 꽂을
때 다른 FC 가 그 번호를 받아 열린다.

포트만으로는 모자란다 — 같은 6C 를 쓰는 다른 기체일 수 있다. 첫 하트비트를
check_heartbeat() 로 반드시 본다. 사용자가 포트를 직접 줘도 마찬가지다.
표준 라이브러리만 쓴다 (agent.py 는 시스템 python3 으로 돈다).
"""
import glob

BY_ID = '/dev/serial/by-id/usb-Auterion*v6C*-if00'

AUTOPILOT_PX4 = 12
TYPE_VTOL = 22            # QGC tlog 실측 (1,1,12,22) — 2026-08-17~24

NO_PORT = '이 기체 FC(Pixhawk 6C) 가 없다 — ls /dev/serial/by-id/'

# FC 가 아닌 하트비트. GCS·짐벌·ADSB·컴패니언은 판정 대상이 아니다
# (pymavlink probably_vehicle_heartbeat 와 같은 기준).
_AUTOPILOT_INVALID = 8
_NOT_VEHICLE = (6, 18, 26, 27)


class NotThisFC(SystemExit):
    """다른 FC 다. SystemExit 이라 안 잡으면 메시지를 찍고 exit 1."""


def find_port():
    """by-id 링크 경로. 없거나 둘 이상이면 None — 어느 것인지 모른다."""
    hits = sorted(glob.glob(BY_ID))
    return hits[0] if len(hits) == 1 else None


def is_vehicle(hb):
    """판정할 하트비트인가. GCS·주변기기는 건너뛴다."""
    return hb.autopilot != _AUTOPILOT_INVALID and hb.type not in _NOT_VEHICLE


def check_heartbeat(hb):
    """이 기체 FC 면 None, 아니면 사유."""
    if hb.autopilot == AUTOPILOT_PX4 and hb.type == TYPE_VTOL:
        return None
    return '이 기체 FC 가 아니다 (autopilot=%d type=%d)' % (hb.autopilot, hb.type)


def wait_fc_heartbeat(m, timeout):
    """pymavlink 연결에서 FC 하트비트 하나. 없으면 None, 다른 FC 면 NotThisFC."""
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
        except TypeError:
            continue          # pymavlink 2.4.49 인스턴스 필드 버그
        if hb is None or not is_vehicle(hb):
            continue
        err = check_heartbeat(hb)
        if err:
            try:
                m.close()
            except Exception:
                pass
            raise NotThisFC('🔴 ' + err + ' — 중단')
        return hb
    return None
