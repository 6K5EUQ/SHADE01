// 라이브 트래킹 프론트.
//
// 폴링이다 (WebSocket 이 아니라). 서버가 상태 하나를 들고 있고 화면은 그것을
// 5Hz 로 긁어 간다. 이유: 잠깐 끊겨도 다음 폴에서 저절로 복구되고, 되감을
// 상태가 없어 재접속 로직이 필요 없다. 텔레메트리 자체가 5Hz 라 더 자주
// 받아도 같은 값이 두 번 온다.
//
// 항적은 증분으로 받는다 (?since=n). 40분 비행이면 점이 만 개가 넘는데
// 매번 전부 보내면 폴 하나가 수백 KB 가 된다.

'use strict';

const POLL_MS = 200;
const CHART_SEC = 60;                 // 스파크라인이 보여주는 시간 창
const CHART_N = CHART_SEC * 5;        // 5Hz 기준 점 개수

const $ = (id) => document.getElementById(id);

let map, trackLine, craft, homeMarker, missionLine;
let follow = true;
let trackPts = [];                    // [lat, lon]
let trackHave = 0;                    // 서버 기준 '받은 총 개수' (배열 길이가 아니다)
let havePos = false;
const hist = { alt: [], spd: [], cur: [] };
let lastSeq = -1;

// ── 지도 ────────────────────────────────────────────────────────────
function initMap() {
  map = L.map('map', { zoomControl: true, attributionControl: true }).setView([36.5, 127.8], 6);

  // 타일은 외부에서 온다 — 로그 뷰어(log.html)와 같은 소스다. 백팩 AP 에
  // 붙어 있으면 인터넷이 없어 타일이 안 뜬다. 그래도 항적·계기는 다 돈다.
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap',
  }).addTo(map);

  trackLine = L.polyline([], { color: '#58a6ff', weight: 3, opacity: .9 }).addTo(map);

  // 기수 방향을 보여줘야 해서 원이 아니라 삼각형 아이콘이다.
  craft = L.marker([0, 0], {
    icon: L.divIcon({
      className: 'craft-icon', iconSize: [28, 28], iconAnchor: [14, 14],
      html: '<svg width="28" height="28" viewBox="0 0 28 28">' +
        '<polygon points="14,2 21,24 14,19 7,24" fill="#f0883e" ' +
        'stroke="#0d1117" stroke-width="1.5" stroke-linejoin="round"/></svg>',
    }),
    interactive: false, keyboard: false,
  });

  map.on('dragstart', () => setFollow(false));    // 손으로 끌면 추적을 끈다
}

function setFollow(on) {
  follow = on;
  $('followBtn').classList.toggle('on', on);
}

// ── 인공수평의 ──────────────────────────────────────────────────────
// 지도만으로는 기울기를 못 본다. QGC·Mission Planner 와 같은 관용구로,
// 하늘/땅을 roll 만큼 돌리고 pitch 만큼 밀어 그린다.
function drawAHI(roll, pitch) {
  const r = roll || 0, p = pitch || 0;
  const cx = 100, cy = 100, R = 92;
  // 기수를 들면(pitch +) 수평선은 **아래로** 내려간다. QGC·Mission Planner 와
  // 같은 방향이다. 부호를 빼먹으면 계기가 거꾸로 돌아 조종자를 속인다.
  const off = p * 2.2;                            // 1도당 2.2px

  const ticks = [];
  for (let d = -30; d <= 30; d += 10) {
    if (d === 0) continue;
    const y = cy + off + d * 2.2;
    const w = d % 20 === 0 ? 26 : 15;
    ticks.push(`<line x1="${cx - w}" y1="${y}" x2="${cx + w}" y2="${y}"
      stroke="#e6edf3" stroke-width="1.2" opacity=".55"/>`);
  }

  $('ahi').innerHTML = `
    <defs><clipPath id="ahiClip"><circle cx="${cx}" cy="${cy}" r="${R}"/></clipPath></defs>
    <g clip-path="url(#ahiClip)">
      <g transform="rotate(${-r} ${cx} ${cy})">
        <rect x="-120" y="${cy + off - 420}" width="440" height="440" fill="#2f6fa8"/>
        <rect x="-120" y="${cy + off}" width="440" height="440" fill="#7a5230"/>
        <line x1="-120" y1="${cy + off}" x2="320" y2="${cy + off}"
              stroke="#e6edf3" stroke-width="2"/>
        ${ticks.join('')}
      </g>
    </g>
    <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="#30363d" stroke-width="2"/>
    <!-- 고정 기체 심볼 -->
    <path d="M${cx - 34} ${cy} h22 M${cx + 12} ${cy} h22" stroke="#f0883e"
          stroke-width="3" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="3" fill="#f0883e"/>
    <polygon points="${cx},${cy - R + 4} ${cx - 6},${cy - R + 15} ${cx + 6},${cy - R + 15}"
             fill="#e6edf3"/>`;
}

// ── 스파크라인 ──────────────────────────────────────────────────────
function spark(el, vals, color) {
  const H = 44;
  const LBL = 42;              // 오른쪽 현재값 자리. 그래프는 여기까지만 그린다
  const W = 300 - LBL;
  const pts = vals.filter((v) => v != null && isFinite(v));
  if (pts.length < 2) { el.innerHTML = ''; return; }
  let lo = Math.min(...pts), hi = Math.max(...pts);
  if (hi - lo < 1e-6) { hi = lo + 1; lo -= 1; }
  const pad = (hi - lo) * 0.12;
  lo -= pad; hi += pad;

  // 창이 다 찰 때까지는 있는 만큼 폭에 펴서 그린다. CHART_N 에 고정하면
  // 처음 1분 동안 오른쪽 끝에만 실오라기처럼 붙어 안 보인다. 다 차면
  // 두 식이 같아지므로, 그때부터는 왼쪽으로 흘러가는 보통 스크롤 차트다.
  const span = Math.max(vals.length - 1, 1);
  const step = W / Math.max(span, 1);
  const x = (i) => W - (vals.length - 1 - i) * step;
  const y = (v) => H - 3 - ((v - lo) / (hi - lo)) * (H - 6);

  let d = '';
  vals.forEach((v, i) => {
    if (v == null || !isFinite(v)) return;
    d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1);
  });
  const last = pts[pts.length - 1];
  // 라벨은 뷰박스가 세로로 눌려도 안 찌그러지게 non-scaling 을 못 쓰므로,
  // preserveAspectRatio="none" 아래에서는 글자가 늘어난다. 그래서 축 눈금은
  // 위/아래 한 개씩만 두고 현재값만 크게 보여준다.
  el.innerHTML =
    `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.6"
       vector-effect="non-scaling-stroke"/>` +
    `<text x="3" y="10" fill="#6e7681" font-size="8">${hi.toFixed(0)}</text>` +
    `<text x="3" y="${H - 3}" fill="#6e7681" font-size="8">${lo.toFixed(0)}</text>` +
    `<text x="${W + LBL - 3}" y="${H / 2 + 5}" fill="${color}" font-size="14"
       text-anchor="end" font-weight="700"
       font-family="ui-monospace, monospace">${last.toFixed(1)}</text>`;
}

function push(arr, v) {
  arr.push(v == null || !isFinite(v) ? null : v);
  if (arr.length > CHART_N) arr.shift();
}

// ── 표시 유틸 ───────────────────────────────────────────────────────
const fmt = (v, n = 1) => (v == null || !isFinite(v) ? '—' : v.toFixed(n));

function setBadge(el, cls, text) {
  el.className = 's ' + cls;
  el.querySelector('b').textContent = text;
}

function dist(a, b) {
  const dlat = (b[0] - a[0]) * 111320;
  const dlon = (b[1] - a[1]) * 111320 * Math.cos(a[0] * Math.PI / 180);
  return Math.hypot(dlat, dlon);
}

// ── 렌더 ────────────────────────────────────────────────────────────
function render(s) {
  const d = s.d || {};

  // 링크·ARM·모드
  const link = $('link');
  link.textContent = s.live ? '링크 ON' : (s.packets ? '링크 끊김' : '링크 없음');
  link.className = 'pill ' + (s.live ? 'pill-live' : 'pill-off');

  const armed = $('armed');
  armed.textContent = d.armed ? 'ARMED' : 'DISARMED';
  armed.className = 'pill ' + (d.armed ? 'pill-armed' : 'pill-off');

  $('mode').textContent = d.mode || '—';

  // VTOL 상태 — 쿼드 전용 운용이라 FW 로 넘어가면 눈에 띄어야 한다.
  const vt = $('vtol');
  if (d.vtol) {
    vt.hidden = false;
    vt.textContent = d.vtol;
    vt.className = 'pill ' + (d.vtol === 'MC' ? '' : 'pill-warn');
  } else { vt.hidden = true; }

  $('stats').textContent = s.src
    ? `${s.src} · ${s.packets.toLocaleString()}pkt · ${(s.bytes / 1024).toFixed(0)}KB`
    : 'MAVLink 대기 중…';

  // 경고 배너
  const banner = $('banner');
  let msg = '', bad = false;
  if (!s.live && s.packets) { msg = `링크 끊김 — 마지막 수신 ${s.age}초 전`; bad = true; }
  else if (d.vtol && d.vtol !== 'MC' && d.vtol !== '') {
    msg = `⚠ 고정익 천이 상태: ${d.vtol} — 이 기체는 쿼드 전용이다`; bad = true;
  } else if (d.fix != null && d.fix < 3 && d.armed) { msg = 'GPS fix 없음 (ARM 상태)'; }
  banner.hidden = !msg;
  banner.textContent = msg;
  banner.className = bad ? 'bad' : '';

  // 큰 숫자
  $('b-alt').textContent = fmt(d.alt);
  $('b-spd').textContent = fmt(d.groundspeed);
  $('b-volt').textContent = fmt(d.volt, 2);
  $('b-cur').textContent = fmt(d.cur);

  // 전류·전압 임계 — README 기준: 최대 66.8A 이력, 6S 만충 25.2V
  const cur = $('b-cur');
  cur.className = 'num' + (d.cur > 60 ? ' bad' : d.cur > 45 ? ' warn' : '');
  const volt = $('b-volt');
  volt.className = 'num' + (d.volt && d.volt < 21.0 ? ' bad'
    : d.volt && d.volt < 22.2 ? ' warn' : '');

  // 자세
  drawAHI(d.roll, d.pitch);
  $('g-roll').textContent = fmt(d.roll);
  $('g-pitch').textContent = fmt(d.pitch);
  $('g-hdg').textContent = d.hdg != null ? fmt(d.hdg, 0) : fmt(d.yaw, 0);
  $('g-climb').textContent = fmt(d.climb);
  $('g-thr').textContent = d.throttle != null ? d.throttle : '—';
  $('g-air').textContent = fmt(d.airspeed);

  // 상태 배지
  const fixName = { 0: 'fix 없음', 1: 'fix 없음', 2: '2D', 3: '3D', 4: 'DGPS', 5: 'RTK-F', 6: 'RTK-X' };
  if (d.fix != null) {
    setBadge($('s-gps'), d.fix >= 3 ? 'ok' : 'bad',
      `${fixName[d.fix] || d.fix} · ${d.sats ?? '?'}기`);
  } else setBadge($('s-gps'), 'none', '—');

  // EKF — 플래그가 꺼진 것과 혁신 비율(>1 이면 검사 실패) 둘 다 본다.
  if (d.ekf) {
    const off = Object.entries(d.ekf).filter(([, v]) => !v).map(([k]) => k);
    const rt = d.ekf_ratio || {};
    const hot = Object.entries(rt).filter(([, v]) => v > 1.0).map(([k]) => k);
    const worst = Math.max(0, ...Object.values(rt));
    let cls = 'ok', txt = 'OK';
    if (off.length) { cls = off.length > 1 ? 'bad' : 'warn'; txt = off.join(','); }
    else if (hot.length) { cls = 'bad'; txt = hot.join(',') + ' ' + worst.toFixed(1); }
    else if (worst > 0.5) { cls = 'warn'; txt = worst.toFixed(2); }
    setBadge($('s-ekf'), cls, txt);
    $('s-ekf').title = Object.entries(rt).map(([k, v]) => `${k} ${v}`).join('  ');
  } else setBadge($('s-ekf'), 'none', '—');

  if (d.vibe) {
    const mx = Math.max(...d.vibe);
    setBadge($('s-vibe'), mx > 30 ? 'bad' : mx > 15 ? 'warn' : 'ok', mx.toFixed(1));
  } else setBadge($('s-vibe'), 'none', '—');

  if (d.batt_pct != null) {
    setBadge($('s-batt'), d.batt_pct < 20 ? 'bad' : d.batt_pct < 35 ? 'warn' : 'ok',
      d.batt_pct + '%');
  } else setBadge($('s-batt'), 'none', '—');

  if (d.rssi != null) {
    setBadge($('s-rc'), d.rssi < 60 ? 'bad' : d.rssi < 120 ? 'warn' : 'ok', String(d.rssi));
  } else setBadge($('s-rc'), 'none', '—');

  setBadge($('s-mah'), 'none', d.mah != null ? d.mah + ' mAh' : '—');

  // 차트 — 폴마다 한 점. 값이 안 바뀌어도 시간은 흐른다.
  push(hist.alt, d.alt);
  push(hist.spd, d.groundspeed);
  push(hist.cur, d.cur);
  spark($('c-alt'), hist.alt, '#58a6ff');
  spark($('c-spd'), hist.spd, '#f0883e');
  spark($('c-cur'), hist.cur, '#f85149');

  // 지도 — 항적은 증분으로 온다.
  // track_from 은 이 응답의 첫 점이 **전체에서** 몇 번째인가다 (리스트 인덱스가
  // 아니다). 서버가 앞을 버렸거나 리셋됐으면 우리가 아는 개수보다 앞을 가리키므로
  // 그때는 통째로 갈아끼운다. 안 그러면 항적이 겹치거나 빠진다.
  if (s.track_from < trackHave) {
    trackPts = s.track.map((p) => [p[0], p[1]]);
  } else {
    for (const p of s.track) trackPts.push([p[0], p[1]]);
  }
  trackHave = s.track_n;
  if (s.track.length) trackLine.setLatLngs(trackPts);

  if (d.lat != null && d.lon != null && (d.lat || d.lon)) {
    const ll = [d.lat, d.lon];
    if (!havePos) {
      craft.addTo(map);
      map.setView(ll, 18);
      havePos = true;
    }
    craft.setLatLng(ll);
    // 아이콘을 기수 방향으로 돌린다.
    // ⚠️ 마커의 style.transform 을 건드리면 안 된다 — Leaflet 이 거기에
    //    translate3d 로 위치를 쓰므로, 회전을 덧붙이면 매 프레임 누적되고
    //    (5Hz → 초당 5개씩 쌓인다) 다음 위치 갱신 때 지워진다.
    //    안쪽 <svg> 를 따로 돌리면 둘이 안 부딪힌다.
    const svg = craft.getElement() && craft.getElement().querySelector('svg');
    const hdg = d.hdg != null ? d.hdg : d.yaw;
    if (svg && hdg != null) svg.style.transform = `rotate(${hdg}deg)`;
    if (follow) map.panTo(ll, { animate: false });

    $('o-lat').textContent = d.lat.toFixed(7);
    $('o-lon').textContent = d.lon.toFixed(7);
    $('o-home').textContent = s.home ? dist(s.home, ll).toFixed(0) + ' m' : '—';
  }
  $('o-trk').textContent = trackPts.length ? trackPts.length + ' pt' : '—';

  if (s.home && !homeMarker) {
    homeMarker = L.marker(s.home, {
      icon: L.divIcon({
        className: '', iconSize: [20, 20], iconAnchor: [10, 10],
        html: '<svg width="20" height="20" viewBox="0 0 20 20">' +
          '<circle cx="10" cy="10" r="7" fill="none" stroke="#3fb950" stroke-width="2"/>' +
          '<text x="10" y="14" text-anchor="middle" fill="#3fb950" ' +
          'font-size="10" font-weight="700">H</text></svg>',
      }),
      interactive: false,
    }).addTo(map);
  } else if (s.home && homeMarker) {
    homeMarker.setLatLng(s.home);
  }

  // 메시지
  const box = $('msgs');
  if (s.messages && s.messages.length) {
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 20;
    box.innerHTML = s.messages.map((m) => {
      const time = new Date(m.t * 1000).toLocaleTimeString('ko-KR', { hour12: false });
      return `<div><span class="sev s-${m.sev}">${m.sev}</span>` +
        `<span class="sev">${time}</span>${escapeHtml(m.text)}</div>`;
    }).join('');
    if (atBottom) box.scrollTop = box.scrollHeight;
  } else if (!box.dataset.init) {
    box.innerHTML = '<div class="empty">FC 메시지 없음</div>';
    box.dataset.init = '1';
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// ── 폴 루프 ─────────────────────────────────────────────────────────
// setInterval 이 아니라 꼬리물기다. 서버가 느려도 요청이 쌓이지 않는다.
async function poll() {
  try {
    const r = await fetch('/api/state?since=' + trackHave, { cache: 'no-store' });
    if (r.ok) {
      const s = await r.json();
      render(s);
      lastSeq = s.seq;
      $('link').title = '';
    }
  } catch (e) {
    $('link').textContent = '서버 없음';
    $('link').className = 'pill pill-off';
    $('link').title = 'mav_live.py 가 안 떠 있다';
  }
  setTimeout(poll, POLL_MS);
}

// ── 기동 ────────────────────────────────────────────────────────────
initMap();
drawAHI(0, 0);

$('followBtn').onclick = () => setFollow(!follow);
$('clearBtn').onclick = async () => {
  await fetch('/api/reset');
  trackPts = [];
  trackHave = 0;
  trackLine.setLatLngs([]);
  hist.alt.length = hist.spd.length = hist.cur.length = 0;
};

poll();
