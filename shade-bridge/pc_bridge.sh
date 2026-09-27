#!/usr/bin/env bash
# FC 를 USB 로 직결한 PC 에서 실행한다. 다른 PC 의 QGC 가 Tailscale 로 붙는다.
#
#   ./pc_bridge.sh
#
# raspb1 이 FC USB 를 잡고 있으면 이 스크립트는 쓰지 않는다 (FC USB 는 하나뿐).
# 펌웨어 작업 등으로 raspb1 USB 를 뽑고 PC 에 직결했을 때만 쓴다.

set -u

# 중계 대상. 자기 자신도 넣어 로컬 QGC 가 붙게 한다.
TARGETS=(
  100.99.120.110:14550   # ku-dgs1
  100.107.83.47:14550    # rim
  100.117.47.105:14550   # rim3
  100.66.204.25:14550    # gram-labtop
  127.0.0.1:14551        # 이 PC 의 라이브 트래킹 (./qgc live on 14551)
  100.107.83.47:14551    # rim 의 라이브 트래킹 — QGC 가 14550 을 쥐고 있다
)

# 왜 :14551 대상이 둘이나 있나 — 어떤 PC 는 14550 을 이미 다른 것이 쥐고 있어서
# 라이브 페이지가 그 포트를 못 연다. 페이지는 14551 로 비켜 앉는데, 브리지가
# 거기로도 같은 스트림을 보내주지 않으면 페이지는 켜져만 있고 패킷 0 이다.
#   127.0.0.1  브리지 자신이 14550 을 쥔다 (rim3 에서 실제로 그랬다)
#   rim        QGC 가 14550 을 쥔다 (22시간째 떠 있는 상주 지상국이다)
# 14551 은 전부 **읽기 전용 트래커**다 — 그쪽에서 FC 로 돌아오는 바이트가 없다.
# 🔴 그 단방향을 **브리지가 강제한다** (2026-09-17). mav_bridge.py 의
#    READONLY_PORTS 가 14551 에서 온 UDP 를 FC 로 안 보낸다. 허용 목록은
#    IP 기준이라 트래커가 같은 호스트에 있으면 그것만으로는 못 막는다.
# 받는 쪽이 없으면 커널이 조용히 버리므로, 트래커를 안 켠 PC 에도 무해하다.

BRIDGE="$(dirname "$0")/mav_bridge.py"

if [[ ! -f "$BRIDGE" ]]; then
  echo "mav_bridge.py 를 못 찾았다: $BRIDGE" >&2
  exit 1
fi

# FC 시리얼 — 이 기체의 FC(Pixhawk 6C)만 잡는다. USB id 로 고른다.
# 🔴 ttyACM0 을 그대로 잡지 마라 — 무엇이 꽂히든 잡아 그 텔레메트리가 이 기체의
#    라이브·기록·웹으로 섞인다.
# by-id 링크 그대로 넘긴다 — 브리지가 다시 열 때도 이 FC 만 열린다.
# ttyACM0 으로 풀어 넘기면 뽑고 다른 FC 를 꽂았을 때 그것이 열린다.
# 없으면 꽂힐 때까지 조용히 기다린다 (서비스가 재시작 루프를 돌지 않게).
PORT="${MAV_SERIAL:-}"
waited=0
while [[ -z "$PORT" ]]; do
  for p in /dev/serial/by-id/usb-Auterion*v6C*-if00; do
    [[ -e "$p" ]] && PORT="$p" && break
  done
  if [[ -z "$PORT" ]]; then
    [[ $waited -eq 0 ]] && echo "FC(Pixhawk 6C) 기다리는 중 — ls /dev/serial/by-id/" >&2
    waited=1
    sleep 3
  fi
done

if ! [[ -r "$PORT" && -w "$PORT" ]]; then
  echo "$PORT 에 접근 권한이 없다. dialout 그룹에 들어가야 한다:" >&2
  echo "  sudo usermod -aG dialout \$USER   # 후 재로그인" >&2
  exit 1
fi

echo "FC: $PORT"
echo "중계 대상: ${TARGETS[*]}"
echo "종료: Ctrl-C"
echo

MAV_SERIAL="$PORT" exec python3 "$BRIDGE" "${TARGETS[@]}"
