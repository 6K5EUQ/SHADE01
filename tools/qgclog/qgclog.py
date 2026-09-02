#!/usr/bin/env python3
"""QGC/PX4 ULog 로그 목록·분석 도구.

  qgclog list          최근 로그를 1..N 으로 나열 (1 = 가장 최근)
  qgclog <N>           N번 로그를 분석해 리포트 출력
  qgclog <path.ulg>    경로를 직접 지정해 분석

로그 디렉토리는 --dir, 환경변수 QGC_LOG_DIR, 그리고 아래 기본 후보 순으로 찾는다.
"""
import argparse
import contextlib
import math
import warnings
import glob
import io
import os
import re
import struct
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import numpy as np

DEFAULT_DIRS = [
    "~/QGroundControl/Logs",
    "~/Documents/QGroundControl/Logs",
    "./Logs",
]

# ── 판정 임계값 ──────────────────────────────────────────────────────
# 근거는 SHADE01 문서에 기록. 기체별로 다르면 여기만 고친다.
XT90_CONT_A = 45.0        # Holybro 커넥터 정격 (연속)
XT90_PEAK_A = 90.0        # 동 순간
CELL_LOW_V = 3.5          # 6S LiPo 셀당 경고선
VIB_WARN = 10.0           # accel_vibration_metric 경고
VIB_BAD = 30.0            # 동 위험
INNOV_WARN = 1.0          # EKF innovation test ratio 정상 상한
TILT_WARN = 45.0          # 멀티로터 자세 경고 (deg)

NAV_STATE = {
    0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION", 4: "AUTO_LOITER",
    5: "AUTO_RTL", 6: "AUTO_RCRECOVER", 7: "AUTO_RTGS", 8: "AUTO_LANDENGFAIL",
    9: "AUTO_LANDGPSFAIL", 10: "ACRO", 11: "UNUSED", 12: "DESCEND",
    13: "TERMINATION", 14: "OFFBOARD", 15: "STAB", 16: "RATTITUDE",
    17: "AUTO_TAKEOFF", 18: "AUTO_LAND", 19: "AUTO_FOLLOW_TARGET",
    20: "AUTO_PRECLAND", 21: "ORBIT", 22: "AUTO_VTOL_TAKEOFF",
}
VTOL_STATE = {0: "UNDEFINED", 1: "TRANSITION_TO_FW", 2: "TRANSITION_TO_MC",
              3: "MC", 4: "FW"}


class LogUnreadable(Exception):
    """로그를 읽을 수 없다. 호출자가 그 파일만 건너뛰게 하기 위한 신호."""


def kst(boot_us):
    """PX4 boot_time_utc_us -> KST naive datetime."""
    return (datetime.fromtimestamp(boot_us / 1e6, timezone.utc)
            + timedelta(hours=9)).replace(tzinfo=None)


def find_log_dir(explicit=None):
    if explicit:
        p = os.path.expanduser(explicit)
        if os.path.isdir(p):
            return p
        sys.exit("로그 디렉토리 없음: %s" % p)
    env = os.environ.get("QGC_LOG_DIR")
    if env:
        p = os.path.expanduser(env)
        if os.path.isdir(p):
            return p
    for cand in DEFAULT_DIRS:
        p = os.path.expanduser(cand)
        if os.path.isdir(p):
            return p
    sys.exit("로그 디렉토리를 찾지 못했다. --dir 로 지정하라.")


def list_logs(log_dir):
    """최신순 정렬. 인덱스 1 = 가장 최근."""
    out = []
    for name in os.listdir(log_dir):
        if name.lower().endswith(".ulg"):
            full = os.path.join(log_dir, name)
            out.append((os.path.getmtime(full), full))
    out.sort(reverse=True)
    return [f for _, f in out]


def _time_from_name(path):
    """log_<n>_YYYY-M-D-H-M-S.ulg 또는 YYYY-MM-DD_HH_MM_SS.ulg 에서 시각을 뽑는다.

    boot_time_utc_us 는 '부팅' 시각이라 같은 세션 로그가 전부 같은 값이 된다.
    파일명이 로그마다 다르므로 이쪽이 정확하다.
    """
    base = os.path.basename(path)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})[-_](\d{1,2})[-_](\d{2})[-_](\d{2})", base)
    if m:
        try:
            return datetime(*[int(x) for x in m.groups()])
        except ValueError:
            return None
    return None


def _why_broken(path):
    """읽기 실패 원인을 구분한다. '손상' 으로 뭉뚱그리지 않는다."""
    try:
        raw = open(path, "rb").read()
    except OSError as exc:
        return "파일 읽기 실패: %s" % exc
    if len(raw) < 16 or raw[:4] != b"ULog":
        return "ULog 헤더 아님"
    o = 16
    n = len(raw)
    while o + 3 <= n:
        ln, _ty = struct.unpack_from("<HB", raw, o)
        if o + 3 + ln > n:
            return "데이터 깨짐 — %.0f%% 지점에서 메시지 구조 붕괴" % (o / n * 100)
        o += 3 + ln
    if not _subscription_block(raw):
        return "구독 섹션 유실 — 같은 포맷의 정상 로그가 없어 복구 불가"
    return "구조는 온전하나 pyulog 가 해석 실패"


def quick_scan(path):
    """목록 표시용 최소 정보. 전체 파싱 없이 빠르게."""
    from pyulog import ULog
    # pyulog 는 미구독 메시지 id 를 stdout 으로 경고한다. 표가 깨지므로 삼킨다.
    info = {"size_mb": os.path.getsize(path) / 1e6,
            "utc": _time_from_name(path)}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ulog = ULog(path, message_name_filter_list=["actuator_armed"])
        datasets = ulog.data_list
    except Exception:
        datasets = []
    if not datasets:
        # 구독 섹션 유실 가능성 — 복구해 본다
        repaired = _repair(path)
        if repaired:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    ulog = ULog(repaired)
                datasets = ulog.data_list
                info["repaired"] = True
            except Exception:
                datasets = []
            finally:
                os.unlink(repaired)
    if not datasets:
        info["error"] = _why_broken(path)
        return info
    armed_s = 0.0
    for dataset in datasets:
        if dataset.name != "actuator_armed":
            continue
        t = dataset.data["timestamp"] / 1e6
        armed = dataset.data["armed"].astype(bool)
        if armed.any():
            armed_s = t[armed][-1] - t[armed][0]
    info["armed_s"] = armed_s
    if info.get("utc") is None:
        boot = ulog.msg_info_dict.get("boot_time_utc_us")
        if boot:
            info["utc"] = kst(boot)
    return info


def get(ulog, name):
    for dataset in ulog.data_list:
        if dataset.name == name:
            return dataset
    return None


def stat(arr, fn, default=None):
    """빈 배열이면 default. arm 구간에 그 토픽 샘플이 하나도 없으면 빈 배열이 된다.

    numpy 집계는 빈 배열에 ValueError 를 던지고, 전부 NaN 이면 float(nan) 이
    되어 리포트에 nan 이 샌다. 둘 다 여기서 막는다.
    """
    if arr is None or len(arr) == 0:
        return default
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # all-NaN slice 경고
        v = fn(arr)
    v = float(v)
    return default if math.isnan(v) else v


def _patch_pyulog():
    """포맷 정의를 잃은 토픽 하나 때문에 로그 전체를 버리지 않게 한다.

    ULog 정의 구간에 깨진 바이트가 있어 'A'(0x41) 로 오독되면 pyulog 는
    거기서 정의 읽기를 멈춘다(core.py `_read_file_definitions`). 그러면 뒤에
    오는 'F'(포맷) 정의가 통째로 유실되고, 나중에 그 토픽을 참조하는 시점에
    `message_formats[type_name]` 이 KeyError 로 터져 나온다.

    pyulog 는 데이터 구간의 손상을 이미 IndexError 로 처리한다 — 잡아서
    _file_corrupt 만 세우고 계속 읽는다. KeyError 를 그 IndexError 로 바꿔
    같은 복구 경로에 태운다. 결과적으로 포맷을 잃은 그 토픽만 빠지고
    나머지 토픽은 전부 살아난다.

    참고: message_name_filter_list 로는 못 피한다. _parse_format() 이
    필터 검사보다 먼저 돌기 때문이다.
    """
    from pyulog.core import ULog
    cls = ULog._MessageAddLogged
    if getattr(cls, "_shade_patched", False):
        return
    original = cls._parse_nested_type

    def lenient(self, prefix_str, type_name, message_formats):
        try:
            return original(self, prefix_str, type_name, message_formats)
        except KeyError as exc:
            raise IndexError("format missing for %s" % (exc,)) from exc

    cls._parse_nested_type = lenient

    # 두 번째 구멍 — 짧은 메시지 하나가 로그의 나머지를 통째로 날린다.
    #
    # 읽기 루프는 메시지 종류별로 파서를 부르는데, 그 파서들이 `struct.unpack` 을
    # 길이 검사 없이 호출한다. 본문이 잘려 있으면 struct.error 가 나고, 이 예외는
    # 루프 안쪽의 `except IndexError` 에 안 걸린 채 바깥의
    # `except struct.error: pass` 까지 올라간다 — 거기서 루프가 끝난다.
    # 파일에 데이터가 20MB 더 남아 있어도 그대로 버려진다.
    #
    # 실측(2026-09-01, `09_38_28.ulg` 23MB):
    #   손도 안 댔을 때   1.5MB 에서 멈춤 — DATA  6.1% (비행 27초로 보임)
    #   DATA 만 고쳤을 때  9.9MB 에서 멈춤 — DATA 42.7% (194초)
    #   전 메시지 일괄     끝까지 읽음    — DATA  100% (453초 = 실제)
    # 로그는 멀쩡했다. 3분짜리 비행이 27초로 보이던 것이 이 버그 때문이다.
    #
    # struct.error 를 IndexError 로 바꿔 pyulog 가 이미 가진 손상 처리 경로
    # (그 메시지만 버리고 계속 읽기)에 태운다. 헤더 파서는 건드리지 않는다 —
    # 거기서 나는 struct.error 는 진짜 EOF 라 루프가 끝나는 게 맞다.
    for attr in dir(ULog):
        if not attr.startswith(("_Message", "Message")) or attr == "_MessageHeader":
            continue
        mc = getattr(ULog, attr)
        if not isinstance(mc, type) or getattr(mc, "_shade_patched", False):
            continue
        for meth in ("__init__", "initialize"):
            fn = mc.__dict__.get(meth)
            if fn is None:
                continue
            def wrap(fn):
                def guarded(self, *args, **kwargs):
                    try:
                        return fn(self, *args, **kwargs)
                    except struct.error as exc:
                        raise IndexError("truncated message: %s" % (exc,)) from exc
                return guarded
            setattr(mc, meth, wrap(fn))
        mc._shade_patched = True

    cls._shade_patched = True


def _scan_sections(raw):
    """ULog 메시지를 훑어 (타입, offset, length) 목록을 만든다."""
    out = []
    o = 16                     # 파일 헤더 16 바이트
    n = len(raw)
    while o + 3 <= n:
        ln, ty = struct.unpack_from("<HB", raw, o)
        out.append((chr(ty) if 32 <= ty < 127 else "?", o, ln))
        o += 3 + ln
    return out


def _subscription_block(raw):
    """연속된 A(구독) 메시지 덩어리를 원본 바이트 그대로 잘라낸다."""
    for kind, off, _ln in _scan_sections(raw):
        if kind != "A":
            continue
        o = off
        blk = b""
        while o + 3 <= len(raw):
            ln, ty = struct.unpack_from("<HB", raw, o)
            if chr(ty) != "A":
                break
            blk += raw[o:o + 3 + ln]
            o += 3 + ln
        return blk
    return b""


def _repair(path):
    """구독(A) 섹션이 유실된 로그를 같은 디렉토리의 정상 로그로 복구한다.

    PX4 는 로그 앞부분에 F(포맷) → P(파라미터) → A(구독) 순으로 정의를 쓴다.
    A 가 통째로 없으면 pyulog 가 D(데이터)를 어느 토픽에 넣을지 몰라 토픽 0개가 된다.
    포맷 정의(F)가 완전히 같은 로그를 찾아 A 블록만 이식하면 읽을 수 있다.

    반환: 복구된 임시 파일 경로, 또는 복구 불가 시 None.
    """
    raw = open(path, "rb").read()
    if _subscription_block(raw):
        return None                       # 멀쩡하다

    def formats(buf):
        out = {}
        for kind, off, ln in _scan_sections(buf):
            if kind == "F":
                txt = buf[off + 3:off + 3 + ln].decode("utf-8", "replace")
                out[txt.split(":")[0]] = txt
        return out

    mine = formats(raw)
    donor_blk = None
    for cand in sorted(glob.glob(os.path.join(os.path.dirname(path) or ".", "*.ulg"))):
        if os.path.abspath(cand) == os.path.abspath(path):
            continue
        try:
            other = open(cand, "rb").read()
        except OSError:
            continue
        blk = _subscription_block(other)
        # 포맷 정의가 완전히 같아야 msg_id 매핑을 믿을 수 있다
        if blk and formats(other) == mine:
            donor_blk = blk
            break
    if not donor_blk:
        return None

    # 정의 섹션의 끝(첫 D 직전 마지막 P 뒤)에 끼워 넣는다
    insert_at = None
    for kind, off, ln in _scan_sections(raw):
        if kind == "P":
            insert_at = off + 3 + ln
        elif kind == "D":
            break
    if insert_at is None:
        return None

    fixed = tempfile.NamedTemporaryFile(suffix=".ulg", delete=False)
    fixed.write(raw[:insert_at] + donor_blk + raw[insert_at:])
    fixed.close()
    return fixed.name


def _load(path):
    """ULog 를 연다. 구독 섹션이 없으면 한 번 복구를 시도한다.

    실패하면 LogUnreadable 을 던진다 — 배치 처리에서 한 파일 때문에
    전체가 멈추지 않도록.
    """
    from pyulog import ULog
    _patch_pyulog()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ulog = ULog(path)
    except Exception as exc:
        raise LogUnreadable(_why_broken(path) or str(exc)) from exc
    if ulog.data_list:
        return ulog, False
    repaired = _repair(path)
    if not repaired:
        return ulog, False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ulog = ULog(repaired)
    except Exception:
        return ulog, False
    finally:
        os.unlink(repaired)
    return ulog, bool(ulog.data_list)


def transitions(t, values, mapping=None):
    """값이 바뀌는 지점만 (시각, 값) 으로."""
    if values is None or len(values) == 0:
        return []
    idx = np.where(np.diff(values.astype(float)) != 0)[0]
    out = [(t[0], values[0])]
    out += [(t[i + 1], values[i + 1]) for i in idx]
    if mapping:
        out = [(ts, mapping.get(int(v), str(v))) for ts, v in out]
    return out


def analyse(path):
    ulog, repaired = _load(path)
    rep = {"path": path, "findings": [], "good": [], "todo": [], "repaired": repaired,
           "corrupt": bool(getattr(ulog, "file_corrupt", False))}

    # ── 비행 구간 ────────────────────────────────────────────────
    armed = get(ulog, "actuator_armed")
    if armed is None:
        raise LogUnreadable("actuator_armed 토픽이 없다. 로그가 손상됐을 수 있다.")
    t_arm = armed.data["timestamp"] / 1e6
    is_armed = armed.data["armed"].astype(bool)
    if not is_armed.any():
        raise LogUnreadable("arm 된 구간이 없다 (지상 로그).")
    t0, t1 = t_arm[is_armed][0], t_arm[is_armed][-1]
    rep["t0"], rep["t1"] = t0, t1
    rep["duration"] = t1 - t0

    boot = ulog.msg_info_dict.get("boot_time_utc_us")
    rep["utc"] = kst(boot) if boot else None
    rep["hw"] = ulog.msg_info_dict.get("ver_hw", "?")
    rep["sw"] = ulog.msg_info_dict.get("ver_sw", "?")[:12]

    def window(dataset):
        """arm 구간으로 자른 (t, mask)."""
        t = dataset.data["timestamp"] / 1e6
        return t, (t >= t0) & (t <= t1)

    # ── 비행 모드 ────────────────────────────────────────────────
    status = get(ulog, "vehicle_status")
    if status is not None:
        t, mask = window(status)
        rep["nav"] = transitions(t[mask], status.data["nav_state"][mask], NAV_STATE)

    vtol = get(ulog, "vtol_vehicle_status")
    if vtol is not None and "vehicle_vtol_state" in vtol.data:
        t, mask = window(vtol)
        rep["vtol"] = transitions(t[mask], vtol.data["vehicle_vtol_state"][mask], VTOL_STATE)

    # ── 고도·속도 ────────────────────────────────────────────────
    pos = get(ulog, "vehicle_local_position")
    if pos is not None:
        t, mask = window(pos)
        alt = -pos.data["z"][mask]
        vz = -pos.data["vz"][mask]
        spd = np.hypot(pos.data["vx"][mask], pos.data["vy"][mask])
        alt_max = stat(alt, np.max)
        speed_max = stat(spd, np.max)
        # print_report 가 alt_max 로 게이트를 열고 speed_max 를 무조건 읽는다.
        # 둘은 같이 있거나 같이 없어야 한다.
        if alt_max is not None and speed_max is not None:
            rep["alt_max"] = alt_max
            rep["speed_max"] = speed_max
        rep["climb_max"] = stat(vz, np.max, 0.0)
        rep["descent_max"] = stat(vz, np.min, 0.0)

    # ── 배터리 ───────────────────────────────────────────────────
    batt = get(ulog, "battery_status")
    if batt is not None:
        t, mask = window(batt)
        volt = batt.data["voltage_v"][mask]
        cur = batt.data["current_a"][mask]
        cells = int(stat(batt.data.get("cell_count", [6]), np.nanmax, 6)) or 6
        v_min = stat(volt, np.min)
        v_max = stat(volt, np.max)
        # v_min 게이트가 열리면 print_report 가 형제 6개를 무조건 읽는다.
        if v_min is not None and v_max is not None:
            rep["v_min"], rep["v_max"] = v_min, v_max
            rep["cell_min"] = v_min / cells
            rep["cur_max"] = stat(cur, np.max, 0.0)
            rep["cur_mean"] = stat(cur, np.mean, 0.0)
        # discharged_mah 는 FC 부팅 후 누적치다. 이 비행분만 보려면 증가분을 써야 한다.
        dis = batt.data.get("discharged_mah")
        if dis is not None and mask.any():
            win = dis[mask]
            win = win[np.isfinite(win)]
            rep["mah"] = float(win[-1] - win[0]) if len(win) else 0.0
            rep["mah_total"] = float(win[-1]) if len(win) else 0.0
        else:
            rep["mah"] = 0.0
        rep["sag"] = stat(volt, np.max, 0.0) - stat(volt, np.min, 0.0)

        for thresh in (XT90_CONT_A, 60.0, XT90_PEAK_A):
            over = cur > thresh
            if not over.any():
                continue
            edge = np.diff(np.concatenate(([0], over.astype(int), [0])))
            starts = np.where(edge == 1)[0]
            ends = np.where(edge == -1)[0]
            tw = t[mask]
            durs = [tw[min(e, len(tw) - 1)] - tw[s] for s, e in zip(starts, ends)]
            rep.setdefault("over", []).append(
                (thresh, len(starts), float(sum(durs)), float(max(durs))))

        if rep.get("cur_max", 0.0) > XT90_CONT_A:
            rep["findings"].append(
                ("전류", "최대 %.1fA — 커넥터 연속 정격 %.0fA 초과" % (rep["cur_max"], XT90_CONT_A),
                 "비행 후 XT90 커넥터 발열 확인. 지속되면 AS150/XT120 교체"))
        if rep.get("cell_min", 99.0) < CELL_LOW_V:
            rep["findings"].append(
                ("배터리", "셀당 최저 %.2fV (경고선 %.1fV)" % (rep["cell_min"], CELL_LOW_V),
                 "부하 시 전압 강하 %.2fV. 배터리 내부저항·용량 점검" % rep["sag"]))

    # ── GPS ──────────────────────────────────────────────────────
    gps = get(ulog, "sensor_gps")
    if gps is not None:
        t, mask = window(gps)
        sats = stat(gps.data["satellites_used"][mask], np.mean)
        eph = stat(gps.data["eph"][mask], np.mean)
        epv = stat(gps.data["epv"][mask], np.mean)
        fix = stat(gps.data["fix_type"][mask], np.max)
        # sats 게이트가 열리면 eph/epv/fix 를 무조건 읽는다 — 넷은 한 묶음이다.
        if None not in (sats, eph, epv, fix):
            rep["sats"], rep["eph"], rep["epv"] = sats, eph, epv
            rep["fix"] = int(fix)
        if rep.get("sats", 0) >= 12 and rep.get("eph", 99) < 1.0:
            rep["good"].append("GPS 양호 — 위성 %.0f개, eph %.2fm" % (rep["sats"], rep["eph"]))

    # ── 진동 ─────────────────────────────────────────────────────
    imu = get(ulog, "vehicle_imu_status")
    if imu is not None:
        t, mask = window(imu)
        vib = imu.data.get("accel_vibration_metric")
        vib_mean = stat(vib[mask], np.mean) if vib is not None else None
        vib_max = stat(vib[mask], np.max) if vib is not None else None
        # vib_max 게이트가 열리면 vib_mean 을 무조건 읽는다.
        if vib_mean is not None and vib_max is not None:
            rep["vib_mean"], rep["vib_max"] = vib_mean, vib_max
            if rep["vib_max"] > VIB_BAD:
                rep["findings"].append(
                    ("진동", "accel_vibration 최대 %.1f (위험선 %.0f)" % (rep["vib_max"], VIB_BAD),
                     "프로펠러 밸런스·모터 마운트·FC 방진 점검"))
            elif rep["vib_max"] > VIB_WARN:
                rep["findings"].append(
                    ("진동", "accel_vibration 최대 %.1f (경고선 %.0f)" % (rep["vib_max"], VIB_WARN),
                     "프로펠러 밸런싱 권장. 추세 관찰"))
            else:
                rep["good"].append("진동 양호 — 최대 %.1f" % rep["vib_max"])
        clip = sum(stat(imu.data["accel_clipping[%d]" % i][mask], np.max, 0.0)
                   for i in range(3) if "accel_clipping[%d]" % i in imu.data)
        rep["clip"] = clip
        if clip > 0:
            rep["findings"].append(
                ("클리핑", "가속도계 클리핑 %d회" % clip,
                 "IMU 포화. 방진 마운트 개선 필요"))

    # ── EKF 이상 ─────────────────────────────────────────────────
    innov = get(ulog, "estimator_innovation_test_ratios")
    if innov is not None:
        t, mask = window(innov)
        bad = []
        for key, val in innov.data.items():
            if key.startswith("timestamp"):
                continue
            peak = float(np.nanmax(np.abs(val[mask]))) if val[mask].size else 0.0
            if peak > INNOV_WARN:
                bad.append((key, peak))
        rep["innov"] = sorted(bad, key=lambda x: -x[1])

    # ── 에어스피드 (VTOL 필수) ───────────────────────────────────
    asp = get(ulog, "airspeed_validated")
    if asp is not None and "true_airspeed_m_s" in asp.data:
        t, mask = window(asp)
        val = asp.data["true_airspeed_m_s"][mask]
        val = val[~np.isnan(val)]
        if val.size:
            rep["as_mean"] = stat(val, np.mean, 0.0)
            rep["as_min"] = stat(val, np.min, 0.0)
            rep["as_max"] = stat(val, np.max, 0.0)
            if rep["as_mean"] < 0:
                rep["findings"].append(
                    ("에어스피드", "평균 %.1f m/s — 음수 (물리적으로 불가)" % rep["as_mean"],
                     "피토관 튜브 역결선 또는 영점 오류. 고정익 전환 전 필수 수정"))

    # ── 자세 ─────────────────────────────────────────────────────
    att = get(ulog, "vehicle_attitude")
    land = get(ulog, "vehicle_land_detected")
    if att is not None:
        t, mask = window(att)
        q = [att.data["q[%d]" % i][mask] for i in range(4)]
        roll = np.degrees(np.arctan2(2 * (q[0] * q[1] + q[2] * q[3]),
                                     1 - 2 * (q[1] ** 2 + q[2] ** 2)))
        pitch = np.degrees(np.arcsin(np.clip(2 * (q[0] * q[2] - q[3] * q[1]), -1, 1)))
        tw = t[mask]
        tl = land.data["timestamp"] / 1e6 if land is not None else np.empty(0)
        if tl.size:
            flying = np.interp(tw, tl, land.data["landed"].astype(float)) < 0.5
        else:
            flying = np.ones(len(tw), bool)
        if flying.any():
            rep["roll_max"] = stat(np.abs(roll[flying]), np.max, 0.0)
            rep["pitch_max"] = stat(np.abs(pitch[flying]), np.max, 0.0)
            rep["tilt_t"] = float(tw[flying][np.argmax(np.abs(roll[flying]))])
            if max(rep["roll_max"], rep["pitch_max"]) > TILT_WARN:
                rep["findings"].append(
                    ("자세", "최대 경사 roll %.0f° / pitch %.0f° @ %.1fs"
                     % (rep["roll_max"], rep["pitch_max"], rep["tilt_t"]),
                     "제어 상실 의심 구간. 해당 시점 모터 출력·조종 입력 확인"))

    # ── 제어 배분 포화 ───────────────────────────────────────────
    alloc = get(ulog, "control_allocator_status")
    if alloc is not None:
        t, mask = window(alloc)
        peaks = {}
        for axis, key in enumerate(("unallocated_torque[0]", "unallocated_torque[1]",
                                    "unallocated_torque[2]", "unallocated_thrust[2]")):
            if key in alloc.data:
                peaks[key] = stat(np.abs(alloc.data[key][mask]), np.nanmax, 0.0)
        rep["alloc"] = peaks
        worst = max(peaks.values()) if peaks else 0.0
        if worst > 0.3:
            rep["findings"].append(
                ("제어 포화", "미배분 토크 최대 %.2f" % worst,
                 "모터 추력 부족 또는 기체 불균형. 무게중심·추력여유 점검"))

    # ── 자기계 간섭 ──────────────────────────────────────────────
    mag = get(ulog, "vehicle_magnetometer")
    if mag is not None and batt is not None:
        t, mask = window(mag)
        comps = [mag.data["magnetometer_ga[%d]" % i][mask] for i in range(3)]
        norm = np.sqrt(sum(c ** 2 for c in comps))
        tb, mb = window(batt)
        # np.interp 는 xp 가 비면 ValueError — 가드가 먼저 와야 한다.
        if norm.size > 10 and tb[mb].size:
            cur_i = np.interp(t[mask], tb[mb], batt.data["current_a"][mb])
            corr = float(np.corrcoef(cur_i, norm)[0, 1])
            rep["mag_corr"] = corr
            rep["mag_mean"] = stat(norm, np.mean, 0.0)
            if abs(corr) > 0.5:
                rep["findings"].append(
                    ("자기 간섭", "전류-자기장 상관 %.2f" % corr,
                     "전력선이 나침반에 간섭. GPS 마스트를 높이거나 전력선 이격"))

    # ── failsafe ────────────────────────────────────────────────
    fs = get(ulog, "failsafe_flags")
    if fs is not None:
        t, mask = window(fs)
        active = []
        for key, val in fs.data.items():
            if key == "timestamp":
                continue
            v = val[mask]
            if v.size and set(np.unique(v)).issubset({0, 1}) and v.any():
                active.append((key, stat(v, np.mean, 0.0) * 100))
        rep["failsafe"] = sorted(active, key=lambda x: -x[1])

    # ── CPU ─────────────────────────────────────────────────────
    cpu = get(ulog, "cpuload")
    if cpu is not None:
        t, mask = window(cpu)
        cpu_max = stat(cpu.data["load"][mask], np.max)
        ram_max = stat(cpu.data["ram_usage"][mask], np.max)
        # cpu_max 게이트가 열리면 ram_max 를 무조건 읽는다.
        if cpu_max is not None and ram_max is not None:
            rep["cpu_max"] = cpu_max * 100
            rep["ram_max"] = ram_max * 100
        if rep.get("cpu_max", 100) < 70:
            rep["good"].append("CPU 여유 — 최대 %.0f%%" % rep["cpu_max"])

    # ── 로그 메시지 ─────────────────────────────────────────────
    rep["msgs"] = [(m.timestamp / 1e6, m.log_level_str(), m.message)
                   for m in ulog.logged_messages if m.log_level <= 4]
    rep["dropouts"] = (len(ulog.dropouts), sum(d.duration for d in ulog.dropouts))
    return rep


def print_report(rep):
    W = 74
    print("=" * W)
    print("비행 로그 분석  %s" % os.path.basename(rep["path"]))
    print("=" * W)
    when = rep["utc"].strftime("%Y-%m-%d %H:%M:%S KST") if rep.get("utc") else "시각 불명"
    print("  일시      %s" % when)
    # 원본이 온전하지 않았다면 숫자를 믿기 전에 먼저 알린다.
    if rep.get("repaired"):
        print("  ⚠️ 출처    구독 섹션이 유실돼 **다른 로그의 정의를 이식해** 읽었다.")
        print("            토픽 이름·필드 해석이 어긋났을 수 있다. 수치를 정본으로 쓰지 마라.")
    if rep.get("corrupt"):
        print("  ⚠️ 원본    중간에 깨진 구간이 있다 (pyulog file_corrupt).")
        print("            그 구간 샘플은 빠졌다 — 비행시간·최대값이 실제보다 작을 수 있다.")
    print("  기체      %s / PX4 %s" % (rep["hw"], rep["sw"]))
    print("  비행시간  %.0f초 (%.1f분)" % (rep["duration"], rep["duration"] / 60))
    if "alt_max" in rep:
        print("  최고고도  %.1f m   최대속도 %.1f m/s" % (rep["alt_max"], rep["speed_max"]))

    if rep.get("nav"):
        print("\n[비행 모드]")
        for ts, name in rep["nav"]:
            print("  %7.1fs  %s" % (ts - rep["t0"], name))
    if rep.get("vtol"):
        states = {name for _, name in rep["vtol"]}
        print("\n[VTOL] %s" % (" → ".join(n for _, n in rep["vtol"])
                               if len(states) > 1 else "멀티로터 모드만 (고정익 전환 없음)"))

    print("\n[배터리]")
    if "v_min" in rep:
        print("  전압    %.2f ~ %.2f V   셀당 최저 %.2f V   강하 %.2f V"
              % (rep["v_min"], rep["v_max"], rep["cell_min"], rep["sag"]))
        tot = rep.get("mah_total")
        extra = "  (부팅후 누적 %.0f)" % tot if tot and tot > rep["mah"] * 1.05 else ""
        print("  전류    평균 %.1f A   최대 %.1f A   이번비행 %.0f mAh%s"
              % (rep["cur_mean"], rep["cur_max"], rep["mah"], extra))
        for thresh, cnt, total, longest in rep.get("over", []):
            print("  >%.0fA    %d회, 누적 %.1fs, 최장 연속 %.1fs" % (thresh, cnt, total, longest))

    if "sats" in rep:
        print("\n[GPS]  위성 %.0f개  eph %.2fm  epv %.2fm  fix %d"
              % (rep["sats"], rep["eph"], rep["epv"], rep["fix"]))
    if "vib_max" in rep:
        print("[진동] 평균 %.1f  최대 %.1f  클리핑 %d회"
              % (rep["vib_mean"], rep["vib_max"], int(rep.get("clip", 0))))
    if "cpu_max" in rep:
        print("[부하] CPU 최대 %.0f%%  RAM %.0f%%" % (rep["cpu_max"], rep["ram_max"]))
    if rep.get("dropouts", (0, 0))[0]:
        print("[로그] 드롭아웃 %d회 %.0fms" % rep["dropouts"])

    if rep.get("innov"):
        print("\n[EKF 이상]  test ratio > %.1f 는 센서 불일치" % INNOV_WARN)
        for key, peak in rep["innov"][:6]:
            print("  %-28s 최대 %.2f" % (key, peak))

    if rep.get("msgs"):
        print("\n[FC 경고]")
        for ts, lvl, text in rep["msgs"][:15]:
            print("  %7.1fs [%s] %s" % (ts - rep["t0"], lvl, text))

    if rep["good"]:
        print("\n" + "-" * W)
        print("잘 된 것")
        print("-" * W)
        for line in rep["good"]:
            print("  ✅ %s" % line)

    print("\n" + "-" * W)
    print("문제 (%d건)" % len(rep["findings"]))
    print("-" * W)
    if not rep["findings"]:
        print("  자동 검출된 문제 없음")
    for i, (cat, what, fix) in enumerate(rep["findings"], 1):
        print("  %d. [%s] %s" % (i, cat, what))
        print("     → %s" % fix)

    if rep.get("failsafe"):
        print("\n[failsafe 플래그]  (지상 테스트면 정상인 것 포함)")
        for key, pct in rep["failsafe"][:8]:
            print("  %-34s %.0f%% 구간" % (key, pct))
    print("=" * W)


def main():
    ap = argparse.ArgumentParser(prog="qgclog", add_help=True)
    ap.add_argument("target", nargs="?", default="list",
                    help="'list' | 번호 | .ulg 경로")
    ap.add_argument("--dir", help="로그 디렉토리")
    ap.add_argument("-n", type=int, default=15, help="목록 개수")
    args = ap.parse_args()

    if args.target.lower().endswith(".ulg"):
        target = os.path.expanduser(args.target)
        try:
            print_report(analyse(target))
        except LogUnreadable as exc:
            sys.exit("읽을 수 없다: %s\n  %s" % (os.path.basename(target), exc))
        return

    log_dir = find_log_dir(args.dir)
    logs = list_logs(log_dir)
    if not logs:
        sys.exit("ULog 파일이 없다: %s" % log_dir)

    if args.target == "list":
        print("로그 디렉토리: %s" % log_dir)
        print("%-4s %-34s %-20s %8s %8s" % ("#", "파일", "일시(KST)", "비행", "크기"))
        print("-" * 78)
        for i, path in enumerate(logs[:args.n], 1):
            info = quick_scan(path)
            if "error" in info:
                print("%-4d %-34s  파싱 실패: %s" % (i, os.path.basename(path)[:34], info["error"][:24]))
                continue
            when = info["utc"].strftime("%Y-%m-%d %H:%M") if info.get("utc") else "-"
            armed = info.get("armed_s", 0)
            flew = "%.0f초" % armed if armed else "지상"
            print("%-4d %-34s %-20s %8s %7.1fM"
                  % (i, os.path.basename(path)[:34], when, flew, info["size_mb"]))
        print("\n분석: qgclog <번호>")
        return

    try:
        idx = int(args.target)
    except ValueError:
        sys.exit("번호나 'list' 또는 .ulg 경로를 넣어라: %s" % args.target)
    if not 1 <= idx <= len(logs):
        sys.exit("범위 밖이다 (1..%d)" % len(logs))
    try:
        print_report(analyse(logs[idx - 1]))
    except LogUnreadable as exc:
        sys.exit("읽을 수 없다: %s\n  %s" % (os.path.basename(logs[idx - 1]), exc))


if __name__ == "__main__":
    main()
