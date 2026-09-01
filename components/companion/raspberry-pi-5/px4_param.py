#!/usr/bin/env python3
"""PX4 파라미터를 시리얼로 직접 읽고 쓴다.

pymavlink 없이 MAVLink v2 프레임을 손으로 만든다. QGC 를 띄울 수 없는
상황(헤드리스 기지, 링크 불안정)에서 파라미터 한두 개를 확인·수정할 때 쓴다.

    ./px4_param.py get SENS_DPRES_OFF
    ./px4_param.py set SENS_DPRES_OFF 0.0
    ./px4_param.py set COM_ARM_WO_GPS 0 --type int32

⚠️ 브리지와 동시에 못 쓴다 — 같은 시리얼 포트를 연다. 먼저 내려라:

    sudo systemctl stop mavlink-bridge.service
    ./px4_param.py get SENS_DPRES_OFF
    sudo systemctl start mavlink-bridge.service

환경변수 MAV_SERIAL / MAV_BAUD 는 mav_bridge.py 와 같다.
"""

import argparse
import os
import struct
import sys
import time

import serial

SERIAL_PORT = os.environ.get("MAV_SERIAL", "/dev/ttyACM0")
BAUD = int(os.environ.get("MAV_BAUD", "921600"))

# 우리가 흉내내는 GCS 의 신원. QGC 기본값(255/190)과 겹치지 않게 잡는다.
MY_SYS = 254
MY_COMP = 190

# 상대 (PX4 기본)
TARGET_SYS = 1
TARGET_COMP = 1

MSG_PARAM_REQUEST_READ = 20
MSG_PARAM_SET = 23
MSG_PARAM_VALUE = 22

# MAV_PARAM_TYPE
PARAM_TYPES = {
    "int8": 2, "uint8": 1, "int16": 4, "uint16": 3,
    "int32": 6, "uint32": 5, "real32": 9, "float": 9,
}

STX_V2 = 0xFD

# MAVLink CRC_EXTRA — 메시지별 상수. 이 세 개만 필요하다.
CRC_EXTRA = {
    MSG_PARAM_REQUEST_READ: 214,
    MSG_PARAM_VALUE: 220,
    MSG_PARAM_SET: 168,
}


def x25_crc(data, crc=0xFFFF):
    for b in data:
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def build_v2(msgid, payload, seq):
    """MAVLink v2 프레임 한 개. 서명·확장 없음."""
    # 뒤쪽 0 바이트는 잘라 보내도 된다 (payload truncation).
    p = payload.rstrip(b"\x00")
    hdr = struct.pack(
        "<BBBBBBBB",
        STX_V2, len(p), 0, 0, seq, MY_SYS, MY_COMP,
        msgid & 0xFF,
    ) + struct.pack("<BB", (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF)
    crc = x25_crc(hdr[1:] + p)
    crc = x25_crc(bytes([CRC_EXTRA[msgid]]), crc)
    return hdr + p + struct.pack("<H", crc)


def parse_stream(buf):
    """buf 에서 완성된 v2 프레임을 뽑아 (msgid, payload) 로 내놓는다."""
    out = []
    i = 0
    while i < len(buf):
        if buf[i] != STX_V2:
            i += 1
            continue
        if len(buf) - i < 12:
            break
        plen = buf[i + 1]
        incompat = buf[i + 2]
        total = 12 + plen + (13 if incompat & 0x01 else 0)
        if len(buf) - i < total:
            break
        msgid = buf[i + 7] | (buf[i + 8] << 8) | (buf[i + 9] << 16)
        payload = buf[i + 10:i + 10 + plen]
        out.append((msgid, payload))
        i += total
    return out, buf[i:]


def decode_param_value(payload):
    """PARAM_VALUE: float value, uint16 count, uint16 index, char[16] id, uint8 type."""
    p = payload.ljust(25, b"\x00")
    value, count, index = struct.unpack("<fHH", p[0:8])
    pid = p[8:24].split(b"\x00")[0].decode("ascii", "replace")
    ptype = p[24]
    return pid, value, ptype, index, count


def reinterpret(value_float, ptype):
    """PX4 는 정수 파라미터도 PARAM_VALUE 의 float 칸에 비트 그대로 실어 보낸다."""
    raw = struct.pack("<f", value_float)
    if ptype in (1, 2):
        return struct.unpack("<b", raw[0:1])[0] if ptype == 2 else struct.unpack("<B", raw[0:1])[0]
    if ptype in (3, 4):
        return struct.unpack("<h", raw[0:2])[0] if ptype == 4 else struct.unpack("<H", raw[0:2])[0]
    if ptype in (5, 6):
        return struct.unpack("<i", raw)[0] if ptype == 6 else struct.unpack("<I", raw)[0]
    return value_float


def wait_for(ser, want_id, timeout=3.0):
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = ser.read(4096)
        if chunk:
            buf += chunk
            frames, buf = parse_stream(buf)
            for msgid, payload in frames:
                if msgid != MSG_PARAM_VALUE:
                    continue
                pid, value, ptype, index, count = decode_param_value(payload)
                if pid == want_id:
                    return pid, value, ptype, index, count
        else:
            time.sleep(0.01)
    return None


def cmd_get(ser, name, seq):
    # v2 는 필드를 크기 내림차순으로 재배열한다: int16 param_index, uint8 x2, char[16].
    payload = (struct.pack("<hBB", -1, TARGET_SYS, TARGET_COMP)
               + name.encode("ascii").ljust(16, b"\x00"))
    ser.write(build_v2(MSG_PARAM_REQUEST_READ, payload, seq))
    got = wait_for(ser, name)
    if got is None:
        print("no reply for %s" % name, file=sys.stderr)
        return 1
    pid, value, ptype, index, count = got
    print("%s = %s  (type=%d index=%d of %d)" % (pid, reinterpret(value, ptype), ptype, index, count))
    return 0


def cmd_set(ser, name, value, type_name, seq):
    ptype = PARAM_TYPES[type_name]
    if ptype == 9:
        raw = struct.pack("<f", float(value))
    elif ptype == 6:
        raw = struct.pack("<i", int(value))
    elif ptype == 5:
        raw = struct.pack("<I", int(value))
    elif ptype == 4:
        raw = struct.pack("<h", int(value)) + b"\x00\x00"
    elif ptype == 3:
        raw = struct.pack("<H", int(value)) + b"\x00\x00"
    elif ptype == 2:
        raw = struct.pack("<b", int(value)) + b"\x00\x00\x00"
    else:
        raw = struct.pack("<B", int(value)) + b"\x00\x00\x00"

    payload = raw + struct.pack("<BB", TARGET_SYS, TARGET_COMP) \
        + name.encode("ascii").ljust(16, b"\x00") + struct.pack("<B", ptype)
    ser.write(build_v2(MSG_PARAM_SET, payload, seq))

    got = wait_for(ser, name)
    if got is None:
        print("no confirmation for %s - value may not be applied" % name, file=sys.stderr)
        return 1
    pid, v, t, index, count = got
    print("%s = %s  (confirmed)" % (pid, reinterpret(v, t)))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get", help="파라미터 하나 읽기")
    g.add_argument("name")

    s = sub.add_parser("set", help="파라미터 하나 쓰기")
    s.add_argument("name")
    s.add_argument("value")
    s.add_argument("--type", default="real32", choices=sorted(PARAM_TYPES),
                   help="기본 real32. 정수 파라미터는 int32 등으로 지정")

    args = ap.parse_args()

    if len(args.name) > 16:
        print("param name too long (max 16): %s" % args.name, file=sys.stderr)
        return 2

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0)
    except (serial.SerialException, OSError) as e:
        print("cannot open %s: %s" % (SERIAL_PORT, e), file=sys.stderr)
        print("(브리지가 포트를 잡고 있으면 먼저 내려라: "
              "sudo systemctl stop mavlink-bridge.service)", file=sys.stderr)
        return 2

    with ser:
        if args.cmd == "get":
            return cmd_get(ser, args.name, 0)
        return cmd_set(ser, args.name, args.value, args.type, 0)


if __name__ == "__main__":
    sys.exit(main())
