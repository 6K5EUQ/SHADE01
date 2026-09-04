#!/usr/bin/env python3
"""ULog 하나를 읽어 웹이 쓸 JSON 세 덩어리를 stdout 으로 낸다.

    extract.py row   <path>   목록 한 줄
    extract.py full  <path>   요약 + 시계열 (서버가 쪼개 캐시한다)

🔴 **이 파일이 유일한 파싱 경로다.** `pyulog` 를 직접 부르지 마라 — 잘린 메시지
하나에서 읽기를 포기해 23MB 로그가 27초로 보인다. 반드시 `qgclog._load()` 를 거친다.
자세한 이유: <repo>/PROCEDURE.md "분석기 — 잘린 메시지에서 멈추지 않는다".

고도는 반드시 `qgclog._agl()` 로 arm 기준 상대고도를 만든다. `z` 를 그대로 쓰면
EKF 원점 기준이라 지상 로그가 -7.0 m 로 나온다.

시계열은 **균일 격자**로 리샘플한다. 토픽마다 레이트가 달라서(자세 20Hz,
지역위치 10Hz, 배터리·스틱 5Hz, IMU 1Hz) 각자의 시간축을 그대로 보내면 지도·차트·
재생 커서가 서로 다른 인덱스를 쓰게 되고, 거기서 "고도와 위치가 한 칸씩 어긋나는"
버그가 난다. 격자 하나를 공유하면 `i = round(t * rate)` 산술 하나로 전부 정렬된다.

⚠️ 격자 값은 **보여주기용**이다. 최대/최소는 리샘플 전 원본에서 뽑아 `sum` 에 담는다
(5Hz 격자는 79.3A 같은 순간 첨두를 놓칠 수 있다).
"""

import datetime
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "qgclog"))
import qgclog  # noqa: E402


GRID_HZ = 5.0          # 배터리·스틱의 실제 레이트. 이보다 올려도 절반이 복제값이다.
GRID_MAX_PTS = 4000    # 긴 비행에서 격자가 무한정 커지지 않게. 넘으면 레이트를 낮춘다.
MAX_EVENTS = 500       # FC 메시지 상한


def coerce(o):
    """numpy·datetime 을 JSON 이 아는 타입으로. NaN/inf 는 null 로."""
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return [coerce(x) for x in o.tolist()]
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    raise TypeError("직렬화 못 하는 타입: %s" % type(o).__name__)


def clean(arr, limit=None):
    """길이를 보존하며 이상치를 NaN 으로. 시계열 전용.

    `qgclog._sane()` 은 샘플을 **버려서** 배열이 짧아진다. 시계열에 그걸 쓰면
    시간축이 밀린다. 여기서는 값만 죽이고 자리는 남긴다.

    `limit` 은 물리적으로 불가능한 크기를 걸러낸다. 파일이 깨지면 float32 한 샘플의
    지수부가 튀어 `5.03e14 m` 같은 값이 나오는데(실측: log_182), 유효 플래그로는
    안 걸린다 — EKF 가 낸 값이 아니라 파일이 깨진 것이기 때문이다. 이걸 안 거르면
    차트 y축이 그 한 점에 끌려가 나머지가 평평한 선이 된다.
    """
    a = np.asarray(arr, dtype=np.float64).copy()
    a[~np.isfinite(a)] = np.nan
    if limit is not None:
        a[np.abs(a) > limit] = np.nan
    return a


def to_grid(t_src, v_src, grid):
    """원본 (시각, 값) 을 균일 격자에 올린다. 격자 밖은 NaN."""
    v = clean(v_src)
    ok = np.isfinite(v)
    if ok.sum() < 2:
        return [None] * len(grid)
    ts = np.asarray(t_src)[ok]
    # np.interp 는 범위 밖을 가장자리 값으로 채운다(기본). 격자 첫/끝 점은 첫 샘플보다
    # 수십 ms 바깥이기 마련이라 그 정도는 채워야 한다 — 안 그러면 t=0 의 읽기 패널이
    # 전부 '–' 로 나온다. 대신 진짜로 데이터가 없는 구간(한 격자 간격 이상)은 지운다.
    out = np.interp(grid, ts, v[ok])
    tol = 1.0 / GRID_HZ
    out[(grid < ts[0] - tol) | (grid > ts[-1] + tol)] = np.nan
    return [None if math.isnan(x) else round(float(x), 3) for x in out]


def armed_window(ulog):
    """(t0, t1, armed) — arm 구간. arm 이 없으면 로그 전체 구간과 armed=False."""
    a = qgclog.get(ulog, "actuator_armed")
    if a is not None:
        t = a.data["timestamp"] / 1e6
        on = a.data["armed"].astype(bool)
        if on.any():
            return float(t[on][0]), float(t[on][-1]), True
    # arm 이 없어도 지상 시험 로그로서 볼 값이 있다. 전체 구간을 쓴다.
    lo, hi = None, None
    for d in ulog.data_list:
        ts = d.data.get("timestamp")
        if ts is None or not len(ts):
            continue
        lo = ts[0] / 1e6 if lo is None else min(lo, ts[0] / 1e6)
        hi = ts[-1] / 1e6 if hi is None else max(hi, ts[-1] / 1e6)
    if lo is None:
        raise qgclog.LogUnreadable("타임스탬프가 있는 토픽이 하나도 없다.")
    return float(lo), float(hi), False


def win(ulog, name, t0, t1):
    """토픽을 구간으로 자른 (dataset, 상대시각, mask). 없으면 (None, None, None)."""
    d = qgclog.get(ulog, name)
    if d is None:
        return None, None, None
    t = d.data["timestamp"] / 1e6
    m = (t >= t0) & (t <= t1)
    if not m.any():
        return None, None, None
    return d, t[m] - t0, m


def live_motor_channels(d, m):
    """실제로 쓰이는 모터 채널 번호. control[0] 이 미사용인 기체가 있어 자동 탐지한다."""
    out = []
    for i in range(12):
        k = "control[%d]" % i
        if k not in d.data:
            continue
        v = d.data[k][m]
        v = v[np.isfinite(v)]
        if v.size and v.max() > -0.9:
            out.append(i)
    return out


def build_track(ulog, t0, t1):
    """지도 궤적 + 균일 격자 시계열."""
    dur = max(t1 - t0, 0.001)
    hz = GRID_HZ
    while dur * hz > GRID_MAX_PTS and hz > 1.0:
        hz /= 2.0
    n = int(dur * hz) + 1
    grid = np.arange(n) / hz
    trk = {"hz": hz, "n": n, "dur": round(dur, 2)}

    # ── 위치·고도·속도 ──────────────────────────────────────────
    p, tp, mp = win(ulog, "vehicle_local_position", t0, t1)
    if p is not None:
        # 한계는 qgclog 의 것과 같은 상수를 쓴다 — 요약과 시계열이 갈리면 안 된다.
        AL, SP = qgclog._SANE_ALT_M, qgclog._SANE_SPEED_MS
        agl = qgclog._agl(-clean(p.data["z"][mp], AL), tp)
        trk["alt"] = to_grid(tp, clean(agl, AL), grid)
        trk["spd"] = to_grid(tp, np.hypot(clean(p.data["vx"][mp], SP),
                                          clean(p.data["vy"][mp], SP)), grid)
        trk["climb"] = to_grid(tp, -clean(p.data["vz"][mp], SP), grid)

    g, tg, mg = win(ulog, "vehicle_global_position", t0, t1)
    if g is not None:
        # 위경도는 to_grid 의 소수 3자리 반올림으로는 못 쓴다 (1도 ≈ 111km).
        # 같은 규칙을 쓰되 7자리로 남긴다.
        tol = 1.0 / hz
        for key, src, lim in (("lat", g.data["lat"][mg], 90.0),
                              ("lon", g.data["lon"][mg], 180.0)):
            v = clean(src, lim)
            ok = np.isfinite(v)
            if ok.sum() < 2:
                continue
            ts = tg[ok]
            arr = np.interp(grid, ts, v[ok])
            arr[(grid < ts[0] - tol) | (grid > ts[-1] + tol)] = np.nan
            trk[key] = [None if math.isnan(x) else round(float(x), 7) for x in arr]

    # 기수방위 — 쿼터니언에서 yaw. 도 단위 0~360.
    a, ta, ma = win(ulog, "vehicle_attitude", t0, t1)
    if a is not None:
        q = [clean(a.data["q[%d]" % i][ma]) for i in range(4)]
        qn = np.sqrt(sum(x ** 2 for x in q))
        bad = ~np.isfinite(qn) | (np.abs(qn - 1.0) > 0.1)   # 깨진 샘플
        yaw = np.degrees(np.arctan2(2 * (q[0] * q[3] + q[1] * q[2]),
                                    1 - 2 * (q[2] ** 2 + q[3] ** 2))) % 360.0
        roll = np.degrees(np.arctan2(2 * (q[0] * q[1] + q[2] * q[3]),
                                     1 - 2 * (q[1] ** 2 + q[2] ** 2)))
        pitch = np.degrees(np.arcsin(np.clip(2 * (q[0] * q[2] - q[3] * q[1]), -1, 1)))
        for arr in (yaw, roll, pitch):
            arr[bad] = np.nan
        # 방위는 0/360 을 넘나들어 선형보간이 틀린다. 최근접 샘플을 쓴다.
        idx = np.clip(np.searchsorted(ta, grid), 0, len(ta) - 1)
        trk["hdg"] = [None if math.isnan(yaw[i]) else round(float(yaw[i]), 1) for i in idx]
        trk["roll"] = to_grid(ta, roll, grid)
        trk["pitch"] = to_grid(ta, pitch, grid)

    # ── 자세 목표 (실측과 한 축에 겹쳐 "추종했나" 를 본다) ────────
    # PX4 Flight Review 의 핵심 관용구다. 그 코드 주석이 설계 철학을 그대로 말한다:
    #   colors2 = [...]  # 'what it is' and 'what it should be'
    # 실측과 목표를 같은 축에 놓으면 차이를 따로 계산하지 않아도 눈에 보인다.
    sp, tsp, msp = win(ulog, "vehicle_attitude_setpoint", t0, t1)
    if sp is not None:
        if "q_d[0]" in sp.data:
            # 최신 PX4 는 목표 자세를 쿼터니언 q_d[] 로 낸다 (예전엔 roll_body 였다).
            qd = [clean(sp.data["q_d[%d]" % i][msp]) for i in range(4)]
            qn = np.sqrt(sum(x ** 2 for x in qd))
            bad = ~np.isfinite(qn) | (np.abs(qn - 1.0) > 0.1)
            r = np.degrees(np.arctan2(2 * (qd[0] * qd[1] + qd[2] * qd[3]),
                                      1 - 2 * (qd[1] ** 2 + qd[2] ** 2)))
            pch = np.degrees(np.arcsin(np.clip(2 * (qd[0] * qd[2] - qd[3] * qd[1]), -1, 1)))
            r[bad] = np.nan
            pch[bad] = np.nan
            trk["roll_sp"] = to_grid(tsp, r, grid)
            trk["pitch_sp"] = to_grid(tsp, pch, grid)
        else:
            for src, dst in (("roll_body", "roll_sp"), ("pitch_body", "pitch_sp")):
                if src in sp.data:
                    trk[dst] = to_grid(tsp, np.degrees(clean(sp.data[src][msp], 10.0)), grid)

    # ── 각속도 (실측 + 목표) ────────────────────────────────────
    av, tav, mav = win(ulog, "vehicle_angular_velocity", t0, t1)
    if av is not None:
        for i, ax in enumerate("xyz"):
            k = "xyz[%d]" % i
            if k in av.data:
                trk["rate_" + ax] = to_grid(tav, np.degrees(clean(av.data[k][mav], 100.0)), grid)
    rs, trs, mrs = win(ulog, "vehicle_rates_setpoint", t0, t1)
    if rs is not None:
        for ax in "xyz":
            src = {"x": "roll", "y": "pitch", "z": "yaw"}[ax]
            if src in rs.data:
                trk["rate_%s_sp" % ax] = to_grid(
                    trs, np.degrees(clean(rs.data[src][mrs], 100.0)), grid)

    # ── 고도 여러 출처 (융합 vs 기압 vs GPS) ────────────────────
    # 같은 물리량을 다른 센서로 겹쳐 그리면 어느 센서가 튀는지 바로 보인다.
    ad, tad, mad = win(ulog, "vehicle_air_data", t0, t1)
    if ad is not None and "baro_alt_meter" in ad.data:
        b = clean(ad.data["baro_alt_meter"][mad], qgclog._SANE_ALT_M)
        fin = b[np.isfinite(b)]
        if fin.size:
            trk["alt_baro"] = to_grid(tad, b - np.median(fin[:max(1, int(len(fin) * 0.02))]), grid)

    # ── 진동 ────────────────────────────────────────────────────
    im, tim, mim = win(ulog, "vehicle_imu_status", t0, t1)
    if im is not None and "accel_vibration_metric" in im.data:
        trk["vib"] = to_grid(tim, clean(im.data["accel_vibration_metric"][mim], 1000.0), grid)

    # ── GPS 품질 ────────────────────────────────────────────────
    gp, tgp, mgp = win(ulog, "sensor_gps", t0, t1)
    if gp is not None:
        if "satellites_used" in gp.data:
            trk["sats"] = to_grid(tgp, clean(gp.data["satellites_used"][mgp], 100.0), grid)
        if "eph" in gp.data:
            trk["eph"] = to_grid(tgp, clean(gp.data["eph"][mgp], 1000.0), grid)

    # ── EKF innovation (센서 간 불일치) ─────────────────────────
    iv, tiv, miv = win(ulog, "estimator_innovation_test_ratios", t0, t1)
    if iv is not None:
        # 1.0 을 넘은 적 있는 필드만 싣는다. 전부 실으면 20개가 넘어 읽을 수 없다.
        best = []
        for k, v in iv.data.items():
            if k.startswith("timestamp"):
                continue
            vv = clean(v[miv], 100.0)
            fin = vv[np.isfinite(vv)]
            if fin.size and np.nanmax(np.abs(fin)) > qgclog.INNOV_WARN:
                best.append((float(np.nanmax(np.abs(fin))), k, vv))
        for _, k, vv in sorted(best, reverse=True)[:4]:
            trk["innov_" + k.replace("[", "_").replace("]", "")] = to_grid(tiv, np.abs(vv), grid)

    # ── CPU ─────────────────────────────────────────────────────
    cp, tcp, mcp = win(ulog, "cpuload", t0, t1)
    if cp is not None:
        for src, dst in (("load", "cpu"), ("ram_usage", "ram")):
            if src in cp.data:
                trk[dst] = to_grid(tcp, clean(cp.data[src][mcp], 10.0) * 100, grid)

    # ── 배터리 ──────────────────────────────────────────────────
    b, tb, mb = win(ulog, "battery_status", t0, t1)
    if b is not None:
        trk["cur"] = to_grid(tb, clean(b.data["current_a"][mb], 1000.0), grid)
        trk["volt"] = to_grid(tb, clean(b.data["voltage_v"][mb], 200.0), grid)

    # ── 조종 입력 ───────────────────────────────────────────────
    mc, tm, mm = win(ulog, "manual_control_setpoint", t0, t1)
    if mc is not None:
        for k in ("roll", "pitch", "yaw", "throttle"):
            if k in mc.data:
                trk["stick_" + k] = to_grid(tm, clean(mc.data[k][mm], 10.0), grid)

    # ── 모터 ────────────────────────────────────────────────────
    mo, tmo, mmo = win(ulog, "actuator_motors", t0, t1)
    if mo is not None:
        chans = live_motor_channels(mo, mmo)
        trk["motors"] = {str(i): to_grid(tmo, clean(mo.data["control[%d]" % i][mmo], 10.0), grid)
                         for i in chans}

    # ── 비행모드 밴드 (리샘플하지 않는다 — 전환 지점 그대로) ─────
    s, ts, ms = win(ulog, "vehicle_status", t0, t1)
    if s is not None:
        tr = qgclog.transitions(ts, s.data["nav_state"][ms], qgclog.NAV_STATE)
        trk["modes"] = [{"t": round(float(x), 2), "name": str(v)} for x, v in tr]
    else:
        # `vehicle_status` 가 통째로 없는 로그가 있다 (실측: log_182, 디코딩 89.2%).
        # 그러면 모드 밴드도 읽기 패널의 '모드' 도 비어 버린다. 제어 플래그로
        # 대신 세운다 — nav_state 만큼 세밀하진 않지만 어느 계열인지는 알려준다.
        c, tc, mc_ = win(ulog, "vehicle_control_mode", t0, t1)
        if c is not None:
            def flag(k):
                return c.data[k][mc_].astype(bool) if k in c.data else np.zeros(mc_.sum(), bool)
            auto, pos = flag("flag_control_auto_enabled"), flag("flag_control_position_enabled")
            alt, man = flag("flag_control_altitude_enabled"), flag("flag_control_manual_enabled")
            code = np.where(auto, 3, np.where(pos & man, 2,
                            np.where(alt & man, 1, np.where(man, 0, 4))))
            NAMES = {0: "MANUAL~", 1: "ALTCTL~", 2: "POSCTL~", 3: "AUTO~", 4: "?"}
            tr = qgclog.transitions(tc, code)
            trk["modes"] = [{"t": round(float(x), 2), "name": NAMES.get(int(v), "?")}
                            for x, v in tr]
            # 물결표는 '추정' 이라는 표시다. 화면에서 그대로 보인다.
            trk["modes_estimated"] = True

    # ── 착륙(접지) 구간 ────────────────────────────────────────
    # 접지 뒤에도 EKF 는 값을 계속 낸다. 지면효과로 기압이 흔들려 고도가
    # 몇 십 cm 올라가고 상승률이 +로 뒤집히는데, 표시가 없으면 "착륙 직전에
    # 다시 떴다" 로 읽힌다 (실측 log_184: 198.7s 접지 후 AGL 1.24→1.43 m).
    # 그 구간을 밴드로 덮어 "여기부터는 비행이 아니다" 를 눈에 보이게 한다.
    ld, tld, mld = win(ulog, "vehicle_land_detected", t0, t1)
    if ld is not None and "landed" in ld.data:
        lv = ld.data["landed"][mld].astype(bool)
        spans, st = [], None
        for tt, v in zip(tld, lv):
            if v and st is None:
                st = float(tt)
            elif not v and st is not None:
                spans.append([round(st, 2), round(float(tt), 2)]); st = None
        if st is not None:
            # 접지한 채로 로그가 끝나면 마지막 샘플이 아니라 **구간 끝까지** 덮는다.
            # 실측(log_184): landed=1 샘플이 198.8s 하나뿐인데 창은 199.75s 까지다.
            # 마지막 샘플로 닫으면 폭 0 이 되어 정작 볼 구간이 사라진다.
            spans.append([round(st, 2), round(dur, 2)])
        # 이륙 직전까지의 '아직 땅' 구간은 덮지 않는다 — 가릴 것이 없다.
        # 스치듯 뜨는 한두 샘플짜리 판정도 버린다.
        trk["landed_spans"] = [a for a in spans
                               if a[1] - a[0] >= 0.5 and a[1] > dur * 0.5]

    # failsafe 는 vehicle_status 가 있을 때만 읽는다 (위 else 로 들어온 로그엔 없다)
    if s is not None and "failsafe" in s.data:
        fs = qgclog.transitions(ts, s.data["failsafe"][ms].astype(int))
        trk["failsafe"] = [{"t": round(float(x), 2), "on": bool(v)} for x, v in fs]

    # ── failsafe 플래그별 구간 ──────────────────────────────────
    f, tf, mf = win(ulog, "failsafe_flags", t0, t1)
    if f is not None:
        flags = {}
        for k, v in f.data.items():
            if k.startswith("timestamp"):
                continue
            vv = v[mf]
            if not vv.size or not set(np.unique(vv)).issubset({0, 1}) or not vv.any():
                continue
            flags[k] = [{"t": round(float(x), 2), "on": bool(y)}
                        for x, y in qgclog.transitions(tf, vv.astype(int))]
        if flags:
            trk["flags"] = flags

    # ── FC 메시지 ───────────────────────────────────────────────
    ev = []
    for m in ulog.logged_messages:
        rt = m.timestamp / 1e6 - t0
        if -1.0 <= rt <= (t1 - t0) + 1.0:
            ev.append({"t": round(rt, 2),
                       "lvl": qgclog._log_level(m),
                       "lvl_str": m.log_level_str(),
                       "msg": m.message.strip()})
    trk["events"] = ev[:MAX_EVENTS]
    return trk


def flight_key(ulog, t0, t1):
    """같은 비행을 가리키는 열쇠. 파일명이 달라도 이걸로 묶인다.

    FC 는 로그를 `/fs/microsd/log/<날짜>/<HH_MM_SS>.ulg` 로 저장하고, 그 경로를
    로그 안에 남긴다. QGC 로 받으면 `log_<n>_...` 로 이름이 바뀌므로 파일명으로는
    같은 비행인지 알 수 없다 — 실측으로 한 비행이 두 줄로 보이는 경우가 4쌍 있었다.
    경로가 안 남은 로그(짧게 끊긴 것들)는 부팅시각+구간으로 대신한다.
    """
    for m in ulog.logged_messages:
        if "/fs/microsd" in m.message:
            return m.message.split()[-1]
    boot = ulog.msg_info_dict.get("boot_time_utc_us")
    if boot:
        return "boot:%s:%.0f:%.0f" % (boot, t0, t1)
    return None


def decoded_points(ulog):
    """디코딩된 샘플 수. 같은 비행의 사본 중 어느 쪽이 온전한지 고르는 데 쓴다."""
    return sum(len(d.data["timestamp"]) for d in ulog.data_list)


def classify(row):
    """목록 배지. 임계값은 skills/qgc-log/SKILL.md 의 휴리스틱 그대로.

    단정적 문장은 만들지 않는다 — 로그는 '무엇' 만 알고 '왜' 는 모른다.
    """
    if not row.get("armed"):
        return "noarm"
    dur = row.get("duration") or 0
    alt = row.get("alt_max")
    spd = row.get("speed_max")
    if alt is None or spd is None:
        return "unknown"
    if spd >= 3.0 or alt >= 10.0:
        return "flight"          # 실비행
    if dur <= 6:
        return "abort"           # 즉시 disarm — 이륙 포기이거나 지상 점검
    if alt < 0.5 and spd <= 0.5:
        return "ground"          # 지상
    return "hover"               # 저고도·저속 — 호버이거나 지상 확인


def summarize(path):
    """analyse() 를 돌리고, arm 이 없으면 예외를 잡아 최소 요약이라도 만든다."""
    try:
        rep = qgclog.analyse(path)
        rep.pop("path", None)
        rep["armed"] = True
        return rep, None
    except qgclog.LogUnreadable as exc:
        reason = str(exc)
        if "arm" not in reason:
            raise
        # arm 이 없는 지상 로그. 목록에서 사라지게 두지 않는다.
        ulog, repaired = qgclog._load(path)
        t0, t1, _ = armed_window(ulog)
        info = ulog.msg_info_dict
        return {"armed": False, "duration": t1 - t0, "t0": t0, "t1": t1,
                "hw": info.get("ver_hw", "?"), "sw": info.get("ver_sw", "?")[:12],
                "utc": qgclog.kst(info["boot_time_utc_us"]) if "boot_time_utc_us" in info else None,
                "repaired": repaired, "corrupt": bool(getattr(ulog, "file_corrupt", False)),
                "findings": [], "good": [], "msgs": [], "note": reason}, reason


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("row", "full"):
        sys.exit("사용법: extract.py row|full <path.ulg>")
    mode, path = sys.argv[1], sys.argv[2]

    try:
        rep, note = summarize(path)
    except qgclog.LogUnreadable as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return
    except Exception as exc:                                  # noqa: BLE001
        print(json.dumps({"ok": False,
                          "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return

    st = os.stat(path)
    # 정렬·표시 시각은 **파일명**이 정본이다. `boot_time_utc_us` 는 부팅 시각이라
    # 한 세션에서 나온 로그가 전부 같은 값이 된다 (실측: 같은 값 3개가 겹쳤다).
    # qgclog.list_logs() 도 같은 이유로 파일명을 쓴다.
    stamp = qgclog._time_from_name(path)
    row = {
        "name": os.path.basename(path),
        "size": st.st_size,
        "utc": stamp if stamp is not None else rep.get("utc"),
        "time_source": "filename" if stamp is not None else "boot",
        "boot_utc": rep.get("utc"),
        "duration": rep.get("duration"),
        "alt_max": rep.get("alt_max"),
        "speed_max": rep.get("speed_max"),
        "armed": rep.get("armed", True),
        "repaired": bool(rep.get("repaired")),
        "corrupt": bool(rep.get("corrupt")),
        "findings_n": len(rep.get("findings", [])),
        "cur_max": rep.get("cur_max"),
        "vib_max": rep.get("vib_max"),
        "hw": rep.get("hw"),
    }
    row["badge"] = classify(row)

    ulog, _ = qgclog._load(path)
    t0, t1, armed = armed_window(ulog)
    row["flight"] = flight_key(ulog, t0, t1)
    row["points"] = decoded_points(ulog)

    if mode == "row":
        print(json.dumps({"ok": True, "row": row}, default=coerce, ensure_ascii=False))
        return

    out = {"ok": True, "row": row, "sum": rep, "trk": build_track(ulog, t0, t1)}
    out["sum"]["uuid"] = ulog.msg_info_dict.get("sys_uuid", "?")
    if note:
        out["sum"]["note"] = note
    print(json.dumps(out, default=coerce, ensure_ascii=False))


if __name__ == "__main__":
    main()
