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

# 어느 주소에 바인딩할지. 비워두면 Tailscale 주소를 찾아 거기에만 연다.
# 0.0.0.0 을 명시하면 모든 인터페이스에 열린다 — 공인 IP 가 있는 PC 에서는 위험하다.
BIND_ADDR = os.environ.get("MAV_BIND", "")

# 이 IP 들에서 온 UDP 만 FC 로 흘린다. 고정 대상 + 로컬 + 자기 자신은 자동 포함.
# 쉼표로 더 추가할 수 있다.  MAV_ALLOW_ANY=1 이면 검사를 끈다 (권장하지 않음).
ALLOW_EXTRA = [x.strip() for x in os.environ.get("MAV_ALLOW", "").split(",") if x.strip()]
ALLOW_ANY = os.environ.get("MAV_ALLOW_ANY", "") == "1"

# Tailscale 이 쓰는 CGNAT 대역 100.64.0.0/10.
TAILSCALE_NET = (100 << 24) | (64 << 16)
TAILSCALE_MASK = 0xFFC00000

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


def ip_to_int(ip):
    try:
        a, b, c, d = (int(x) for x in ip.split("."))
    except ValueError:
        return None
    return (a << 24) | (b << 16) | (c << 8) | d


def is_tailscale(ip):
    v = ip_to_int(ip)
    return v is not None and (v & TAILSCALE_MASK) == TAILSCALE_NET


def local_addr_for(target_ip):
    """target 으로 나갈 때 커널이 고를 로컬 주소. 패킷은 보내지 않는다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 9))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def pick_bind_addr(fixed):
    """바인딩할 주소를 고른다. Tailscale 주소가 있으면 거기에만 연다."""
    if BIND_ADDR:
        return BIND_ADDR, "MAV_BIND 지정"

    # 고정 대상 중 Tailscale 주소로 나가는 경로의 로컬 주소를 쓴다.
    for host, _ in fixed:
        if is_tailscale(host):
            local = local_addr_for(host)
            if local and is_tailscale(local):
                return local, "Tailscale 자동탐지"

    # 고정 대상이 없으면 Tailscale 의 MagicDNS 주소로 경로를 물어본다.
    local = local_addr_for("100.100.100.100")
    if local and is_tailscale(local):
        return local, "Tailscale 자동탐지"

    return "0.0.0.0", "Tailscale 주소를 못 찾음"


def open_serial():
    """시리얼을 연다. 실패하면 None — 호출자가 재시도한다.

    exclusive=True 로 연다. QGC 의 autoConnectPixhawk 가 켜져 있으면 QGC 가
    같은 /dev/ttyACM* 를 먼저 잡아 FC 를 낚아채고, 브리지는 읽기가 빈 채로
    도는 좀비가 된다 — 다른 PC 에서는 기체가 그냥 사라진 것처럼 보인다.
    """
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0, exclusive=True)
    except (serial.SerialException, OSError) as e:
        return None, e
    return ser, None


def main():
    fixed = [parse_target(a) for a in sys.argv[1:]]

    bind_addr, why = pick_bind_addr(fixed)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # SO_REUSEADDR 을 켜지 않는다. 켜면 두 번째 브리지나 QGC 가 같은 포트에
    # 조용히 붙어, 커널이 패킷을 둘 중 하나에만 주면서 원격 GCS 명령이
    # 사라진다. 여기서 시끄럽게 죽는 편이 낫다.
    try:
        sock.bind((bind_addr, UDP_PORT))
    except OSError as e:
        log("mav_bridge: %s:%d 를 열 수 없다 (%s)" % (bind_addr, UDP_PORT, e))
        log("mav_bridge: 이미 브리지나 QGC 가 이 포트를 쓰고 있다. 확인:")
        log("mav_bridge:   ss -ulnp | grep %d" % UDP_PORT)
        sys.exit(1)
    sock.setblocking(False)

    # 받은 UDP 를 FC 로 흘려보낼 IP. 여기 없는 곳에서 온 것은 버린다.
    allowed = set(ALLOW_EXTRA)
    allowed.update(host for host, _ in fixed)
    allowed.update(("127.0.0.1", bind_addr))
    allowed.discard("0.0.0.0")

    log("mav_bridge: serial=%s baud=%d udp=%s:%d (%s)"
        % (SERIAL_PORT, BAUD, bind_addr, UDP_PORT, why))
    if fixed:
        log("mav_bridge: fixed targets: " + ", ".join("%s:%d" % t for t in fixed))
    else:
        log("mav_bridge: no fixed targets - waiting for a GCS to speak first")

    if ALLOW_ANY:
        log("mav_bridge: ⚠️  MAV_ALLOW_ANY=1 - 송신자 검사를 하지 않는다")
    else:
        log("mav_bridge: 허용 송신자: " + ", ".join(sorted(allowed)))

    if bind_addr == "0.0.0.0":
        log("mav_bridge: ⚠️  모든 인터페이스에 열렸다. 이 호스트에 공인 IP 가 있으면")
        log("mav_bridge: ⚠️  인터넷에서 FC 로 MAVLink 를 주입할 수 있다.")
        log("mav_bridge: ⚠️  MAV_BIND=<tailscale 주소> 로 좁혀라.")

    # 이미 거절을 알린 송신자. 로그가 넘치지 않게 IP 당 한 번만 찍는다.
    refused = set()

    # 시리얼이 끊긴 동안 명령을 버렸다고 이미 알렸는지.
    dropped_while_down = False

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
            # 시리얼이 없는 동안 소켓 버퍼에 쌓인 것을 버리고 시작한다.
            # 안 버리면 복구 직후 옛 명령이 FC 로 들어간다.
            flushed = 0
            while True:
                try:
                    sock.recvfrom(READ_CHUNK)
                    flushed += 1
                except (BlockingIOError, OSError):
                    break
            if flushed:
                log("mav_bridge: 밀려 있던 GCS 패킷 %d 개 버림" % flushed)
            dropped_while_down = False
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
                if not ALLOW_ANY and addr[0] not in allowed:
                    if addr[0] not in refused:
                        refused.add(addr[0])
                        log("mav_bridge: 거절 %s - 허용 목록에 없다 (FC 로 안 보냄)" % (addr[0],))
                    continue
                if addr not in peers:
                    log("GCS connected: %s" % (addr,))
                peers[addr] = now
                if ser is None:
                    # 시리얼이 끊긴 동안 들어온 명령은 버린다. 소켓 버퍼에
                    # 쌓아 두면 복구 순간 밀린 명령이 한꺼번에 FC 로 쏟아진다
                    # — 조종자가 이미 지나갔다고 생각한 모드 변경까지 포함해서.
                    if not dropped_while_down:
                        log("mav_bridge: 시리얼이 없다 - 그동안 들어온 GCS 명령은 버린다")
                        dropped_while_down = True
                    continue
                if True:
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
