#!/usr/bin/env python3
"""MAVFTP 다운로드 손상이 어떤 모양인지 본다. 읽기 전용.

    ftpdiag.py <원격경로> [반복횟수] [burst크기]
    ftpdiag.py /fs/microsd/log/2026-09-05/04_35_47.ulg 6 239

같은 파일을 여러 번 받아, FC 가 낸 CRC 와 일치하는 사본을 정본으로 삼고 나머지가
어디서 어떻게 다른지 짚는다. 각 손상 구간마다 **그 바이트열이 정본의 어느 위치에
있는지**를 찾아 준다 — 손상이 노이즈인지 블록 중복인지 이것으로 갈린다.

## 무엇을 알아냈나 (2026-09-09)

**손상은 직전 512바이트의 중복이다.** 손상본 4개 전부에서 깨진 구간이 정본의
`delta -512` 위치에 그대로 있었다. `burst_read_size` 와는 무정렬이다.

배제된 것: SD 카드, burst 크기(239·110 동일), 보드레이트(USB CDC-ACM 이라 명목값),
pymavlink 갭 처리(`gaps_left=0`), pymavlink 공용 임시파일(`0xAA` 오염 시험 통과).

남은 후보는 **NuttX 의 FAT/SD 계층** — PX4 응용 코드는 매 패킷 절대 오프셋으로
`lseek` 하므로 거기서 -512 가 생길 구조가 아니다.
경위는 `FLIGHT-SYNC.md` 의 「손상의 정체」.

## 쓰는 법

FC 가 USB 로 붙은 PC 에서 돌린다. **브리지를 먼저 멈춰야 한다** (시리얼 하나뿐).

    ssh rim3@rim3 'systemctl --user stop shade-bridge.service'
    scp tools/qgclog/ftpdiag.py tools/qgclog/fcfetch.py rim3@rim3:/tmp/
    ssh rim3@rim3 'cd /tmp && ~/.venv-mav/bin/python ftpdiag.py <경로> 6'
    ssh rim3@rim3 'systemctl --user start shade-bridge.service'

⚠️ 손상이 안 나오는 회차도 많다. 넉넉히 돌려라 — 정본 1개와 손상본 1개는 나와야
비교가 선다. `dataman`(0.13MB)은 늘 깨끗하므로 시험 대상으로는 로그를 써라.
"""
import hashlib, os, struct, sys, time
sys.path.insert(0, "/tmp")
import fcfetch
from pymavlink import mavftp

_caught = {}
_orig = mavftp.MAVFTP._MAVFTP__handle_crc_reply
def _patched(self, op, m):
    if op.opcode == mavftp.OP_Ack and op.size == 4:
        _caught["crc"], = struct.unpack("<I", op.payload)
    return _orig(self, op, m)
mavftp.MAVFTP._MAVFTP__handle_crc_reply = _patched

def connect_retry(device, baud, burst, tries=12):
    for _ in range(tries):
        try:
            m, ftp = fcfetch.connect(device, baud)
            if burst:
                ftp.ftp_settings.burst_read_size = burst
            return m, ftp
        except (TypeError, SystemExit):
            time.sleep(1.5)
    raise SystemExit("connect failed")

def px4_crc32(b):
    import zlib
    return zlib.crc32(b, 0xFFFFFFFF) ^ 0xFFFFFFFF

def main():
    remote = sys.argv[1]
    n      = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    burst  = int(sys.argv[3]) if len(sys.argv) > 3 else 239
    device = os.environ.get("FC_DEVICE", "/dev/ttyACM0")

    print("remote : %s\nrounds : %d\nburst  : %d\n" % (remote, n, burst), flush=True)

    copies, ref_crc = [], None
    for i in range(1, n + 1):
        m, ftp = connect_retry(device, 115200, burst)
        _caught.clear()
        ftp.cmd_crc([remote])
        c = _caught.get("crc")
        if c is not None:
            ref_crc = c
        local = "/tmp/_ftpdiag_%d.bin" % i
        if os.path.exists(local):
            os.remove(local)
        err, sz, dt = fcfetch.cmd_get(ftp, remote, local, quiet=True)
        data = open(local, "rb").read() if sz else None
        if data:
            copies.append(data)
        print("  %d: fc_crc=%s got=%s crc=%s (%.1fs)" % (
            i, "0x%08x" % c if c else "none", sz,
            "0x%08x" % px4_crc32(data) if data else "none", dt), flush=True)
        try: m.close()
        except Exception: pass
        time.sleep(4.0)

    if not copies or ref_crc is None:
        print("\nnot enough data"); return

    good = [d for d in copies if px4_crc32(d) == ref_crc]
    bad  = [d for d in copies if px4_crc32(d) != ref_crc]
    print("\n=== %d copies: %d match the FC's CRC, %d do not ===" % (len(copies), len(good), len(bad)))
    if not good:
        print("no reference copy -- cannot localise differences"); return
    if not bad:
        print("no corrupt copy this run"); return

    ref = good[0]
    BURST, SECTOR = burst, 512
    for k, d in enumerate(bad, 1):
        print("\n--- corrupt copy %d ---" % k)
        print("  length: %d (reference %d)%s" % (
            len(d), len(ref), "  SAME" if len(d) == len(ref) else "  DIFFERENT"))
        if len(d) != len(ref):
            continue
        diffs = [i for i in range(len(ref)) if ref[i] != d[i]]
        print("  differing bytes: %d of %d (%.4f%%)" % (
            len(diffs), len(ref), 100.0*len(diffs)/len(ref)))
        # group into runs
        runs, s = [], None
        for i, off in enumerate(diffs):
            if s is None:
                s = off
            elif off != diffs[i-1] + 1:
                runs.append((s, diffs[i-1])); s = off
        if s is not None:
            runs.append((s, diffs[-1]))
        print("  contiguous runs: %d" % len(runs))
        for a, b in runs[:6]:
            ln = b - a + 1
            print("    @%-8d len=%-5d  burst_off=%-4d sector_off=%-4d" % (
                a, ln, a % BURST, a % SECTOR))
            # is the corrupt region a copy of data from elsewhere in the file?
            seg = d[a:b+1]
            if len(seg) >= 8:
                pos = ref.find(seg)
                if pos >= 0 and pos != a:
                    print("       ^ this run appears in the reference at %d (delta %+d)"
                          % (pos, pos - a))
        if len(runs) > 6:
            print("    ... %d more runs" % (len(runs)-6))
        firsts = [a for a, _ in runs]
        print("  run starts mod burst(%d): %s" % (BURST, sorted(set(a % BURST for a in firsts))[:8]))
        print("  run starts mod sector(%d): %s" % (SECTOR, sorted(set(a % SECTOR for a in firsts))[:8]))

if __name__ == "__main__":
    main()
