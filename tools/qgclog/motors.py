#!/usr/bin/env python3
"""SHADE VTOL - 실시간 모터 추력 모니터

터미널에 모터 5개의 PWM·추력비율·전류를 실시간 표시.
  python3 motors.py            자동 (USB 우선, 없으면 백팩 UDP)
  python3 motors.py usb
  python3 motors.py udp
"""
import sys, os, struct, time, glob, socket

# ---- MAVLink 최소 구현 (외부 의존성 없음) ----
X25 = 0xFFFF
def _ca(b, c):
    t = b ^ (c & 0xFF); t = (t ^ (t << 4)) & 0xFF
    return ((c >> 8) ^ (t << 8) ^ (t << 3) ^ (t >> 4)) & 0xFFFF
def _crc(pl, e):
    c = X25
    for b in pl: c = _ca(b, c)
    return _ca(e, c)
CRC_EXTRA = {0: 50, 76: 152}
_seq = [0]
def pack(mid, pl):
    h = struct.pack("<BBBBBBBBBB", 0xFD, len(pl), 0, 0, _seq[0] & 0xFF, 255, 190,
                    mid & 0xFF, (mid >> 8) & 0xFF, (mid >> 16) & 0xFF)
    _seq[0] += 1
    return h + pl + struct.pack("<H", _crc(h[1:] + pl, CRC_EXTRA[mid]))
def heartbeat():
    return pack(0, struct.pack("<IBBBBB", 0, 6, 8, 0, 4, 3))
def set_interval(msgid, us):
    return pack(76, struct.pack("<7f", msgid, us, 0, 0, 0, 0, 0)
                + struct.pack("<HBBB", 511, 1, 1, 0))

class Parser:
    def __init__(self): self.b = bytearray()
    def feed(self, d):
        self.b += d; out = []
        while True:
            i = self.b.find(b"\xfd")
            if i < 0: self.b.clear(); break
            if len(self.b) < i + 12: break
            ln = self.b[i+1]; sg = 13 if (self.b[i+2] & 1) else 0
            tot = i + 10 + ln + 2 + sg
            if len(self.b) < tot: break
            m = self.b[i+7] | (self.b[i+8] << 8) | (self.b[i+9] << 16)
            out.append((m, bytes(self.b[i+10:i+10+ln])))
            del self.b[:tot]
        return out

class SerialLink:
    def __init__(self, port, baud=115200):
        import serial
        self.s = serial.Serial(port, baud, timeout=0.05)
        self.p = Parser(); time.sleep(0.8); self.s.reset_input_buffer()
        self.name = "USB(%s)" % port
    def send(self, d):
        try: self.s.write(d)
        except Exception: pass
    def recv(self):
        try: return self.p.feed(self.s.read(16384))
        except Exception: return []
    def close(self):
        try: self.s.close()
        except Exception: pass

class UdpLink:
    def __init__(self, port=14550):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind(("0.0.0.0", port)); self.s.settimeout(0.05)
        self.peer = None; self.p = Parser()
        self.name = "UDP(%d)" % port
    def send(self, d):
        if self.peer:
            try: self.s.sendto(d, self.peer)
            except OSError: pass
    def recv(self):
        try:
            d, a = self.s.recvfrom(8192); self.peer = a
            return self.p.feed(d)
        except socket.timeout: return []
    def close(self): self.s.close()

def open_link(prefer="auto"):
    if prefer in ("auto", "usb"):
        for dev in sorted(glob.glob("/dev/ttyACM*")):
            try: return SerialLink(dev)
            except Exception: continue
    if prefer in ("auto", "udp"):
        try: return UdpLink(14550)
        except Exception: pass
    return None

# ---- 기체 설정: MAIN 채널 → 모터 이름 ----
# 실기 확인값 (2026-08): MAIN2=M1(크루즈) 3=M2 4=M3 6=M4 7=M5
MOTORS = [
    (2, "크루즈",  "Forwards"),
    (3, "우후",    "CW"),
    (4, "우전",    "CCW"),
    (6, "좌후",    "CCW"),
    (7, "좌전",    "CW"),
]
PWM_MIN, PWM_MAX = 1100, 1900

def bar(pct, width=24):
    n = int(pct * width / 100 + 0.5)
    n = max(0, min(width, n))
    return "█" * n + "·" * (width - n)

def main():
    prefer = sys.argv[1] if len(sys.argv) > 1 else "auto"
    L = open_link(prefer)
    if not L:
        print("링크 없음 (USB 미연결 & UDP 수신 없음)"); return 1
    print("링크: %s  —  Ctrl+C 로 종료" % L.name)
    time.sleep(0.5)

    hb = heartbeat()
    out = [0] * 8
    volt = curr = 0.0
    armed = False
    last_req = 0.0
    peak = [0] * 8

    try:
        while True:
            now = time.time()
            if now - last_req > 2.0:
                L.send(hb)
                L.send(set_interval(36, 50000))   # SERVO_OUTPUT_RAW 20Hz
                L.send(set_interval(1, 200000))   # SYS_STATUS 5Hz
                last_req = now

            for mid, pl in L.recv():
                if mid == 36:
                    q = pl.ljust(21, b"\0")
                    ch = struct.unpack("<8H", q[4:20])
                    out = list(ch)
                    for i, v in enumerate(ch):
                        if v > peak[i]: peak[i] = v
                elif mid == 1:
                    q = pl.ljust(31, b"\0")
                    # SYS_STATUS 필드 순서: present, enabled, health (u32 x3),
                    # load, voltage_battery (u16 x2), current_battery (i16).
                    # load 를 전압으로 읽으면 ~0.2V, 전압을 전류로 읽으면 ~250A 가 된다.
                    v = struct.unpack("<IIIHHhb", q[:19])
                    volt = v[4] / 1000.0
                    curr = v[5] / 100.0
                elif mid == 0 and len(pl) >= 9:
                    bm = struct.unpack("<IBBBBB", pl[:9])[3]
                    armed = bool(bm & 128)

            os.system("clear")
            print("=" * 60)
            print(" SHADE VTOL 모터 모니터      링크: %s" % L.name)
            print("=" * 60)
            state = "ARMED" if armed else "disarmed"
            print(" 상태: %-10s  배터리: %.2fV  전류: %.1fA" % (state, volt, curr))
            if curr > 45:
                print(" ⚠ 전류 %.1fA — XT90 연속정격(45A) 초과" % curr)
            print("-" * 60)
            print(" 모터        PWM    추력                        피크")
            for ch, name, d in MOTORS:
                v = out[ch-1] if ch-1 < len(out) else 0
                pk = peak[ch-1] if ch-1 < len(peak) else 0
                if v >= PWM_MIN:
                    pct = (v - PWM_MIN) * 100.0 / (PWM_MAX - PWM_MIN)
                else:
                    pct = 0.0
                pct = max(0.0, min(100.0, pct))
                print(" %-6s %-4s %4d  %s %5.1f%%  %4d"
                      % (name, d, v, bar(pct), pct, pk))
            print("-" * 60)
            print(" PWM %d~%d 기준 · 추력은 근사치 (실제 추력 ∝ RPM²)" % (PWM_MIN, PWM_MAX))
            time.sleep(0.15)
    except KeyboardInterrupt:
        print("\n종료")
    finally:
        L.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
