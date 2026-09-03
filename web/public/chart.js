// 시간축 차트. SVG 문자열을 만들어 innerHTML 에 한 번에 넣는다 —
// Lab_Main 의 drawAirconChart(), bewe.co.kr 의 UPS 차트와 같은 관용구다.
// 라이브러리를 쓰지 않는 이유는 이 집의 다른 서비스와 같다: 외부 의존 0.
//
// 모든 차트가 **같은 균일 격자**(extract.py 가 만든 5Hz)를 쓰므로
// x 좌표 계산이 하나뿐이고, 커서 인덱스는 i = round(t * hz) 산술로 구해진다.

'use strict';

const PAD = { l: 46, r: 46, t: 8, b: 16 };

function niceScale(values, opts = {}) {
  let lo = Infinity, hi = -Infinity;
  for (const v of values) {
    if (v == null || !isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === Infinity) return null;                 // 유효값이 하나도 없다
  if (opts.min != null) lo = Math.min(lo, opts.min);
  if (opts.max != null) hi = Math.max(hi, opts.max);
  if (hi - lo < 1e-9) { hi = lo + 1; lo -= 1; }     // 평평한 계열도 그려야 한다
  const pad = (hi - lo) * 0.08;
  return { lo: lo - pad, hi: hi + pad };
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

/**
 * 한 단을 그린다.
 *   el     : <svg>
 *   trk    : extract.py 의 trk (hz, n, 채널 배열들)
 *   spec   : { series:[{key,color,label,unit,axis}], bands, events, thresholds }
 */
function drawChart(el, trk, spec) {
  const W = el.clientWidth || 900;
  const H = el.clientHeight || 120;
  el.setAttribute('viewBox', `0 0 ${W} ${H}`);
  el.setAttribute('preserveAspectRatio', 'none');

  const dur = trk.dur || (trk.n - 1) / trk.hz;
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const x = (t) => PAD.l + (dur ? (t / dur) * iw : 0);
  const xi = (i) => x(i / trk.hz);

  // 좌/우 축을 각각 자기 계열들로 스케일한다
  const scales = {};
  for (const ax of ['left', 'right']) {
    const keys = spec.series.filter((s) => (s.axis || 'left') === ax).map((s) => s.key);
    if (!keys.length) continue;
    const vals = [];
    for (const k of keys) for (const v of (trk[k] || [])) vals.push(v);
    const extra = {};
    if (ax === 'left' && spec.thresholds) {
      for (const th of spec.thresholds) extra.max = Math.max(extra.max ?? -Infinity, th.v);
    }
    scales[ax] = niceScale(vals, extra);
  }
  const y = (v, ax) => {
    const s = scales[ax || 'left'];
    return PAD.t + (1 - (v - s.lo) / (s.hi - s.lo)) * ih;
  };

  let svg = '';

  // ── 비행모드 밴드 (배경) ────────────────────────────────────────
  if (spec.bands && trk.modes && trk.modes.length) {
    for (let i = 0; i < trk.modes.length; i++) {
      const a = trk.modes[i].t;
      const b = i + 1 < trk.modes.length ? trk.modes[i + 1].t : dur;
      svg += `<rect x="${x(a).toFixed(1)}" y="${PAD.t}" width="${Math.max(0, x(b) - x(a)).toFixed(1)}"
              height="${ih}" fill="${modeColor(trk.modes[i].name)}" opacity=".18"/>`;
      if (x(b) - x(a) > 44) {
        svg += `<text x="${(x(a) + 4).toFixed(1)}" y="${PAD.t + 11}" fill="#8b949e"
                font-size="9">${esc(trk.modes[i].name)}</text>`;
      }
    }
  }

  // ── 격자 + y 눈금 ───────────────────────────────────────────────
  for (let i = 0; i <= 3; i++) {
    const gy = PAD.t + (i / 3) * ih;
    svg += `<line x1="${PAD.l}" y1="${gy.toFixed(1)}" x2="${W - PAD.r}" y2="${gy.toFixed(1)}"
            stroke="#21262d" stroke-dasharray="3 3"/>`;
    for (const [ax, anchor, tx] of [['left', 'end', PAD.l - 5], ['right', 'start', W - PAD.r + 5]]) {
      const s = scales[ax];
      if (!s) continue;
      const v = s.hi - (i / 3) * (s.hi - s.lo);
      const col = (spec.series.find((q) => (q.axis || 'left') === ax) || {}).color || '#6e7681';
      svg += `<text x="${tx}" y="${(gy + 3).toFixed(1)}" fill="${col}" font-size="9"
              text-anchor="${anchor}">${fmtTick(v)}</text>`;
    }
  }

  // ── 임계선 (전류 45A/90A 같은 것) ───────────────────────────────
  for (const th of (spec.thresholds || [])) {
    if (!scales.left || th.v > scales.left.hi || th.v < scales.left.lo) continue;
    const gy = y(th.v, 'left');
    svg += `<line x1="${PAD.l}" y1="${gy.toFixed(1)}" x2="${W - PAD.r}" y2="${gy.toFixed(1)}"
            stroke="${th.color}" stroke-width="1" stroke-dasharray="5 4" opacity=".75"/>`;
    // 오른쪽 축 눈금과 겹치지 않게 안쪽에 붙인다
    svg += `<text x="${W - PAD.r - 8}" y="${(gy - 4).toFixed(1)}" fill="${th.color}"
            font-size="9" text-anchor="end">${esc(th.label)}</text>`;
  }

  // ── 계열 ────────────────────────────────────────────────────────
  for (const s of spec.series) {
    const arr = trk[s.key];
    if (!arr || !scales[s.axis || 'left']) continue;
    // null 이 섞이면 선을 끊는다. 이어 그리면 없는 데이터를 지어내는 셈이다.
    let d = '', pen = false;
    for (let i = 0; i < arr.length; i++) {
      const v = arr[i];
      if (v == null || !isFinite(v)) { pen = false; continue; }
      d += `${pen ? 'L' : 'M'}${xi(i).toFixed(1)},${y(v, s.axis).toFixed(1)}`;
      pen = true;
    }
    if (d) {
      // 주 계열(굵게)과 보조 계열(가늘고 옅게)을 나눈다. 모터 4선이 전류를
      // 덮어버리면 45A 초과 여부를 못 읽는다 — 정작 그게 보려는 값이다.
      const w = s.weight || 1.4;
      const op = s.dim ? 0.55 : 1;
      svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${w}"
              opacity="${op}" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
    }
  }

  // ── FC 메시지 눈금 (경고 이상만) ────────────────────────────────
  if (spec.events && trk.events) {
    for (const e of trk.events) {
      if (e.lvl > 4 || e.t < 0 || e.t > dur) continue;
      const col = e.lvl <= 3 ? '#f85149' : '#d29922';
      svg += `<line x1="${x(e.t).toFixed(1)}" y1="${PAD.t}" x2="${x(e.t).toFixed(1)}"
              y2="${PAD.t + ih}" stroke="${col}" stroke-width="1" opacity=".55"/>`;
    }
  }

  // ── x 눈금 ──────────────────────────────────────────────────────
  for (let i = 0; i <= 4; i++) {
    const t = (i / 4) * dur;
    const anchor = i === 0 ? 'start' : i === 4 ? 'end' : 'middle';
    svg += `<text x="${x(t).toFixed(1)}" y="${H - 4}" fill="#6e7681" font-size="9"
            text-anchor="${anchor}">${t.toFixed(0)}s</text>`;
  }

  // ── 커서 (재생 위치) ────────────────────────────────────────────
  svg += `<line class="cursor" x1="0" y1="${PAD.t}" x2="0" y2="${PAD.t + ih}"
          stroke="#e6edf3" stroke-width="1" opacity=".85" style="display:none"/>`;

  el.innerHTML = svg;
  el._geom = { x, xi, W, H, dur, PAD };
  return el._geom;
}

function fmtTick(v) {
  const a = Math.abs(v);
  return a >= 100 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2);
}

const MODE_COLORS = {
  MANUAL: '#6e7681', STAB: '#6e7681', ACRO: '#6e7681',
  ALTCTL: '#58a6ff', POSCTL: '#3fb950',
  AUTO_MISSION: '#a371f7', AUTO_LOITER: '#d29922', AUTO_RTL: '#f85149',
  AUTO_TAKEOFF: '#3fb950', AUTO_LAND: '#f0883e',
};
function modeColor(name) {
  for (const k in MODE_COLORS) if (name === k) return MODE_COLORS[k];
  for (const k in MODE_COLORS) if (String(name).startsWith(k)) return MODE_COLORS[k];
  return '#6e7681';
}

/** 모든 차트의 커서를 t 초 위치로 옮긴다. */
function moveCursors(svgs, t) {
  for (const el of svgs) {
    const g = el._geom;
    const c = el.querySelector('.cursor');
    if (!g || !c) continue;
    const px = g.x(Math.max(0, Math.min(t, g.dur)));
    c.setAttribute('x1', px); c.setAttribute('x2', px);
    c.style.display = '';
  }
}
