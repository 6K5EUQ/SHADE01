#!/usr/bin/env python3
"""로컬 트래커의 라이브 상태를 shade01.bewe.co.kr 로 밀어 올린다.

    [FC] ──USB/ELRS──> [rim3 트래커 :4400] ──HTTPS POST──> [랩서버] ──> 웹

🔴 **rim3 가 현장 노트북이다.** 비행 나갈 때 들고 나가는 PC 가 rim3 이고,
   FC 는 거기에 USB 나 ELRS 백팩으로 붙는다. 그래서 라이브 중계는 **rim3 에서
   돈다** — 다른 PC 에 켜 두면 기체가 없으므로 아무것도 안 올라간다.
   랩서버(`ku@ku-labserver`)는 웹만 돌린다. FC 를 직접 못 본다.

🔴 **한 방향뿐이다.** 여기서 하는 것은 트래커에게 GET 해서 서버로 POST 하는
   것뿐이다. 서버에서 받은 것을 FC 로 보내는 경로는 **없다.** 트래커는 여전히
   소켓에 쓰는 코드가 0줄이고, 이 스크립트도 FC 를 향해 아무것도 안 연다.
   웹에서 기체를 조작할 길은 구조적으로 존재하지 않는다.

⚠️ 인터넷이 없으면 조용히 계속 재시도한다. 로컬 화면(:4400)은 인터넷과
   무관하게 계속 돈다 — 중계가 죽어도 현장 화면은 안 죽는다.

    ./livepush.py                        # 기본값으로
    ./livepush.py --to https://shade01.bewe.co.kr --interval 1.0
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

# 서버로 올리는 주기. 1초면 웹에서 충분히 "지금" 으로 읽힌다. 더 잦게 하면
# LTE 로 올릴 때 데이터만 먹는다 (현장에서 테더링을 쓴다).
DEFAULT_INTERVAL = 1.0

# 로컬 트래커에서 읽을 때/서버로 올릴 때의 타임아웃.
LOCAL_TIMEOUT = 3.0
PUSH_TIMEOUT = 8.0

# 서버가 죽었거나 인터넷이 없을 때 물러서는 최대 간격.
BACKOFF_MAX = 30.0

# 이 시간 넘게 프레임이 없으면 굳이 안 올린다 — 서버가 알아서 「끊김」으로
# 만든다. 기체가 없는데 계속 올려 봐야 데이터만 쓴다.
IDLE_STOP_S = 120.0


def _get_local(base, since):
    """트래커에서 상태 하나를 읽는다. 항적은 증분으로 받는다."""
    url = '%s/api/state?since=%d' % (base.rstrip('/'), since)
    req = urllib.request.Request(url, headers={'Cache-Control': 'no-store'})
    with urllib.request.urlopen(req, timeout=LOCAL_TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8'))


def _push(to, key, payload):
    """서버로 올린다. 성공하면 서버 응답(dict), 실패하면 예외."""
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    req = urllib.request.Request(
        to.rstrip('/') + '/api/live/push', data=body, method='POST',
        headers={'Content-Type': 'application/json',
                 'X-Live-Key': key})
    with urllib.request.urlopen(req, timeout=PUSH_TIMEOUT) as r:
        raw = r.read().decode('utf-8') or '{}'
        return json.loads(raw)


def main():
    ap = argparse.ArgumentParser(
        description='라이브 상태를 shade01 웹으로 중계한다 (한 방향)')
    ap.add_argument('--from', dest='src',
                    default=os.environ.get('LIVE_LOCAL', 'http://127.0.0.1:4400'),
                    help='로컬 트래커 주소 (기본 http://127.0.0.1:4400)')
    ap.add_argument('--to', default=os.environ.get(
        'LIVE_PUSH_URL', 'https://shade01.bewe.co.kr'),
        help='랩서버 주소 (기본 https://shade01.bewe.co.kr)')
    ap.add_argument('--key', default=os.environ.get('LIVE_PUSH_KEY', ''),
                    help='밀어 올릴 때 쓰는 암호. 서버의 LIVE_PUSH_KEY 와 같아야 한다')
    ap.add_argument('--interval', type=float,
                    default=float(os.environ.get('LIVE_PUSH_INTERVAL',
                                                 DEFAULT_INTERVAL)),
                    help='올리는 주기(초). 기본 %.1f' % DEFAULT_INTERVAL)
    ap.add_argument('--name', default=os.environ.get('LIVE_PUSH_NAME',
                                                     socket.gethostname()),
                    help='어느 PC 가 올리는지. 화면에 뜬다 (기본 호스트명)')
    args = ap.parse_args()

    if not args.key:
        sys.exit('LIVE_PUSH_KEY 가 없다. 서버와 같은 값을 넣어라 '
                 '(~/.config/shade-live.env).')

    print('중계: %s → %s  (%.1f초마다, 이름 %s)'
          % (args.src, args.to, args.interval, args.name), flush=True)
    print('🔴 한 방향이다 — 서버에서 FC 로 가는 경로는 없다.', flush=True)

    since = 0
    backoff = 0.0
    warned_local = warned_push = False
    sent = 0
    last_live = time.monotonic()

    while True:
        t0 = time.monotonic()

        # ── 1. 로컬 트래커에서 읽는다 ──────────────────────────────
        try:
            st = _get_local(args.src, since)
            if warned_local:
                print('로컬 트래커 복구', flush=True)
                warned_local = False
        except Exception as e:
            if not warned_local:
                print('로컬 트래커를 못 읽는다 (%s) — 계속 시도한다' % e, flush=True)
                warned_local = True
            time.sleep(args.interval)
            continue

        # 기체가 오래 조용하면 올리지 않는다. 서버가 알아서 끊김으로 만든다.
        if st.get('live'):
            last_live = t0
        elif t0 - last_live > IDLE_STOP_S:
            time.sleep(args.interval)
            continue

        # ── 2. 서버로 올린다 ──────────────────────────────────────
        st['pusher'] = args.name
        try:
            resp = _push(args.to, args.key, st)
            sent += 1
            if warned_push:
                print('서버 복구 (%d번째)' % sent, flush=True)
                warned_push = False
            backoff = 0.0
            # 🔴 서버가 "나는 여기까지 받았다" 고 알려 준다. 그 다음부터 보낸다.
            #    서버가 재시작해 항적을 잃으면 0 을 돌려주고, 그러면 처음부터
            #    다시 보낸다 — 지도에 궤적이 통째로 빠지는 것을 막는다.
            nxt = resp.get('track_n')
            since = int(nxt) if isinstance(nxt, int) else st.get('track_n', since)
        except urllib.error.HTTPError as e:
            if not warned_push:
                print('서버가 거절했다 (%s %s) — 키가 맞나?'
                      % (e.code, e.reason), flush=True)
                warned_push = True
            backoff = min(BACKOFF_MAX, max(2.0, backoff * 2 or 2.0))
        except Exception as e:
            if not warned_push:
                print('서버로 못 올린다 (%s) — 인터넷이 없나? 계속 시도한다' % e,
                      flush=True)
                warned_push = True
            backoff = min(BACKOFF_MAX, max(2.0, backoff * 2 or 2.0))

        time.sleep(max(0.0, args.interval - (time.monotonic() - t0)) + backoff)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n종료')
