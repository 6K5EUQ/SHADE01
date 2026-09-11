#!/usr/bin/env python3
"""FC SD 의 /fs/microsd/etc/extras.txt 를 받아 두고, 새 것을 올린다.

    backup  — FC 의 현재 파일을 내려받는다 (아무것도 안 쓴다)
    verify  — 받은 백업과 올릴 파일의 첫 줄을 바이트로 대조한다
    push    — 새 파일을 올린다 (CRC32 로 확인)

🔴 push 만 FC 에 쓴다. backup/verify 는 읽기 전용이다.
"""
import argparse, os, sys, time, zlib
from pymavlink import mavutil, mavftp

REMOTE = '/fs/microsd/etc/extras.txt'


def connect(dev, baud):
    m = mavutil.mavlink_connection(dev, baud=baud)
    print('하트비트 대기...', flush=True)
    if not m.wait_heartbeat(timeout=30):
        sys.exit('하트비트 없음 — FC 가 안 붙었거나 포트를 다른 게 쥐고 있다')
    print('연결: sys %d comp %d' % (m.target_system, m.target_component), flush=True)
    # 🔴 ARM 이면 아무것도 안 한다.
    hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=10)
    armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    print('ARM 상태: %s' % ('🔴 ARMED' if armed else 'disarmed'), flush=True)
    if armed:
        sys.exit('🔴 ARM 상태다. 중단한다.')
    f = mavftp.MAVFTP(m, target_system=m.target_system,
                      target_component=m.target_component)
    return m, f


def prog(frac):
    if frac is None:
        return
    print('\r  %5.1f%%' % (frac * 100), end='', flush=True)


def do_get(f, local):
    """FC → 로컬. cmd_get 은 요청만 보내고 즉시 반환하므로 reply 를 돌려야 한다."""
    f.cmd_get([REMOTE, local], progress_callback=prog)
    ret = f.process_ftp_reply('OpenFileRO', timeout=120)
    print()
    return ret


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('backup', 'verify', 'push'))
    ap.add_argument('--dev', default='/dev/ttyACM0')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--backup', default=None, help='백업 파일 경로')
    ap.add_argument('--new', default=None, help='올릴 파일')
    a = ap.parse_args()

    if a.mode == 'verify':
        # 연결 없이 파일 두 개만 본다.
        b = open(a.backup, 'rb').read()
        n = open(a.new, 'rb').read()
        bl, nl = b.split(b'\n')[0], n.split(b'\n')[0]
        print('FC 첫 줄 : %r' % bl)
        print('새 첫 줄 : %r' % nl)
        if bl != nl:
            sys.exit('🔴 첫 줄이 다르다 — 에어스피드 센서 기동 줄이다. 중단.')
        print('✅ 첫 줄 바이트 동일')
        print('FC  %d bytes / crc32 %08x' % (len(b), zlib.crc32(b) & 0xffffffff))
        print('새  %d bytes / crc32 %08x' % (len(n), zlib.crc32(n) & 0xffffffff))
        # 줄 단위 차이 요약
        bs, ns = b.decode().splitlines(), n.decode().splitlines()
        import difflib
        d = [l for l in difflib.unified_diff(bs, ns, 'FC', 'NEW', lineterm='', n=0)]
        print('\n--- 차이 ---')
        print('\n'.join(d) if d else '(없음)')
        return

    m, f = connect(a.dev, a.baud)

    if a.mode == 'backup':
        print('받는 중: %s' % REMOTE, flush=True)
        ret = do_get(f, a.backup)
        if not os.path.exists(a.backup) or os.path.getsize(a.backup) == 0:
            sys.exit('🔴 0바이트다 — 받기 실패. ret=%s' % ret)
        d = open(a.backup, 'rb').read()
        print('✅ %d bytes  crc32 %08x  → %s'
              % (len(d), zlib.crc32(d) & 0xffffffff, a.backup))
        print(d.decode())
        return

    # ── push ─────────────────────────────────────────────────────
    new = open(a.new, 'rb').read()
    print('올리는 중: %s → %s (%d bytes)' % (a.new, REMOTE, len(new)), flush=True)
    f.cmd_put([a.new, REMOTE], progress_callback=prog)
    ret = f.process_ftp_reply('CreateFile', timeout=120)
    print()
    print('put ret: %s' % ret)

    # 🔴 되읽기는 **연결을 새로 열어서** 한다. 같은 세션으로 바로 읽으면
    #    `OpenFileRO failed, no sessions available` 이 난다 — cmd_put 의 쓰기
    #    세션이 안 닫혀서다. 2026-09-11 에 실제로 겪었고, 그때 업로드가 실패한
    #    줄 알았으나 파일은 멀쩡했다. 판정은 되읽기 CRC 로만 한다.
    m.close()
    time.sleep(2.0)
    back = a.new + '.readback'
    print('되읽는 중 (새 연결)...', flush=True)
    m, f = connect(a.dev, a.baud)
    do_get(f, back)
    got = open(back, 'rb').read()
    print('FC 되읽기 %d bytes  crc32 %08x' % (len(got), zlib.crc32(got) & 0xffffffff))
    print('올린 파일 %d bytes  crc32 %08x' % (len(new), zlib.crc32(new) & 0xffffffff))
    if got != new:
        sys.exit('🔴 되읽은 내용이 다르다. 백업으로 되돌려라.')
    print('✅ 바이트 단위 일치')
    print(got.decode())


if __name__ == '__main__':
    main()
