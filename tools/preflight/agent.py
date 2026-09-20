#!/usr/bin/env python3
"""점검 에이전트 — FC 가 꽂힌 PC 에서 돌고, 웹서버가 HTTP 로 부른다.

## 왜 이게 따로 있나

웹서버는 랩서버(`ku`)에서 돌고 FC 는 정비 PC(`rim3`)에 꽂힌다. 랩서버에서
FC 를 직접 읽으려면 rim3 브리지의 **허용 목록에 랩서버를 넣어야** 하는데,
그러면 공개 웹이 도는 기계가 FC 조종 포트(14550)에 상행 권한을 얻는다.
웹서버 쪽 버그 하나가 기체로 흘러갈 수 있는 경로를 여는 셈이다.

그래서 FC 와 말하는 일은 **이 PC 안에서만** 한다. 랩서버가 보내는 것은
"점검을 돌려라" 라는 HTTP 요청 하나고, 받는 것은 JSON 판정표 하나다.
브리지 허용 목록은 손대지 않는다.

## 무엇을 하나

`preflight.py --json` 을 그대로 돌려 그 출력을 넘긴다. **판정은 여기서
하지 않는다** — 임계값은 `preflight.py` 의 `EXPECT` 한 곳에만 있고,
터미널(`./shade01 test`)과 웹이 같은 코드로 같은 답을 내야 한다.

## 읽기 전용이라는 사실은 preflight.py 가 보증한다

`preflight.py` 는 `PARAM_SET`·`COMMAND_LONG`·미션 업로드를 보내지 않는다.
이 에이전트는 그 프로그램을 인자 없이 부르는 것 외에 아무것도 안 한다 —
요청 본문으로 받은 것을 명령줄에 싣지 않는다.

## 띄우기

    SHADE_PREFLIGHT_KEY=<암호> python3 tools/preflight/agent.py

기본 바인드는 이 PC 의 Tailscale 주소다. 공인 IP 에 열리지 않게 하려는
것이다 — `0.0.0.0` 에 열면 인터넷에서 점검을 돌릴 수 있게 된다.
"""

import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PREFLIGHT = os.path.join(HERE, 'preflight.py')

PORT = int(os.environ.get('SHADE_PREFLIGHT_PORT', '4402'))
BIND = os.environ.get('SHADE_PREFLIGHT_BIND', '')
KEY = os.environ.get('SHADE_PREFLIGHT_KEY', '')
# 점검에 줄 시간. preflight 는 실측 3~6초인데, 시리얼이 바쁘면 후보를 훑느라
# 길어진다. 넉넉히 주되 무한정은 아니다 — 매달린 프로세스가 쌓이면 곤란하다.
TIMEOUT = float(os.environ.get('SHADE_PREFLIGHT_TIMEOUT', '45'))
# 🔴 연타 방지. 점검은 FC 링크를 쓰므로 여러 개가 동시에 돌면 서로 밟는다.
MIN_INTERVAL = float(os.environ.get('SHADE_PREFLIGHT_INTERVAL', '5'))


def python_bin():
    """preflight 를 돌릴 파이썬. pymavlink 가 있는 것을 고른다."""
    cands = [os.environ.get('QGCLOG_PYTHON'),
             os.path.join(REPO, '.venv', 'bin', 'python'),
             os.path.expanduser('~/shade01-venv/bin/python'),
             sys.executable]
    for c in cands:
        if not c or not os.path.exists(c):
            continue
        try:
            subprocess.run([c, '-c', 'import pymavlink'], check=True,
                           capture_output=True, timeout=15)
            return c
        except Exception:
            continue
    return None


def tailscale_ip():
    try:
        out = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True,
                             text=True, timeout=4).stdout.strip().split('\n')
        return out[0].strip() if out and out[0].strip() else None
    except Exception:
        return None


class State:
    last_run = 0.0
    running = False


def run_preflight(secs):
    py = python_bin()
    if py is None:
        return 503, {'ok': False, 'verdict': 'NO-GO', 'error':
                     'pymavlink 이 있는 파이썬을 못 찾았다',
                     'notes': ['이 PC 에 venv 를 만들어라 — '
                               '.venv/bin/pip install -r web/requirements.txt'],
                     'groups': [], 'standing': []}
    # 🔴 인자는 여기서만 만든다. 요청이 준 것은 `secs` 뿐이고 숫자로 강제한다.
    cmd = [py, PREFLIGHT, '--json', '--no-color', '-t', '%.1f' % secs]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return 504, {'ok': False, 'verdict': 'NO-GO',
                     'error': '점검이 %.0f초 안에 안 끝났다' % TIMEOUT,
                     'notes': ['FC 시리얼을 누가 쥐고 있는지 확인하라 '
                               '(fuser -v /dev/ttyACM0)'],
                     'groups': [], 'standing': []}
    try:
        return 200, json.loads(p.stdout)
    except Exception:
        # 판정을 못 읽었으면 GO 라고 하지 않는다. 깨진 것을 깨졌다고 낸다.
        return 500, {'ok': False, 'verdict': 'NO-GO',
                     'error': 'preflight 출력이 JSON 이 아니다',
                     'notes': [(p.stderr or p.stdout)[:400]],
                     'groups': [], 'standing': []}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *a):
        sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), fmt % a))

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/health':
            return self._json(200, {'ok': True, 'host': os.uname().nodename,
                                    'serial': [d for d in ('/dev/ttyACM0', '/dev/ttyACM1')
                                               if os.path.exists(d)],
                                    'running': State.running})
        if path != '/preflight':
            return self._json(404, {'error': '없는 경로'})

        if KEY and self.headers.get('X-Preflight-Key') != KEY:
            return self._json(401, {'error': '암호가 다르다'})

        if State.running:
            return self._json(409, {'ok': False, 'verdict': 'NO-GO',
                                    'error': '이미 점검이 돌고 있다',
                                    'groups': [], 'standing': []})
        wait = MIN_INTERVAL - (time.time() - State.last_run)
        if wait > 0:
            return self._json(429, {'ok': False, 'verdict': 'NO-GO',
                                    'error': '%.0f초 뒤에 다시 하라' % wait,
                                    'groups': [], 'standing': []})

        secs = 6.0
        try:
            q = self.path.split('?', 1)
            if len(q) == 2:
                for kv in q[1].split('&'):
                    k, _, v = kv.partition('=')
                    if k == 't':
                        secs = max(2.0, min(20.0, float(v)))
        except Exception:
            secs = 6.0

        State.running = True
        try:
            code, obj = run_preflight(secs)
        finally:
            State.running = False
            State.last_run = time.time()
        obj['agent'] = os.uname().nodename
        return self._json(code, obj)


def main():
    bind = BIND or tailscale_ip() or '127.0.0.1'
    if not KEY:
        sys.stderr.write(
            '⚠️  SHADE_PREFLIGHT_KEY 가 비었다 — 이 주소에 닿는 누구나 점검을 '
            '돌릴 수 있다.\n')
    srv = ThreadingHTTPServer((bind, PORT), Handler)
    sys.stderr.write('preflight agent: http://%s:%d  (preflight=%s)\n'
                     % (bind, PORT, PREFLIGHT))
    srv.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
