#!/usr/bin/env bash
# 흩어진 비행로그를 모아 서버(정본 보관소)로 올린다.
#
#   web/tools/gather.sh            # 수집 + 업로드 (기본)
#   web/tools/gather.sh --local    # 수집만 (이 PC 의 logs/ 까지)
#   web/tools/gather.sh --dry      # 무엇이 올지 보여주기만
#
# 왜 이게 필요한가: `.ulg` 는 git 에서 제외돼(`*.ulg`) PC 마다 따로 쌓인다.
# flights/LOG-INVENTORY.md 가 "한 대에만 있는 것 — 그 PC 가 죽으면 사라진다" 고
# 경고하는 상태를 이 스크립트가 끝낸다.
#
# 이 PC(gram)만 세 대 전부에 SSH 가 되므로 여기서 돌린다. 서버가 개발 PC 로
# 접속할 필요가 없다.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LOCAL="$REPO/logs"

# 🔴 리포가 public 이라 호스트 주소를 여기 적지 않는다.
#    `web/tools/hosts.conf` (gitignore 됨) 에 적는다 — hosts.conf.example 참고.
#    Tailscale 이름을 쓰면 IP 없이도 된다.
CONF="$(dirname "$0")/hosts.conf"
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
else
  echo "설정이 없다: $CONF"
  echo "  cp $(dirname "$0")/hosts.conf.example $CONF  후 주소를 채워라."
  exit 1
fi
: "${SOURCES:?hosts.conf 에 SOURCES 가 없다}"
: "${SERVER:?hosts.conf 에 SERVER 가 없다}"

# 🔴 logs/ 와 QGroundControl/Logs 만 훑는다 — PX4-Autopilot/docs 와
# qgc-build/.cache 에도 .ulg 가 있는데 그건 상류 프로젝트의 시험용 파일이지
# 우리 비행로그가 아니다 (ku-dgs1 에서 4개 발견).
REMOTE_DIRS="${REMOTE_DIRS:-~/SHADE01/logs ~/SHADE01/QGroundControl/Logs}"
SERVER_LOGS="${SERVER_LOGS:-/home/ku/shade01-data/logs}"
PUBLIC_URL="${PUBLIC_URL:-https://shade01.bewe.co.kr}"

DRY=0; LOCAL_ONLY=0
for a in "$@"; do
  case "$a" in
    --dry) DRY=1 ;;
    --local) LOCAL_ONLY=1 ;;
    *) echo "모르는 인자: $a"; exit 1 ;;
  esac
done

mkdir -p "$LOCAL"
have() { ls "$LOCAL"/*.ulg 2>/dev/null | xargs -rn1 basename | sort -u; }

echo "== 수집 =="
before=$(have | wc -l)
for src in "${SOURCES[@]}"; do
  echo "-- $src"
  # 파일명\t경로. 하위 폴더(날짜별)도 훑되 평면으로 가져온다 — qgclog._repair() 가
  # 기증자를 **자기 디렉토리에서만** 찾기 때문에 한 곳에 모여 있어야 복구가 된다.
  list=$(timeout 60 ssh -o BatchMode=yes -o ConnectTimeout=15 "$src" \
    "find $REMOTE_DIRS -name '*.ulg' -type f -printf '%f\t%p\n' 2>/dev/null" || true)
  [ -n "$list" ] || { echo "   (없음 또는 접속 실패)"; continue; }
  n=0
  while IFS=$'\t' read -r name p; do
    [ -n "$name" ] || continue
    [ -e "$LOCAL/$name" ] && continue
    if [ "$DRY" = 1 ]; then echo "   [dry] $name"; n=$((n+1)); continue; fi
    if timeout 180 scp -q -o BatchMode=yes "$src:$p" "$LOCAL/$name"; then
      n=$((n+1))
    else
      echo "   ✗ $name"
    fi
  done <<< "$list"
  echo "   새로 $n개"
done
echo "로컬 $(before=$before; have | wc -l)개 (이전 $before개)"

# 같은 이름에 다른 내용이 있으면 위험하다. 실측상 지금까지는 없었다.
dupname=$(ls "$LOCAL"/*.ulg 2>/dev/null | xargs -rn1 basename | sort | uniq -d | wc -l)
[ "$dupname" = "0" ] || echo "⚠️ 이름 중복 $dupname 건 — 확인 필요"

[ "$LOCAL_ONLY" = 1 ] && exit 0
[ "$DRY" = 1 ] && exit 0

echo "== 서버로 업로드 =="
# rsync 가 있으면 그걸 쓴다(중복 전송 없음). 없으면 scp 로 없는 것만.
if command -v rsync >/dev/null && timeout 20 ssh -o BatchMode=yes "$SERVER" 'command -v rsync' >/dev/null 2>&1; then
  ssh -o BatchMode=yes "$SERVER" "mkdir -p '$SERVER_LOGS'"
  rsync -a --ignore-existing --info=stats1 "$LOCAL"/*.ulg "$SERVER:$SERVER_LOGS/"
else
  echo "rsync 없음 — scp 로 없는 것만 보낸다"
  remote=$(ssh -o BatchMode=yes "$SERVER" "mkdir -p '$SERVER_LOGS'; ls '$SERVER_LOGS' 2>/dev/null | sort")
  for f in "$LOCAL"/*.ulg; do
    b=$(basename "$f")
    grep -qxF "$b" <<< "$remote" || scp -q "$f" "$SERVER:$SERVER_LOGS/"
  done
fi

echo "== 서버 반영 =="
# 서버는 재시작 시 새 .ulg 를 찾아 캐시를 굽는다. 실측: 67개에 약 7초.
ssh -o BatchMode=yes "$SERVER" 'sudo systemctl restart lab-shade01' || true
sleep 8
curl -s "$PUBLIC_URL/api/health" || true
echo
