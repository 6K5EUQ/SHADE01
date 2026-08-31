#!/usr/bin/env python3
"""MAVLink SERIAL_CONTROL 로 PX4 NSH 셸을 열어 명령을 실행한다.

QGC 의 MAVLink Console 과 같은 경로. USB(ttyACM0)로 붙는다.
    ./pxsh.py "mavlink status"
"""
import serial, struct, sys, time

PORT = "/dev/ttyACM0"
MY_SYS, MY_COMP = 255, 190
DEV_SHELL = 10
FLAG_RESPOND, FLAG_EXCLUSIVE, FLAG_MULTI = 2, 4, 16

def crc_calc(buf, extra):
    crc = 0xFFFF
    for b in tuple(buf) + (extra,):
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc

_seq = [0]
def frame(msgid, payload, extra):
    s = _seq[0]; _seq[0] = (s + 1) & 0xFF
    hdr = struct.pack('<BBBBBBBBBB', 0xFD, len(payload), 0, 0, s, MY_SYS, MY_COMP,
                      msgid & 0xFF, (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF)
    return hdr + payload + struct.pack('<H', crc_calc(hdr[1:] + payload, extra))

def heartbeat():
    return frame(0, struct.pack('<IBBBBB', 0, 6, 8, 0, 4, 3), 50)

def serial_control(cmd):
    """SERIAL_CONTROL(126): baudrate u32, timeout u16, device u8, flags u8,
       count u8, data[70], ext target_system u8, target_component u8"""
    data = cmd.encode()[:70].ljust(70, b'\0')
    pl = (struct.pack('<IHBBB', 0, 0, DEV_SHELL, FLAG_RESPOND | FLAG_MULTI, len(cmd.encode()[:70]))
          + data + struct.pack('<BB', 1, 1))
    return frame(126, pl, 220)

def run(cmds, listen=6.0):
    s = serial.Serial(PORT, 115200, timeout=0)
    time.sleep(0.4); s.reset_input_buffer()
    for _ in range(3):
        s.write(heartbeat()); s.flush(); time.sleep(0.15)
    for c in cmds:
        s.write(serial_control(c + "\n")); s.flush(); time.sleep(0.3)

    out = bytearray(); buf = b''; t = time.time()
    while time.time() - t < listen:
        d = s.read(65536)
        if d: buf += d
        i = 0
        while i < len(buf) - 12:
            if buf[i] != 0xFD: i += 1; continue
            ln = buf[i+1]; end = i + 10 + ln + 2
            if end > len(buf): break
            mid = buf[i+7] | (buf[i+8] << 8) | (buf[i+9] << 16)
            if mid == 126:
                p = buf[i+10:i+10+ln]
                if len(p) >= 79:
                    cnt = p[8]
                    out += p[9:9+cnt]
            i = end
        buf = buf[i:] if i < len(buf) else b''
        time.sleep(0.02)
    s.close()
    return bytes(out)

if __name__ == '__main__':
    txt = run(sys.argv[1:] or ["mavlink status"])
    print(txt.decode(errors='replace') if txt else '(셸 응답 없음)')
