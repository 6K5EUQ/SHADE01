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
const CHART_SEC = 60;                 // 전류 스파크가 보여주는 시간 창
const CHART_N = CHART_SEC * 5;        // 5Hz 기준 점 개수

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
const CUR_H = 46;                     // 하단 전류 밴드 높이
const BAND_H = 52;                    // 하단 상태 밴드 높이

const SVGNS = 'http://www.w3.org/2000/svg';
const $ = (id) => document.getElementById(id);

// ── 레이아웃 변수. layout() 에서만 갱신, 매 프레임 transform 이 이걸 읽는다 ──
let W = 0, H = 0, TAPE_W = 72, AY0 = HDG_H, AY1 = 0, AH = 0;
let cx = 0, cy = 0, ARC_R = 0, CENTER_DY = 0, BAR_X0 = 140, BAR_W = 0;
let NARROW = false;                   // 상태밴드 한 칸(W/4)이 글자를 못 담는 폭

const h = {};                         // HUD 노드 참조
let map, trackLine, craft, homeMarker, fenceCircle;
// 미션 폴리라인은 없다: mav_live.py 가 st.mission 을 [] 로 초기화한 뒤 채우는
// MISSION_ITEM 핸들러가 없어 항상 빈 배열이다. 서버에 미션 다운로드를 구현하기
// 전까지는 그릴 것이 없다 — 다음 사람이 다시 시도하지 않게 남긴다.
let follow = true;
let trackPts = [];                    // [lat, lon]
let trackHave = 0;                    // 서버 기준 '받은 총 개수' (배열 길이가 아니다)
let havePos = false;
const hist = { cur: [] };
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

  // ⑦ 하단 전류 밴드 — 이 기체 1위 위험이다 (8/31 최대 66.8A, 453초 중 270초가 45A 초과).
  // 숫자만으로는 '58A' 가 위험인지 안 보이므로 위치 비교로 바꾼다.
  h.curBg = el('rect', { fill: 'rgba(13,17,23,.72)' }, svg);
  h.curTop = el('line', { stroke: 'var(--border-2)', 'stroke-width': 1 }, svg);
  h.curSpark = el('path', { fill: 'none', stroke: 'var(--dim)', opacity: .45, 'stroke-width': 1.4 }, svg);
  h.curTrack = el('rect', { fill: 'var(--panel-2)' }, svg);
  h.curFill = el('rect', { fill: 'var(--c-cur)' }, svg);
  h.ref45 = el('line', { stroke: 'var(--warn)', 'stroke-width': 2 }, svg);
  h.ref45t = el('text', { 'font-size': 9, fill: 'var(--warn)', 'text-anchor': 'middle' }, svg);
  h.ref45t.textContent = '45';
  h.ref66 = el('line', { stroke: 'var(--bad)', 'stroke-width': 2 }, svg);
  h.ref66t = el('text', { 'font-size': 9, fill: 'var(--bad)', 'text-anchor': 'middle' }, svg);
  h.ref66t.textContent = '66.8';
  h.curVal = el('text', { 'font-size': 30, 'text-anchor': 'start', fill: 'var(--c-cur)' }, svg);
  h.curUnit = el('text', { 'font-size': 12, fill: 'var(--muted)' }, svg);
  h.curUnit.textContent = 'A';

  // ⑧ 하단 상태 밴드 — GPS / EKF / 진동 3축 / RC.
  // 🔴 색 예산: 정상은 전부 무채색이다. 색이 보이는 것 자체가 신호라
  //    조종자가 읽는 건 4개 값이 아니라 '색이 있나' 하나다.
  h.cells = [];
  const NAMES = ['GPS', 'EKF', '진동', 'RC'];
  for (let i = 0; i < 4; i++) {
    const c = {
      bar: el('rect', { fill: 'var(--border-2)' }, svg),
      lbl: el('text', { 'font-size': 10, fill: 'var(--muted)' }, svg),
      val: el('text', { 'font-size': 14, fill: 'var(--dim)' }, svg),
    };
    c.lbl.textContent = NAMES[i];
    h.cells.push(c);
  }
  // 진동은 max 로 안 뭉갠다 — 3m 낙하 이력 기체에서 '어느 축이 뛴다'가 정비 지시로 직결된다.
  // 막대 뒤에 눈금 배경을 깐다. 평소 진동(실측 평균 2.5 → 26px 중 2px)은
  // 배경 없이는 사실상 안 보여서 '데이터 없음'과 구분이 안 된다.
  h.vibeTrack = [];
  h.vibeBars = [];
  for (let i = 0; i < 3; i++) h.vibeTrack.push(el('rect', { fill: 'var(--panel-2)' }, svg));
  for (let i = 0; i < 3; i++) h.vibeBars.push(el('rect', { fill: 'var(--border-2)' }, svg));

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
  AY0 = HDG_H; AY1 = H - CUR_H - BAND_H; AH = AY1 - AY0;
  cx = W / 2; cy = AY0 + AH / 2;
  // min(W,AH) 가 핵심 — max 나 W 를 쓰면 세로가 짧은 패널에서 호가 잘린다.
  ARC_R = Math.min(W, AH) * 0.36;
  CENTER_DY = Math.min(AH * 0.17, 150);
  BAR_X0 = 140; BAR_W = Math.max(40, W - 156);
  // 칸 하나가 175px 밑이면 'DGPS · 27기 · 0.19m' 가 옆 칸을 침범한다.
  NARROW = W / 4 < 175;

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

  // 전류 밴드
  const cy0 = H - CUR_H - BAND_H;
  box(h.curBg, 0, cy0, W, CUR_H);
  setAttr(h.curTop, 'x1', 0); setAttr(h.curTop, 'y1', cy0);
  setAttr(h.curTop, 'x2', W); setAttr(h.curTop, 'y2', cy0);
  setAttr(h.curVal, 'x', 12); setAttr(h.curVal, 'y', cy0 + 34);
  setAttr(h.curUnit, 'x', 100); setAttr(h.curUnit, 'y', cy0 + 34);
  box(h.curTrack, BAR_X0, cy0 + 16, BAR_W, 14);
  setAttr(h.curFill, 'x', BAR_X0); setAttr(h.curFill, 'y', cy0 + 16); setAttr(h.curFill, 'height', 14);
  const refx = (a) => BAR_X0 + (a / 70) * BAR_W;
  setAttr(h.ref45, 'x1', refx(45)); setAttr(h.ref45, 'x2', refx(45));
  setAttr(h.ref45, 'y1', cy0 + 12); setAttr(h.ref45, 'y2', cy0 + 34);
  setAttr(h.ref45t, 'x', refx(45)); setAttr(h.ref45t, 'y', cy0 + 44);
  setAttr(h.ref66, 'x1', refx(66.8)); setAttr(h.ref66, 'x2', refx(66.8));
  setAttr(h.ref66, 'y1', cy0 + 12); setAttr(h.ref66, 'y2', cy0 + 34);
  setAttr(h.ref66t, 'x', refx(66.8)); setAttr(h.ref66t, 'y', cy0 + 44);

  // 상태 밴드
  const by = H - BAND_H, cw = W / 4;
  h.cells.forEach((c, i) => {
    const x = i * cw;
    box(c.bar, x + 6, by + 8, 3, 30);
    setAttr(c.lbl, 'x', x + 16); setAttr(c.lbl, 'y', by + 20);
    setAttr(c.val, 'x', x + 16); setAttr(c.val, 'y', by + 40);
    setAttr(c.val, 'font-size', NARROW ? 12 : 14);
  });
  h.vibeBars.forEach((b, i) => {
    setAttr(b, 'x', 2 * cw + 58 + i * 10); setAttr(b, 'width', 6);
  });
  h.vibeTrack.forEach((t, i) => {
    setAttr(t, 'x', 2 * cw + 58 + i * 10); setAttr(t, 'width', 6);
    setAttr(t, 'y', H - 34); setAttr(t, 'height', 26);
  });

  box(h.freeze, 0, 0, W, H);
  setAttr(h.freezeTxt, 'x', cx); setAttr(h.freezeTxt, 'y', cy);
}

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

  // 🔴 pan:false 가 핵심이다 — 기본 인자로 부르면 재중심 팬이 일어나
  //    follow 의 5Hz panTo 와 싸운다. 창 리사이즈·900px 경계·브라우저 줌·
  //    메시지 서랍 토글을 이 하나가 다 커버한다.
  let pend = false;
  new ResizeObserver(() => {
    if (pend) return;
    pend = true;
    requestAnimationFrame(() => { pend = false; map.invalidateSize({ animate: false, pan: false }); });
  }).observe($('map'));
}

function setFollow(on) {
  follow = on;
  $('followBtn').classList.toggle('on', on);
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

// ── 전류 스파크 ─────────────────────────────────────────────────────
// 🔴 기존 spark() 의 자동 스케일을 쓰지 않는다 — 정지 중 노이즈를 산맥처럼
//    그리고 막대의 45/66.8 눈금과 축이 안 맞는다. 고정 0~70A 축이라
//    순간 피크인지 지속 과전류인지가 이 한 겹으로 갈린다.
function drawCurSpark() {
  const v = hist.cur, n = v.length;
  if (n < 2) { setAttr(h.curSpark, 'd', ''); return; }
  const y0 = H - CUR_H - BAND_H;
  const step = BAR_W / Math.max(n - 1, 1);
  let d = '', pen = false;
  for (let i = 0; i < n; i++) {
    const x = BAR_X0 + i * step;
    if (v[i] == null) { pen = false; continue; }
    const y = y0 + 40 - clamp(v[i] / 70, 0, 1) * 36;
    d += (pen ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    pen = true;
  }
  setAttr(h.curSpark, 'd', d);
}
function push(arr, v) {
  arr.push(v == null || !isFinite(v) ? null : v);
  if (arr.length > CHART_N) arr.shift();
}

// ── 렌더 ────────────────────────────────────────────────────────────
function render(s) {
  pollN++;
  const d = s.d || {};

  // ① hist 먼저. 🔴 조기반환 뒤에 두면 데이터가 안 오는 동안 시간축이 압축돼
  //    전류 스파크가 거짓 추세를 그린다.
  push(hist.cur, d.cur);
  if (pollN % 5 === 0) drawCurSpark();

  // ② 링크·프리즈·경고 만료 — 조기반환과 무관하게 항상 돈다.
  const changed = s.seq !== lastSeq;
  if (changed) { lastSeq = s.seq; lastSeqPoll = pollN; }
  const stall = (pollN - lastSeqPoll) * POLL_MS / 1000;

  const link = $('link');
  let lt, lc, frz = '';
  if (!s.packets) { lt = '링크 없음'; lc = 'pill-off'; }
  else if (!s.live) { lt = '링크 끊김'; lc = 'pill-bad'; frz = `링크 끊김 · ${Math.round(s.age)}s`; }
  else if (stall >= 3) {
    lt = '데이터 정지'; lc = 'pill-warn';
    frz = `데이터 정지 · ${stall.toFixed(0)}s (링크는 살아 있음)`;
  } else { lt = '링크 ON'; lc = 'pill-live'; }
  setText(link, lt);
  link.className = 'pill ' + lc;
  show(h.freeze, !!frz);
  show(h.freezeTxt, !!frz);
  if (frz) setText(h.freezeTxt, frz);

  setText($('stats'), s.src
    ? `${s.src} · ${s.packets.toLocaleString()}pkt · ${(s.bytes / 1024).toFixed(0)}KB`
    : 'MAVLink 대기 중…');

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

  // ── 전류 밴드
  setText(h.curVal, fmt(d.cur));
  setAttr(h.curFill, 'width', (clamp((d.cur || 0) / 70, 0, 1) * BAR_W).toFixed(1));
  // 🔴 정상 구간은 무채색이다. --c-cur 은 #f85149 로 --bad 와 **글자 그대로 같은 색**이라,
  //    그걸 기본색으로 쓰면 30A 정상 비행 내내 새빨간 막대가 켜져 있고 진짜 60A 초과가
  //    와도 안 튄다. 색이 보이는 것 자체가 신호여야 한다 (색 예산).
  const curCol = d.cur > 60 ? 'var(--bad)' : d.cur > 45 ? 'var(--warn)' : 'var(--dim)';
  setAttr(h.curFill, 'fill', curCol);
  setAttr(h.curVal, 'fill', d.cur > 45 ? curCol : 'var(--text)');

  // ── 상태 밴드
  const cell = (i, cls, txt) => {
    const c = h.cells[i];
    const col = cls === 'ok' ? 'var(--ok)' : cls === 'warn' ? 'var(--warn)'
      : cls === 'bad' ? 'var(--bad)' : 'var(--border-2)';
    setAttr(c.bar, 'fill', col);
    setAttr(c.val, 'fill', cls === 'none' ? 'var(--muted)' : cls === 'ok' ? 'var(--dim)' : col);
    setText(c.val, txt);
  };
  const fixName = { 0: 'fix없음', 1: 'fix없음', 2: '2D', 3: '3D', 4: 'DGPS', 5: 'RTK-F', 6: 'RTK-X' };
  if (d.fix != null) {
    // eph 는 실측 0.15~0.23m 로 거의 상수라 평소엔 배경이지만, fix 가 3D 를
    // 유지한 채 eph 가 먼저 부푸는 것이 열화의 첫 징후다.
    // 좁으면 eph 를 뺀다 — fix·위성수가 먼저다. 넓어지면 되살아난다.
    const e = (d.eph != null && !NARROW) ? ` · ${d.eph.toFixed(2)}m` : '';
    cell(0, d.fix >= 3 ? 'ok' : 'bad', `${fixName[d.fix] || d.fix} · ${d.sats ?? '?'}기${e}`);
  } else cell(0, 'none', '—');

  if (d.ekf) {
    const off = Object.entries(d.ekf).filter(([, v]) => !v).map(([k]) => k);
    const rt2 = d.ekf_ratio || {};
    const hot = Object.entries(rt2).filter(([, v]) => v > 1.0).map(([k]) => k);
    const worst = Math.max(0, ...Object.values(rt2));
    let cls = 'ok', txt = 'OK';
    if (off.length) { cls = off.length > 1 ? 'bad' : 'warn'; txt = off.join(','); }
    else if (hot.length) { cls = 'bad'; txt = hot.join(',') + ' ' + worst.toFixed(1); }
    else if (worst > 0.5) { cls = 'warn'; txt = worst.toFixed(2); }
    // eph_ekf 는 eph 와 단위·자릿수가 똑같아 나란히 두면 매번 되짚는다. 2m 초과일 때만.
    if (d.eph_ekf > 2) txt += ` 추정±${d.eph_ekf.toFixed(1)}m`;
    cell(1, cls, txt);
  } else cell(1, 'none', '—');

  if (d.vibe) {
    const mx = Math.max(...d.vibe);
    cell(2, mx > 30 ? 'bad' : mx > 15 ? 'warn' : 'ok', '');
    const by = H - 8;
    h.vibeBars.forEach((b, i) => {
      const v = clamp((d.vibe[i] || 0) / 30, 0, 1) * 26;
      setAttr(b, 'y', by - v); setAttr(b, 'height', v.toFixed(1));
      setAttr(b, 'fill', mx > 30 ? 'var(--bad)' : mx > 15 ? 'var(--warn)' : 'var(--border-2)');
    });
  } else {
    cell(2, 'none', '—');
    h.vibeBars.forEach((b) => setAttr(b, 'height', 0));
  }
  for (const t of h.vibeTrack) show(t, !!d.vibe);

  // RADIO_STATUS 는 SiK 관용구다. 이 기체 링크 3경로에 SiK 가 없어 영구 미수신이므로
  // 상시 자리를 주지 않고, d.rssi 가 없을 때만 출처를 밝혀 대체한다.
  if (d.rssi != null) cell(3, d.rssi < 60 ? 'bad' : d.rssi < 120 ? 'warn' : 'ok', String(d.rssi));
  else if (d.radio_rssi != null) { cell(3, 'none', 'RF ' + d.radio_rssi); }
  else cell(3, 'none', '—');

  // ── 숫자 스트립
  const sc = (id, cls) => { const e = $(id); if (e) e.className = 'sc' + (cls ? ' ' + cls : ''); };
  setText($('st-volt'), fmt(d.volt, 2));
  // PM08 DroneCAN 은 셀 전압을 안 준다 (d.cells 는 6 이 아니라 1). 6S 는
  // 하드웨어 사실이므로 volt/6 을 직접 계산한다.
  setText($('st-cell'), d.volt != null ? `V · ${(d.volt / 6).toFixed(2)}/셀` : 'V');
  sc('sc-volt', d.volt && d.volt < 21.0 ? 'bad' : d.volt && d.volt < 22.2 ? 'warn' : '');
  setText($('st-mah'), d.mah != null ? String(d.mah) : '—');
  setText($('st-pct'), d.batt_pct != null ? `mAh · ${d.batt_pct}%` : 'mAh');
  sc('sc-mah', d.batt_pct != null && d.batt_pct < 20 ? 'bad'
    : d.batt_pct != null && d.batt_pct < 35 ? 'warn' : '');
  setText($('st-thr'), d.throttle != null ? String(d.throttle) : '—');
  setText($('st-climb'), fmt(d.climb));
  setText($('st-home'), s.home && pos ? dist(s.home, pos).toFixed(0) : '—');
  sc('sc-home', s.home && pos && dist(s.home, pos) > FENCE.HOR * 0.9 ? 'warn' : '');

  // WP 칸은 AUTO.* 일 때만. 멈춘 wp_dist 는 없는 숫자보다 나쁘다.
  const auto = /^AUTO\./.test(d.mode || '');
  $('sc-wp').hidden = !auto;
  if (auto) {
    setText($('st-wp'), (d.wp_seq != null ? String(d.wp_seq) : '—')
      + (d.wp_dist != null ? ` · ${d.wp_dist.toFixed(0)}m` : ''));
    setText($('st-xt'), d.xtrack != null
      ? (d.xtrack < 0 ? '←' : '→') + Math.abs(d.xtrack).toFixed(1) + 'm' : '');
  }
  // 🔴 대기속도는 여기에만 있다. 정지 시 −4.7~−5.0 m/s 를 읽는 고장 센서라
  //    (SENS_DPRES_OFF=-4.52) 어떤 경고·색 판정에도 안 들어간다.
  setText($('st-air'), fmt(d.airspeed));
  setText($('st-load'), d.load != null ? d.load.toFixed(0) : '—');

  // ── 지도. 항적은 증분으로 온다.
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

  if (pos) {
    if (!havePos) { craft.addTo(map); map.setView(pos, 18); havePos = true; }
    craft.setLatLng(pos);
    // ⚠️ 마커의 style.transform 을 건드리면 안 된다 — Leaflet 이 거기에
    //    translate3d 로 위치를 쓰므로, 회전을 덧붙이면 매 프레임 누적되고
    //    (5Hz → 초당 5개씩 쌓인다) 다음 위치 갱신 때 지워진다.
    //    안쪽 <svg> 를 따로 돌리면 둘이 안 부딪힌다.
    const svg = craft.getElement() && craft.getElement().querySelector('svg');
    if (svg && haveHdg) svg.style.transform = `rotate(${hh}deg)`;
    if (follow) map.panTo(pos, { animate: false });
    setText($('o-lat'), d.lat.toFixed(7));
    setText($('o-lon'), d.lon.toFixed(7));
  }
  setText($('o-trk'), trackPts.length ? trackPts.length + ' pt' : '—');

  if (s.home) {
    if (!homeMarker) {
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
      // 펜스는 홈 기준이다 — arm 한 자리가 원점이지 이륙 지점이 아니다.
      fenceCircle = L.circle(s.home, {
        radius: FENCE.HOR, color: '#f85149', weight: 1, opacity: .5,
        fillOpacity: .04, dashArray: '6 6', interactive: false,
      }).addTo(map);
    } else {
      homeMarker.setLatLng(s.home);
      fenceCircle.setLatLng(s.home);
    }
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
    const r = await fetch('/api/state?since=' + trackHave, { cache: 'no-store' });
    if (r.ok) { render(await r.json()); $('link').title = ''; }
  } catch (e) {
    setText($('link'), '서버 없음');
    $('link').className = 'pill pill-off';
    $('link').title = 'mav_live.py 가 안 떠 있다';
  }
  setTimeout(poll, POLL_MS);
}

// ── 기동 ────────────────────────────────────────────────────────────
buildHUD();
initMap();

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

$('followBtn').onclick = () => setFollow(!follow);
$('msgToggle').onclick = () => {
  const c = $('mapPane').classList.toggle('msgcollapsed');
  $('msgToggle').textContent = c ? '펴기' : '접기';
};
$('clearBtn').onclick = async () => {
  if (!DEMO) await fetch('/api/reset');
  trackPts = [];
  trackHave = 0;
  trackLine.setLatLngs([]);
  hist.cur.length = 0;
  msgLastKey = ''; msgCrit = 0; lastMsgKey = ''; warnUntil = 0;
  $('msgs').innerHTML = ''; delete $('msgs').dataset.init;
};

poll();
