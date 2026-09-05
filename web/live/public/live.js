// 라이브 트래킹 프론트.
//
// 폴링이다 (WebSocket 이 아니라). 서버가 상태 하나를 들고 있고 화면은 그것을
// 5Hz 로 긁어 간다. 이유: 잠깐 끊겨도 다음 폴에서 저절로 복구되고, 되감을
// 상태가 없어 재접속 로직이 필요 없다. 텔레메트리 자체가 5Hz 라 더 자주
// 받아도 같은 값이 두 번 온다.
//
// 항적은 증분으로 받는다 (?since=n). 40분 비행이면 점이 만 개가 넘는데
// 매번 전부 보내면 폴 하나가 수백 KB 가 된다.
//
// ── HUD 아키텍처: build-once / mutate-only ───────────────────────────
// buildHUD() 가 기동 시 약 500 노드를 한 번 만들고, 매 폴에는 transform·
// 기하 속성·가드된 textContent 만 쓴다 (프레임당 약 50 write). innerHTML
// 재생성은 HUD 어디에도 없다 — 5Hz 로 500 노드를 다시 만들면 초당 2500 노드
// 생성 + SVG 파싱 + 패널 전체 재래스터이고, clipPath 를 매 프레임 다시 만들면
// Blink 가 SVG 리소스 캐시를 버려 클립 영역을 통째로 다시 굽는다.
// 비용이 눈금 개수와 무관해지므로 나중에 요소를 더 얹어도 안 나빠진다.
//
// 좌표는 전부 원점(0,0) 기준으로 authored 하고, translate(cx,cy) 하나가
// 화면 위치를 담당한다. 리사이즈 때 자식 노드를 하나도 안 건드린다.

'use strict';

const POLL_MS = 200;

// ── 계기 스케일 상수. 빌드와 layout() 이 같은 값을 읽는다 (두 벌이 되면 어긋난다) ──
const PPD_PITCH = 6.0;                // 피치 px/도
const PPU_SPD = 12;                   // 대지속도 px/(m/s)
const PPU_ALT = 8;                    // 고도 px/m — alt=0 일 때 50m 펜스선이 창 위 가장자리
const PPD_HDG = 8.0;                  // 기수 px/도
const PPU_VSI = 22;                   // 상승률 px/(m/s)
const OVER = 2600;                    // 하늘/땅 오버스캔 반폭 (4K 반대각선의 1.7배)

// 🔴 FC 파라미터를 여기 박아 둔 것이다. 서버는 이 값을 안 보낸다 —
//    GF_MAX_HOR_DIST / GF_MAX_VER_DIST 와 조용히 어긋날 수 있으므로
//    화면 라벨에 '설정값' 을 붙여 실측이 아님을 밝힌다. 근거: README '현재 상태' 표.
const FENCE = { HOR: 150, VER: 50 };

const HDG_H = 34;                     // 상단 기수 테이프 높이

const SVGNS = 'http://www.w3.org/2000/svg';
const $ = (id) => document.getElementById(id);

// ── 레이아웃 변수. layout() 에서만 갱신, 매 프레임 transform 이 이걸 읽는다 ──
let W = 0, H = 0, TAPE_W = 72, AY0 = HDG_H, AY1 = 0, AH = 0;
let cx = 0, cy = 0, ARC_R = 0, CENTER_DY = 0;

const h = {};                         // HUD 노드 참조
let havePos = false;
let winSec = 180;                     // 차트가 보여주는 시간 창 (0 = 전체)
let hoverT = null;                    // 커서가 붙잡고 있는 시각 (없으면 null)

// ── 차트 버퍼 ───────────────────────────────────────────────────────
// 로그 뷰어의 extract.py 가 만드는 trk 와 **같은 모양**이다: 균일 격자(hz, n)
// 위에 채널별 배열. 그래야 web/public/chart.js 의 drawChart 를 고치지 않고
// 그대로 쓸 수 있고, 지난 비행과 지금 비행이 같은 그림으로 나온다.
//
// 폴 한 번이 격자 한 칸이다. 값이 없으면 null 을 넣는다 — 건너뛰면 시간축이
// 밀려 20분 뒤 그래프가 실제보다 짧아진다.
const HZ = 1000 / POLL_MS;            // 5Hz
const KEEP_N = 3600 * HZ;             // 1시간치까지 들고 있는다
const trk = { hz: HZ, n: 0, dur: 0, modes: [], events: [] };
let lastMode = null;
let lastSeq = -1, lastSeqPoll = 0, pollN = 0;
let warnUntil = 0, warnText = '', lastMsgKey = '';

// ── SVG 헬퍼 ────────────────────────────────────────────────────────
// SVG 요소에 innerHTML 로 자식을 넣으면 네임스페이스가 어긋나고, 빌드 코드
// (문자열)와 갱신 코드(DOM)가 갈라져 좌표 상수가 두 벌이 된다. 전부 createElementNS.
function el(tag, attrs, parent) {
  const e = document.createElementNS(SVGNS, tag);
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
// 같은 문자열을 매 프레임 덮어쓰면 불필요한 텍스트 재측정이 난다.
function setText(e, s) { if (e._v !== s) { e._v = s; e.textContent = s; } }
function setAttr(e, k, v) {
  const c = e['_a' + k];
  if (c !== v) { e['_a' + k] = v; e.setAttribute(k, v); }
}
function show(e, on) { e.classList.toggle('off', !on); }

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const wrap180 = (x) => ((x + 180) % 360 + 360) % 360 - 180;
const wrap360 = (x) => ((x % 360) + 360) % 360;
const fmt = (v, n = 1) => (v == null || !isFinite(v) ? '—' : v.toFixed(n));

// ── HUD 생성 (기동 시 1회) ──────────────────────────────────────────
function buildHUD() {
  const svg = $('hud');
  const defs = el('defs', null, svg);
  const clip = (id) => el('rect', {}, el('clipPath', { id }, defs));
  h.clipAll = clip('hudClipAll');
  h.clipCore = clip('hudClipCore');
  h.clipSpd = clip('hudClipSpd');
  h.clipAlt = clip('hudClipAlt');
  h.clipHdg = clip('hudClipHdg');

  // ① 인공수평의 배경 — 테이프 뒤까지 깔린다 (테이프 배경이 반투명이라 비친다).
  // 🔴 클립은 회전하지 않는 바깥 <g> 에 건다. 회전 그룹 안에 걸면 클립 사각형이
  //    같이 돌아 화면 모서리가 샌다. 그래서 자세 transform 이 2쌍이다.
  const bgWrap = el('g', { 'clip-path': 'url(#hudClipAll)' }, svg);
  h.bgCore = el('g', {}, bgWrap);
  h.bgRoll = el('g', {}, h.bgCore);
  h.bgPitch = el('g', {}, h.bgRoll);
  el('rect', { x: -OVER, y: -3300, width: OVER * 2, height: 3300, fill: '#2f6fa8' }, h.bgPitch);
  el('rect', { x: -OVER, y: 0, width: OVER * 2, height: 3300, fill: '#7a5230' }, h.bgPitch);
  el('line', { x1: -OVER, y1: 0, x2: OVER, y2: 0, stroke: '#0d1117', 'stroke-width': 6 }, h.bgPitch);
  el('line', { x1: -OVER, y1: 0, x2: OVER, y2: 0, stroke: '#e6edf3', 'stroke-width': 2 }, h.bgPitch);

  // ② 계기층 — 테이프 안쪽으로 잘린다.
  const coreWrap = el('g', { 'clip-path': 'url(#hudClipCore)' }, svg);
  h.core = el('g', {}, coreWrap);
  h.roll = el('g', {}, h.core);
  // 🔴 피치는 회전 g 의 **자식** 에 translate 로 준다 — '회전 후 이동' 순서를
  //    구조로 강제한다. 순서가 뒤집히면 롤이 걸린 상태에서 피치가 엉뚱한 축으로 움직인다.
  h.pitch = el('g', {}, h.roll);

  // 피치 사다리. 헤일로를 한 벌 먼저 깔고 그 위에 본체 — filter 금지
  // (회전 그룹에 붙이면 매 프레임 래스터 재계산).
  const halo = el('g', { stroke: '#0d1117', 'stroke-width': 6, fill: 'none' }, h.pitch);
  const lad = el('g', { stroke: '#e6edf3', 'stroke-width': 2, fill: 'none' }, h.pitch);
  h.ladLabels = [];
  for (let P = -40; P <= 40; P += 5) {
    if (P === 0) continue;
    const y = -P * PPD_PITCH;
    const w = P % 10 === 0 ? 60 : 30;
    // 음수(하강)는 파선 — 수평선이 화면 밖으로 나가도 하늘/땅 방향을 알려준다.
    const dash = P < 0 ? { 'stroke-dasharray': '8 6' } : {};
    el('line', Object.assign({ x1: -w, y1: y, x2: w, y2: y }, dash), halo);
    el('line', Object.assign({ x1: -w, y1: y, x2: w, y2: y }, dash), lad);
    if (P % 10 === 0) {
      const t = String(Math.abs(P));
      h.ladLabels.push(
        el('text', { x: -66, y: y + 5, 'text-anchor': 'end', 'font-size': 13, fill: '#e6edf3' }, lad),
        el('text', { x: 66, y: y + 5, 'text-anchor': 'start', 'font-size': 13, fill: '#e6edf3' }, lad));
      h.ladLabels[h.ladLabels.length - 2].textContent = t;
      h.ladLabels[h.ladLabels.length - 1].textContent = t;
    }
  }

  // 롤 지시 삼각형 — hudRoll 의 자식이라 rotate 를 **상속만** 한다.
  // 매 프레임 쓸 것이 없고, 구조적으로 수평선과 같은 각도로 붙어 돈다.
  h.rollPtr = el('polygon', { points: '0,0 -9,16 9,16', fill: 'var(--c-spd)' }, h.roll);

  // 롤 호 눈금 — 회전하지 않는다 (core 직속).
  h.rollArc = el('g', { stroke: '#e6edf3', fill: 'none' }, h.core);
  h.arcTicks = [];
  for (let i = 0; i < 11; i++) h.arcTicks.push(el('line', {}, h.rollArc));
  h.arcRef = el('polygon', { fill: '#e6edf3', stroke: 'none' }, h.core);

  // 고정 기체 심볼 — 야외 글레어 대비 얇은 선 금지.
  const symH = el('g', { stroke: '#0d1117', 'stroke-width': 8, fill: 'none', 'stroke-linecap': 'round' }, h.core);
  const symB = el('g', { stroke: '#f0883e', 'stroke-width': 4, fill: 'none', 'stroke-linecap': 'round' }, h.core);
  for (const g of [symH, symB]) {
    el('path', { d: 'M-110 0 H-40 L-40 14' }, g);
    el('path', { d: 'M110 0 H40 L40 14' }, g);
  }
  el('circle', { cx: 0, cy: 0, r: 4, fill: '#f0883e', stroke: 'none' }, h.core);

  // 중앙 상태 블록
  h.center = el('g', {}, h.core);
  h.arm = el('text', { x: 0, y: 0, 'text-anchor': 'middle', class: 'armTxt' }, h.center);
  h.mode = el('text', { x: 0, y: 34, 'text-anchor': 'middle', class: 'modeTxt', fill: 'var(--text)' }, h.center);
  h.vtol = el('g', { class: 'off' }, h.center);
  el('rect', { x: -190, y: 42, width: 380, height: 32, fill: 'none', stroke: 'var(--bad)', 'stroke-width': 2 }, h.vtol);
  h.vtolTxt = el('text', { x: 0, y: 65, 'text-anchor': 'middle', class: 'vtolTxt', fill: 'var(--bad)' }, h.vtol);
  h.warn = el('text', { x: 0, y: 96, 'text-anchor': 'middle', class: 'warnTxt', fill: 'var(--bad)' }, h.center);

  // ③ 좌측 테이프 — 대지속도 (🔴 대기속도가 아니다)
  h.spdBg = el('rect', { fill: 'rgba(13,17,23,.55)' }, svg);
  const spdClip = el('g', { 'clip-path': 'url(#hudClipSpd)' }, svg);
  h.spdSlide = el('g', {}, spdClip);
  for (let v = 0; v <= 40; v++) {
    const y = -v * PPU_SPD, five = v % 5 === 0;
    el('line', { x1: 0, y1: y, x2: five ? -14 : -8, y2: y, stroke: '#e6edf3', 'stroke-width': five ? 1.6 : 1, opacity: five ? 1 : .6 }, h.spdSlide);
    if (five) {
      const t = el('text', { x: -18, y: y + 4, 'text-anchor': 'end', 'font-size': 12, fill: '#e6edf3' }, h.spdSlide);
      t.textContent = String(v);
    }
  }
  h.spdBox = el('rect', { fill: '#0d1117', opacity: .92, stroke: 'var(--c-spd)', 'stroke-width': 1.5 }, svg);
  h.spdApex = el('polygon', { fill: '#0d1117', opacity: .92, stroke: 'var(--c-spd)', 'stroke-width': 1.5 }, svg);
  h.spdVal = el('text', { 'text-anchor': 'end', 'font-size': 22, fill: '#e6edf3' }, svg);
  // 🔴 두 줄이다 — 한 줄이면 폭이 테이프(62~92px)를 넘어 잘린다.
  //    MP 는 이 자리가 대기속도지만 이 기체 airspeed 는 고장 센서다.
  //    자리만 같고 소스가 다르면 오독하므로 계기 면에 GS 라고 못박는다.
  h.spdHead = el('text', { 'text-anchor': 'middle', 'font-size': 10, fill: 'var(--muted)' }, svg);
  h.spdHead.textContent = '대지속도';
  h.spdHead2 = el('text', { 'text-anchor': 'middle', 'font-size': 10, fill: 'var(--muted)' }, svg);
  h.spdHead2.textContent = 'GS m/s';

  // ④ 우측 테이프 — 고도 AGL + 지면대 + 펜스 천장선
  h.altBg = el('rect', { fill: 'rgba(13,17,23,.55)' }, svg);
  const altClip = el('g', { 'clip-path': 'url(#hudClipAlt)' }, svg);
  h.altSlide = el('g', {}, altClip);
  h.gndBand = el('rect', { y: 0, fill: 'var(--bad)', opacity: .10 }, h.altSlide);
  h.gndLine = el('line', { x1: 0, y1: 0, y2: 0, stroke: 'var(--dim)', 'stroke-width': 2 }, h.altSlide);
  h.fenceLine = el('line', { x1: 0, y1: -FENCE.VER * PPU_ALT, y2: -FENCE.VER * PPU_ALT, stroke: 'var(--bad)', 'stroke-width': 2 }, h.altSlide);
  h.fenceTxt = el('text', { x: 4, y: -FENCE.VER * PPU_ALT - 4, 'font-size': 9, fill: 'var(--bad)' }, h.altSlide);
  h.fenceTxt.textContent = '펜스 ' + FENCE.VER + ' 설정값';
  for (let v = -10; v <= 120; v += 2) {
    const y = -v * PPU_ALT, ten = v % 10 === 0;
    el('line', { x1: 0, y1: y, x2: ten ? 14 : 8, y2: y, stroke: '#e6edf3', 'stroke-width': ten ? 1.6 : 1, opacity: ten ? 1 : .6 }, h.altSlide);
    if (ten) {
      const t = el('text', { x: 18, y: y + 4, 'text-anchor': 'start', 'font-size': 12, fill: '#e6edf3' }, h.altSlide);
      t.textContent = String(v);
    }
  }
  h.altBox = el('rect', { fill: '#0d1117', opacity: .92, stroke: 'var(--c-alt)', 'stroke-width': 1.5 }, svg);
  h.altApex = el('polygon', { fill: '#0d1117', opacity: .92, stroke: 'var(--c-alt)', 'stroke-width': 1.5 }, svg);
  h.altVal = el('text', { 'text-anchor': 'start', 'font-size': 22, fill: '#e6edf3' }, svg);
  h.altHead = el('text', { 'text-anchor': 'middle', 'font-size': 10, fill: 'var(--muted)' }, svg);
  h.altHead.textContent = '고도 AGL';
  h.altHead2 = el('text', { 'text-anchor': 'middle', 'font-size': 10, fill: 'var(--muted)' }, svg);
  h.altHead2.textContent = '홈기준 m';

  // ⑤ 상승률 리본 — 숫자는 안 쓴다. 크기보다 부호와 추세라 막대가 더 빠르다.
  h.vsiTicks = [];
  for (let i = 0; i < 4; i++) h.vsiTicks.push(el('line', { stroke: 'var(--border-2)', 'stroke-width': 1 }, svg));
  h.vsi = el('rect', { fill: 'var(--c-alt)' }, svg);

  // ⑥ 상단 기수 테이프. 🔴 359→0 이음매: 사다리를 -60..780 한 벌로 만들어
  //    어느 방향으로 몇 바퀴를 돌아도 재렌더·모듈로 로직이 0 이다.
  h.hdgBg = el('rect', { fill: 'rgba(13,17,23,.55)' }, svg);
  h.hdgWrap = el('g', { 'clip-path': 'url(#hudClipHdg)' }, svg);
  h.hdgSlide = el('g', {}, h.hdgWrap);
  h.hdgMinor = [];
  const CARD = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };
  for (let d = -60; d <= 780; d += 5) {
    const x = d * PPD_HDG, ten = d % 10 === 0;
    const ln = el('line', { x1: x, y1: HDG_H, x2: x, y2: ten ? 20 : 26, stroke: '#e6edf3', 'stroke-width': ten ? 1.6 : 1, opacity: ten ? 1 : .6 }, h.hdgSlide);
    if (!ten) h.hdgMinor.push(ln);
    if (ten) {
      const w = wrap360(d), c = CARD[w];
      const t = el('text', {
        x, y: 17, 'text-anchor': 'middle', 'font-size': c ? 15 : 13,
        fill: c ? 'var(--accent)' : '#e6edf3', 'font-weight': c ? 700 : 400,
      }, h.hdgSlide);
      t.textContent = c || String(w / 10).padStart(2, '0');
    }
  }
  // 코스 마커·홈 벅은 슬라이드가 아니라 창 좌표로 놓는다 (자기 transform 을 가진다).
  h.course = el('polygon', { points: '0,4 6,10 0,16 -6,10', fill: '#e6edf3', class: 'off' }, h.hdgWrap);
  h.homeBug = el('g', { class: 'off' }, h.hdgWrap);
  el('polygon', { points: '0,4 6,12 -6,12', fill: 'var(--ok)' }, h.homeBug);
  const hb = el('text', { x: 0, y: 24, 'text-anchor': 'middle', 'font-size': 10, fill: 'var(--ok)' }, h.homeBug);
  hb.textContent = 'H';
  // 창 밖으로 나가면 가장자리 삼각형으로 바꾼다 — 클램프해서 붙여 두면
  // '정확히 저쪽 57°' 로 읽혀 계기가 거짓말한다.
  h.bugL = el('polygon', { fill: '#e6edf3', class: 'off' }, svg);
  h.bugR = el('polygon', { fill: '#e6edf3', class: 'off' }, svg);
  h.hdgApex = el('polygon', { fill: '#0d1117', opacity: .92, stroke: 'var(--border-2)' }, svg);
  h.hdgBox = el('rect', { fill: '#0d1117', opacity: .92, stroke: 'var(--border-2)' }, svg);
  h.hdgVal = el('text', { 'text-anchor': 'middle', 'font-size': 17, fill: '#e6edf3' }, svg);
  h.hdgSrc = el('text', { 'font-size': 9, fill: 'var(--muted)' }, svg);

  // ⑨ 프리즈 오버레이 — 얼어붙은 테이프는 정상 테이프와 겉모습이 같다.
  //    얼어붙은 계기는 자기가 얼었다고 온몸으로 말해야 한다.
  h.freeze = el('rect', { fill: '#0d1117', opacity: .55, class: 'off' }, svg);
  h.freezeTxt = el('text', { 'text-anchor': 'middle', 'font-size': 30, fill: 'var(--bad)', class: 'off' }, svg);
}

// ── 리사이즈 배치 ───────────────────────────────────────────────────
// 🔴 viewBox 속성만 바꾸고 width/height/style 은 절대 안 건드린다 →
//    레이아웃에 영향을 안 주므로 ResizeObserver 무한루프가 성립하지 않는다.
function layout(w, hh) {
  W = w; H = hh;
  TAPE_W = clamp(W * 0.082, 62, 92);
  AY0 = HDG_H; AY1 = H; AH = AY1 - AY0;
  cx = W / 2; cy = AY0 + AH / 2;
  // min(W,AH) 가 핵심 — max 나 W 를 쓰면 세로가 짧은 패널에서 호가 잘린다.
  ARC_R = Math.min(W, AH) * 0.36;
  CENTER_DY = Math.min(AH * 0.17, 150);

  const svg = $('hud');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.classList.toggle('small', AH < 420);

  const box = (r, x, y, ww, hg) => {
    setAttr(r, 'x', x); setAttr(r, 'y', y);
    setAttr(r, 'width', Math.max(0, ww)); setAttr(r, 'height', Math.max(0, hg));
  };
  box(h.clipAll, 0, AY0, W, AH);
  box(h.clipCore, TAPE_W, AY0, W - 2 * TAPE_W, AH);
  box(h.clipSpd, 0, AY0, TAPE_W, AH);
  box(h.clipAlt, W - TAPE_W, AY0, TAPE_W, AH);
  box(h.clipHdg, TAPE_W, 0, W - 2 * TAPE_W, HDG_H + 40);

  setAttr(h.bgCore, 'transform', `translate(${cx},${cy})`);
  setAttr(h.core, 'transform', `translate(${cx},${cy})`);
  setAttr(h.center, 'transform', `translate(0,${CENTER_DY})`);

  // 롤 호 — scale 을 쓰지 않는다 (stroke 폭까지 바뀐다). 좌표를 다시 쓴다.
  const ARC = [0, -10, 10, -20, 20, -30, 30, -45, 45, -60, 60];
  ARC.forEach((a, i) => {
    const big = a === 0 || Math.abs(a) === 30 || Math.abs(a) === 60;
    const L = big ? 11 : 7, th = (-90 + a) * Math.PI / 180;
    const c = Math.cos(th), s = Math.sin(th), t = h.arcTicks[i];
    setAttr(t, 'x1', (ARC_R * c).toFixed(1)); setAttr(t, 'y1', (ARC_R * s).toFixed(1));
    setAttr(t, 'x2', ((ARC_R + L) * c).toFixed(1)); setAttr(t, 'y2', ((ARC_R + L) * s).toFixed(1));
    setAttr(t, 'stroke-width', big ? 2.5 : 2);
  });
  setAttr(h.arcRef, 'points', `0,${-ARC_R - 2} -8,${-ARC_R - 14} 8,${-ARC_R - 14}`);
  setAttr(h.rollPtr, 'transform', `translate(0,${-ARC_R})`);
  show(h.rollArc, AH >= 300);
  show(h.arcRef, AH >= 300);
  show(h.rollPtr, AH >= 300);
  // 좁으면 라벨·단눈금을 끈다 (노드 삭제가 아니다 — 넓어지면 되살아난다).
  for (const t of h.ladLabels) show(t, W >= 460);
  for (const t of h.hdgMinor) show(t, W >= 460);

  // 좌 테이프. 🔴 판독 박스 폭은 TAPE_W 에 맞춘다 — 88px 로 고정하면
  //    테이프(62~92px)보다 넓어져 박스가 패널 밖으로 잘려 나간다.
  box(h.spdBg, 0, AY0, TAPE_W, AH);
  box(h.spdBox, 0, cy - 15, TAPE_W, 30);
  setAttr(h.spdApex, 'points', `${TAPE_W},${cy - 9} ${TAPE_W + 12},${cy} ${TAPE_W},${cy + 9}`);
  setAttr(h.spdVal, 'x', TAPE_W - 6); setAttr(h.spdVal, 'y', cy + 8);
  setAttr(h.spdHead, 'x', TAPE_W / 2); setAttr(h.spdHead, 'y', AY0 + 13);
  setAttr(h.spdHead2, 'x', TAPE_W / 2); setAttr(h.spdHead2, 'y', AY0 + 25);

  // 우 테이프
  box(h.altBg, W - TAPE_W, AY0, TAPE_W, AH);
  box(h.altBox, W - TAPE_W, cy - 15, TAPE_W, 30);
  setAttr(h.altApex, 'points', `${W - TAPE_W},${cy - 9} ${W - TAPE_W - 12},${cy} ${W - TAPE_W},${cy + 9}`);
  setAttr(h.altVal, 'x', W - TAPE_W + 6); setAttr(h.altVal, 'y', cy + 8);
  setAttr(h.altHead, 'x', W - TAPE_W / 2); setAttr(h.altHead, 'y', AY0 + 13);
  setAttr(h.altHead2, 'x', W - TAPE_W / 2); setAttr(h.altHead2, 'y', AY0 + 25);
  setAttr(h.gndBand, 'width', TAPE_W); setAttr(h.gndBand, 'height', 80);
  setAttr(h.gndLine, 'x2', TAPE_W);
  setAttr(h.fenceLine, 'x2', TAPE_W);

  // VSI — 고도 테이프 안쪽 모서리에 붙는다
  const vx = W - TAPE_W - 16;
  [2, -2, 5, -5].forEach((v, i) => {
    const t = h.vsiTicks[i], y = cy - v * PPU_VSI;
    setAttr(t, 'x1', vx); setAttr(t, 'y1', y); setAttr(t, 'x2', vx + 12); setAttr(t, 'y2', y);
  });
  setAttr(h.vsi, 'x', vx); setAttr(h.vsi, 'width', 12);

  // 기수 테이프
  box(h.hdgBg, TAPE_W, 0, W - 2 * TAPE_W, HDG_H);
  setAttr(h.hdgApex, 'points', `${cx},${HDG_H} ${cx - 9},${HDG_H + 10} ${cx + 9},${HDG_H + 10}`);
  box(h.hdgBox, cx - 34, HDG_H + 10, 68, 24);
  setAttr(h.hdgVal, 'x', cx); setAttr(h.hdgVal, 'y', HDG_H + 27);
  setAttr(h.hdgSrc, 'x', cx + 40); setAttr(h.hdgSrc, 'y', HDG_H + 27);
  setAttr(h.bugL, 'points', `${TAPE_W + 2},${HDG_H + 4} ${TAPE_W + 12},${HDG_H - 2} ${TAPE_W + 12},${HDG_H + 10}`);
  setAttr(h.bugR, 'points', `${W - TAPE_W - 2},${HDG_H + 4} ${W - TAPE_W - 12},${HDG_H - 2} ${W - TAPE_W - 12},${HDG_H + 10}`);

  box(h.freeze, 0, 0, W, H);
  setAttr(h.freezeTxt, 'x', cx); setAttr(h.freezeTxt, 'y', cy);
}

// ── 차트 ────────────────────────────────────────────────────────────
// 단 구성·색은 로그 뷰어(log.html 의 CHARTS)와 맞춘다.
const CHARTS = [
  { id: 'k-alt', title: '고도', on: true, series: [
      { key: 'alt', color: 'var(--c-alt)', label: '고도', axis: 'left', weight: 2, unit: 'm' },
      { key: 'climb', color: 'var(--c-spd)', label: '상승률', axis: 'right', unit: 'm/s' }] },
  { id: 'k-spd', title: '속도', on: true, series: [
      { key: 'spd', color: 'var(--c-spd)', label: '수평속도', axis: 'left', weight: 2, unit: 'm/s' },
      { key: 'aspd', color: '#a371f7', label: '대기속도', axis: 'left', unit: 'm/s' }] },
  { id: 'k-pwr', title: '전력', on: true, series: [
      { key: 'cur', color: 'var(--c-cur)', label: '전류', axis: 'left', weight: 2, unit: 'A' },
      { key: 'volt', color: 'var(--c-volt)', label: '전압', axis: 'right', unit: 'V' }],
    // 45A 는 8/31 비행에서 453초 중 270초를 넘긴 선이다 (README 「전류」).
    thresholds: [{ v: 45, label: '45A', color: '#d29922' }] },
  { id: 'k-att', title: '자세', on: false, series: [
      { key: 'roll', color: '#d55e00', label: '롤', axis: 'left', weight: 2, unit: '°' },
      { key: 'pitch', color: '#e69f00', label: '피치', axis: 'left', weight: 2, unit: '°' }] },
  { id: 'k-vib', title: '진동', on: false, series: [
      { key: 'vib', color: '#f0883e', label: '진동(최대축)', axis: 'left', weight: 2 }],
    thresholds: [{ v: 30, label: '한계', color: '#d29922' }] },
  { id: 'k-gps', title: 'GPS', on: false, series: [
      { key: 'sats', color: '#3fb950', label: '위성 수', axis: 'left', weight: 2 },
      { key: 'eph', color: '#f85149', label: '위치 오차', axis: 'right', unit: 'm' }] },
  { id: 'k-ekf', title: 'EKF', on: false, series: [
      { key: 'ekf_vel', color: '#58a6ff', label: '속도', axis: 'left' },
      { key: 'ekf_pos', color: '#3fb950', label: '위치', axis: 'left' },
      { key: 'ekf_alt', color: '#f0883e', label: '고도', axis: 'left' },
      { key: 'ekf_mag', color: '#a371f7', label: '지자기', axis: 'left' }],
    // 비율이다. 1 을 넘으면 그 센서의 혁신 검사가 깨지고 있다는 뜻.
    thresholds: [{ v: 1, label: '한계', color: '#d29922' }] },
];
const shownIds = new Set(CHARTS.filter((c) => c.on).map((c) => c.id));

// 🔴 chart.js 는 stroke 를 **SVG 속성**으로 쓴다 (stroke="..."). 속성값은 CSS
//    변수를 풀지 않으므로 var(--c-alt) 를 그대로 넘기면 선이 그려지긴 해도
//    색이 없어 화면에서 사라진다. log.html 이 cssVar() 를 거치는 이유가 이것이다.
//    기동 시 한 번 실제 색으로 바꿔 둔다.
function cssVar(v) {
  return v && v.startsWith('var(')
    ? getComputedStyle(document.documentElement).getPropertyValue(v.slice(4, -1)).trim() || v
    : v;
}
function resolveColors() {
  for (const c of CHARTS) for (const sx of c.series) sx.color = cssVar(sx.color);
}

/** 폴 한 번 = 격자 한 칸. */
function pushSample(d) {
  const put = (k, v) => {
    // 뒤늦게 처음 등장한 채널은 앞을 null 로 채워 길이를 맞춘다.
    if (!trk[k]) trk[k] = new Array(trk.n).fill(null);
    trk[k].push(v == null || !isFinite(v) ? null : v);
  };
  put('alt', d.alt);
  put('climb', d.climb);
  put('spd', d.groundspeed);
  put('aspd', d.airspeed);
  put('roll', d.roll);
  put('pitch', d.pitch);
  put('cur', d.cur);
  put('volt', d.volt);
  put('vib', d.vibe ? Math.max(...d.vibe) : null);
  put('sats', d.sats);
  put('eph', d.eph);
  const r = d.ekf_ratio || {};
  put('ekf_vel', r.vel); put('ekf_pos', r.pos); put('ekf_alt', r.alt); put('ekf_mag', r.mag);

  trk.n++;
  trk.dur = (trk.n - 1) / trk.hz;

  // 모드가 바뀌면 밴드를 연다 — 로그 뷰어와 같은 배경 띠가 된다.
  if (d.mode && d.mode !== lastMode) {
    trk.modes.push({ t: trk.dur, name: d.mode });
    lastMode = d.mode;
  }

  // 오래된 것을 버린다. 모든 채널에서 **같은 개수**를 떨궈야 인덱스가 안 어긋난다.
  if (trk.n > KEEP_N) {
    const drop = trk.n - KEEP_N;
    for (const k of Object.keys(trk)) {
      if (Array.isArray(trk[k]) && k !== 'modes' && k !== 'events') trk[k].splice(0, drop);
    }
    trk.n -= drop;
    const shift = drop / trk.hz;
    trk.dur -= shift;
    for (const m of trk.modes) m.t -= shift;
    // 창 밖으로 나간 밴드는 접는다. 첫 밴드는 0 에 붙여 두어야 배경이 안 빈다.
    while (trk.modes.length > 1 && trk.modes[1].t <= 0) trk.modes.shift();
    if (trk.modes.length) trk.modes[0].t = Math.max(0, trk.modes[0].t);
  }
}

/** 단 DOM 을 만든다. 그리기는 renderCharts() 가 매 폴마다 한다. */
function buildCharts() {
  const host = $('charts');
  const want = CHARTS.filter((c) => shownIds.has(c.id));
  if (!want.length) {
    host.innerHTML = '<div class="empty">볼 단을 오른쪽 위에서 고른다.</div>';
    return;
  }
  host.innerHTML = want.map((c) => `
    <div class="lchart">
      <!-- 계열 이름은 chart.js 가 축 머리말로 이미 적는다 (색까지 같이).
           여기서 또 적으면 같은 말이 두 번이다 — 그 자리는 현재값에 준다. -->
      <div class="now" id="n-${c.id}"></div>
      <svg id="${c.id}"></svg>
      <div class="tip" id="tip-${c.id}"></div>
    </div>`).join('');
  for (const c of want) bindHover(c);
  renderCharts();
}

function buildToc() {
  $('toc').innerHTML = CHARTS.map((c) =>
    `<label class="${shownIds.has(c.id) ? 'on' : ''}" data-id="${c.id}">
       <input type="checkbox" ${shownIds.has(c.id) ? 'checked' : ''}>${c.title}</label>`).join('');
  $('toc').querySelectorAll('label').forEach((el) => {
    el.querySelector('input').onchange = (e) => {
      if (e.target.checked) shownIds.add(el.dataset.id); else shownIds.delete(el.dataset.id);
      el.classList.toggle('on', e.target.checked);
      buildCharts();
    };
  });
}

/** 마우스를 올린 지점의 값을 읽어 준다 (로그 뷰어 log.html 과 같은 관용구).
 *
 * 흘러가는 화면이라 커서를 올린 동안에는 **그 시각을 붙잡아** 다시 그린다 —
 * 안 그러면 읽는 사이에 그래프가 밀려 다른 값을 가리킨다.
 */
function bindHover(c) {
  const el = $(c.id);
  const tip = $('tip-' + c.id);
  if (!el || !tip || el._bound) return;
  el._bound = true;

  const move = (e) => {
    const g = el._geom;
    if (!g || !trk.n) return;
    const r = el.getBoundingClientRect();
    // _geom.tAt 은 viewBox 좌표를 받는다. 화면 px → viewBox px 로 환산한다.
    const vx = (e.clientX - r.left) * (g.W / r.width);
    const t = g.tAt(vx);
    if (t < g.v0 || t > g.v1) { hide(); return; }

    const i = Math.max(0, Math.min(trk.n - 1, Math.round(t * trk.hz)));
    const ago = trk.dur - t;
    let html = `<div class="t">${ago < 1 ? '지금' : '-' + ago.toFixed(1) + 's'}` +
               `${modeAt(t) ? ' · ' + modeAt(t) : ''}</div>`;
    for (const sx of c.series) {
      const arr = trk[sx.key];
      const v = arr ? arr[i] : null;
      html += `<div class="r"><span class="d" style="background:${sx.color}"></span>` +
              `<span class="n">${sx.label}</span>` +
              `<b>${v == null ? '–' : (+v).toFixed(2)}</b>` +
              (sx.unit ? `<i>${sx.unit}</i>` : '') + '</div>';
    }
    tip.innerHTML = html;
    tip.style.opacity = '1';

    // 커서 옆에 두되 단 밖으로 안 나가게 접는다.
    const sec = el.parentElement.getBoundingClientRect();
    const w = tip.offsetWidth, hh = tip.offsetHeight;
    let x = e.clientX - sec.left + 14;
    if (x + w > sec.width - 4) x = e.clientX - sec.left - 14 - w;
    if (x < 4) x = 4;
    let y = e.clientY - sec.top - hh - 12;
    if (y < 4) y = e.clientY - sec.top + 16;
    if (y + hh > sec.height - 4) y = Math.max(4, sec.height - hh - 4);
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';

    // 커서 세로선. chart.js 가 만들어 둔 .cursor 를 그대로 쓴다.
    const cur = el.querySelector('.cursor');
    if (cur) {
      cur.setAttribute('x1', g.x(t)); cur.setAttribute('x2', g.x(t));
      cur.style.display = '';
    }
    hoverT = t;                       // 흘러가는 것을 멈춘다 (renderCharts 가 읽는다)
  };

  const hide = () => {
    tip.style.opacity = '0';
    const cur = el.querySelector('.cursor');
    if (cur) cur.style.display = 'none';
    hoverT = null;
  };

  el.addEventListener('pointermove', move);
  el.addEventListener('pointerleave', hide);
}

/** 그 시각의 비행모드 이름. */
function modeAt(t) {
  let n = '';
  for (const m of trk.modes) { if (m.t <= t) n = m.name; else break; }
  return n;
}

function renderCharts() {
  if (!trk.n) return;
  // 보이는 구간 = 최근 winSec 초. 이 창이 오른쪽으로 밀리는 것이 곧 "흘러감" 이다.
  // 🔴 커서를 올린 동안에는 안 민다. 흘러가면 읽으려던 지점이 옆으로 도망가
  //    커서와 숫자가 서로 다른 시각을 가리킨다.
  if (hoverT != null) return;
  const t1 = trk.dur;
  const t0 = winSec > 0 ? Math.max(0, t1 - winSec) : 0;
  for (const c of CHARTS) {
    if (!shownIds.has(c.id)) continue;
    const el = $(c.id);
    if (!el) continue;
    drawChart(el, trk, {
      series: c.series, bands: true, thresholds: c.thresholds,
      relTime: true,          // x축을 "몇 초 전" 으로
      view: { t0, t1: Math.max(t1, t0 + 1e-3) },
    });
    const s0 = c.series[0];
    const arr = trk[s0.key] || [];
    const v = arr.length ? arr[arr.length - 1] : null;
    const n = $('n-' + c.id);
    if (n) {
      setText(n, v == null ? '' : v.toFixed(1) + (s0.unit || ''));
      n.style.color = s0.color;
    }
  }
}

function dist(a, b) {
  const dlat = (b[0] - a[0]) * 111320;
  const dlon = (b[1] - a[1]) * 111320 * Math.cos(a[0] * Math.PI / 180);
  return Math.hypot(dlat, dlon);
}
function bearing(from, to) {
  const R = Math.PI / 180;
  const p1 = from[0] * R, p2 = to[0] * R, dl = (to[1] - from[1]) * R;
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return wrap360(Math.atan2(y, x) * 180 / Math.PI);
}

// ── 렌더 ────────────────────────────────────────────────────────────
function render(s) {
  pollN++;
  const d = s.d || {};

  // ② 링크·프리즈·경고 만료 — 조기반환과 무관하게 항상 돈다.
  const changed = s.seq !== lastSeq;
  if (changed) { lastSeq = s.seq; lastSeqPoll = pollN; }
  const stall = (pollN - lastSeqPoll) * POLL_MS / 1000;

  // 링크 상태는 점 하나로 말한다 (우하단 바). 자세한 사정은 HUD 의 프리즈
  // 오버레이가 크게 적으므로 여기서 글자를 또 쓸 이유가 없다.
  // 색만으로는 색맹에게 안 보이니 title 에 같은 내용을 남긴다.
  const dot = $('dot');
  let lt, lc, frz = '';
  if (!s.packets) { lt = '링크 없음'; lc = ''; }
  else if (!s.live) { lt = '링크 끊김'; lc = 'bad'; frz = `링크 끊김 · ${Math.round(s.age)}s`; }
  else if (stall >= 3) {
    lt = '데이터 정지'; lc = 'warn';
    frz = `데이터 정지 · ${stall.toFixed(0)}s (링크는 살아 있음)`;
  } else { lt = '링크 ON'; lc = 'live'; }
  if (dot.dataset.st !== lt) {          // 매 폴 DOM 을 건드리지 않는다
    dot.dataset.st = lt;
    dot.className = 'dot ' + lc;
    dot.title = lt;
  }
  show(h.freeze, !!frz);
  show(h.freezeTxt, !!frz);
  if (frz) setText(h.freezeTxt, frz);

  // 하단 바는 좁다. 송신 주소는 title 로 밀고 숫자만 남긴다.
  const stEl = $('stats');
  setText(stEl, s.packets
    ? `${s.packets.toLocaleString()}pkt · ${(s.bytes / 1024).toFixed(0)}KB`
    : 'MAVLink 대기 중…');
  if (s.src && stEl.dataset.src !== s.src) {
    stEl.dataset.src = s.src;
    stEl.title = s.src;
  }

  // ── 차트 표본. 🔴 조기반환보다 **위**에 있어야 한다.
  //    시계열의 x축은 벽시계 시간이다 — 새 프레임이 없다고 표본을 건너뛰면
  //    링크가 끊긴 20초가 그래프에서 통째로 사라져, 끊긴 자국 없이 선이
  //    이어져 버린다 (실측: pollN 15 인데 trk.n 이 2 였다).
  //    값이 안 바뀐 폴은 같은 값이 한 칸 더 들어가고, 링크가 죽으면 아래
  //    pushSample 이 null 을 넣어 선이 끊긴다 — 둘 다 사실대로다.
  pushSample(s.live ? d : {});
  // 5Hz 로 단 3개를 전부 다시 그리면 초당 15회 SVG 재생성이다. 2.5Hz 로
  // 줄여 HUD 에 CPU 를 남긴다. 처음 몇 칸만 매번 그려 첫 화면이 안 빈다.
  if (trk.n < 4 || pollN % 2 === 0) renderCharts();

  // ③ 조기반환 — 여기부터는 새 데이터가 있을 때만.
  if (!changed) return;

  // ── 자세. 🔴 roll/pitch 에 CSS transition 이나 보간을 넣지 마라 —
  //    주 자세계에 100~200ms 지연이 생겨 계기가 과거를 보여준다.
  //    데이터가 5Hz 니 화면도 5Hz 다. 끊겨 보이면 고칠 곳은 텔레메트리 레이트지 화면이 아니다.
  const roll = d.roll || 0, pitch = d.pitch || 0;
  // 기수를 들면(pitch +) 수평선은 **아래로** 내려간다. 부호를 빼먹으면 계기가 거꾸로 돈다.
  const rt = `rotate(${(-roll).toFixed(2)})`, pt = `translate(0,${(pitch * PPD_PITCH).toFixed(1)})`;
  setAttr(h.bgRoll, 'transform', rt);
  setAttr(h.bgPitch, 'transform', pt);
  setAttr(h.roll, 'transform', rt);
  setAttr(h.pitch, 'transform', pt);
  setAttr(h.rollPtr, 'fill', Math.abs(roll) > 35 ? 'var(--warn)' : 'var(--c-spd)');

  // ── 대지속도 테이프. 눈금만 클램프하고 판독 박스는 진짜 숫자를 쓴다 —
  //    계기가 포화돼도 숫자는 절대 거짓이 안 된다.
  const gs = d.groundspeed;
  const gsC = clamp(gs == null ? 0 : gs, 0, 40);
  setAttr(h.spdSlide, 'transform', `translate(${TAPE_W},${(cy + gsC * PPU_SPD).toFixed(1)})`);
  setText(h.spdVal, fmt(gs));
  setAttr(h.spdBox, 'stroke', gs > 40 ? 'var(--warn)' : 'var(--c-spd)');

  // ── 고도 테이프
  const alt = d.alt;
  const altC = clamp(alt == null ? 0 : alt, -10, 120);
  setAttr(h.altSlide, 'transform', `translate(${W - TAPE_W},${(cy + altC * PPU_ALT).toFixed(1)})`);
  setText(h.altVal, fmt(alt));
  setAttr(h.altBox, 'stroke', (alt > 120 || alt < -10) ? 'var(--warn)' : 'var(--c-alt)');

  // ── VSI
  const cl = clamp(d.climb == null ? 0 : d.climb, -5, 5), ch = Math.abs(cl) * PPU_VSI;
  setAttr(h.vsi, 'y', cl >= 0 ? cy - ch : cy);
  setAttr(h.vsi, 'height', d.climb == null ? 0 : ch);

  // ── 기수 테이프. hdg 도 yaw 도 없으면 0 을 그리지 않는다 —
  //    가짜 0° 는 북쪽을 향한 것처럼 보인다.
  const hdgRaw = d.hdg != null ? d.hdg : d.yaw;
  const haveHdg = hdgRaw != null && isFinite(hdgRaw);
  const hh = haveHdg ? wrap360(hdgRaw) : 0;
  setAttr(h.hdgWrap, 'opacity', haveHdg ? 1 : .3);
  setAttr(h.hdgSlide, 'transform', `translate(${(cx - (hh + 360) * PPD_HDG).toFixed(1)},0)`);
  setText(h.hdgVal, haveHdg ? String(Math.round(hh) % 360).padStart(3, '0') : '—');
  setText(h.hdgSrc, !haveHdg ? '방위없음' : (d.hdg != null ? 'HDG' : 'YAW'));

  const halfWin = (W - 2 * TAPE_W) / 2 / PPD_HDG;
  // 🔴 edgeL/edgeR 은 코스 마커일 때 null 이다 — 숨기는 가지에서도 반드시 가드한다.
  //    가드가 없으면 gs<1.5 (정지·호버) 인 순간 show(null) 이 TypeError 를 던져
  //    render() 가 여기서 죽고 중앙 상태·스트립·상태밴드가 통째로 안 그려진다.
  const place = (node, edgeL, edgeR, deg) => {
    if (deg == null || !haveHdg) {
      show(node, false);
      if (edgeL) show(edgeL, false);
      if (edgeR) show(edgeR, false);
      return;
    }
    const dd = wrap180(deg - hh);
    const out = Math.abs(dd) > halfWin;
    show(node, !out);
    if (edgeL) show(edgeL, out && dd < 0);
    if (edgeR) show(edgeR, out && dd > 0);
    if (!out) setAttr(node, 'transform', `translate(${(cx + dd * PPD_HDG).toFixed(1)},0)`);
  };
  // 코스 마커 — 🔴 에어스피드가 고장이라 기수와 코스의 벌어짐이 바람에 밀리는
  // 각을 아는 유일한 수단이다. 호버에서 atan2 는 노이즈이므로 gs<1.5 면 숨긴다.
  const moving = gs != null && gs >= 1.5 && d.vx != null && d.vy != null;
  place(h.course, null, null, moving ? wrap360(Math.atan2(d.vy, d.vx) * 180 / Math.PI) : null);
  const pos = (d.lat != null && d.lon != null && (d.lat || d.lon)) ? [d.lat, d.lon] : null;
  place(h.homeBug, h.bugL, h.bugR, (s.home && pos) ? bearing(pos, s.home) : null);

  // ── 중앙 상태 블록
  // 🔴 ARMED 를 빨갛게 쓰지 않는다 — 지상 대기·정상 비행은 이상 상태가 아니고,
  //    매 비행마다 빨강을 보면 빨강의 의미가 닳는다 (색 예산).
  const tail = d.landed === 2 ? ' · 공중' : d.landed === 1 ? ' · 지상' : '';
  setText(h.arm, d.armed ? 'ARMED' + tail : 'DISARMED');
  setAttr(h.arm, 'fill', d.armed ? 'var(--text)' : 'var(--muted)');
  setText(h.mode, d.mode || '—');

  const vtBad = d.vtol && d.vtol !== 'MC';
  show(h.vtol, !!vtBad);
  if (vtBad) setText(h.vtolTxt, `⚠ ${d.vtol} · 이 기체는 쿼드 전용`);

  // 붉은 한 줄. 🔴 만료를 m.t 로 판정하지 마라 — m.t 는 서버 시계이고 비교는
  //    브라우저 시계라, RTC 없는 Pi 나 NTP 미동기면 창이 영원히 안 열리거나 안 닫힌다.
  //    길이 비교도 쓰지 마라 — 서버가 messages[-40:] 슬라이딩 창을 준다.
  const msgs = s.messages || [];
  const keyOf = (m) => m.t + '|' + m.text;
  const newKey = msgs.length ? keyOf(msgs[msgs.length - 1]) : '';
  if (newKey !== lastMsgKey) {
    let start = 0;
    for (let i = msgs.length - 1; i >= 0; i--) if (keyOf(msgs[i]) === lastMsgKey) { start = i + 1; break; }
    const SEV = { EMERG: 1, ALERT: 1, CRIT: 1, ERROR: 1, WARN: 1 };
    for (let i = msgs.length - 1; i >= start; i--) {
      if (SEV[msgs[i].sev]) { warnText = msgs[i].text.slice(0, 48); warnUntil = pollN + 75; break; }
    }
    lastMsgKey = newKey;
  }
  const crit = d.system_status === 6 ? 'FC 상태 CRITICAL'
    : d.system_status === 7 ? 'FC 상태 EMERGENCY' : '';
  setText(h.warn, crit || (pollN < warnUntil ? warnText : ''));
  // 점멸은 우선순위 상위 하나에만 — 동시에 여럿 깜빡이면 아무것도 안 튄다.
  h.vtol.classList.toggle('blink', !!vtBad);
  h.warn.classList.toggle('blink', !vtBad && !!crit);

  // ── HUD 아래 한 줄. 전류밴드·상태밴드·숫자스트립 3층을 통합했다.
  //    비행 중 곁눈질로 읽는 값만 남긴다 — 나머지는 우측 차트에 있다.
  //
  // 🔴 색 예산은 그대로다: 평소엔 전부 무채색이고, 색이 보이는 것 자체가 신호다.
  //    (--c-cur 이 --bad 와 같은 #f85149 라 그걸 기본색으로 쓰면 30A 정상
  //     비행 내내 새빨갛고 정작 60A 초과가 안 튄다.)
  const sc = (id, cls) => { const e = $(id); if (e) e.className = 'sc' + (cls ? ' ' + cls : ''); };

  setText($('st-cur'), fmt(d.cur));
  sc('sc-cur', d.cur > 60 ? 'bad' : d.cur > 45 ? 'warn' : '');

  setText($('st-batt'), d.batt_pct != null ? String(d.batt_pct) : '—');
  sc('sc-batt', d.batt_pct != null && d.batt_pct < 20 ? 'bad'
    : d.batt_pct != null && d.batt_pct < 35 ? 'warn' : '');

  setText($('st-spd'), fmt(d.groundspeed));
  setText($('st-alt'), fmt(d.alt));

  // 위성은 개수와 fix 를 같이 본다 — 8기라도 fix 가 없으면 위치는 없다.
  setText($('st-sats'), d.sats != null ? String(d.sats) : '—');
  sc('sc-sats', d.fix != null && d.fix < 3 ? 'bad' : (d.sats != null && d.sats < 8) ? 'warn' : '');

  // 모터 4개. 기체에 붙은 자리 그대로 2×2 로 놓인다 — 절대값보다
  // **넷이 서로 비슷한가**가 판정이다.
  const mt = d.motors || {};
  const mv = ['LF', 'RF', 'LB', 'RB'].map((k) => mt[k]).filter((v) => v != null);
  const mmax = mv.length ? Math.max(...mv) : null;
  const mmin = mv.length ? Math.min(...mv) : null;
  // 네 모터가 20%p 넘게 벌어지면 기체가 한쪽을 억지로 붙들고 있다는 뜻이다.
  // 무게중심·프롭 손상·모터 열화의 첫 신호다. 그때 **튄 놈만** 색을 준다 —
  // 넷 다 칠하면 어느 것이 문제인지 도로 못 읽는다.
  const spread = (mmax != null && mmax - mmin > 20);
  for (const k of ['LF', 'RF', 'LB', 'RB']) {
    const v = mt[k];
    setText($('st-m' + k), v == null ? '—' : v.toFixed(0));
    sc('sc-m' + k, spread && (v === mmax || v === mmin) ? 'warn' : '');
  }

  renderMsgs(msgs);
}

// 🔴 증분 append. 길이 비교로 판정하면 서버의 messages[-40:] 슬라이딩 창 때문에
//    40에서 영원히 멈춘다. 마지막으로 렌더한 키를 배열에서 찾아 그 뒤만 붙인다.
let msgLastKey = '', msgCrit = 0;
function renderMsgs(msgs) {
  const box = $('msgs');
  if (!msgs.length) {
    if (!box.dataset.init) { box.innerHTML = '<div class="empty">FC 메시지 없음</div>'; box.dataset.init = '1'; }
    return;
  }
  const keyOf = (m) => m.t + '|' + m.text;
  const last = keyOf(msgs[msgs.length - 1]);
  if (last === msgLastKey) return;

  let start = 0, found = false;
  for (let i = msgs.length - 1; i >= 0; i--) if (keyOf(msgs[i]) === msgLastKey) { start = i + 1; found = true; break; }
  if (!found) { box.innerHTML = ''; msgCrit = 0; start = 0; }
  box.dataset.init = '1';

  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 20;
  const SEV = { EMERG: 1, ALERT: 1, CRIT: 1, ERROR: 1 };
  for (let i = start; i < msgs.length; i++) {
    const m = msgs[i];
    const time = new Date(m.t * 1000).toLocaleTimeString('ko-KR', { hour12: false });
    const div = document.createElement('div');
    div.innerHTML = `<span class="sev s-${m.sev}">${m.sev}</span><span class="sev">${time}</span>`;
    div.appendChild(document.createTextNode(m.text));
    box.appendChild(div);
    if (SEV[m.sev]) msgCrit++;
  }
  while (box.childElementCount > 200) box.removeChild(box.firstChild);
  msgLastKey = last;
  setText($('msgCnt'), msgCrit ? `심각 ${msgCrit}` : '');
  if (atBottom) box.scrollTop = box.scrollHeight;
}

// ── 데모 피드 ───────────────────────────────────────────────────────
// FC 없이는 종횡비·이음매·클리핑을 현장에서야 발견하는데, 이 페이지의 검증
// 실패 비용은 비행 중이다. ?demo=1 로 합성 값을 5Hz 로 먹인다.
function demoState(n) {
  const q = new URLSearchParams(location.search);
  const t = n / 5;
  const fx = (k, v) => (q.has(k) ? parseFloat(q.get(k)) : v);
  const hdg = fx('hdg', wrap360(t * 24));
  const gs = fx('gs', 12 + 11 * Math.sin(t / 7));
  return {
    live: true, seq: n, age: 0, packets: n * 5, bytes: n * 300, src: 'demo',
    track_n: 0, track_from: 0, track: [], home: [37.5, 127.0],
    messages: n > 25 && n < 40 ? [{ t: 1757000000, sev: 'CRIT', text: 'demo: Preflight Fail: Attitude failure (roll)' }] : [],
    d: {
      armed: (n % 300) > 60, landed: (n % 300) > 100 ? 2 : 1,
      mode: fx('auto', 0) ? 'AUTO.MISSION' : 'POSCTL',
      vtol: (n % 400) > 340 ? 'TRANSITION_TO_FW' : 'MC',
      system_status: 4,
      lat: 37.5 + Math.sin(t / 20) * 3e-4, lon: 127.0 + Math.cos(t / 20) * 3e-4,
           alt: fx('alt', 45 + 40 * Math.sin(t / 9)),
      vx: Math.cos(t / 7) * gs, vy: Math.sin(t / 7) * gs,
      groundspeed: gs, climb: 3 * Math.cos(t / 9), hdg, yaw: hdg,
      roll: fx('roll', 55 * Math.sin(t / 5)), pitch: fx('pitch', 22 * Math.sin(t / 6.5)),
      airspeed: -4.9, throttle: 52, load: 41,
      volt: fx('volt', 23.4), cur: fx('cur', 35 + 32 * Math.sin(t / 11)),
      batt_pct: 63, mah: 4820,
      fix: 4, sats: 27, eph: 0.19, eph_ekf: 0.4,
      vibe: [2.5, 3.1, 4.4], ekf: { pos: 1, vel: 1, hgt: 1 }, ekf_ratio: { vel: 0.3 },
      rssi: 200, wp_seq: 3, wp_dist: 27.4, xtrack: -2.1,
    },
  };
}

// ── 폴 루프 ─────────────────────────────────────────────────────────
// setInterval 이 아니라 꼬리물기다. 서버가 느려도 요청이 쌓이지 않는다.
const DEMO = new URLSearchParams(location.search).has('demo');
let demoN = 0;

async function poll() {
  if (DEMO) {
    render(demoState(demoN++));
    setTimeout(poll, POLL_MS);
    return;
  }
  try {
    // track=0 — 지도를 뺐으므로 항적은 안 받는다. 긴 비행에서 폴마다 수백 KB 가
    // 오가는 것을 막는다 (서버는 개수만 알려 준다).
    const r = await fetch('/api/state?track=0', { cache: 'no-store' });
    if (r.ok) render(await r.json());
  } catch (e) {
    // 서버가 죽었을 때도 점으로 말한다 — 깜빡이는 빨강.
    const dot = $('dot');
    dot.dataset.st = '서버 없음';
    dot.className = 'dot bad';
    dot.title = '서버 없음 — mav_live.py 가 안 떠 있다';
    setText($('stats'), '서버 없음');
  }
  setTimeout(poll, POLL_MS);
}

// ── 기동 ────────────────────────────────────────────────────────────
buildHUD();
resolveColors();      // 반드시 buildCharts 앞에 — 범례·선이 같은 색을 쓴다
buildToc();
buildCharts();

// 🔴 콜백에서 즉시 계산하지 말고 rAF 로 한 번만 예약 — 드래그 중 프레임마다
//    콜백이 오고, 콜백이 관찰 대상 크기를 바꾸면 'ResizeObserver loop' 가 터진다.
let lpend = false;
const doLayout = () => {
  const r = $('hudBox').getBoundingClientRect();
  if (r.width > 0 && r.height > 0) layout(Math.round(r.width), Math.round(r.height));
};
new ResizeObserver(() => {
  if (lpend) return;
  lpend = true;
  requestAnimationFrame(() => { lpend = false; doLayout(); });
}).observe($('hudBox'));
doLayout();

$('win').onchange = (e) => { winSec = +e.target.value; renderCharts(); };
$('msgToggle').onclick = () => {
  const c = $('chartPane').classList.toggle('msgcollapsed');
  $('msgToggle').textContent = c ? '펴기' : '접기';
};
poll();
