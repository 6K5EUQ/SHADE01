#!/usr/bin/env python3
"""대한민국 공역(비행금지·제한·관제권 등) -> GeoJSON.

출처: VWorld WFS (api.vworld.kr) — 국토교통부 항공정보 레이어.
드론원스톱(drone.onestop.go.kr/common/flightArea)이 쓰는 것과 같은 소스다.

인증키: vworld.kr 가입 후 [오픈API > 인증키 발급] 으로 직접 받아라.
        키는 도메인 잠금이라 발급 시 등록한 도메인을 DOMAIN 에 적어야 한다.
공역은 거의 안 바뀐다 — 분기에 한 번 정도만 다시 돌리면 된다.

    python3 tools/fetch_airspace.py --key <KEY> --domain <DOMAIN> \
        -o web/live/public/data/kr_airspace.geojson
"""
import argparse, json, math, sys, urllib.parse, urllib.request

WFS = 'https://api.vworld.kr/req/wfs'

# 레이어 -> (표시명, 이름 속성, 색)
LAYERS = {
    'lt_c_aisprhc':      ('비행금지구역',        'prh_lbl_1', '#d32f2f'),
    'lt_c_aistemp':      ('임시금지구역',        'prh_lbl_1', '#b71c1c'),
    'lt_c_aisresc':      ('비행제한구역',        'res_lbl_1', '#f57c00'),
    'lt_c_aisctrc':      ('관제권',             'ctr_lbl_1', '#c2185b'),
    'lt_c_aisdngc':      ('위험구역',           'dng_lbl_1', '#7b1fa2'),
    'lt_c_aisaltc':      ('경계구역',           'alt_lbl_1', '#5d4037'),
    'lt_c_aisuac':       ('초경량비행장치공역(UA)', 'name_txt', '#388e3c'),
    'lt_c_aisdronezone': ('드론전용구역',        'name',      '#1976d2'),
}

# 기지 좌표 — 각 구역까지 거리를 미리 박아 둔다(창원)
HOME_LAT, HOME_LON = 35.1811, 128.5538


def km(lat, lon):
    return math.hypot((lat - HOME_LAT) * 111.32,
                      (lon - HOME_LON) * 111.32 * math.cos(math.radians(HOME_LAT)))


def nearest(geom):
    best = float('inf')
    if not geom:
        return best
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    for poly in polys:
        for ring in poly:
            for lon, lat in ring:
                best = min(best, km(lat, lon))
    return best


def fetch(layer, key, domain):
    qs = urllib.parse.urlencode({
        'service': 'WFS', 'key': key, 'domain': domain,
        'version': '1.1.0', 'request': 'GetFeature',
        'typename': layer, 'output': 'application/json',
        'srsname': 'EPSG:4326', 'maxfeatures': '1000',
    })
    req = urllib.request.Request(f'{WFS}?{qs}', headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode('utf-8')
    if not raw.lstrip().startswith('{'):
        # ServiceException 은 XML 로 온다 (만료키·도메인 불일치 등)
        raise SystemExit(f'{layer}: WFS 오류\n{raw[:400]}')
    return json.loads(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', required=True, help='VWorld 인증키')
    ap.add_argument('--domain', required=True, help='인증키에 등록한 도메인')
    ap.add_argument('-o', '--out', default='web/live/public/data/kr_airspace.geojson')
    a = ap.parse_args()

    feats = []
    for layer, (label, namekey, color) in LAYERS.items():
        d = fetch(layer, a.key, a.domain)
        n = 0
        for f in d.get('features', []):
            if not f.get('geometry'):
                continue
            p = f['properties']
            f['properties'] = {
                'zone_type': label,
                'layer': layer,
                'name': p.get(namekey),
                'upper': p.get(namekey.replace('_1', '_2')) or p.get('vertical'),
                'lower': p.get(namekey.replace('_1', '_3')),
                'color': color,
                'dist_km': round(nearest(f['geometry']), 2),
            }
            feats.append(f)
            n += 1
        print(f'  {label:22} {n:4d}', file=sys.stderr)

    fc = {'type': 'FeatureCollection',
          'attribution': '국토교통부 / VWorld (api.vworld.kr)',
          'features': feats}
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(',', ':'))
    print(f'{a.out}: {len(feats)} features', file=sys.stderr)


if __name__ == '__main__':
    main()
