#!/usr/bin/env python3
"""전류-나침반 간섭 분석.

호버가 불안정하거나 기수가 흐를 때, 그것이 **전력 전류가 나침반을 교란한
것인지** 아니면 바람·자세 때문인지 가른다.

핵심은 |B|(자기장 세기)가 **회전불변량**이라는 것이다 — 기체가 어떻게 기울고
돌든 지구 자기장 세기는 변할 수 없다. 그런데 전류에 따라 변한다면 외부
자기원(전력선)이 있다는 뜻이다.

바람을 배제하는 방법 세 가지를 모두 돌린다:
  1. 바람 대리지표(경사·수평속도)와 |B| 의 상관 — 0 이어야 한다
  2. 편상관 — 경사 영향을 제거해도 전류 상관이 남는가
  3. 정지 호버 구간만 — 바람이 가장 약할 때 오히려 강해지는가

사용법:
    .venv/bin/python tools/qgclog/magcheck.py <log.ulg> [log2.ulg ...]

판정: |r| > 0.5 면 간섭. 2026-09-05 실측은 -0.91 / -0.74 였다.
자세한 해석은 flights/2026-09-05-hover-compass-interference.md 참조.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import qgclog

np.seterr(all='ignore')

THRESH = 0.5          # qgclog 자동판정과 같은 임계값
MOTOR_IDX = [2, 3, 5, 6]   # MAIN3/4/6/7 = VTOL 모터 4개 (기체별로 다르다)


def _ds(ulog, name):
    try:
        return ulog.get_dataset(name).data
    except Exception:
        return None


def _rs(t_src, v, t_dst):
    return np.interp(t_dst, t_src, v)


def _cc(a, b, mask=None):
    if mask is not None:
        a, b = a[mask], b[mask]
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 30:
        return np.nan
    return np.corrcoef(a[ok], b[ok])[0, 1]


def _partial(x, y, z):
    """z 의 영향을 제거한 x-y 편상관."""
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[ok], y[ok], z[ok]
    if len(x) < 30:
        return np.nan
    rxy = np.corrcoef(x, y)[0, 1]
    rxz = np.corrcoef(x, z)[0, 1]
    ryz = np.corrcoef(y, z)[0, 1]
    return (rxy - rxz * ryz) / np.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))


def analyse(path):
    ulog, repaired = qgclog._load(path)
    print('=' * 78)
    print(os.path.basename(path) + ('   ⚠복구됨' if repaired else ''))

    mg = _ds(ulog, 'vehicle_magnetometer')
    bat = _ds(ulog, 'battery_status')
    att = _ds(ulog, 'vehicle_attitude')
    lp = _ds(ulog, 'vehicle_local_position')
    ao = _ds(ulog, 'actuator_outputs')
    if mg is None or bat is None:
        print('  자력계 또는 배터리 토픽이 없다 — 분석 불가')
        return

    tm = mg['timestamp'] / 1e6
    t0 = tm[0]
    tm = tm - t0
    B = np.sqrt(mg['magnetometer_ga[0]'] ** 2 +
                mg['magnetometer_ga[1]'] ** 2 +
                mg['magnetometer_ga[2]'] ** 2)
    cur = _rs(bat['timestamp'] / 1e6 - t0, bat['current_a'], tm)

    print(f'  샘플 {len(tm)}  자력계 간격 {np.diff(tm).mean()*1000:.0f}ms  '
          f'전류 {cur.min():.1f}~{cur.max():.1f}A  |B| {B.min():.3f}~{B.max():.3f}G')

    # 자세 (바람 대리지표)
    tilt = spd = None
    if att is not None:
        q0, q1, q2, q3 = att['q[0]'], att['q[1]'], att['q[2]'], att['q[3]']
        ta = att['timestamp'] / 1e6 - t0
        roll = np.degrees(np.arctan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1 ** 2 + q2 ** 2)))
        pitch = np.degrees(np.arcsin(np.clip(2 * (q0 * q2 - q3 * q1), -1, 1)))
        yaw = np.degrees(np.arctan2(2 * (q0 * q3 + q1 * q2), 1 - 2 * (q2 ** 2 + q3 ** 2)))
        tilt = _rs(ta, np.sqrt(roll ** 2 + pitch ** 2), tm)
        yaw_i = _rs(ta, np.unwrap(np.radians(yaw)), tm)
    if lp is not None:
        tl = lp['timestamp'] / 1e6 - t0
        spd = _rs(tl, np.sqrt(lp['vx'] ** 2 + lp['vy'] ** 2), tm)

    r_cur = _cc(cur, B)
    print('\n  [상관]')
    print(f'    전류     vs |B|   {r_cur:+.3f}   <<< 판정 대상 (임계 {THRESH})')
    if tilt is not None:
        print(f'    경사     vs |B|   {_cc(tilt, B):+.3f}   <- 바람이 원인이면 여기가 커야')
        print(f'    yaw      vs |B|   {_cc(yaw_i, B):+.3f}   <- |B|는 회전불변, 0 이어야 정상')
    if spd is not None:
        print(f'    수평속도 vs |B|   {_cc(spd, B):+.3f}   <- 바람이 원인이면 여기가 커야')

    if ao is not None:
        tA = ao['timestamp'] / 1e6 - t0
        M = []
        for i in MOTOR_IDX:
            k = f'output[{i}]'
            if k not in ao:
                continue
            v = ao[k]
            v = np.where(np.isfinite(v) & (v > 800) & (v < 2200), v, np.nan)
            M.append(_rs(tA, np.nan_to_num(v, nan=np.nanmedian(v)), tm))
        if M:
            Mm = np.nanmean(np.array(M), axis=0)
            print(f'    모터평균 vs |B|   {_cc(Mm, B):+.3f}   (모터 vs 전류 {_cc(Mm, cur):+.3f})')

    # 바람 배제 ①: 경사 구간별
    if tilt is not None:
        print('\n  [경사 구간별 — 자세를 묶고 전류만 본다]')
        for lo, hi in [(0, 3), (3, 6), (6, 10), (10, 90)]:
            m = (tilt >= lo) & (tilt < hi)
            if m.sum() < 50:
                continue
            print(f'    경사 {lo:2d}-{hi:2d}°  n={m.sum():6d}  전류-|B| {_cc(cur, B, m):+.3f}')

        # 바람 배제 ②: 편상관
        print(f'\n  [편상관] 경사 영향 제거 후 전류-|B| : {_partial(cur, B, tilt):+.3f}')

    # 바람 배제 ③: 정지 호버 구간
    if tilt is not None and spd is not None:
        m = (spd < 0.5) & (tilt < 3) & np.isfinite(B) & np.isfinite(cur)
        if m.sum() > 50:
            r_q = _cc(cur, B, m)
            print(f'  [정지호버만] n={m.sum()}  전류-|B| {r_q:+.3f}   '
                  f'(전체보다 {"강함 → 바람 아님" if abs(r_q) > abs(r_cur) else "약함"})')

    # 방위 편향 — 실제로 얼마나 틀어지는가
    hdg = np.degrees(np.arctan2(mg['magnetometer_ga[1]'], mg['magnetometer_ga[0]']))
    lo_m, hi_m = cur < 10, cur > 45
    if lo_m.sum() > 20 and hi_m.sum() > 20:
        d = ((hdg[hi_m].mean() - hdg[lo_m].mean() + 180) % 360) - 180
        print('\n  [방위 편향]')
        print(f'    전류 <10A : {hdg[lo_m].mean():+7.1f}°  (std {hdg[lo_m].std():5.1f}°)')
        print(f'    전류 >45A : {hdg[hi_m].mean():+7.1f}°  (std {hdg[hi_m].std():5.1f}°)')
        print(f'    => 고전류에서 {d:+.1f}° 편향')

    # 축별 — 자기원의 방향을 가리킨다
    print('\n  [축별 전류상관 — 큰 축 방향에 자기원이 있다]')
    for nm, k in (('X', 0), ('Y', 1), ('Z', 2)):
        print(f'    {nm}축  {_cc(cur, mg[f"magnetometer_ga[{k}]"]):+.3f}')

    # 시간 지연 — 0 이면 순수 전자기 현상
    dt = 0.05
    tb = bat['timestamp'] / 1e6 - t0
    tg = np.arange(max(tm[0], tb[0]), min(tm[-1], tb[-1]), dt)
    if len(tg) > 100:
        Bz = np.interp(tg, tm, B)
        Cz = np.interp(tg, tb, bat['current_a'])
        Bz = (Bz - Bz.mean()) / Bz.std()
        Cz = (Cz - Cz.mean()) / Cz.std()
        best = (0.0, 0.0)
        for lag in np.arange(-2, 2.001, dt):
            k = int(round(lag / dt))
            if k >= 0:
                a, b = Cz[:len(Cz) - k if k else None], Bz[k:]
            else:
                a, b = Cz[-k:], Bz[:len(Bz) + k]
            n = min(len(a), len(b))
            if n < 50:
                continue
            r = np.corrcoef(a[:n], b[:n])[0, 1]
            if abs(r) > abs(best[1]):
                best = (lag, r)
        res = np.diff(tm).mean()
        print(f'\n  [시간지연] 최대상관 lag {best[0]:+.2f}s  r={best[1]:+.3f}')
        print(f'    자력계 분해능 {res:.2f}s — |lag| < 분해능이면 "동시"로 읽어라')
        print('    지연 0 = 순수 전자기 현상(암페어 법칙). 열·기계적 원인이면 지연이 남는다')

    print()
    if np.isfinite(r_cur) and abs(r_cur) > THRESH:
        print(f'  🔴 판정: 전류 간섭 (|{r_cur:.3f}| > {THRESH})')
        print('     전원선 +/- 트위스트로 루프 면적을 줄이는 것이 가장 효과적이다.')
        print('     ⚠️ 은박지(알루미늄)는 DC 자기장을 막지 못한다 — 효과 없다.')
    elif np.isfinite(r_cur):
        print(f'  ✅ 판정: 전류 간섭 임계 미만 ({r_cur:+.3f})')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print(__doc__)
        return 1
    for p in args:
        if not os.path.exists(p):
            print(f'없는 파일: {p}')
            continue
        analyse(p)
    return 0


if __name__ == '__main__':
    sys.exit(main())
