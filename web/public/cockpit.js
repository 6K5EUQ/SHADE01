// 콕핏 — 3D 기체 + 실시간 + 부품 + 비행 전 점검.
//
// 모델은 web/model/striver.py(Blender)가 만든 /model/striver.glb.
// 좌표: +z 기수, +y 위, 단위 m, 좌익 +x. 노드 이름으로 부품을 찾는다 —
// rotor_*, prop_nose, aileron_L/R, elevator_L/R, rudder, hatch_F/R, bay_*, in_*.
//
// 🔴 판정은 여기서 하지 않는다. 점검은 /api/preflight/stream 이 준 level·verdict
//    를 그대로 그린다 (preflight.js 와 같은 규칙, 임계값은 preflight.py 한 곳).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const $ = (id) => document.getElementById(id);
const txt = (id, s) => { const e = $(id); if (e && e.textContent !== s) e.textContent = s; };
const html = (id, s) => { const e = $(id); if (e && e.innerHTML !== s) e.innerHTML = s; };
const num = (v, n = 0) => (v == null || !Number.isFinite(v)) ? '—' : v.toFixed(n);
const icon = (n) => `<svg class="i"><use href="#i-${n}"/></svg>`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const lvl = (v, warn, bad, low = true) => v == null ? '' : low ? (v < bad ? 'bad' : v < warn ? 'warn' : '') : (v > bad ? 'bad' : v > warn ? 'warn' : '');
const mins = (s) => s == null ? '—' : s < 60 ? `${Math.round(s)}초` : `${Math.floor(s / 60)}분 ${String(Math.round(s % 60)).padStart(2, '0')}초`;

let S = { live: false, d: {} };   // /api/live/state
let R = null;                      // 비행 기록 요약
let tab = 'sum';
let sel = null;                    // 고른 탑재칸
let mode = '3d';                   // 3d | map
const D = () => (S.live ? (S.d || {}) : {});

// ── 부품 — components/*/README.md 에서 옮긴 요약 ─────────────────────
const BAYS = {
  head: { name: '기수', hatch: 'hatch_F', rows: [
    ['크루즈 모터', 'MFE X4120 KV430'],
    ['크루즈 ESC', 'MFE ESC 6100 · 6S 100A · 85 g'],
    ['프롭', '2엽 견인식'] ] },
  battery: { name: '배터리', hatch: 'hatch_F', rows: [
    ['배터리', 'Fullymax 6S 16000 mAh'],
    ['정격', '22.2 V · 25C (400 A)'],
    ['무게', '2,150 g · XT90-S'] ] },
  power: { name: '배전', hatch: 'hatch_F', rows: [
    ['전원 모듈', 'Holybro PM08-CAN · 200 A'],
    ['배전판', 'Holybro PDB 300A'],
    ['서보 전원', 'MFE UBEC 3–14S · 10 A'] ] },
  payload: { name: '탑재', hatch: 'hatch_R', rows: [
    ['탑재칸', '220 × 150 × 110 mm'],
    ['최대 탑재', '1 kg'],
    ['페이로드', 'SDR 신호정보 장비'] ] },
  fc: { name: 'FC', hatch: 'hatch_R', rows: [
    ['비행제어기', 'Holybro Pixhawk 6C Mini'],
    ['펌웨어', 'PX4 v1.17.0'],
    ['수신기', 'RadioMaster RP4TD-M · ELRS 2.4 GHz'] ] },
  gps: { name: 'GPS', hatch: null, rows: [
    ['GPS', 'Holybro M10N · u-blox M10'],
    ['컴퍼스', 'IST8310'],
    ['정확도', '2.0 m CEP'] ] },
};
const TAB_INFO = {
  sum: { name: 'Striver Mini VTOL 4+1', rows: [
    ['익폭', '2,100 mm'], ['동체', '1,200 mm'], ['최대 이륙', '6.98 kg'], ['순항', '18–21 m/s'] ] },
  pwr: { name: '동력', bays: ['head'], rows: [
    ['VTOL 모터', 'MFE M4112 KV460 × 4'], ['VTOL ESC', 'MFE ESC 650 · 6S 50A × 4'],
    ['크루즈 모터', 'MFE X4120 KV430'], ['크루즈 ESC', 'MFE ESC 6100 · 6S 100A'],
    ['조종면 서보', 'MFE S3054 × 5'] ] },
  nav: { name: '항법', bays: ['fc', 'gps'], rows: [
    ['비행제어기', 'Pixhawk 6C Mini · STM32H743'], ['IMU', 'ICM-42688-P · BMI088'],
    ['기압계', 'MS5611'], ['GPS', 'Holybro M10N · u-blox M10'], ['대기속도', 'Holybro DroneCAN'] ] },
  bat: { name: '전원', bays: ['battery', 'power'], rows: [
    ['배터리', 'Fullymax 6S 16000 mAh · 2,150 g'], ['전원 모듈', 'Holybro PM08-CAN · 200 A'],
    ['배전판', 'Holybro PDB 300A'], ['서보 전원', 'MFE UBEC · 10 A'] ] },
  rec: null,
  pf: null,
};

// 점검 묶음 → 기체 부위. 소프트웨어 설정(failsafe·미션 등)은 부위가 없다.
const PF_BAY = {
  'GPS·추정': ['gps'], '전원': ['battery', 'power'], '센서': ['fc'], '링크': ['fc'],
  '기체 상태': ['fc'], 'FC 자신의 말': ['fc'], '파라미터': ['fc'], 'ARM 조건': ['fc'],
  '회로차단기': ['fc'], '기록': ['fc'],
};
const LV_COLOR = { ok: 0x1f9d55, warn: 0xd99a06, blk: 0xdc2626, info: 0x828284 };
const LV_RANK = { info: 0, ok: 1, warn: 2, blk: 3 };

// ── 3D ───────────────────────────────────────────────────────────────
const canvas = $('view');
let renderer = null;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); } catch { canvas.style.display = 'none'; }

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(26, 1, 0.05, 50);
const craft = new THREE.Group();      // 사용자가 끌어 돌리는 것
const attitude = new THREE.Group();   // 실시간 자세
craft.add(attitude); scene.add(craft);

scene.add(new THREE.HemisphereLight(0xffffff, 0xdedee3, 1.5));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(1.4, 3.4, 1.8); sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048); sun.shadow.radius = 6; sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.01;
Object.assign(sun.shadow.camera, { left: -1.4, right: 1.4, top: 1.4, bottom: -1.4, near: 0.5, far: 8 });
scene.add(sun);
const fill = new THREE.DirectionalLight(0xf2f4ff, 0.9); fill.position.set(-2.5, 1.2, -1.5); scene.add(fill);
const front = new THREE.DirectionalLight(0xffffff, 0.5); front.position.set(0, 0.6, 3); scene.add(front);

const FLOOR = -0.125;
const ground = new THREE.Mesh(new THREE.PlaneGeometry(10, 10), new THREE.ShadowMaterial({ opacity: 0.16 }));
ground.rotation.x = -Math.PI / 2; ground.position.y = FLOOR; ground.receiveShadow = true; scene.add(ground);
{ // 접지 그림자 — 기체 밑이 가장 진하고 바깥으로 사라진다
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const x = c.getContext('2d'), gr = x.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, 'rgba(40,40,48,.30)'); gr.addColorStop(.5, 'rgba(40,40,48,.10)'); gr.addColorStop(1, 'rgba(40,40,48,0)');
  x.fillStyle = gr; x.fillRect(0, 0, 256, 256);
  const blob = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.8), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
  blob.rotation.x = -Math.PI / 2; blob.position.y = FLOOR + 0.001; craft.add(blob);
}

if (renderer) {
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;
  // 금속 재질이 비칠 환경 — 밝은 스튜디오
  const pm = new THREE.PMREMGenerator(renderer);
  const env = new THREE.Scene();
  env.background = new THREE.Color(0xf0f0f3);
  const panel = (w, h, pos, s) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide })); m.position.set(...pos); m.lookAt(0, 0, 0); m.material.color.multiplyScalar(s); env.add(m); };
  panel(6, 2, [0, 5, 0], 2.2); panel(3, 3, [5, 2, 3], 1.4); panel(3, 3, [-5, 1, -2], 1.0);
  const floorM = new THREE.Mesh(new THREE.PlaneGeometry(20, 20), new THREE.MeshBasicMaterial({ color: 0x9a9aa0, side: THREE.DoubleSide }));
  floorM.rotation.x = -Math.PI / 2; floorM.position.y = -2; env.add(floorM);
  scene.environment = pm.fromScene(env, 0.04).texture;
  scene.environmentIntensity = 0.6;
}

// 모델이 오기 전까지 비어 있다 — 없으면 해당 동작만 건너뛴다
const rotors = {};          // LF/RF/LB/RB → { node, dir, v, disc }
let nose = null, anchors = {};
const surfaces = {};        // AL/AR/EL/ER/R → { node, base }
const hatches = {};         // hatch_F/R → { node, base, t }
const bays = {};            // head/... → { mesh, fill, edges, color, a }
const skin = [];            // 반투명이 되는 겉면 재질
let skinT = 0;              // 0 불투명 ~ 1 반투명
const discMat = new THREE.MeshBasicMaterial({ color: 0x5a5d63, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false });
function addDisc(node, R) {
  const d = new THREE.Mesh(new THREE.CircleGeometry(R, 64), discMat.clone());
  d.rotation.x = -Math.PI / 2; node.add(d); return d;
}
// 동체·날개와 그 위의 표식 — 칸을 열면 비친다
const SKIN = /^(fuselage|wing|wing_mid|wing_tip|center_panel|root_band|boom_|belly|registration|name|panel_seam|hatch_l|hatch_r|servo_|hinge_|clamp_)/;

new GLTFLoader().load('/model/striver.glb', (g) => {
  const m = g.scene;
  m.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = true; o.receiveShadow = true;
    if (SKIN.test(o.name)) {
      o.material = o.material.clone();
      o.material.transparent = true;
      skin.push(o.material);
    }
  });
  for (const k of ['LF', 'RF', 'LB', 'RB']) {
    const n = m.getObjectByName('rotor_' + k);
    if (n) rotors[k] = { node: n, dir: (k === 'RF' || k === 'LB') ? 1 : -1, v: 0, disc: addDisc(n, 0.215) };
  }
  const pn = m.getObjectByName('prop_nose');
  if (pn) nose = { node: pn, v: 0, disc: addDisc(pn, 0.18) };
  for (const [k, name] of [['AL', 'aileron_L'], ['AR', 'aileron_R'], ['EL', 'elevator_L'], ['ER', 'elevator_R'], ['R', 'rudder']]) {
    const n = m.getObjectByName(name);
    if (n) surfaces[k] = { node: n, base: n.quaternion.clone(), a: 0 };
  }
  for (const name of ['hatch_F', 'hatch_R']) {
    const n = m.getObjectByName(name);
    if (n) hatches[name] = { node: n, base: n.position.clone(), t: 0 };
  }
  for (const k of Object.keys(BAYS)) {
    const mesh = m.getObjectByName('bay_' + k);
    if (!mesh) continue;
    // 클릭 영역. 안 보이게 두되 광선은 맞는다 (colorWrite 만 끈다).
    mesh.castShadow = mesh.receiveShadow = false;
    mesh.material = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false });
    const fillM = new THREE.MeshBasicMaterial({ color: 0x3e6ae1, transparent: true, opacity: 0, depthWrite: false });
    const fillMesh = new THREE.Mesh(mesh.geometry, fillM);
    fillMesh.renderOrder = 5;
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 40),   // 곡면 안쪽 선은 빼고 양 끝 테두리만
      new THREE.LineBasicMaterial({ color: 0x3e6ae1, transparent: true, opacity: 0, depthTest: false }));
    edges.renderOrder = 6;
    mesh.add(fillMesh, edges);
    bays[k] = { mesh, fill: fillM, edges: edges.material, a: 0 };
  }
  // 부위 표시가 붙을 자리
  const at = (name, off = [0, 0, 0]) => { const n = m.getObjectByName(name); if (!n) return null; const a = new THREE.Object3D(); a.position.set(...off); n.add(a); return a; };
  anchors = {
    gps: at('gps', [0, 0.02, 0]),
    bat: at('bay_battery', [0, 0.1, 0]),
    nose: at('prop_nose'),
    LF: at('rotor_LF'), RF: at('rotor_RF'), LB: at('rotor_LB'), RB: at('rotor_RB'),
  };
  attitude.add(m);
  $('loading').remove();
  setView();
}, (e) => { if (e.total) $('loading').firstChild.style.width = (100 * e.loaded / e.total) + '%'; },
() => { $('loading').remove(); });

// ── 조작 — 끌면 기체가 돈다, 휠·두 손가락은 거리, 두 번 누르면 제자리, 눌러서 칸 선택 ──
const VIEWS = {
  sum: { yaw: -2.6, tilt: 0.6, dist: 3.9 },
  pwr: { yaw: -2.75, tilt: 0.78, dist: 4.1 },
  nav: { yaw: 0.65, tilt: 0.45, dist: 3.3 },
  bat: { yaw: -1.9, tilt: 0.5, dist: 3.3 },
  rec: { yaw: -2.6, tilt: 0.6, dist: 3.9 },
  pf: { yaw: -2.1, tilt: 0.75, dist: 3.4 },
  bay: { yaw: -1.25, tilt: 0.62, dist: 2.3 },
};
const cam = { ...VIEWS.sum, vYaw: 0, vTilt: 0 };
const goal = { ...VIEWS.sum, on: false };
const look = new THREE.Vector3(0, 0.02, 0);
const ptrs = new Map();
let pinch0 = 0, dist0 = 0, down = null;
const clampTilt = (t) => Math.max(-0.15, Math.min(1.4, t));
const clampDist = (d) => Math.max(1.4, Math.min(8, d));
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
function pickBay(e) {
  const r = canvas.getBoundingClientRect();
  ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const hit = ray.intersectObjects(Object.values(bays).map((b) => b.mesh), false)[0];
  return hit ? Object.keys(bays).find((k) => bays[k].mesh === hit.object) : null;
}
let hover = null;
canvas.addEventListener('pointerdown', (e) => {
  canvas.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
  down = { x: e.clientX, y: e.clientY };
  canvas.classList.add('drag'); goal.on = false; cam.vYaw = cam.vTilt = 0;
  if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch0 = Math.hypot(a[0] - b[0], a[1] - b[1]); dist0 = cam.dist; }
});
canvas.addEventListener('pointermove', (e) => {
  const p = ptrs.get(e.pointerId);
  if (!p) {   // 끌지 않는 중 — 칸 위면 손 모양
    hover = e.pointerType === 'mouse' ? pickBay(e) : null;
    canvas.style.cursor = hover ? 'pointer' : '';
    return;
  }
  if (ptrs.size === 1) {
    const dx = e.clientX - p[0], dy = e.clientY - p[1];
    cam.vYaw = dx * 0.008; cam.vTilt = dy * 0.006;
    cam.yaw += cam.vYaw; cam.tilt = clampTilt(cam.tilt + cam.vTilt);
  }
  p[0] = e.clientX; p[1] = e.clientY;
  if (ptrs.size === 2) {
    const [a, b] = [...ptrs.values()];
    cam.dist = clampDist(dist0 * pinch0 / Math.max(1, Math.hypot(a[0] - b[0], a[1] - b[1])));
  }
});
const up = (e) => {
  ptrs.delete(e.pointerId);
  if (!ptrs.size) canvas.classList.remove('drag');
  // 거의 안 움직였으면 누른 것이다
  if (down && e.type === 'pointerup' && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 6) {
    const k = pickBay(e);
    if (k) selectBay(k === sel ? null : k);
  }
  down = null;
};
canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
canvas.addEventListener('pointerleave', () => { hover = null; });
canvas.addEventListener('wheel', (e) => { e.preventDefault(); goal.on = false; cam.dist = clampDist(cam.dist * Math.exp(e.deltaY * 0.001)); }, { passive: false });
canvas.addEventListener('dblclick', () => setView());

function setView() {
  const v = VIEWS[sel ? 'bay' : tab], twoPi = Math.PI * 2;
  goal.yaw = v.yaw + Math.round((cam.yaw - v.yaw) / twoPi) * twoPi;   // 가까운 쪽으로 돈다
  goal.tilt = v.tilt; goal.dist = v.dist; goal.on = true; cam.vYaw = cam.vTilt = 0;
}

function resize() {
  const r = canvas.getBoundingClientRect();
  if (!renderer || !r.width) return;
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / r.height;
  camera.userData.k = Math.max(1, 1.35 / camera.aspect);   // 좁으면 물러선다
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvas);

// ── 칸 선택 ──────────────────────────────────────────────────────────
function selectBay(k) {
  sel = k;
  setView();
  renderInfo();
  renderCalls();
}

/** 칸마다 지금 칠할 색과 세기. 점검 탭이면 판정 색, 아니면 고른 칸·탭 칸만 파랑. */
function bayLook(k) {
  if (tab === 'pf' && !sel) {
    const lv = pf.bayLevel[k];
    return lv ? { color: LV_COLOR[lv], a: 1 } : { color: 0x3e6ae1, a: 0 };
  }
  if (sel) return { color: 0x3e6ae1, a: k === sel ? 1 : 0 };
  const tb = TAB_INFO[tab];
  if (tb && tb.bays && tb.bays.includes(k)) return { color: 0x3e6ae1, a: 0.7 };
  return { color: 0x3e6ae1, a: k === hover ? 0.5 : 0 };
}

// ── 부위 표시 ────────────────────────────────────────────────────────
const CALLS = {
  sum: (d) => [['bat', 'BATTERY', d.batt_pct != null ? `${d.batt_pct}%` : '—', lvl(d.batt_pct, 35, 20)]],
  pwr: (d) => { const m = d.motors || {}; const f = (k) => m[k] != null ? `${Math.round(m[k])}%` : '—';
    return [['LF', 'LF', f('LF')], ['RF', 'RF', f('RF')], ['LB', 'LB', f('LB')], ['RB', 'RB', f('RB')],
            ['nose', 'CRUISE', d.cruise != null ? `${Math.round(d.cruise)}%` : '—']]; },
  nav: (d) => [['gps', 'GPS', d.sats != null ? `${d.sats}기 · ${num(d.eph, 1)}m` : '—', lvl(d.sats, 8, 5)],
               ['nose', 'HEADING', d.hdg != null ? `${Math.round(d.hdg)}°` : '—']],
  bat: (d) => [['bat', 'BATTERY', d.volt != null ? `${d.volt.toFixed(1)}V · ${num(d.cur, 1)}A` : '—', lvl(d.batt_pct, 35, 20)]],
  rec: () => [],
  pf: () => [],
};
const callEls = new Map();
function renderCalls() {
  const want = sel || mode !== '3d' ? [] : CALLS[tab](D());
  const keep = new Set();
  for (const [a, k, v, c] of want) {
    keep.add(a);
    let el = callEls.get(a);
    if (!el) {
      el = document.createElement('div'); el.className = 'call';
      el.innerHTML = '<span class="k"></span><span class="v"></span><i></i>';
      $('calls').append(el); callEls.set(a, el);
    }
    el.children[0].textContent = k;
    el.children[1].textContent = v;
    el.children[1].className = 'v ' + (c || '');
  }
  for (const [a, el] of callEls) if (!keep.has(a)) { el.remove(); callEls.delete(a); }
}
const tmpV = new THREE.Vector3();
function placeCalls() {
  const r = canvas.getBoundingClientRect();
  const moving = goal.on && Math.abs(goal.yaw - cam.yaw) + Math.abs(goal.tilt - cam.tilt) > 0.08;
  for (const [a, el] of callEls) {
    const o = anchors[a];
    if (!o) { el.style.opacity = 0; continue; }
    o.getWorldPosition(tmpV); tmpV.project(camera);
    const x = (tmpV.x + 1) / 2 * r.width, y = (1 - tmpV.y) / 2 * r.height;
    el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -100%)`;
    el.style.opacity = moving || y < 150 ? 0 : 1;   // 시점이 크게 바뀌는 동안은 숨긴다
  }
}

// ── 그리기 ───────────────────────────────────────────────────────────
// 조종면 방향 — 서보 값(-1~+1)에 곱하는 부호. 기체마다 반전이 달라
// 실기와 맞춰 봐야 한다 (엘리베이터는 FC 에서 반전돼 있다, OPERATIONS.md 2026-09-01).
const SURF_DIR = { AL: 1, AR: -1, EL: 1, ER: -1, R: 1 };
const SURF_MAX = THREE.MathUtils.degToRad(25);
// AUX1/AUX3 가 어느 쪽 엘리베이터인지는 아직 실측 전이다 — E1 을 좌로 둔다.
const SURF_SRC = { AL: 'AL', AR: 'AR', EL: 'E1', ER: 'E2', R: 'R' };
const qTmp = new THREE.Quaternion(), yAxis = new THREE.Vector3(0, 1, 0);
const lookGoal = new THREE.Vector3();

const timer = new THREE.Timer();
function frame() {
  requestAnimationFrame(frame);
  if (!renderer || mode !== '3d') return;
  timer.update();
  const dt = Math.min(timer.getDelta(), 0.05);
  const ease = (r) => 1 - Math.exp(-dt * r);
  if (goal.on) {
    const k = ease(3.2);
    cam.yaw += (goal.yaw - cam.yaw) * k; cam.tilt += (goal.tilt - cam.tilt) * k; cam.dist += (goal.dist - cam.dist) * k;
    if (Math.abs(goal.yaw - cam.yaw) < 0.003 && Math.abs(goal.tilt - cam.tilt) < 0.003) goal.on = false;
  } else if (!ptrs.size) {
    cam.yaw += cam.vYaw; cam.tilt = clampTilt(cam.tilt + cam.vTilt);
    cam.vYaw *= 0.93; cam.vTilt *= 0.88;
  }
  craft.rotation.y = cam.yaw;
  craft.updateMatrixWorld();
  // 고른 칸을 가운데로
  if (sel && bays[sel]) bays[sel].mesh.getWorldPosition(lookGoal); else lookGoal.set(0, 0.02, 0);
  look.lerp(lookGoal, ease(4));
  const dist = cam.dist * (camera.userData.k || 1);
  camera.position.set(look.x, look.y + Math.sin(cam.tilt) * dist, look.z + Math.cos(cam.tilt) * dist);
  camera.lookAt(look);

  // 실시간 자세 — 기체가 붙어 있을 때만, 없으면 수평으로 돌아온다
  const d = D();
  const tr = d.roll != null ? THREE.MathUtils.degToRad(d.roll) : 0;
  const tp = d.pitch != null ? THREE.MathUtils.degToRad(d.pitch) : 0;
  attitude.rotation.order = 'YXZ';
  attitude.rotation.z += (tr - attitude.rotation.z) * ease(6);
  attitude.rotation.x += (-tp - attitude.rotation.x) * ease(6);

  // 로터 — ARM 이고 출력이 있으면 돈다. 빨라지면 날 대신 원판이 보인다.
  const mt = d.motors || {};
  for (const [k, r] of Object.entries(rotors)) {
    const pct = d.armed ? (mt[k] ?? 0) : 0;
    r.v += ((pct > 0 ? 10 + pct * 0.6 : 0) - r.v) * ease(2);
    r.node.rotateY(r.dir * r.v * dt);
    r.disc.material.opacity = Math.min(0.09, Math.max(0, (r.v - 12) / 200));
  }
  if (nose) {
    // 크루즈 출력(MAIN8)이 오면 그 값대로, 아니면 FW·천이일 때만
    const pct = !d.armed ? 0 : d.cruise != null ? d.cruise
      : (d.vtol === 'FW' || /TRANSITION/.test(d.vtol || '')) ? 70 : 0;
    nose.v += ((pct > 0 ? 10 + pct * 0.6 : 0) - nose.v) * ease(2);
    nose.node.rotateY(nose.v * dt);
    nose.disc.material.opacity = Math.min(0.09, Math.max(0, (nose.v - 12) / 200));
  }
  // 조종면 — 서보 출력대로. 값이 없으면 중립으로 돌아온다.
  const sv = d.servos || {};
  for (const [k, s] of Object.entries(surfaces)) {
    const v = sv[SURF_SRC[k]];
    const want = v == null ? 0 : v * SURF_DIR[k] * SURF_MAX;
    s.a += (want - s.a) * ease(10);
    s.node.quaternion.copy(s.base).multiply(qTmp.setFromAxisAngle(yAxis, s.a));
  }
  // 해치 — 고른 칸의 해치만 들린다
  const open = sel && BAYS[sel].hatch;
  for (const [name, h] of Object.entries(hatches)) {
    h.t += ((open === name ? 1 : 0) - h.t) * ease(5);
    h.node.position.set(h.base.x, h.base.y + 0.11 * h.t, h.base.z - (name === 'hatch_F' ? 0.05 : -0.05) * h.t);
  }
  // 겉면 — 칸을 고르면 비친다
  skinT += ((sel && sel !== 'gps' ? 1 : 0) - skinT) * ease(5);
  for (const m of skin) {
    m.opacity = 1 - 0.85 * skinT;
    m.depthWrite = skinT < 0.5;
  }
  // 칸 강조
  for (const [k, b] of Object.entries(bays)) {
    const L = bayLook(k);
    b.a += (L.a - b.a) * ease(8);
    b.fill.color.setHex(L.color); b.edges.color.setHex(L.color);
    b.fill.opacity = 0.24 * b.a; b.edges.opacity = 0.9 * b.a;
  }
  renderer.render(scene, camera);
  placeCalls();
}
frame();

// ── 정보 카드 ────────────────────────────────────────────────────────
function rowsHtml(rows) {
  return rows.map(([k, v]) => `<div class="row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
}
function renderInfo() {
  const box = $('info');
  if (mode !== '3d') { box.hidden = true; return; }
  if (sel) {
    const b = BAYS[sel];
    box.hidden = false;
    box.innerHTML = `<div class="ih"><b>${esc(b.name)}</b><button class="x" id="infoX" aria-label="닫기">×</button></div>${rowsHtml(b.rows)}`;
    $('infoX').onclick = () => selectBay(null);
    return;
  }
  if (tab === 'pf') { box.hidden = false; renderPf(); return; }
  const t = TAB_INFO[tab];
  if (!t) { box.hidden = true; return; }
  box.hidden = false;
  const chips = (t.bays || []).map((k) => `<button class="chip" data-bay="${k}">${esc(BAYS[k].name)}</button>`).join('');
  box.innerHTML = `<div class="ih"><b>${esc(t.name)}</b></div>${rowsHtml(t.rows)}${chips ? `<div class="chips">${chips}</div>` : ''}`;
}
$('info').addEventListener('click', (e) => {
  const c = e.target.closest('[data-bay]');
  if (c) selectBay(c.dataset.bay);
});

// ── 탭·타일 ──────────────────────────────────────────────────────────
const TILES = {
  sum: (d) => [
    ['alt', '고도', num(d.alt, 1), 'm'],
    ['spd', '대지속도', num(d.groundspeed, 1), 'm/s'],
    ['air', '대기속도', num(d.airspeed, 1), 'm/s'],
    ['climb', '상승률', num(d.climb, 1), 'm/s'],
    ['hdg', '헤딩', num(d.hdg), '°'],
  ],
  pwr: (d) => {
    const m = d.motors || {};
    return [['LF', '좌전'], ['RF', '우전'], ['LB', '좌후'], ['RB', '우후']]
      .map(([k, l]) => ['rotor', l, num(m[k]), '%', '', d.armed && m[k] > 0])
      .concat([['air', '크루즈', num(d.cruise), '%', '', d.armed && d.cruise > 0]]);
  },
  nav: (d) => [
    ['sat', '위성', num(d.sats), '기', lvl(d.sats, 8, 5)],
    ['pin', '수평 오차', num(d.eph, 1), 'm', lvl(d.eph, 3, 6, false)],
    ['pin', '위도', num(d.lat, 5), ''],
    ['pin', '경도', num(d.lon, 5), ''],
    ['hdg', '헤딩', num(d.hdg), '°'],
  ],
  bat: (d) => [
    ['bat', '잔량', num(d.batt_pct), '%', lvl(d.batt_pct, 35, 20)],
    ['volt', '전압', num(d.volt, 2), 'V'],
    ['cur', '전류', num(d.cur, 1), 'A'],
    ['temp', '온도', num(d.batt_temp, 1), '°C'],
  ],
  rec: () => R ? [
    ['count', '비행 횟수', String(R.n), '회'],
    ['time', '누적 비행', num(R.min), '분'],
    ['alt', '최고 고도', num(R.alt, 1), 'm'],
    ['spd', '최대 속도', num(R.spd, 1), 'm/s'],
    ['cur', '최대 전류', num(R.cur), 'A'],
  ] : [],
  pf: () => [],
};
function renderTiles() {
  html('tiles', mode !== '3d' ? '' : TILES[tab](D()).map(([ic, l, v, u, c, on]) =>
    `<div class="tile ${c || ''}${on ? ' on' : ''}">${icon(ic)}<b class="num">${v}${u && v !== '—' ? `<small>${u}</small>` : ''}</b><span>${l}</span></div>`).join(''));
  renderCalls();
}
$('tabs').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  tab = b.dataset.t; sel = null;
  for (const x of $('tabs').children) x.classList.toggle('on', x === b);
  setView(); renderTiles(); renderInfo();
});

// ── 기체 / 지도 ──────────────────────────────────────────────────────
let lmap = null, trackLine = null, acMarker = null, homeMarker = null;
let track = [], trkHave = 0, followAt = 0;
const AC_SVG = '<svg viewBox="0 0 32 32" width="34" height="34"><path d="M16 3l3 11 9 3v3l-9-1-1 7 3 2v2l-5-1-5 1v-2l3-2-1-7-9 1v-3l9-3z" fill="#3e6ae1" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
async function ensureMap() {
  if (lmap) return;
  if (!window.L) {
    await new Promise((res, rej) => { const s = document.createElement('script'); s.src = '/vendor/leaflet/leaflet.js'; s.onload = res; s.onerror = rej; document.head.append(s); });
  }
  const L = window.L;
  lmap = L.map('map', { zoomControl: false, attributionControl: true });
  lmap.setView([36.5, 127.8], 7);   // 🔴 레이어 전에 뷰부터 (live.js 와 같은 함정)
  L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 20, maxNativeZoom: 18, attribution: 'Esri World Imagery' }).addTo(lmap);
  trackLine = L.polyline([], { color: '#3e6ae1', weight: 3, opacity: 0.95 }).addTo(lmap);
  acMarker = L.marker([0, 0], { icon: L.divIcon({ className: 'ac', html: AC_SVG, iconSize: [34, 34], iconAnchor: [17, 17] }), interactive: false });
  homeMarker = L.circleMarker([0, 0], { radius: 6, color: '#fff', weight: 2, fillColor: '#171a20', fillOpacity: 1 });
  lmap.on('dragstart', () => { followAt = Date.now(); });
}
function renderMap() {
  if (!lmap) return;
  const d = D();
  trackLine.setLatLngs(track.map((p) => [p[0], p[1]]));
  const hm = Array.isArray(S.home) ? { lat: S.home[0], lon: S.home[1] } : S.home;
  if (hm && hm.lat != null) homeMarker.setLatLng([hm.lat, hm.lon]).addTo(lmap);
  if (d.lat != null && d.lon != null) {
    acMarker.setLatLng([d.lat, d.lon]).addTo(lmap);
    const el = acMarker.getElement();
    if (el) el.firstChild.style.transform = `rotate(${d.hdg || 0}deg)`;
    // 손으로 끈 뒤 8초는 따라가지 않는다 (live.js 와 같은 규칙)
    if (Date.now() - followAt > 8000) lmap.setView([d.lat, d.lon], Math.max(lmap.getZoom(), 17), { animate: false });
  } else if (track.length) {
    lmap.fitBounds(trackLine.getBounds(), { padding: [40, 40] });
  }
}
async function setMode(m) {
  mode = m;
  for (const b of document.querySelectorAll('#modes button')) b.classList.toggle('on', b.dataset.m === m);
  document.querySelector('.main').classList.toggle('mapmode', m === 'map');
  if (m === 'map') { await ensureMap(); lmap.invalidateSize(); trkHave = 0; track = []; if (!pb.on) pollLive(true); }
  renderTiles(); renderInfo(); resize();
}
$('modes').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) setMode(b.dataset.m); });

// ── 비행 전 점검 ─────────────────────────────────────────────────────
// preflight.js 와 같은 스트림·암호(sessionStorage pf_pw)를 쓴다.
const pf = { state: 'idle', groups: [], res: {}, prog: {}, verdict: null, error: null, notes: [], at: null, open: null, bayLevel: {} };
let pfPw = '';
try { pfPw = sessionStorage.getItem('pf_pw') || ''; } catch { /* 사설 모드 */ }
const PF_SECS = 10;
const PF_MARK = { blk: '✖', warn: '▲', ok: '✔', info: '·' };

function pfBayLevels() {
  const out = {};
  for (const g of Object.values(pf.res)) {
    for (const k of PF_BAY[g.name] || []) {
      if (!out[k] || LV_RANK[g.level] > LV_RANK[out[k]]) out[k] = g.level;
    }
  }
  pf.bayLevel = out;
}
function renderPf() {
  const box = $('info');
  let h = '<div class="ih"><b>비행 전 점검</b>' + (pf.at ? `<span class="at">${esc(pf.at.replace('T', ' ').slice(5, 16))}</span>` : '') + '</div>';
  if (pf.verdict) {
    const go = pf.verdict === 'GO';
    h += `<div class="verdict ${go ? 'ok' : 'blk'}">${go ? 'GOOD TO GO' : 'NO GO'}</div>`;
  }
  if (pf.error) {
    h += `<div class="pferr"><b>${esc(pf.error)}</b>${(pf.notes || []).map((n) => `<div>· ${esc(n)}</div>`).join('')}</div>`;
  }
  if (pf.groups.length) {
    h += '<ol class="pfl">' + pf.groups.map((g) => {
      const r = pf.res[g.name];
      const p = pf.prog[g.name];
      const right = r ? esc(r.verdict) : p > 0 ? Math.round(p * 100) + '%' : '대기';
      const cls = r ? r.level : p > 0 ? 'run' : 'wait';
      let body = '';
      if (r && pf.open === g.name) {
        body = '<div class="pfb">' + (r.items.length ? r.items.map((it) =>
          `<div class="it ${it.level}"><i>${PF_MARK[it.level] || '·'}</i><span>${esc(it.name)}</span><em>${esc(it.detail)}</em>${it.why ? `<p>${esc(String(it.why).replace(/\*\*/g, ''))}</p>` : ''}</div>`).join('')
          : '<div class="it info"><span>읽은 것이 없다</span></div>') + '</div>';
      }
      return `<li class="${cls}" style="--pct:${r ? 100 : Math.round((p || 0) * 100)}%"><button data-g="${esc(g.name)}"><span>${esc(g.label)}</span><b>${right}</b></button>${body}</li>`;
    }).join('') + '</ol>';
  }
  h += `<button class="pfgo" id="pfGo" ${pf.state === 'run' ? 'disabled' : ''}>${pf.state === 'run' ? '점검 중' : pf.verdict || pf.error ? '다시 점검' : '기체 점검'}</button>`;
  box.innerHTML = h;
  $('pfGo').onclick = () => pfRun();
}
$('info').addEventListener('click', (e) => {
  const g = e.target.closest('[data-g]');
  if (!g || !pf.res[g.dataset.g]) return;
  pf.open = pf.open === g.dataset.g ? null : g.dataset.g;
  renderPf();
});

function pfAsk(err) {
  $('pwErr').hidden = !err; $('pwErr').textContent = err || '';
  $('modal').hidden = false; $('pw').value = ''; $('pw').focus();
}
$('pwCancel').onclick = () => { $('modal').hidden = true; };
$('modal').addEventListener('click', (e) => { if (e.target === $('modal')) $('modal').hidden = true; });
$('pwForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const v = $('pw').value;
  if (!v) return;
  pfPw = v; $('modal').hidden = true; pfRun();
});

function pfLine(d) {
  if (d.t === 'agent' || d.t === 'start' || d.t === 'done') if (d.at) pf.at = d.at;
  if (d.t === 'start') { pf.groups = d.groups || []; pf.res = {}; pf.prog = {}; }
  else if (d.t === 'prog') Object.assign(pf.prog, d.progress || {});
  else if (d.t === 'group') pf.res[d.group.name] = d.group;
  else if (d.t === 'done') {
    for (const g of d.groups || []) pf.res[g.name] = g;
    if (d.error) { pf.error = d.error; pf.notes = d.notes || []; } else pf.verdict = d.verdict;
    pf.state = 'done';
  }
  pfBayLevels();
  if (tab === 'pf' && !sel) renderPf();
}

async function pfRun() {
  if (pf.state === 'run') return;
  if (!pfPw) { pfAsk(); return; }
  Object.assign(pf, { state: 'run', groups: [], res: {}, prog: {}, verdict: null, error: null, notes: [], open: null, bayLevel: {} });
  renderPf();
  try {
    const res = await fetch('/api/preflight/stream?t=' + PF_SECS, { method: 'POST', headers: { 'X-Preflight-Password': pfPw } });
    if (res.status === 401) {
      pfPw = ''; try { sessionStorage.removeItem('pf_pw'); } catch { /* 사설 모드 */ }
      pf.state = 'idle'; renderPf(); pfAsk('암호가 틀렸다'); return;
    }
    try { sessionStorage.setItem('pf_pw', pfPw); } catch { /* 사설 모드 */ }
    if (!(res.headers.get('content-type') || '').includes('ndjson')) {
      const d = await res.json().catch(() => ({ error: '응답을 읽지 못했다' }));
      pf.error = d.error || '점검하지 못했다'; pf.notes = [...(d.notes || []), ...(d.hints || [])];
      pf.state = 'done'; renderPf(); return;
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line) continue;
        try { pfLine(JSON.parse(line)); } catch { /* 반쪽 줄 */ }
      }
    }
  } catch (e) {
    pf.error = '서버에 닿지 못했다: ' + e.message;
  }
  if (pf.state === 'run') pf.state = 'done';
  if (tab === 'pf' && !sel) renderPf();
}

// ── 로그 재생 ────────────────────────────────────────────────────────
// 서버 재생 엔진(/api/playback/*, mav_live.py)을 그대로 쓴다. 상태가 실시간과
// 같은 모양이라 화면의 모든 칸이 그대로 채워진다 — 여기서는 시각만 넘긴다.
// ⚠️ 재생 세션은 서버에 하나뿐이다 — /live 에서 누가 재생 중이면 그쪽이 바뀐다.
const pb = { on: false, t: 0, dur: 0, rate: 1, playing: false, last: 0, name: '', timer: 0, seeking: false, when: '' };
const RATES = [1, 2, 4, 8];
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const fmtWhen = (utc) => { if (!utc) return ''; const t = new Date(utc + 'Z'), two = (n) => String(n).padStart(2, '0');
  return `${t.getFullYear()}.${two(t.getMonth() + 1)}.${two(t.getDate())} ${two(t.getHours())}:${two(t.getMinutes())}`; };

async function pbSheet(open) {
  const sh = $('pbSheet');
  sh.hidden = !open;
  if (!open) return;
  sh.innerHTML = '<div class="ih"><b>비행 재생</b><button class="x" id="pbSheetX" aria-label="닫기">×</button></div><div class="pbmsg">목록을 읽는 중</div>';
  $('pbSheetX').onclick = () => pbSheet(false);
  try {
    const rows = (await (await fetch('/api/logs', { cache: 'no-store' })).json())
      .filter((x) => !x.error && !x.corrupt && (x.badge === 'flight' || x.badge === 'hover'))
      .sort((a, b) => (b.utc || '').localeCompare(a.utc || '')).slice(0, 60);
    sh.querySelector('.pbmsg').remove();
    const list = document.createElement('div'); list.className = 'pbl';
    list.innerHTML = rows.map((x) => `<button data-log="${esc(x.name)}" data-utc="${esc(x.utc || '')}">
      <span class="w">${esc(fmtWhen(x.utc))}</span><span class="b ${x.badge}">${x.badge === 'flight' ? '비행' : '호버'}</span>
      <span class="n">${esc(mins(x.duration))}</span><span class="n">${x.alt_max != null ? x.alt_max.toFixed(0) + ' m' : '—'}</span></button>`).join('');
    sh.append(list);
  } catch { sh.querySelector('.pbmsg').textContent = '목록을 읽지 못했다'; }
}
$('pbSheet').addEventListener('click', (e) => {
  const b = e.target.closest('[data-log]');
  if (b) pbStart(b.dataset.log, b.dataset.utc);
});
$('pbBtn').onclick = () => (pb.on ? null : pbSheet($('pbSheet').hidden));

async function pbStart(name, utc) {
  pbSheet(false);
  if (pb.on) await pbStop(true);
  pb.name = name; pb.when = fmtWhen(utc);
  document.querySelector('.main').classList.add('pbmode');
  $('pbBar').hidden = false;
  $('pbName').textContent = pb.when + ' · 여는 중';
  $('pbSeek').disabled = true;
  try {
    const r = await fetch('/api/playback/open?name=' + encodeURIComponent(name), { cache: 'no-store' });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || '열지 못했다');
    for (;;) {   // 큰 로그는 굽는 데 수십 초 걸린다
      await new Promise((z) => setTimeout(z, 400));
      const info = await (await fetch('/api/playback/info', { cache: 'no-store' })).json();
      if (info.state === 'ready') { pb.dur = info.dur; break; }
      if (info.state === 'error') throw new Error(info.error || '읽을 수 없다');
      if ($('pbBar').hidden) return;   // 기다리는 사이에 닫았다
    }
  } catch (e) {
    $('pbName').textContent = pb.when + ' · ' + e.message;
    return;
  }
  clearTimeout(pollTimer);
  Object.assign(pb, { on: true, t: 0, playing: true, last: performance.now() });
  document.body.classList.add('replay');
  txt('replayWhen', pb.when);
  $('pbName').textContent = pb.when;
  $('pbSeek').disabled = false;
  trkHave = 0; track = [];
  pbSync();
  clearInterval(pb.timer);
  pb.timer = setInterval(pbTick, 200);   // 로그 격자 5 Hz
}
async function pbStop(keepBar) {
  clearInterval(pb.timer);
  const was = pb.on;
  Object.assign(pb, { on: false, playing: false });
  if (was) fetch('/api/playback/close').catch(() => {});
  document.body.classList.remove('replay');
  if (!keepBar) { $('pbBar').hidden = true; document.querySelector('.main').classList.remove('pbmode'); }
  // 실시간으로 돌아간다 — 로그의 항적을 지우고 다시 받는다
  S = { live: false, d: {} }; trkHave = 0; track = [];
  render();
  if (!keepBar) pollLive();
}
function pbSync() {
  $('pbPlay').innerHTML = pb.playing ? '<svg viewBox="0 0 24 24"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>'
    : '<svg viewBox="0 0 24 24"><path d="M7 4.5v15l12.5-7.5z"/></svg>';
  $('pbRate').textContent = pb.rate + '×';
  txt('pbTime', mmss(pb.t) + ' / ' + mmss(pb.dur));
  if (!pb.seeking) $('pbSeek').value = String(pb.dur ? Math.round(pb.t / pb.dur * 1000) : 0);
  $('pbSeek').style.setProperty('--p', (pb.dur ? pb.t / pb.dur * 100 : 0) + '%');
}
let pbInflight = false;
async function pbTick() {
  const now = performance.now(), dt = (now - pb.last) / 1000;
  pb.last = now;
  if (pb.playing && !pb.seeking) {
    pb.t += dt * pb.rate;
    if (pb.t >= pb.dur) { pb.t = pb.dur; pb.playing = false; }
  }
  pbSync();
  if (pbInflight) return;
  pbInflight = true;
  try {
    const r = await fetch('/api/playback/state?t=' + pb.t.toFixed(2), { cache: 'no-store' });
    if (r.ok && pb.on) {
      S = await r.json();
      if (Array.isArray(S.track)) track = S.track;   // 재생 시각까지 통째로 온다
      render();
    }
  } catch { /* 다음 틱에서 다시 */ }
  pbInflight = false;
}
$('pbPlay').onclick = () => { if (!pb.on) return; if (!pb.playing && pb.t >= pb.dur) pb.t = 0; pb.playing = !pb.playing; pb.last = performance.now(); pbSync(); };
$('pbRate').onclick = () => { pb.rate = RATES[(RATES.indexOf(pb.rate) + 1) % RATES.length]; pbSync(); };
$('pbX').onclick = () => pbStop();
$('pbSeek').addEventListener('input', (e) => { pb.seeking = true; pb.t = pb.dur * e.target.value / 1000; pbSync(); });
$('pbSeek').addEventListener('change', () => { pb.seeking = false; pb.last = performance.now(); });

// ── 상태 반영 ────────────────────────────────────────────────────────
function render() {
  const on = !!S.live, d = D();
  txt('spd', d.groundspeed != null ? d.groundspeed.toFixed(0) : '—');
  $('spd').classList.toggle('off', d.groundspeed == null);
  txt('mode', d.mode || '—');
  const arm = $('arm');
  txt('arm', !on ? 'OFFLINE' : d.armed ? (d.landed === 2 ? 'AIRBORNE' : 'ARMED') : 'DISARMED');
  arm.className = on && d.armed ? (d.landed === 2 ? 'air' : 'on') : '';
  const vt = d.vtol || '';
  $('gMC').className = vt === 'MC' ? 'on' : '';
  $('gTR').className = /TRANSITION/.test(vt) ? 'on' : '';
  $('gFW').className = vt === 'FW' ? 'on' : '';
  txt('bat', d.batt_pct != null ? d.batt_pct + ' %' : '—');
  $('batBox').className = 'bat ' + lvl(d.batt_pct, 35, 20);
  $('batFill').setAttribute('width', d.batt_pct != null ? (21 * Math.max(0, Math.min(100, d.batt_pct)) / 100).toFixed(1) : 0);

  txt('sat', d.sats != null ? String(d.sats) : '—');
  $('stSat').className = 'st ' + (d.fix != null && d.fix < 3 ? 'bad' : lvl(d.sats, 8, 5));
  $('linkDot').className = 'dot' + (on ? ' on' : '');
  txt('barLink', on ? (S.link || S.src || 'LINK') : '—');

  $('linkIc').className = 'ic' + (on ? ' on' : '');
  txt('linkNm', on ? (S.link || S.src || '연결') : '링크 없음');
  txt('linkSub', (S.relay && S.relay.pusher) || '—');
  txt('lkPkt', on && S.packets ? S.packets.toLocaleString() : '—');
  txt('lkAge', on && S.relay && S.relay.age != null ? S.relay.age.toFixed(1) + 's' : '—');
  txt('lkUp', on && S.uptime ? mins(S.uptime) : '—');

  const mt = d.motors || {};
  const vs = Object.values(mt).filter((v) => v != null);
  const spread = vs.length ? Math.max(...vs) - Math.min(...vs) : 0;   // live.js 와 같은 기준 10/20%p
  for (const k of ['LF', 'RF', 'LB', 'RB']) {
    const e = $('m' + k);
    e.textContent = mt[k] == null ? '—' : Math.round(mt[k]) + '%';
    e.setAttribute('class', spread > 20 ? 'bad' : spread > 10 ? 'warn' : '');
  }

  const withU = (v, u) => v === '—' ? v : `${v}<small>${u}</small>`;
  html('dAlt', withU(num(d.alt, 1), 'm'));
  html('dClimb', withU(num(d.climb, 1), 'm/s'));
  html('dHdg', withU(num(d.hdg), '°'));
  html('dVolt', withU(num(d.volt, 1), 'V'));
  renderTiles();
  if (mode === 'map') renderMap();
}

function renderRec() {
  if (!R) return;
  txt('totMin', num(R.min)); txt('totN', String(R.n));
  const L = R.last;
  if (!L) return;
  $('lastCard').href = '/log/' + L.id;
  const t = new Date(L.utc + 'Z'), two = (n) => String(n).padStart(2, '0');
  txt('lastWhen', `${t.getFullYear()}.${two(t.getMonth() + 1)}.${two(t.getDate())} ${two(t.getHours())}:${two(t.getMinutes())}`);
  txt('lastBadge', { flight: '비행', hover: '호버' }[L.badge] || '');
  txt('lastDur', mins(L.duration));
  txt('lastAlt', L.alt_max != null ? L.alt_max.toFixed(1) + 'm' : '—');
  txt('lastCur', L.cur_max != null ? L.cur_max.toFixed(0) + 'A' : '—');
}

let pollTimer = 0;
async function pollLive(now) {
  clearTimeout(pollTimer);
  if (pb.on) return;            // 재생 중 — 화면은 로그가 채운다
  try {
    // 지도일 때만 항적을 받는다 — 증분(since)으로, 서버가 앞을 버렸으면 새로 받는다
    const q = mode === 'map' ? `since=${trkHave}` : 'track=0';
    const r = await fetch('/api/live/state?' + q, { cache: 'no-store' });
    if (r.ok) {
      S = await r.json();
      if (mode === 'map' && Array.isArray(S.track)) {
        if (S.track_from === trkHave) track.push(...S.track); else track = S.track.slice();
        trkHave = S.track_n || track.length;
      }
    }
  } catch { S = { live: false, d: {} }; }
  render();
  pollTimer = setTimeout(pollLive, S.live ? 1000 : 4000);
}
async function loadRec() {
  try {
    const r = await fetch('/api/logs', { cache: 'no-store' });
    const rows = (await r.json()).filter((x) => !x.error && !x.corrupt && x.badge && x.badge !== 'ground');
    rows.sort((a, b) => (b.utc || '').localeCompare(a.utc || ''));
    const max = (k) => rows.reduce((m, x) => x[k] != null && x[k] > m ? x[k] : m, 0);
    R = { n: rows.length, min: rows.reduce((s, x) => s + (x.duration || 0), 0) / 60,
      alt: max('alt_max'), spd: max('speed_max'), cur: max('cur_max'), last: rows[0] };
    renderRec(); if (tab === 'rec') renderTiles();
  } catch {}
}
function tick() { const n = new Date(); txt('clk', `${String(n.getHours()).padStart(2, '0')}:${String(n.getMinutes()).padStart(2, '0')}`); }
tick(); setInterval(tick, 5000);
renderInfo(); render(); pollLive(); loadRec(); setInterval(loadRec, 60000);
// 주소로 바로 열기 — /cockpit#pf 점검, #map 지도
if (location.hash === '#pf') document.querySelector('[data-t=pf]').click();
if (location.hash === '#map') setMode('map');
