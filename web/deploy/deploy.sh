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

# 공개 URL 까지 실제로 도는지 본다. 200 이 아니면 실패로 끝난다.
code=$(curl -s -o /dev/null -w '%{http_code}' https://shade01.bewe.co.kr/api/health)
echo "healthcheck $code"
[ "$code" = "200" ] || { echo "❌ 공개 URL 이 200 이 아니다"; exit 1; }
curl -s https://shade01.bewe.co.kr/api/health
echo
