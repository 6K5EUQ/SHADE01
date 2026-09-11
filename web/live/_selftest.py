#!/usr/bin/env python3
"""서버쪽 자체검사. 브라우저 검사(_selftest.html)의 짝이다.

    .venv/bin/python web/live/_selftest.py

FC 도 백팩도 필요 없다 — 전부 합성이다. **FAIL 0 이어야 배포한다.**

여기 있는 것은 전부 실기에서 한 번씩 물렸던 것들이다:
  - 경로 중재 (둘 다 살아 있으면 USB, 죽으면 폴백, 돌아오면 복귀)
  - 백팩 AP 를 껐다 켰다 해도 소켓이 따라오는가 (**fd 누수**)
  - 기록 보존 규칙 (야외 + 1MB)
  - 오래된 기록 청소
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mav_live as M                                        # noqa: E402

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print('%s %-46s %s' % ('OK  ' if ok else 'FAIL', name,
                           '' if ok else '(%r != %r)' % (got, want)))


# ── 1. 경로 중재 ──────────────────────────────────────────────────────
def t_arbitration():
    st = M.State()
    check('프레임 전에는 경로가 없다', st.active_link(), None)
    st.touch(('127.0.0.1', 14550), 1, 'USB')
    check('USB 만 → USB', st.active_link(), 'USB')
    st.touch(('10.0.0.1', 14555), 1, 'ELRS')
    # 🔴 2026-09-11 에 뒤집었다 — 날 때 쓰는 링크를 지상에서도 본다.
    check('둘 다 → ELRS 우선', st.active_link(), 'ELRS')
    st.link_seen['ELRS'] = time.monotonic() - 5.0
    check('ELRS 조용 → USB 로 폴백', st.active_link(), 'USB')
    st.touch(('10.0.0.1', 14555), 1, 'ELRS')
    check('ELRS 복귀 → 다시 ELRS', st.active_link(), 'ELRS')
    st.link_seen['ELRS'] = time.monotonic() - 50.0
    st.link_seen['USB'] = time.monotonic() - 9.0
    check('둘 다 조용 → 마지막에 말한 쪽', st.active_link(), 'USB')


# ── 1-2. 배터리 % 출처 ────────────────────────────────────────────────
# SYS_STATUS 와 BATTERY_STATUS 가 같은 칸을 두고 다툰다. 조종기(ELRS)는
# BATTERY_STATUS 만 읽으므로 웹도 그쪽으로 굳어야 두 화면이 같은 숫자를 보인다.
class _M:
    def __init__(self, t, **kw):
        self._t = t
        self.__dict__.update(kw)

    def get_type(self):
        return self._t

    def get_srcSystem(self):
        return 1

    def get_srcComponent(self):
        return 1


def _sys_status(pct):
    return _M('SYS_STATUS', voltage_battery=24000, current_battery=1200,
              battery_remaining=pct, load=250)


def _batt_status(pct):
    return _M('BATTERY_STATUS', current_battery=1200,
              voltages=[24000] + [65535] * 9, voltages_ext=[],
              battery_remaining=pct, current_consumed=5000, id=124,
              temperature=32767)


def _pct_after(seq):
    st = M.State()
    for m in seq:
        M.handle(m, st)
    return st.d.get('batt_pct')


def _gps_raw(lat, lon, fix=3, sats=8):
    return _M('GPS_RAW_INT', lat=int(lat * 1e7), lon=int(lon * 1e7),
              fix_type=fix, satellites_visible=sats, eph=314)


def _global_pos(lat, lon):
    return _M('GLOBAL_POSITION_INT', lat=int(lat * 1e7), lon=int(lon * 1e7),
              alt=50000, relative_alt=10000, vx=0, vy=0, vz=0, hdg=9000)


def t_gps_coords():
    """🔴 좌표는 GPS_RAW_INT 만 와도 채워져야 한다 (2026-09-10).

    lat/lon 을 GLOBAL_POSITION_INT 에서만 채우고 있었는데, 이 기체는 그
    스트림이 안 온다 — 실측 GPS_RAW 201회 / GLOBAL 0회. fix 3·위성 8·
    eph 3.14m 로 GPS 는 멀쩡한데 지도만 "GPS 대기 중" 이었다. 계기는 fix 를,
    지도는 lat 을 보고 있어 같은 화면이 서로 다른 말을 했다.
    """
    st = M.State()
    M.handle(_gps_raw(35.1795, 128.5553), st)
    check('GPS_RAW 만 와도 lat 이 채워진다', round(st.d.get('lat') or 0, 4), 35.1795)
    check('GPS_RAW 만 와도 항적이 쌓인다', st.track_total >= 1, True)

    # GLOBAL 이 오는 기체에서는 그쪽이 이긴다 — EKF 를 거친 값이라 더 매끄럽다.
    st2 = M.State()
    M.handle(_gps_raw(35.0, 128.0), st2)
    M.handle(_global_pos(36.0, 129.0), st2)
    check('GLOBAL 이 GPS_RAW 를 덮는다', round(st2.d.get('lat') or 0, 3), 36.0)
    M.handle(_gps_raw(35.0, 128.0), st2)
    check('GLOBAL 뒤의 GPS_RAW 는 못 덮는다', round(st2.d.get('lat') or 0, 3), 36.0)

    # fix 가 없으면 좌표를 쓰지 않는다 — 0,0 이 대서양 한가운데로 찍힌다.
    st3 = M.State()
    M.handle(_gps_raw(0, 0, fix=0, sats=0), st3)
    check('fix 없으면 좌표를 안 쓴다', st3.d.get('lat'), None)

    # 🔴 항적의 점마다 **시각**이 붙어야 한다 (2026-09-10). 프론트가 시간
    #    창(1분/3분/10분)으로 자르는 기준이다. 예전에는 프론트가 "받은
    #    시각" 을 붙였는데, 새로고침하면 서버가 5533점을 한 묶음으로 줘서
    #    전부 같은 시각이 됐고 시간 창이 하나도 못 잘랐다.
    st4 = M.State()
    M.handle(_gps_raw(35.1795, 128.5553), st4)
    M.handle(_gps_raw(35.1800, 128.5560), st4)
    check('항적 점에 시각이 붙는다', len(st4.track[0]) >= 4, True)
    if len(st4.track) >= 2 and len(st4.track[0]) >= 4:
        import time as _t
        check('시각이 현재 시각과 맞는다', abs(st4.track[-1][3] - _t.time()) < 5, True)


def _sys_invalid():
    """배터리를 뽑았을 때 FC 가 보내는 SYS_STATUS — 무효를 **명시**한다."""
    return _M('SYS_STATUS', voltage_battery=65535, current_battery=-1,
              battery_remaining=-1, load=250)


def t_battery_removed():
    """🔴 배터리를 뽑으면 값이 **지워져야** 한다 (2026-09-12).

    voltage 65535 · remaining -1 은 "못 받았다" 가 아니라 "배터리가 없다" 다.
    예전에는 batt_pct_src 가 battery_status 로 굳으면 SYS_STATUS 분기를
    통째로 건너뛰어, 배터리를 뽑아도 화면에 5% · 15184mAh 가 그대로 남았다.
    링크 끊김은 고려했는데 배터리 분리는 고려하지 않았던 것이다.
    """
    st = M.State()
    M.handle(_batt_status(62), st)          # 먼저 정상값이 들어온다
    check('배터리 있을 때 pct 가 찬다', st.d.get('batt_pct'), 62)
    M.handle(_sys_invalid(), st)            # 배터리를 뽑았다
    for k in ('batt_pct', 'mah', 'volt', 'cur', 'batt_temp'):
        check('배터리 뽑으면 %s 가 지워진다' % k, st.d.get(k), None)
    check('소스 표시도 지워진다', st.d.get('batt_pct_src'), None)
    # 🔴 링크만 끊긴 것과 구별해야 한다 — 그때는 마지막 값이 남아야 한다.
    st2 = M.State()
    M.handle(_batt_status(62), st2)
    M.handle(_sys_status(80), st2)          # 유효한 SYS 가 와도 battery 가 이긴다
    check('유효한 SYS 는 battery 를 못 덮는다', st2.d.get('batt_pct'), 62)


def t_battery_pct():
    check('SYS 먼저 와도 BATTERY 가 이긴다',
          _pct_after([_sys_status(80), _batt_status(62)]), 62)
    check('BATTERY 뒤의 SYS 는 못 덮는다',
          _pct_after([_batt_status(62), _sys_status(80)]), 62)
    check('번갈아 와도 BATTERY 값만 보인다',
          _pct_after([_sys_status(80), _batt_status(62),
                      _sys_status(79), _batt_status(61),
                      _sys_status(78)]), 61)
    check('BATTERY 가 없으면 SYS 값이라도 보인다',
          _pct_after([_sys_status(80), _sys_status(77)]), 77)
    check('BATTERY 가 -1 이면 마지막 정상값을 지킨다',
          _pct_after([_batt_status(62), _batt_status(-1)]), 62)


# ── 2. --listen 파싱 ──────────────────────────────────────────────────
def t_parse():
    check("'14551'", M.parse_listen('14551', 14550), ('0.0.0.0', 14551))
    check("':14551'", M.parse_listen(':14551', 14550), ('0.0.0.0', 14551))
    check("'10.0.0.100:14550'", M.parse_listen('10.0.0.100:14550', 14550),
          ('10.0.0.100', 14550))
    check("'10.0.0.100' (포트 생략)", M.parse_listen('10.0.0.100', 14550),
          ('10.0.0.100', 14550))
    for bad in ('', 'x:y', '10.0.0.1:99999'):
        try:
            M.parse_listen(bad, 14550)
            check('잘못된 값 %r 은 거부' % bad, 'no error', 'ValueError')
        except ValueError:
            check('잘못된 값 %r 은 거부' % bad, 'ValueError', 'ValueError')


# ── 3. 백팩 AP 토글 — fd 누수 ─────────────────────────────────────────
def t_toggle(cycles=25):
    """🔴 AP 를 껐다 켰다 반복해도 매번 붙어야 한다.

    소켓을 닫을 때 수신 스레드를 join 하지 않으면, 그 스레드가 소켓을 붙들어
    포트가 안 풀린다 — **두 번째부터 영영 실패한다.** 처음 한 번은 되므로
    눈으로는 멀쩡해 보인다. 실제로 199/200 실패로 잡았다 (2026-09-06).
    """
    up = {'v': False}
    real_addr, real_port = M._local_backpack_addr, M._backpack_send_port
    M._local_backpack_addr = lambda: '127.0.0.1' if up['v'] else None
    M._backpack_send_port = lambda host, default=14550: 15699
    try:
        st = M.State()
        st.rec = M.Recorder(tempfile.gettempdir(), enabled=False)
        st.player = M.Player(st)
        lst = M.Listeners(st, [('127.0.0.1', 15698)])
        if not lst.start():
            check('토글 시험 준비 (포트 15698)', 'bind 실패', 'ok')
            return
        bad = 0
        for _ in range(cycles):
            up['v'] = True
            lst._tick()
            if lst.bp_key is None or lst.bp_key not in lst.socks:
                bad += 1
            up['v'] = False
            lst._tick()
            if lst.bp_key is not None:
                bad += 1
        check('AP %d회 토글 — 매번 붙고 떨어진다' % cycles, bad, 0)
        check('fd 누수 없음 (고정 소켓 1개만 남는다)', len(lst.socks), 1)
        for key in list(lst.socks):
            lst._close(key)
    finally:
        M._local_backpack_addr, M._backpack_send_port = real_addr, real_port


# ── 4. 기록 보존 규칙 ─────────────────────────────────────────────────
def _record(gps_seq, target_bytes, link='USB'):
    """합성 비행 하나를 적고, 남은 파일 개수를 돌려준다."""
    d = tempfile.mkdtemp()
    try:
        r = M.Recorder(d, enabled=True)
        r.on_arm(True)
        frame = b'\xfd' + b'x' * 200
        for i in range(max(1, target_bytes // (len(frame) + 8))):
            r.write(frame, link, gps_seq[min(i, len(gps_seq) - 1)])
        r.on_arm(False)
        r._closing_at = time.monotonic() - 1
        r.tick()
        return len([f for f in os.listdir(d) if f.endswith('.tlog')])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_recording():
    OUT, IN = {'fix': 3, 'sats': 9}, {'fix': 1, 'sats': 2}
    check('야외 + 2MB → 남긴다', _record([OUT], 2_000_000), 1)
    check('야외 + 0.2MB → 지운다 (너무 작다)', _record([OUT], 200_000), 0)
    check('실내 + 2MB → 지운다 (GPS 없음)', _record([IN], 2_000_000), 0)
    check('실내 + 0.2MB → 지운다', _record([IN], 200_000), 0)

    # 🔴 ELRS 백팩은 문턱이 다르다 (2026-09-09). 1MB 를 두 경로에 똑같이
    #    걸었더니 그 값이 링크 대역폭을 재고 있었고, 야외 실비행 9편이
    #    전부 버려졌다 — 388초를 날고도 0.5MB 였다.
    #    실측 최소가 92초 0.1MB 이므로 그 아래(0.2MB)도 남아야 한다.
    check('ELRS 야외 + 0.2MB → 남긴다', _record([OUT], 200_000, 'ELRS'), 1)
    check('ELRS 야외 + 0.1MB → 남긴다', _record([OUT], 100_000, 'ELRS'), 1)
    # 백팩이 안 붙으면 바이트가 아예 안 쌓인다 — 실측 19~40초에 0.0MB.
    # 그 지상 arm 은 낮아진 문턱으로도 계속 걸러져야 한다.
    check('ELRS 야외 + 0.01MB → 지운다 (링크가 안 흘렀다)',
          _record([OUT], 10_000, 'ELRS'), 0)
    # 야외 판정은 링크와 무관하게 그대로다.
    check('ELRS 실내 + 0.2MB → 지운다 (GPS 없음)',
          _record([IN], 200_000, 'ELRS'), 0)
    # USB 는 1MB 문턱을 지킨다 — 낮춘 것은 ELRS 뿐이다.
    check('USB 야외 + 0.2MB → 여전히 지운다', _record([OUT], 200_000, 'USB'), 0)
    # 🔴 fix 가 늦게 잡혀도 남아야 하고, **이륙 순간이 파일에 있어야** 한다.
    check('늦게 fix → 남긴다', _record([IN] * 2000 + [OUT], 2_000_000), 1)


def t_recording_keeps_takeoff():
    d = tempfile.mkdtemp()
    try:
        r = M.Recorder(d, enabled=True)
        r.on_arm(True)
        frame = b'\xfd' + b'x' * 200
        n = 9600
        for i in range(n):
            r.write(frame, 'USB',
                    {'fix': 1, 'sats': 2} if i < 3000 else {'fix': 3, 'sats': 9})
        r.on_arm(False)
        r._closing_at = time.monotonic() - 1
        r.tick()
        files = [f for f in os.listdir(d) if f.endswith('.tlog')]
        got = os.path.getsize(os.path.join(d, files[0])) // (len(frame) + 8) if files else 0
        # fix 이전 3000 프레임까지 다 들어 있어야 한다 (이륙 순간이 그 안에 있다)
        check('fix 이전 프레임도 파일에 있다 (이륙이 안 잘린다)', got, n)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 5. 오래된 기록 청소 ───────────────────────────────────────────────
def t_prune():
    d = tempfile.mkdtemp()
    try:
        old = os.path.join(d, '2026-01-01_00-00-00_KST_FC.tlog')
        new = os.path.join(d, '2026-09-06_00-00-00_KST_FC.tlog')
        other = os.path.join(d, 'notes.txt')
        for f in (old, new, other):
            open(f, 'wb').write(b'x')
        os.utime(old, (time.time() - 200 * 86400,) * 2)
        os.utime(new, (time.time() - 5 * 86400,) * 2)
        check('90일 지난 것만 지운다', M.prune_recordings(d, days=90), 1)
        check('.tlog 아닌 파일은 안 건드린다', os.path.exists(other), True)
        check('최근 기록은 남는다', os.path.exists(new), True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    for fn in (t_arbitration, t_gps_coords, t_battery_removed, t_battery_pct, t_parse, t_toggle, t_recording,
               t_recording_keeps_takeoff, t_prune):
        fn()
    print('\n%d PASS · %d FAIL' % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
