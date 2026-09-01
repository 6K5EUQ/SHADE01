#!/usr/bin/env python3
"""로그가 얼마나 온전히 읽히는지 잰다.

파일 안의 DATA 메시지 수를 바이트 수준으로 세고, qgclog 가 실제로 디코딩한
포인트 수와 비교한다. 낮게 나오면 파서가 중간에 포기한 것이다 — 로그가
손상된 것이 아니라.

    python3 decode_rate.py logs/2026-08-31
    python3 decode_rate.py logs/2026-08-31/*.ulg

기준치: 2026-08-31 자 21개에서 DATA 99.36%, 실패 0개 (2026-09-01 실측).
"""
import contextlib
import glob
import io
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qgclog                                   # noqa: E402  (_patch_pyulog 적용)
from pyulog import ULog                         # noqa: E402

KNOWN = set(b'BIMFAPQRLCSOD')                   # ULog 메시지 타입


def raw_data_count(path):
    """파일 안의 DATA 메시지 수. 어긋나면 SYNC 로 재동기한다."""
    raw = open(path, 'rb').read()
    pos, count = 16, 0
    while pos + 3 <= len(raw):
        size, mtype = struct.unpack_from('<HB', raw, pos)
        end = pos + 3 + size
        if mtype in KNOWN and end <= len(raw):
            if mtype == ord('D'):
                count += 1
            pos = end
            continue
        nxt = raw.find(ULog.SYNC_BYTES, pos + 1)
        if nxt < 0:
            break
        pos = nxt + len(ULog.SYNC_BYTES)
    return count


def main():
    args = sys.argv[1:] or ['logs']
    files = []
    for a in args:
        files.extend(sorted(glob.glob(os.path.join(a, '**', '*.ulg'), recursive=True))
                     if os.path.isdir(a) else sorted(glob.glob(a)))
    if not files:
        sys.exit("ulg 파일이 없다: %s" % ' '.join(args))

    print("%-34s %10s %10s %8s" % ("로그", "파일DATA", "디코딩", "비율"))
    total_raw = total_dec = 0
    low = []
    for f in files:
        raw = raw_data_count(f)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                ulog, _ = qgclog._load(f)
            dec = sum(len(d.data['timestamp']) for d in ulog.data_list)
        except Exception as exc:
            print("%-34s %10d  실패 %s" % (os.path.basename(f)[:34], raw,
                                          type(exc).__name__))
            low.append(os.path.basename(f))
            continue
        ratio = dec / raw * 100 if raw else 0.0
        total_raw += raw
        total_dec += dec
        if ratio < 99:
            low.append(os.path.basename(f))
        print("%-34s %10d %10d %7.1f%%" % (os.path.basename(f)[:34], raw, dec, ratio))

    overall = total_dec / total_raw * 100 if total_raw else 0.0
    print("\n합계 %d → %d  (%.2f%%)" % (total_raw, total_dec, overall))
    if low:
        print("99%% 미만: %s" % ', '.join(low))
    if overall < 95:
        print("\n⚠️  95% 미만이다. _patch_pyulog() 가 안 걸렸을 수 있다 —"
              " pyulog 를 직접 부르고 있지 않은지 확인하라.")


if __name__ == '__main__':
    main()
