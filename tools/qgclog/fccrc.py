#!/usr/bin/env python3
"""FC 가 SD 를 읽을 때 같은 바이트를 내는지 시험한다.

    fccrc.py <원격경로> [반복횟수]
    fccrc.py /fs/microsd/log/2026-09-05/09_17_20.ulg 5

같은 파일의 CRC32 를 여러 번 물어 **값이 흔들리는지** 본다. 정지된 파일이므로
값은 매번 같아야 한다. 다르면 FC 의 SD 읽기 경로가 데이터를 망가뜨리고 있다.

## 왜 이게 있나 (2026-09-06)

`./qgc sync` 를 만들며 같은 로그를 네 번 받았더니 **크기는 같고 md5 가 전부
달랐다.** 전송 문제인 줄 알았으나 **FC 자신이 계산한 CRC 도 매번 달랐다** —
읽을 때마다 다른 바이트가 나온다는 뜻이다. 오류율은 읽은 바이트에 비례했다
(0.19MB 4회 중 2종, 1.17MB 4회 중 4종 → 대략 700KB 당 1바이트).

`qgclog` 의 복구·필터 장치들이 지금까지 이걸 덮어 온 것으로 보인다:
구독 섹션 유실, 포맷 정의 유실, 가짜 FLAGS_BITS, 고도 5.03e14 m, fix_type 215.

🔴 **2026-09-09: 이 도구만으로 카드를 판정하지 마라.** 아래 "왜 값이 흔들리나" 참조.
바이트 대조는 `sdverify.py` 가 한다.

## 🔴 왜 값이 흔들리나 — 카드가 아니다 (2026-09-09)

**한 연결에서 CRC 를 연속 호출하면 값이 달라진다.** PX4 의 `_workCalcFileCRC32()` 가
경로 버퍼 `_work_buffer2`(256B)를 그대로 읽기 버퍼로 재사용하기 때문이다
(`PX4-Autopilot/src/modules/mavlink/mavlink_ftp.cpp:875`).

**매 회차 새로 연결해 재보면 CRC 는 일정하다.** 4회 전부 같은 값이 나왔고, 갈린 것은
내려받은 바이트뿐이었다 — 손상은 카드가 아니라 **MAVFTP 전송**에서 생긴다.
경위는 `FLIGHT-SYNC.md` 의 「2026-09-09 정정 — 카드가 아니라 전송 경로다」.

값이 무작위가 아니라는 신호도 있었다: `0xb436ecbc`·`0xb07bcdd5` 가 서로 다른 시행에서
재출현했다. 진짜 무작위 손상이면 32비트 공간에서 재출현하지 않는다.

→ **판정은 `sdverify.py` 로 하라.** 이 도구는 CRC opcode 하나만 본다.

## 쓰는 법

FC 가 USB 로 붙어 있는 PC 에서 돌린다. **브리지를 먼저 멈춰야 한다** —
시리얼 포트가 하나뿐이다.

    ssh rim3@rim3 'systemctl --user stop shade-bridge.service'
    scp tools/qgclog/fccrc.py tools/qgclog/fcfetch.py rim3@rim3:/tmp/
    ssh rim3@rim3 'cd /tmp && ~/.venv-mav/bin/python fccrc.py <경로> 5'
    ssh rim3@rim3 'systemctl --user start shade-bridge.service'

⚠️ 읽기 전용이다. FC 로 나가는 것은 CRC 요청뿐이고 아무것도 쓰지 않는다.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/tmp")          # FC 쪽 PC 로 복사해 쓸 때

from fcfetch import connect                                # noqa: E402
from pymavlink import mavftp                               # noqa: E402

# pymavlink 은 CRC 를 로그로만 흘리고 돌려주지 않는다. 핸들러를 감싸 가로챈다.
_caught = {}
_orig = mavftp.MAVFTP._MAVFTP__handle_crc_reply


def _patched(self, op, m):
    if op.opcode == mavftp.OP_Ack and op.size == 4:
        _caught["crc"], = struct.unpack("<I", op.payload)
    return _orig(self, op, m)


mavftp.MAVFTP._MAVFTP__handle_crc_reply = _patched


def px4_crc32(path):
    """PX4 가 쓰는 CRC32 를 로컬 파일에 대해 계산한다.

    NuttX 의 `crc32part(buf, len, 0)` 이다 — 표준 CRC-32 와 **다항식은 같지만
    초기값이 0 이고 최종 XOR 이 없다.** zlib 로는 이렇게 맞춘다:

        crc32part(d, 0) == zlib.crc32(d, 0xFFFFFFFF) ^ 0xFFFFFFFF

    (근거: PX4-Autopilot/platforms/nuttx/.../crc32.c, 실측 검증 완료)
    """
    import zlib
    with open(path, "rb") as f:
        return zlib.crc32(f.read(), 0xFFFFFFFF) ^ 0xFFFFFFFF


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip().splitlines()[2].strip())
    target = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    device = os.environ.get("FC_DEVICE", "/dev/ttyACM0")

    m, ftp = connect(device, 115200)
    vals = []
    print("파일: %s" % target)
    for i in range(1, n + 1):
        _caught.clear()
        t0 = time.time()
        r = ftp.cmd_crc([target])
        crc = _caught.get("crc")
        vals.append(crc)
        print("  %d: err=%s crc=%s (%.1f초)"
              % (i, getattr(r, "error_code", None),
                 "0x%08x" % crc if crc is not None else "없음",
                 time.time() - t0))
    m.close()

    uniq = len({v for v in vals if v is not None})
    print()
    if uniq <= 1:
        print("✅ 안정 — %d회 전부 같은 값. SD 읽기가 정상이다." % n)
    else:
        print("🔴 불안정 — %d회 중 고유값 %d개." % (n, uniq))
        print("   정지된 파일인데 읽을 때마다 다른 바이트가 나온다.")
        print("   ⚠️  한 연결에서 연속 호출하면 PX4 버퍼 재사용 탓에 흔들린다 —")
        print("      카드 판정의 근거가 못 된다. sdverify.py 로 바이트를 대조하라.")


if __name__ == "__main__":
    main()
