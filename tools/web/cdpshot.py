#!/usr/bin/env python3
"""실시간 헤드리스 스크린샷 — CDP 로 rAF 를 진짜로 돌린다.

    cdpshot.py <url> <out.png> [wait_s] [js] [WxH]

`--virtual-time-budget` 을 쓰지 마라. 그것은 setTimeout 만 앞당기고 anime 의
rAF 엔진은 첫 프레임에서 멈춘다 — 정지 화면을 찍고 통과로 오인한다.

wait_s 동안 실제 시간이 흐른 뒤 찍는다. js 는 그 대기가 **끝난 뒤** 평가되고
결과가 stdout 에 나온다 (Promise 면 await 한다). 뷰포트보다 긴 페이지는
WxH 로 창을 키워라 — `Page.captureScreenshot` 은 보이는 곳만 찍는다.
예) 라이브 뷰어 자체검사는 완주에 ~150초, 세로 3000px 가 필요하다:

    tools/web/cdpshot.py http://127.0.0.1:4400/_selftest.html /tmp/st.png 150 '' 1440x3000
"""
import base64, json, subprocess, sys, time, urllib.request, socket
import websocket

url, out = sys.argv[1], sys.argv[2]
wait = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
js = sys.argv[4] if len(sys.argv) > 4 else ''
win = sys.argv[5] if len(sys.argv) > 5 else '1440x900'
port = 9333
chrome = subprocess.Popen(['google-chrome', '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                           '--window-size=%s' % win.replace('x', ','), '--remote-debugging-port=%d' % port, '--remote-allow-origins=*', 'about:blank'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            tabs = json.load(urllib.request.urlopen('http://127.0.0.1:%d/json' % port)); break
        except Exception:
            time.sleep(0.2)
    ws = websocket.create_connection([t for t in tabs if t['type'] == 'page'][0]['webSocketDebuggerUrl'])
    n = [0]
    def call(method, **params):
        n[0] += 1; ws.send(json.dumps({'id': n[0], 'method': method, 'params': params}))
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == n[0]: return m.get('result', {})
    call('Runtime.enable'); call('Page.enable')
    logs = []
    call('Page.navigate', url=url)
    t0 = time.time()
    ws.settimeout(0.5)
    while time.time() - t0 < 1.5:
        try: m = json.loads(ws.recv())
        except Exception: continue
        if m.get('method') in ('Runtime.exceptionThrown',):
            logs.append('EXC: ' + json.dumps(m['params']['exceptionDetails'].get('exception', {}).get('description', ''))[:200])
        if m.get('method') == 'Runtime.consoleAPICalled' and m['params']['type'] in ('error', 'warning'):
            logs.append(m['params']['type'].upper() + ': ' + ' '.join(str(a.get('value', a.get('description', ''))) for a in m['params']['args'])[:200])
    # 실시간 대기 — 그동안 rAF 가 진짜로 돈다
    ws.settimeout(0.5)
    t1 = time.time()
    while time.time() - t1 < wait:
        try: m = json.loads(ws.recv())
        except Exception: continue
        if m.get('method') == 'Runtime.exceptionThrown':
            logs.append('EXC: ' + json.dumps(m['params']['exceptionDetails'].get('exception', {}).get('description', ''))[:200])
    ws.settimeout(max(15, wait))
    js_out = None
    if js:
        r = call('Runtime.evaluate', expression=js, awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in r:
            logs.append('JS: ' + json.dumps(r['exceptionDetails'])[:200])
        else:
            js_out = r.get('result', {}).get('value')
    r = call('Page.captureScreenshot', format='png')
    open(out, 'wb').write(base64.b64decode(r['data']))
    print('%s  %d B  errors=%d' % (out.split('/')[-1], len(r['data']) * 3 // 4, len(logs)))
    if js_out is not None: print('   js:', js_out)
    for l in logs[:8]: print('   ', l)
finally:
    chrome.terminate()
