#!/usr/bin/env python3
"""FC 시리얼 ↔ UDP MAVLink 브리지.

기체에 탑재된 Raspberry Pi 5 에서 돈다. FC 를 USB 로 읽어
지상국(QGC)에 UDP 14550 으로 중계하고, 반대 방향도 그대로 흘린다.

    ./mav_bridge.py 100.99.120.110:14550 100.107.83.47:14550

인자로 준 주소는 "고정 대상" 이다. GCS 가 먼저 말을 걸지 않아도 텔레메트리를
밀어주므로, QGC 는 UDP 14550 을 바인딩하기만 하면 기체가 뜬다.
인자 없이 띄우면 먼저 말을 걸어온 GCS 에게만 보낸다.

환경변수:
    MAV_SERIAL   시리얼 포트 (기본 /dev/ttyACM0 — FC USB 직결)
    MAV_BAUD     보레이트   (기본 921600)
    MAV_UDP_PORT UDP 리슨 포트 (기본 14550)

pyserial 외에는 의존성이 없다. mavlink-router / MAVProxy / pymavlink 를 쓰지
않는 이유는 프레임을 해석할 필요가 없기 때문이다 — 바이트를 그대로 옮긴다.
"""

import os
import select
import socket
import sys
import time

import serial

SERIAL_PORT = os.environ.get("MAV_SERIAL", "/dev/ttyACM0")
BAUD = int(os.environ.get("MAV_BAUD", "921600"))
UDP_PORT = int(os.environ.get("MAV_UDP_PORT", "14550"))

# 이 시간 동안 아무 것도 안 보낸 GCS 는 목록에서 뺀다. 고정 대상은 영향 없다.
PEER_TIMEOUT = 30.0

# 시리얼이 사라졌을 때 다시 열어보는 간격.
REOPEN_INTERVAL = 2.0

# 한 번에 읽는 최대 바이트. MAVLink v2 최대 프레임(280B)보다 넉넉하게.
READ_CHUNK = 4096


def log(msg):
    print(msg, flush=True)


def parse_target(s):
    """'IP:PORT' 또는 'IP' (포트 생략 시 UDP_PORT)."""
    if ":" in s:
        host, _, port = s.rpartition(":")
        return (host, int(port))
    return (s, UDP_PORT)


def open_serial():
    """시리얼을 연다. 실패하면 None — 호출자가 재시도한다."""
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0)
    except (serial.SerialException, OSError) as e:
        return None, e
    return ser, None


def main():
    fixed = [parse_target(a) for a in sys.argv[1:]]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.setblocking(False)

    log("mav_bridge: serial=%s baud=%d udp=:%d" % (SERIAL_PORT, BAUD, UDP_PORT))
    if fixed:
        log("mav_bridge: fixed targets: " + ", ".join("%s:%d" % t for t in fixed))
    else:
        log("mav_bridge: no fixed targets - waiting for a GCS to speak first")

    # 최근에 패킷을 보내온 GCS. {(ip, port): 마지막 수신 시각}
    peers = {}

    ser = None
    last_open_try = 0.0
    warned_open = False

    while True:
        now = time.monotonic()

        # 시리얼이 없으면 주기적으로 다시 연다. FC 전원이 나중에 들어와도,
        # USB-시리얼이 뽑혔다 꽂혀도 여기서 회복한다.
        if ser is None:
            if now - last_open_try < REOPEN_INTERVAL:
                time.sleep(0.1)
                continue
            last_open_try = now
            ser, err = open_serial()
            if ser is None:
                if not warned_open:
                    log("mav_bridge: cannot open %s (%s) - retrying" % (SERIAL_PORT, err))
                    warned_open = True
                continue
            log("mav_bridge: serial opened: %s @ %d" % (SERIAL_PORT, BAUD))
            warned_open = False

        try:
            rlist, _, _ = select.select([ser, sock], [], [], 0.2)
        except (OSError, ValueError):
            # 시리얼 fd 가 무효해진 경우 (장치 사라짐).
            rlist = []
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            log("mav_bridge: serial went away - will reopen")
            continue

        now = time.monotonic()

        # 시리얼 → UDP (고정 대상 + 살아있는 peer)
        if ser in rlist:
            try:
                data = ser.read(READ_CHUNK)
            except (serial.SerialException, OSError) as e:
                log("mav_bridge: serial read failed (%s) - will reopen" % e)
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                continue

            if data:
                for addr in peers:
                    if now - peers[addr] > PEER_TIMEOUT:
                        continue
                    if addr in fixed:
                        continue  # 아래에서 한 번 보낸다
                    try:
                        sock.sendto(data, addr)
                    except OSError:
                        pass
                for addr in fixed:
                    try:
                        sock.sendto(data, addr)
                    except OSError:
                        pass

        # UDP → 시리얼 (양방향: 명령·파라미터 읽기/쓰기)
        if sock in rlist:
            while True:
                try:
                    data, addr = sock.recvfrom(READ_CHUNK)
                except BlockingIOError:
                    break
                except OSError:
                    break
                if not data:
                    break
                if addr not in peers:
                    log("GCS connected: %s" % (addr,))
                peers[addr] = now
                if ser is not None:
                    try:
                        ser.write(data)
                    except (serial.SerialException, OSError) as e:
                        log("mav_bridge: serial write failed (%s) - will reopen" % e)
                        try:
                            ser.close()
                        except Exception:
                            pass
                        ser = None
                        break

        # 오래된 peer 정리
        stale = [a for a, t in peers.items() if now - t > PEER_TIMEOUT]
        for a in stale:
            del peers[a]
            log("GCS timed out: %s" % (a,))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
