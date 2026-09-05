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
)

# 왜 127.0.0.1:14551 이 있나 — 브리지를 돌리는 PC 는 14550 을 브리지가 쥐고
# 있어서 라이브 페이지가 그 포트를 못 연다. 그래서 페이지는 14551 로 비켜
# 앉는데, 브리지가 거기로도 같은 스트림을 보내주지 않으면 페이지는 켜져만
# 있고 패킷 0 이다 (rim3 에서 실제로 그랬다).
# 루프백이라 외부 노출은 없다. 받는 쪽이 없으면 커널이 조용히 버린다.

BRIDGE="$(dirname "$0")/mav_bridge.py"

if [[ ! -f "$BRIDGE" ]]; then
  echo "mav_bridge.py 를 못 찾았다: $BRIDGE" >&2
  exit 1
fi

# FC 시리얼 자동 탐지. PX4 는 보통 ttyACM0.
PORT="${MAV_SERIAL:-}"
if [[ -z "$PORT" ]]; then
  for p in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0; do
    [[ -e "$p" ]] && PORT="$p" && break
  done
fi

if [[ -z "$PORT" ]]; then
  echo "FC 시리얼을 못 찾았다. USB 가 꽂혀 있나?" >&2
  echo "  ls /dev/ttyACM* /dev/ttyUSB*" >&2
  exit 1
fi

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
