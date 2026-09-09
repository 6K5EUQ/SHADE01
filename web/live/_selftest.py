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
    st.touch(('10.0.0.1', 14555), 1, 'ELRS')
    check('ELRS 만 → ELRS', st.active_link(), 'ELRS')
    st.touch(('127.0.0.1', 14550), 1, 'USB')
    check('둘 다 → USB 우선', st.active_link(), 'USB')
    st.link_seen['USB'] = time.monotonic() - 5.0
    check('USB 조용 → ELRS 로 폴백', st.active_link(), 'ELRS')
    st.touch(('127.0.0.1', 14550), 1, 'USB')
    check('USB 복귀 → 다시 USB', st.active_link(), 'USB')
    st.link_seen['USB'] = time.monotonic() - 50.0
    st.link_seen['ELRS'] = time.monotonic() - 9.0
    check('둘 다 조용 → 마지막에 말한 쪽', st.active_link(), 'ELRS')


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
              battery_remaining=pct, current_consumed=5000, id=124)


def _pct_after(seq):
    st = M.State()
    for m in seq:
        M.handle(m, st)
    return st.d.get('batt_pct')


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
def _record(gps_seq, target_bytes):
    """합성 비행 하나를 적고, 남은 파일 개수를 돌려준다."""
    d = tempfile.mkdtemp()
    try:
        r = M.Recorder(d, enabled=True)
        r.on_arm(True)
        frame = b'\xfd' + b'x' * 200
        for i in range(max(1, target_bytes // (len(frame) + 8))):
            r.write(frame, 'USB', gps_seq[min(i, len(gps_seq) - 1)])
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
    for fn in (t_arbitration, t_battery_pct, t_parse, t_toggle, t_recording,
               t_recording_keeps_takeoff, t_prune):
        fn()
    print('\n%d PASS · %d FAIL' % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
