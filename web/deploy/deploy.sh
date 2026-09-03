#!/usr/bin/env bash
# 서버에서 실행한다:  ssh ku@<서버> 'cd ~/SHADE01 && ./web/deploy/deploy.sh'
#
# 🔴 kill / fuser -k 를 쓰지 마라. Restart= 때문에 TERM 을 보내면 유닛이 죽은 채 남는다.
#    반드시 systemctl 로만 다룬다.
set -euo pipefail

cd "$(dirname "$0")/../.."          # 리포 루트
OLD=$(git rev-parse --short HEAD)

git fetch --quiet
git pull --ff-only
NEW=$(git rev-parse --short HEAD)
if [ "$OLD" = "$NEW" ]; then
  echo "변화 없음 ($NEW)"
else
  echo "$OLD → $NEW"
fi

# 파서나 추출기가 바뀌면 캐시 지문이 달라져 서버가 알아서 다시 굽는다.
sudo systemctl restart lab-shade01
sleep 2
systemctl is-active lab-shade01

# 🔴 곧바로 물으면 502 가 난다. 파서를 고친 배포에서는 캐시를 통째로 다시 굽느라
#    listen 까지 시간이 걸린다 (실측: 로그 67개에 약 7초). 그동안은 터널이
#    붙을 곳이 없어 502 다 — 실패가 아니라 아직 준비 중인 것이다.
echo -n "healthcheck "
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://shade01.bewe.co.kr/api/health" || true)
  [ "$code" = "200" ] && break
  echo -n "."
  sleep 3
done
echo " $code"
[ "$code" = "200" ] || {
  echo "❌ 60초 안에 200 이 안 나왔다"
  systemctl status lab-shade01 --no-pager -n 10 || true
  tail -20 /home/ku/shade01-data/server.log || true
  exit 1
}
curl -s https://shade01.bewe.co.kr/api/health
echo
