#!/usr/bin/env python3
"""바이트를 직접 대조해 손상이 어디서 생기는지 가른다.

    sdverify.py <원격경로> [반복횟수]
    sdverify.py /fs/microsd/log/2026-09-05/04_35_47.ulg 4

매 회차 **새 연결**로 (1) FC 에 CRC 를 묻고 (2) 파일을 실제로 받아 md5 를 낸다.
둘을 나란히 놓으면 카드가 문제인지 전송이 문제인지 갈린다.

| 결과 | 뜻 |
|---|---|
| CRC 일정 · md5 갈림 | **전송 경로가 깨뜨린다** (2026-09-09 실측) |
| CRC 갈림 · md5 일정 | CRC opcode 만 못 믿는 것 |
| 둘 다 갈림 | 그때 비로소 카드를 의심한다 |
| 둘 다 일정 | 정상 |

## 왜 fccrc.py 로는 부족한가 (2026-09-09)

`fccrc.py` 는 **한 연결에서** CRC 를 반복 호출한다. 그러면 값이 흔들리는데,
카드 탓이 아니라 PX4 의 `_workCalcFileCRC32()` 가 경로 버퍼 `_work_buffer2`(256B)
를 그대로 읽기 버퍼로 재사용하기 때문이다
(`PX4-Autopilot/src/modules/mavlink/mavlink_ftp.cpp:875`).

그 함정 때문에 9/6~9/9 사이 "SD 카드가 매번 다른 바이트를 낸다" 는 진단이
서 있었다. 매 회차 새로 연결해 재보니 **FC 가 낸 CRC 는 4회 전부 같았고**
갈린 것은 내려받은 바이트뿐이었다 — 카드가 아니라 전송이다.
경위는 `FLIGHT-SYNC.md` 의 「2026-09-09 정정」.

## 쓰는 법

FC 가 USB 로 붙어 있는 PC 에서 돌린다. **브리지를 먼저 멈춰야 한다** —
시리얼 포트가 하나뿐이다.

    ssh rim3@rim3 'systemctl --user stop shade-bridge.service'
    scp tools/qgclog/sdverify.py tools/qgclog/fcfetch.py rim3@rim3:/tmp/
    ssh rim3@rim3 'cd /tmp && ~/.venv-mav/bin/python sdverify.py <경로> 4'
    ssh rim3@rim3 'systemctl --user start shade-bridge.service'

⚠️ 읽기 전용이다. CRC 요청과 파일 읽기뿐이고 FC 에 아무것도 쓰지 않는다.
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

def connect_retry(device, baud, tries=10):
    for _ in range(tries):
        try:
            return fcfetch.connect(device, baud)
        except (TypeError, SystemExit):
            time.sleep(1.5)
    raise SystemExit("connect failed")

def px4_crc32(path):
    import zlib
    with open(path, "rb") as f:
        return zlib.crc32(f.read(), 0xFFFFFFFF) ^ 0xFFFFFFFF

def main():
    target = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    device = os.environ.get("FC_DEVICE", "/dev/ttyACM0")
    print("target: %s\nrounds: %d\n" % (target, n), flush=True)

    md5s, crcs, locs, sizes = [], [], [], []
    for i in range(1, n + 1):
        m, ftp = connect_retry(device, 115200)     # fresh session each round
        _caught.clear()
        ftp.cmd_crc([target])
        c = _caught.get("crc")
        crcs.append(c)

        local = "/tmp/_sdv_%d.bin" % i
        if os.path.exists(local):
            os.remove(local)
        err, sz, dt = fcfetch.cmd_get(ftp, target, local, quiet=True)
        h = lc = None
        if sz:
            data = open(local, "rb").read()
            h = hashlib.md5(data).hexdigest()[:12]
            lc = px4_crc32(local)
        md5s.append(h); sizes.append(sz); locs.append(lc)
        print("  %d: fc_crc=%s | got %s bytes md5=%s crc_of_bytes=%s (%.1fs) | agree=%s"
              % (i, "0x%08x" % c if c is not None else "none",
                 sz, h, "0x%08x" % lc if lc is not None else "none", dt,
                 "YES" if (c is not None and lc == c) else "no"), flush=True)
        # PX4 offers only a couple of FTP sessions and does not release one the
        # instant a transfer ends, so close the link and wait before the next
        # round asks for a fresh session. cmd_cancel() here made it worse --
        # it disturbed the session the next connect wanted to reuse.
        #
        # Rounds still fail with "no sessions available" now and then. Those
        # print as 0 bytes and drop out of the comparison rather than counting
        # as a difference, so ask for more rounds than you need: the verdict
        # wants two good downloads before it will call anything.
        try:
            m.close()
        except Exception:
            pass
        time.sleep(4.0)

    good = [x for x in md5s if x]
    u_md5, u_crc, u_loc = len(set(good)), len(set(x for x in crcs if x is not None)), len(set(x for x in locs if x is not None))
    print("\n=== RESULT ===")
    print("  sizes             : %s" % sorted(set(sizes)))
    print("  downloaded md5    : %d unique %s" % (u_md5, sorted(set(good))))
    print("  FC CalcFileCRC32  : %d unique %s" % (u_crc, ["0x%08x" % x for x in sorted(set(x for x in crcs if x is not None))]))
    print("  CRC of those bytes: %d unique %s" % (u_loc, ["0x%08x" % x for x in sorted(set(x for x in locs if x is not None))]))
    print()
    if len(good) >= 2 and u_md5 == 1 and u_crc > 1:
        print("  VERDICT: BYTES STABLE, CRC OPCODE FLAKY.")
        print("           The card returns the same data every time; CalcFileCRC32 lies.")
    elif u_md5 > 1:
        print("  VERDICT: downloaded bytes really differ -> data path corrupts")
    elif len(good) < 2:
        print("  VERDICT: inconclusive -- not enough successful downloads")
    else:
        print("  VERDICT: everything stable")

if __name__ == "__main__":
    main()
