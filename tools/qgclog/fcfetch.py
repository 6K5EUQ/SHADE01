#!/usr/bin/env python3
"""FC 내장 SD 에서 MAVFTP 로 비행 로그를 받아온다.

  fcfetch.py ls [경로]              디렉토리 목록
  fcfetch.py get <원격> <로컬>      파일 하나 받기
  fcfetch.py fetch <YYYY-MM-DD> <출력디렉토리>   그날 로그 전부

QGC 없이 USB 만 꽂혀 있으면 된다. MAVFTP 버스트 읽기를 쓰므로
7.6MB 로그가 약 18초에 받아진다 (LOG_DATA 순차 방식은 10분 이상).
"""
import argparse
import logging
import os
import sys
import time

from pymavlink import mavftp, mavutil

logging.basicConfig(level=logging.WARNING)

LOG_ROOT = "/fs/microsd/log"


def connect(device, baud):
    m = mavutil.mavlink_connection(device, baud=baud)
    t0 = time.time()
    while time.time() - t0 < 20:
        try:
            hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
        except TypeError:
            # pymavlink 2.4.49 의 인스턴스 필드 버그. 다음 패킷으로 넘어간다.
            continue
        if hb:
            h = hb.get_header()
            m.target_system, m.target_component = h.srcSystem, h.srcComponent
            ftp = mavftp.MAVFTP(m, target_system=h.srcSystem,
                                target_component=h.srcComponent)
            ftp.ftp_settings.debug = 0
            ftp.ftp_settings.burst_read_size = 239   # 최대 버스트
            return m, ftp
    sys.exit("HEARTBEAT 없음 — FC 연결/포트 점유 확인")


def cmd_ls(ftp, path):
    """cmd_list 는 내부에서 process_ftp_reply 를 호출한다. 밖에서 또 부르면 안 된다."""
    r = ftp.cmd_list([path])
    err = getattr(r, "error_code", None)
    entries = ftp.list_result or []
    return err, entries


def cmd_get(ftp, remote, local, quiet=False):
    """cmd_get 은 요청만 보낸다. process_ftp_reply 를 돌려야 실제로 전송된다."""
    t0 = time.time()
    last = [0.0]

    def prog(frac):
        if frac is None:          # 완료 시 None 이 온다
            return
        if frac - last[0] >= 0.2:
            last[0] = frac
            if not quiet:
                print("    %.0f%%" % (frac * 100), flush=True)

    ftp.cmd_get([remote, local], progress_callback=prog)
    r = ftp.process_ftp_reply("OpenFileRO", timeout=900)
    size = os.path.getsize(local) if os.path.exists(local) else 0
    return getattr(r, "error_code", None), size, time.time() - t0


def main():
    ap = argparse.ArgumentParser(prog="fcfetch")
    ap.add_argument("mode", choices=["ls", "get", "fetch"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--device", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    a = ap.parse_args()

    m, ftp = connect(a.device, a.baud)

    if a.mode == "ls":
        path = a.args[0] if a.args else LOG_ROOT
        err, entries = cmd_ls(ftp, path)
        print("[%s] err=%s  %d개" % (path, err, len(entries)))
        for e in entries:
            kind = "DIR " if e.is_dir else "    "
            print("  %s%-20s %10s" % (kind, e.name,
                                      "" if e.is_dir else "%.2fM" % (e.size_b / 1e6)))
        return

    if a.mode == "get":
        if len(a.args) != 2:
            sys.exit("사용법: fcfetch.py get <원격경로> <로컬경로>")
        err, size, el = cmd_get(ftp, a.args[0], a.args[1])
        print("%s  %.2f MB  %.0f초  err=%s" % (a.args[1], size / 1e6, el, err))
        return

    # fetch: 하루치 전부
    if len(a.args) != 2:
        sys.exit("사용법: fcfetch.py fetch <YYYY-MM-DD> <출력디렉토리>")
    day, outdir = a.args
    os.makedirs(outdir, exist_ok=True)
    err, entries = cmd_ls(ftp, "%s/%s" % (LOG_ROOT, day))
    if err:
        sys.exit("%s 목록 조회 실패 err=%s" % (day, err))
    files = [e for e in entries if not e.is_dir and e.name.endswith(".ulg")]
    print("%s — %d개, 합계 %.1f MB" % (day, len(files),
                                       sum(e.size_b for e in files) / 1e6))
    total = time.time()
    for e in files:
        remote = "%s/%s/%s" % (LOG_ROOT, day, e.name)
        local = os.path.join(outdir, "%s_%s" % (day, e.name))
        if os.path.exists(local) and os.path.getsize(local) == e.size_b:
            print("  %-16s 이미 있음 — 건너뜀" % e.name)
            continue
        print("  %-16s %.2f MB" % (e.name, e.size_b / 1e6), flush=True)
        err, size, el = cmd_get(ftp, remote, local, quiet=True)
        ok = "OK" if size == e.size_b else "크기 불일치(%d)" % size
        print("      → %.2f MB  %.0f초  %s" % (size / 1e6, el, ok))
    print("전체 %.0f초" % (time.time() - total))


if __name__ == "__main__":
    main()
