#!/usr/bin/env python3
"""로그(.ulg) → 라이브 화면과 **같은 모양**의 프레임 열.

라이브 페이지는 `mav_live.py` 가 만드는 `d` 딕셔너리 하나를 5Hz 로 긁어 그린다.
여기서는 같은 `d` 를 **로그에서** 만든다. 화면 코드는 한 줄도 안 바뀐다 —
어느 쪽에서 왔든 계기가 같은 값을 같은 이름으로 받기 때문이다.

    from playback import load_flight
    fl = load_flight('logs/2026-09-05_09_24_04.ulg')
    fl['frames'][0]     # {'t': 0.0, 'd': {...}}

🔴 **`pyulog` 를 직접 부르지 않는다.** 잘린 로그에서 조용히 멈춘다 —
   `tools/qgclog/qgclog.py` 의 `_load()` 를 거친다. 그쪽이 구독 섹션이 깨진
   파일을 형제 로그로 복구한다 (CLAUDE.md 「pyulog 를 직접 부르지 마라」).

🔴 **읽기 전용이다.** 파일을 열어 읽기만 한다. FC 와는 아무 관계가 없다 —
   재생 중에도 실시간 수신 스레드는 그대로 돈다.

## 왜 프레임을 미리 다 만드나

로그는 토픽마다 주기가 다르다 (자세 50Hz, GPS 5Hz, 배터리 5Hz). 화면은
"그 시각의 상태" 하나를 원하므로, 재생 시각마다 각 토픽에서 **그 시각 이하의
마지막 값**을 골라야 한다 — 실시간에서 마지막 수신값이 남아 있는 것과 같다.
매 요청마다 이 탐색을 하면 폴 하나가 수십 ms 를 먹으므로, 열 때 한 번에
5Hz 격자로 굽는다. 40분 비행이면 12000 프레임 — 메모리로 수십 MB 다.
"""

import bisect
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools', 'qgclog'))

# 재생 격자. 라이브 폴 주기(200ms)와 같게 잡는다 — 화면이 같은 리듬으로 움직인다.
FRAME_HZ = 5.0

# 라이브의 PX4_MAIN/PX4_SUB 는 MAVLink custom_mode 용이다. 로그는 nav_state 라
# 이름 체계가 다르다. 화면에 나가는 문자열을 라이브와 **같게** 맞춘다:
# 라이브는 'AUTO.MISSION' / 'POSCTL' 처럼 쓴다.
NAV_TO_LIVE = {
    0: 'MANUAL', 1: 'ALTCTL', 2: 'POSCTL', 3: 'AUTO.MISSION', 4: 'AUTO.LOITER',
    5: 'AUTO.RTL', 6: 'AUTO.RCRECOVER', 7: 'AUTO.RTGS', 8: 'AUTO.LANDENGFAIL',
    9: 'AUTO.LANDGPSFAIL', 10: 'ACRO', 11: 'UNUSED', 12: 'DESCEND',
    13: 'TERMINATION', 14: 'OFFBOARD', 15: 'STABILIZED', 16: 'RATTITUDE',
    17: 'AUTO.TAKEOFF', 18: 'AUTO.LAND', 19: 'AUTO.FOLLOW',
    20: 'AUTO.PRECLAND', 21: 'ORBIT', 22: 'AUTO.VTOL_TAKEOFF',
}

# 라이브 mav_live.py 의 VTOL_STATE 와 **같은 문자열**이어야 한다. 화면이
# 'MC' 가 아니면 붉은 경고를 띄우므로 여기서 이름이 어긋나면 재생 내내 빨갛다.
VTOL_TO_LIVE = {0: '', 1: 'TRANSITION→FW', 2: 'TRANSITION→MC', 3: 'MC', 4: 'FW'}

SEVERITY = ['EMERG', 'ALERT', 'CRIT', 'ERROR', 'WARN', 'NOTICE', 'INFO', 'DEBUG']


def _q_to_euler(w, x, y, z):
    """쿼터니언 → (roll, pitch, yaw) 도. 로그는 자세를 쿼터니언으로만 준다."""
    sinr = 2.0 * (w * x + y * z)
    cosr = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr, cosr)
    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)
    siny = 2.0 * (w * z + x * y)
    cosy = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny, cosy)
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw) % 360


class _Track:
    """한 토픽의 시계열. 재생 시각으로 '그 이하 마지막 표본'을 찾는다.

    실시간에서 새 프레임이 안 오면 화면이 옛 값을 계속 들고 있는 것과 같은
    동작이다 — 선형 보간을 하지 않는 이유가 이것이다. 없는 값을 지어내면
    로그에 없던 중간값이 계기에 뜬다.
    """

    def __init__(self, t, cols):
        self.t = t                # 정렬된 시각 리스트 (초, arm 기준 상대)
        self.cols = cols          # {이름: 값 리스트}

    def at(self, ts):
        """ts 이하의 마지막 인덱스.

        ts 가 첫 표본보다 앞서면 **첫 표본**을 준다. arm 직후에 처음 발행되는
        토픽(vehicle_status·sensor_gps 등)이 있어서, 그러지 않으면 0초 프레임만
        모드·ARMED·고도가 통째로 비어 재생 시작이 깨진 것처럼 보인다.
        같은 비행의 첫 값이므로 없는 값을 지어내는 것이 아니다.
        """
        i = bisect.bisect_right(self.t, ts) - 1
        if i >= 0:
            return i
        return 0 if self.t else None


def _track(ulog, name, fields, t0):
    """토픽 하나를 _Track 으로. 없으면 None."""
    import qgclog as Q
    ds = Q.get(ulog, name)
    if ds is None:
        return None
    data = ds.data
    t = (data['timestamp'] / 1e6 - t0).tolist()
    cols = {}
    for key, src in fields.items():
        if src in data:
            cols[key] = data[src].tolist()
    if not cols:
        return None
    return _Track(t, cols)


def _val(tr, i, key, default=None):
    if tr is None or i is None:
        return default
    col = tr.cols.get(key)
    if col is None or i >= len(col):
        return default
    v = col[i]
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return default
    return v


def load_flight(path):
    """로그 하나를 프레임 열로 굽는다.

    반환: {'name','path','dur','utc','frames':[{'t','d'},...],'messages':[...],
           'home':[lat,lon] 또는 None, 'track':[[lat,lon,alt],...]}
    """
    import qgclog as Q

    ulog, repaired = Q._load(path)
    if not ulog.data_list:
        raise Q.LogUnreadable('디코딩할 토픽이 없다.')

    # ── 구간 정하기 ────────────────────────────────────────────────
    # arm 구간이 있으면 그것을, 없으면(지상 로그) 로그 전체를 쓴다.
    # `analyse()` 는 지상 로그를 거부하지만, 재생은 지상 테스트도 보고 싶다.
    armed = Q.get(ulog, 'actuator_armed')
    t0 = t1 = None
    if armed is not None:
        ta = armed.data['timestamp'] / 1e6
        isa = armed.data['armed'].astype(bool)
        if isa.any():
            t0, t1 = float(ta[isa][0]), float(ta[isa][-1])
    if t0 is None:
        # 지상 로그 — 아무 토픽이나 잡아 전체 구간을 쓴다.
        spans = [(d.data['timestamp'][0] / 1e6, d.data['timestamp'][-1] / 1e6)
                 for d in ulog.data_list if len(d.data['timestamp'])]
        if not spans:
            raise Q.LogUnreadable('표본이 없다.')
        t0 = float(min(s for s, _ in spans))
        t1 = float(max(e for _, e in spans))

    dur = max(0.0, t1 - t0)

    # ── 토픽 → 트랙 ────────────────────────────────────────────────
    gpos = _track(ulog, 'vehicle_global_position',
                  {'lat': 'lat', 'lon': 'lon', 'alt': 'alt', 'eph': 'eph'}, t0)
    lpos = _track(ulog, 'vehicle_local_position',
                  {'vx': 'vx', 'vy': 'vy', 'vz': 'vz', 'z': 'z',
                   'heading': 'heading', 'ref_alt': 'ref_alt'}, t0)
    att = _track(ulog, 'vehicle_attitude',
                 {'q0': 'q[0]', 'q1': 'q[1]', 'q2': 'q[2]', 'q3': 'q[3]'}, t0)
    status = _track(ulog, 'vehicle_status',
                    {'nav': 'nav_state', 'arming': 'arming_state',
                     'failsafe': 'failsafe'}, t0)
    batt = _track(ulog, 'battery_status',
                  {'v': 'voltage_v', 'i': 'current_a', 'rem': 'remaining',
                   'mah': 'discharged_mah', 'cells': 'cell_count'}, t0)
    gps = _track(ulog, 'sensor_gps',
                 {'fix': 'fix_type', 'sats': 'satellites_used', 'eph': 'eph'}, t0)
    # EKF 혁신 검사 비율. 1.0 을 넘으면 그 센서가 깨지고 있다는 뜻이다
    # (분산이 아니다 — mav_live.py 의 같은 주석 참조).
    # ⚠️ 자기(mag)는 펌웨어에 따라 이름이 다르다. 이 기체 로그(v1.17)는
    #    `mag_test_ratio` 가 없고 `hdg_test_ratio` 를 준다 — 둘 다 받아 둔다.
    est = _track(ulog, 'estimator_status',
                 {'vel': 'vel_test_ratio', 'pos': 'pos_test_ratio',
                  'hgt': 'hgt_test_ratio', 'mag': 'mag_test_ratio',
                  'hdg': 'hdg_test_ratio', 'acc': 'pos_horiz_accuracy'}, t0)
    land = _track(ulog, 'vehicle_land_detected', {'landed': 'landed'}, t0)
    vtol = _track(ulog, 'vtol_vehicle_status', {'st': 'vehicle_vtol_state'}, t0)
    aspd = _track(ulog, 'airspeed_validated',
                  {'a': 'calibrated_airspeed_m_s'}, t0)

    # 모터. **actuator_outputs**(PWM us)를 쓴다 — `mav_live.py` 가 실시간에
    # SERVO_OUTPUT_RAW 를 쓰는 것과 같은 값이라 두 화면의 % 가 정확히 맞는다.
    #
    # 🔴 actuator_motors(control[], 0~1 정규화)를 쓰면 안 된다. 이 기체 로그에서
    #    control[0] 은 4292 표본 중 2개만 유효하고 control[3] 은 1e19 같은 쓰레기가
    #    섞여 있다 (실측 2026-09-05). 그대로 그리면 좌전 모터가 통째로 비거나
    #    말도 안 되는 값이 뜬다.
    #
    # 🔴 인덱스는 기체 배치에 묶여 있다 — README 「출력 배치」:
    #    MAIN3/4/6/7 = VTOL 우후/우전/좌후/좌전 → output[] 은 0부터라 2,3,5,6.
    #    MAIN1/2 는 에일러론 서보(로그에서 1500 고정), MAIN8 은 크루즈(1000 고정).
    #    서보를 추력으로 그리면 거짓말이 된다.
    mot = _track(ulog, 'actuator_outputs',
                 {'RB': 'output[2]', 'RF': 'output[3]',
                  'LB': 'output[5]', 'LF': 'output[6]'}, t0)

    # 진동은 로그에 vibration 토픽이 없다 — sensor_accel 로는 라이브와 같은
    # 값을 만들 수 없다. 없는 값은 안 그린다 (화면이 알아서 흐린다).

    # ── 홈 위치 ────────────────────────────────────────────────────
    home = None
    hp = Q.get(ulog, 'home_position')
    if hp is not None and len(hp.data['timestamp']):
        try:
            home = [round(float(hp.data['lat'][-1]), 7),
                    round(float(hp.data['lon'][-1]), 7)]
        except (KeyError, IndexError):
            home = None

    # 홈 고도. 화면의 고도는 **홈 기준 상대**다 (라이브의 relative_alt 와 같게).
    href = None
    if hp is not None and 'alt' in hp.data and len(hp.data['alt']):
        href = float(hp.data['alt'][-1])

    # ── STATUSTEXT ─────────────────────────────────────────────────
    messages = []
    for m in getattr(ulog, 'logged_messages', []) or []:
        ts = m.timestamp / 1e6 - t0
        if ts < -1 or ts > dur + 1:
            continue
        lvl = getattr(m, 'log_level', 6)
        # pyulog 는 syslog 레벨을 문자 코드로 준다 ('6' 등) — 숫자로 맞춘다.
        if isinstance(lvl, str):
            lvl = ord(lvl) - ord('0') if lvl.isdigit() else 6
        messages.append({'t': round(ts, 1),
                         'sev': SEVERITY[lvl] if 0 <= lvl < len(SEVERITY) else '?',
                         'text': m.message.strip()})
    messages.sort(key=lambda x: x['t'])

    # ── 프레임 굽기 ────────────────────────────────────────────────
    n = int(dur * FRAME_HZ) + 1
    frames = []
    track = []
    last_pt = None

    for k in range(n):
        ts = k / FRAME_HZ
        d = {}

        i = gpos.at(ts) if gpos else None
        if i is not None:
            lat = _val(gpos, i, 'lat')
            lon = _val(gpos, i, 'lon')
            alt = _val(gpos, i, 'alt')
            if lat is not None and lon is not None and (lat or lon):
                d['lat'], d['lon'] = lat, lon
                pt = [round(lat, 7), round(lon, 7),
                      round((alt - href) if (alt is not None and href is not None) else 0.0, 1)]
                if last_pt is None or _moved(last_pt, pt) > 0.4:
                    track.append(pt)
                    last_pt = pt
            if alt is not None:
                d['alt_msl'] = round(alt, 2)
                # 홈 기준 상대고도 — 라이브의 `alt` 와 같은 의미여야 한다.
                if href is not None:
                    d['alt'] = round(alt - href, 2)
            e = _val(gpos, i, 'eph')
            if e is not None:
                d['eph'] = round(e, 2)

        i = lpos.at(ts) if lpos else None
        if i is not None:
            vx = _val(lpos, i, 'vx')
            vy = _val(lpos, i, 'vy')
            vz = _val(lpos, i, 'vz')
            if vx is not None and vy is not None:
                d['vx'], d['vy'] = round(vx, 2), round(vy, 2)
                d['groundspeed'] = round(math.hypot(vx, vy), 2)
            if vz is not None:
                d['vz'] = round(vz, 2)
                d['climb'] = round(-vz, 2)
            hd = _val(lpos, i, 'heading')
            if hd is not None:
                d['hdg'] = round(math.degrees(hd) % 360, 1)
            # global_position 이 없을 때만 지역 z 로 고도를 채운다 (z 는 아래가 +).
            if 'alt' not in d:
                z = _val(lpos, i, 'z')
                if z is not None:
                    d['alt'] = round(-z, 2)

        i = att.at(ts) if att else None
        if i is not None:
            q = [_val(att, i, 'q%d' % j) for j in range(4)]
            if all(v is not None for v in q):
                r, p, y = _q_to_euler(*q)
                d['roll'], d['pitch'], d['yaw'] = round(r, 2), round(p, 2), round(y, 1)
                d.setdefault('hdg', d['yaw'])

        i = status.at(ts) if status else None
        if i is not None:
            nav = _val(status, i, 'nav')
            if nav is not None:
                d['mode'] = NAV_TO_LIVE.get(int(nav), 'NAV%d' % int(nav))
            arming = _val(status, i, 'arming')
            # PX4 arming_state: 1=DISARMED 2=ARMED (v1.14+)
            if arming is not None:
                d['armed'] = int(arming) == 2
            fs = _val(status, i, 'failsafe')
            if fs is not None:
                d['failsafe'] = bool(fs)

        i = batt.at(ts) if batt else None
        if i is not None:
            v = _val(batt, i, 'v')
            if v is not None:
                d['volt'] = round(v, 2)
            cur = _val(batt, i, 'i')
            if cur is not None:
                d['cur'] = round(cur, 2)
            rem = _val(batt, i, 'rem')
            if rem is not None:
                d['batt_pct'] = round(rem * 100)
            mah = _val(batt, i, 'mah')
            if mah is not None:
                d['mah'] = round(mah)

        i = gps.at(ts) if gps else None
        if i is not None:
            fx = _val(gps, i, 'fix')
            if fx is not None:
                d['fix'] = int(fx)
            sa = _val(gps, i, 'sats')
            if sa is not None:
                d['sats'] = int(sa)
            if 'eph' not in d:
                e = _val(gps, i, 'eph')
                if e is not None:
                    d['eph'] = round(e, 2)

        i = est.at(ts) if est else None
        if i is not None:
            ratio = {}
            for key, col in (('vel', 'vel'), ('pos', 'pos'), ('alt', 'hgt'),
                             ('mag', 'mag'), ('mag', 'hdg')):
                if key in ratio:
                    continue                  # mag 는 먼저 잡힌 쪽을 쓴다
                v = _val(est, i, col)
                if v is not None:
                    ratio[key] = round(v, 2)
            if ratio:
                d['ekf_ratio'] = ratio
            acc = _val(est, i, 'acc')
            if acc is not None:
                d['eph_ekf'] = round(acc, 2)

        i = land.at(ts) if land else None
        if i is not None:
            lv = _val(land, i, 'landed')
            if lv is not None:
                d['landed'] = 1 if lv else 2      # 라이브와 같게 1=지상 2=공중

        i = vtol.at(ts) if vtol else None
        if i is not None:
            v = _val(vtol, i, 'st')
            if v is not None:
                d['vtol'] = VTOL_TO_LIVE.get(int(v), '')

        i = aspd.at(ts) if aspd else None
        if i is not None:
            a = _val(aspd, i, 'a')
            if a is not None:
                d['airspeed'] = round(a, 2)

        i = mot.at(ts) if mot else None
        if i is not None:
            # PWM us → %. `mav_live.py` 와 **같은 식**이다: 1000~2000us 를 0~100%,
            # 900 미만(안 도는 채널)은 None. 두 화면이 같은 숫자를 보여야 한다.
            out = {}
            for name in ('LF', 'RF', 'LB', 'RB'):
                v = _val(mot, i, name)
                out[name] = None if (v is None or v < 900) else \
                    round(max(0.0, min(100.0, (v - 1000.0) / 10.0)), 1)
            if any(v is not None for v in out.values()):
                d['motors'] = out

        frames.append({'t': round(ts, 2), 'd': d})

    stamp = Q._time_from_name(path)
    return {
        'name': os.path.basename(path),
        'path': path,
        'dur': round(dur, 1),
        'utc': stamp.strftime('%Y-%m-%d %H:%M:%S') if stamp else None,
        'repaired': bool(repaired),
        'hz': FRAME_HZ,
        'frames': frames,
        'messages': messages,
        'home': home,
        'track': track,
    }


def _moved(a, b):
    """두 점 사이 거리(m). mav_live 와 같은 근사."""
    dlat = (b[0] - a[0]) * 111320.0
    dlon = (b[1] - a[1]) * 111320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def list_logs(log_dir=None):
    """재생할 수 있는 로그 목록. 최신순 — 1번이 가장 최근이다."""
    import qgclog as Q
    d = Q.find_log_dir(log_dir)
    out = []
    for p in Q.list_logs(d):
        stamp = Q._time_from_name(p)
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        out.append({
            'name': os.path.basename(p),
            'path': p,
            'size': size,
            'when': stamp.strftime('%Y-%m-%d %H:%M') if stamp else None,
        })
    return out


if __name__ == '__main__':
    if len(sys.argv) < 2:
        for i, e in enumerate(list_logs(), 1):
            print('%3d  %-34s %8.1fMB  %s' % (i, e['name'], e['size'] / 1e6, e['when'] or ''))
        sys.exit(0)
    fl = load_flight(sys.argv[1])
    print('%s  %.1fs  프레임 %d  메시지 %d  항적 %d'
          % (fl['name'], fl['dur'], len(fl['frames']), len(fl['messages']), len(fl['track'])))
    mid = fl['frames'][len(fl['frames']) // 2]['d']
    for k in sorted(mid):
        print('   %-12s %s' % (k, mid[k]))
