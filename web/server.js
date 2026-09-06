// shade01.bewe.co.kr — 비행로그 뷰어
//
// 외부 의존 0. node:http 만 쓴다 (이 호스트의 다른 서비스와 같은 방식).
// Cloudflare 터널 뒤에 있으므로 루프백에만 바인딩한다 — TLS 는 엣지에서 끝난다.
//
// 파싱은 전부 extract.py 서브프로세스가 한다. 이유:
//   qgclog 는 contextlib.redirect_stdout 으로 전역 sys.stdout 을 바꾸고
//   _patch_pyulog() 로 pyulog 클래스를 영구 변형한다. 스레드로 돌리면 서로 밟는다.
//   프로세스를 분리하면 그 문제가 원천적으로 없다.
//
// 데이터(업로드·캐시·로그·비밀)는 **워크트리 밖**에 둔다. git clean -fdx 한 번에
// 업로드 원본이 사라지는 경로를 만들지 않는다.

'use strict';

const http = require('http');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');
const { execFile } = require('child_process');

const REPO = path.dirname(__dirname);
const PUBLIC = path.join(__dirname, 'public');
// 라이브 화면은 로컬 트래커와 **같은 파일**을 쓴다 (web/live/public/).
// 사본을 두면 한쪽만 고쳐져 두 화면이 갈라진다 — 그래서 여기서 그대로 낸다.
const LIVE_PUBLIC = path.join(__dirname, 'live', 'public');

const PORT = parseInt(process.env.PORT || '4300', 10);
const BIND = process.env.BIND_ADDR || '127.0.0.1';
const DATA = process.env.DATA_DIR || path.join(__dirname, 'data');
const LOGS = process.env.LOG_DIR || path.join(DATA, 'logs');
const CACHE = path.join(DATA, 'cache');
const PY = process.env.QGCLOG_PYTHON || path.join(REPO, '.venv', 'bin', 'python');
const EXTRACT = path.join(__dirname, 'extract.py');
const UPLOAD_PASSWORD = process.env.UPLOAD_PASSWORD || '';
const MAX_UPLOAD = parseInt(process.env.MAX_UPLOAD || String(64 * 1024 * 1024), 10);
// 라이브 중계용 암호. rim3 의 livepush.py 가 같은 값을 보낸다.
// 🔴 비우면 라이브 **수신**이 막힌다 (보기는 계속 공개다).
const LIVE_PUSH_KEY = process.env.LIVE_PUSH_KEY || '';
const PARSE_TIMEOUT = parseInt(process.env.PARSE_TIMEOUT || '60000', 10);
const MAX_JOBS = parseInt(process.env.MAX_JOBS || '3', 10);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

// ── 캐시 지문 ────────────────────────────────────────────────────────
// 파서나 추출기가 바뀌면 캐시를 통째로 무효화해야 한다. 안 그러면 오늘 고친
// 버그(FC 경고 0건 등)가 캐시에 굳은 채 계속 보인다.
const FINGERPRINT = (() => {
  const h = crypto.createHash('sha1');
  for (const f of [path.join(REPO, 'tools', 'qgclog', 'qgclog.py'), EXTRACT]) {
    try { h.update(fs.readFileSync(f)); } catch { h.update(f); }
  }
  return h.digest('hex').slice(0, 8);
})();
const CACHE_DIR = path.join(CACHE, 'v1.' + FINGERPRINT);

// ── 상태 ─────────────────────────────────────────────────────────────
const catalog = new Map();   // id -> row
let running = 0;
const queue = [];

function log(...a) { console.log(new Date().toISOString(), ...a); }

// ── 파이썬 호출 ──────────────────────────────────────────────────────
function runExtract(mode, file) {
  return new Promise((resolve, reject) => {
    const go = () => {
      running++;
      execFile(PY, [EXTRACT, mode, file],
        { timeout: PARSE_TIMEOUT, maxBuffer: 256 * 1024 * 1024 },
        (err, stdout, stderr) => {
          running--;
          const next = queue.shift();
          if (next) next();
          if (err && !stdout) {
            return reject(new Error(err.killed ? '파싱 시간 초과' :
              (stderr || err.message).slice(0, 300)));
          }
          try { resolve(JSON.parse(stdout)); }
          catch { reject(new Error('추출기 출력이 JSON 이 아니다: ' + stdout.slice(0, 200))); }
        });
    };
    if (running < MAX_JOBS) go(); else queue.push(go);
  });
}

// ── 캐시 ─────────────────────────────────────────────────────────────
const idOf = (buf) => crypto.createHash('sha256').update(buf).digest('hex').slice(0, 16);
const cachePath = (id, kind) => path.join(CACHE_DIR, `${id}.${kind}.json.gz`);

async function writeGz(file, obj) {
  const gz = zlib.gzipSync(Buffer.from(JSON.stringify(obj)), { level: 6 });
  const tmp = file + '.tmp';
  await fsp.writeFile(tmp, gz);
  await fsp.rename(tmp, file);          // 원자적 — 반쯤 쓰인 캐시를 읽는 일이 없다
}

async function readGz(file) {
  return JSON.parse(zlib.gunzipSync(await fsp.readFile(file)));
}

/** 로그 하나를 파싱해 캐시에 굽는다. 이미 있으면 건너뛴다. */
async function ensureCached(id, file, force = false) {
  const sumPath = cachePath(id, 'sum');
  const trkPath = cachePath(id, 'trk');
  if (!force) {
    try { await fsp.access(sumPath); await fsp.access(trkPath); return null; }
    catch { /* 없으면 굽는다 */ }
  }
  const out = await runExtract('full', file);
  if (!out.ok) throw new Error(out.error || '알 수 없는 파싱 실패');
  await writeGz(sumPath, out.sum);
  await writeGz(trkPath, out.trk);
  return out.row;
}

/** 디스크의 .ulg 를 훑어 카탈로그를 채운다. 없는 캐시는 백그라운드로 굽는다. */
async function reconcile() {
  let names;
  try { names = (await fsp.readdir(LOGS)).filter((n) => n.toLowerCase().endsWith('.ulg')); }
  catch { names = []; }

  const pending = [];
  for (const name of names) {
    const file = path.join(LOGS, name);
    let id;
    try { id = idOf(await fsp.readFile(file)); }
    catch (e) { log('읽기 실패', name, e.message); continue; }

    const rowPath = path.join(CACHE_DIR, `${id}.row.json`);
    try {
      const row = JSON.parse(await fsp.readFile(rowPath, 'utf8'));
      // 🔴 이름은 **디스크가 정본이다.** 캐시 키가 내용 해시라 파일을 개명해도
      //    같은 캐시를 쓰는데, 그 안에는 굽던 때의 옛 이름이 박혀 있다. 그대로
      //    쓰면 파일은 log_246 인데 목록에는 2026-09-05_09_34_04 로 뜬다
      //    (실측 2026-09-06: 번호를 붙였는데 웹에만 옛 이름이 남았다).
      catalog.set(id, { ...row, name, id, file });
      continue;
    } catch { /* row 캐시 없음 */ }

    pending.push({ id, name, file, rowPath });
  }

  if (pending.length) log(`캐시 없는 로그 ${pending.length}개 — 파싱 시작`);
  let done = 0;
  await Promise.all(pending.map(async ({ id, name, file, rowPath }) => {
    try {
      const row = await ensureCached(id, file);
      const r = row || (await runExtract('row', file)).row;
      catalog.set(id, { ...r, name, id, file });
      await fsp.writeFile(rowPath + '.tmp', JSON.stringify(r));
      await fsp.rename(rowPath + '.tmp', rowPath);
    } catch (e) {
      log('파싱 실패', name, e.message);
      catalog.set(id, { id, file, name, error: e.message, size: 0 });
    }
    if (++done % 20 === 0) log(`  ${done}/${pending.length}`);
  }));
  log(`카탈로그 ${catalog.size}개 준비됨`);
}

/** 같은 비행의 사본을 하나로 접는다.
 *
 * 한 비행이 두 경로로 들어온다: FC SD 에서 직접(`YYYY-MM-DD_HH_MM_SS.ulg`, UTC 이름)
 * 과 QGC 로 내려받아(`log_<n>_...`, 로컬 이름). 바이트가 달라 해시로는 안 걸리지만
 * 로그 안에 적힌 FC 경로는 같다 — extract.py 의 `flight` 가 그 열쇠다.
 *
 * 남기는 쪽은 **디코딩된 샘플이 많은 사본**이다. 실측: `09_09_49` 는 원본이 62%,
 * 손 복구본(RECOVERED3)이 99% 라 복구본이 이긴다. 진 사본도 지우지 않는다 —
 * `_repair()` 가 형제 로그를 기증자로 쓰므로 디스크에 있는 편이 낫다.
 * 전부 보려면 `/api/logs?all=1`.
 */
function dedupe(rows, all) {
  const groups = new Map();
  for (const r of rows) {
    const k = r.flight || ('id:' + r.id);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  const out = [];
  for (const [, g] of groups) {
    if (g.length === 1) { out.push(g[0]); continue; }
    g.sort((a, b) => (b.points || 0) - (a.points || 0));
    const [best, ...rest] = g;
    if (all) { out.push({ ...best, copies: g.length }, ...rest.map((r) => ({ ...r, superseded: best.id }))); }
    else out.push({ ...best, copies: g.length, copyNames: rest.map((r) => r.name) });
  }
  return out;
}

// ── HTTP 유틸 ────────────────────────────────────────────────────────
function send(req, res, status, body, type, extra = {}) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(body);
  const headers = { 'Content-Type': type, 'X-Robots-Tag': 'noindex, nofollow', ...extra };
  const wantsGz = /\bgzip\b/.test(req.headers['accept-encoding'] || '');
  if (wantsGz && buf.length > 1024 && !headers['Content-Encoding']) {
    const gz = zlib.gzipSync(buf);
    headers['Content-Encoding'] = 'gzip';
    headers['Vary'] = 'Accept-Encoding';
    headers['Content-Length'] = gz.length;
    res.writeHead(status, headers).end(gz);
    return;
  }
  headers['Vary'] = 'Accept-Encoding';
  headers['Content-Length'] = buf.length;
  res.writeHead(status, headers).end(buf);
}

const sendJson = (req, res, status, obj) =>
  send(req, res, status, JSON.stringify(obj), TYPES['.json'], { 'Cache-Control': 'no-store' });

/** 캐시 파일은 내용 해시로 주소가 정해지므로 영구 캐시해도 안전하다. */
async function sendCached(req, res, file) {
  let gz;
  try { gz = await fsp.readFile(file); }
  catch { return sendJson(req, res, 404, { error: '캐시 없음' }); }
  if (/\bgzip\b/.test(req.headers['accept-encoding'] || '')) {
    return send(req, res, 200, gz, TYPES['.json'],
      { 'Content-Encoding': 'gzip', 'Cache-Control': 'public, max-age=31536000, immutable' });
  }
  send(req, res, 200, zlib.gunzipSync(gz), TYPES['.json'],
    { 'Cache-Control': 'public, max-age=31536000, immutable' });
}

// ── 업로드 ───────────────────────────────────────────────────────────
function readBody(req, max) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let n = 0;
    req.on('data', (c) => {
      n += c.length;
      if (n > max) { reject(new Error('too-large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

function bufIndexOf(buf, needle, from) {
  const i = buf.indexOf(needle, from);
  return i;
}

/** multipart/form-data 를 손으로 판다. 의존성을 안 늘리기 위해서다. */
function parseMultipart(contentType, body) {
  const m = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType || '');
  if (!m) return null;
  const boundary = Buffer.from('--' + (m[1] || m[2]).trim());
  const parts = [];
  let pos = bufIndexOf(body, boundary, 0);
  if (pos < 0) return null;
  pos += boundary.length;
  while (pos < body.length) {
    if (body.slice(pos, pos + 2).toString() === '--') break;      // 끝
    pos += 2;                                                      // CRLF
    const headEnd = bufIndexOf(body, Buffer.from('\r\n\r\n'), pos);
    if (headEnd < 0) break;
    const head = body.slice(pos, headEnd).toString('utf8');
    const next = bufIndexOf(body, boundary, headEnd);
    if (next < 0) break;
    const data = body.slice(headEnd + 4, next - 2);                // 앞 CRLF 제거
    const name = /name="([^"]*)"/i.exec(head);
    const filename = /filename="([^"]*)"/i.exec(head);
    parts.push({ name: name ? name[1] : '', filename: filename ? filename[1] : null, data });
    pos = next + boundary.length;
  }
  return parts;
}

/** 파일명을 안전하게. 날짜가 담긴 원본 이름은 정렬 키라서 최대한 보존한다. */
function safeName(raw) {
  const base = path.basename(String(raw || '')).replace(/[^\w.\-]/g, '_');
  return /\.ulg$/i.test(base) ? base.slice(0, 120) : null;
}

function passwordOk(given) {
  if (!UPLOAD_PASSWORD) return false;                 // 미설정이면 업로드 자체를 막는다
  const a = Buffer.from(String(given || ''));
  const b = Buffer.from(UPLOAD_PASSWORD);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

async function handleUpload(req, res) {
  let body;
  try { body = await readBody(req, MAX_UPLOAD); }
  catch { return sendJson(req, res, 413, { error: `파일이 너무 크다 (상한 ${Math.round(MAX_UPLOAD / 1e6)}MB)` }); }

  const parts = parseMultipart(req.headers['content-type'], body);
  if (!parts) return sendJson(req, res, 400, { error: 'multipart 형식이 아니다' });

  const pw = parts.find((p) => p.name === 'password');
  if (!passwordOk(pw && pw.data.toString('utf8'))) {
    return sendJson(req, res, 401, { error: '업로드 암호가 틀렸다' });
  }

  const fp = parts.find((p) => p.filename);
  if (!fp || !fp.data.length) return sendJson(req, res, 400, { error: '파일이 없다' });

  const name = safeName(fp.filename);
  if (!name) return sendJson(req, res, 400, { error: '.ulg 파일만 받는다' });
  // ULog 매직바이트. 확장자만 믿지 않는다.
  if (fp.data.length < 16 || fp.data.slice(0, 7).toString('latin1') !== 'ULog\x01\x12\x35') {
    return sendJson(req, res, 400, { error: 'ULog 파일이 아니다 (매직바이트 불일치)' });
  }

  const id = idOf(fp.data);
  if (catalog.has(id)) {
    return sendJson(req, res, 200, { id, duplicate: true, name: catalog.get(id).name });
  }

  // 같은 이름이 이미 있으면 뒤에 -2, -3 을 붙인다. 내용이 다르니 덮으면 안 된다.
  let final = name;
  for (let i = 2; fs.existsSync(path.join(LOGS, final)); i++) {
    final = name.replace(/\.ulg$/i, '') + '-' + i + '.ulg';
  }
  // 🔴 반드시 LOGS 바로 아래 평면으로. 하위 폴더를 만들면 qgclog._repair() 가
  //    형제 로그를 기증자로 찾지 못해 구독 섹션 유실 복구가 안 된다.
  const dest = path.join(LOGS, final);
  await fsp.writeFile(dest + '.part', fp.data);
  await fsp.rename(dest + '.part', dest);
  log('업로드', final, fp.data.length, 'bytes');

  try {
    const row = await ensureCached(id, dest, true);
    const r = row || (await runExtract('row', dest)).row;
    catalog.set(id, { ...r, id, file: dest });
    await fsp.writeFile(path.join(CACHE_DIR, `${id}.row.json`), JSON.stringify(r));
    sendJson(req, res, 200, { id, name: final, row: r });
  } catch (e) {
    catalog.set(id, { id, file: dest, name: final, error: e.message, size: fp.data.length });
    sendJson(req, res, 200, { id, name: final, error: e.message });
  }
}

// ── 정적 파일 ────────────────────────────────────────────────────────
/** 라이브 화면의 정적 파일. web/live/public/ 안의 **허용 목록**만 낸다.
 *
 * 🔴 serveStatic 처럼 임의 경로를 받지 않는다. 그 폴더에는 화면과 상관없는
 *    것(_selftest.html 등)도 있고, 무엇보다 루트를 하나 더 여는 것 자체가
 *    경로 탈출 표면을 늘린다. 필요한 네 개만 이름으로 건다.
 */
const LIVE_FILES = new Map([
  ['/live/index.html', 'index.html'],
  ['/live.css', 'live.css'],
  ['/live.js', 'live.js'],
]);

async function serveLiveAsset(req, res, urlPath) {
  const name = LIVE_FILES.get(urlPath);
  if (!name) return send(req, res, 404, '없다', 'text/plain; charset=utf-8');
  let buf;
  try { buf = await fsp.readFile(path.join(LIVE_PUBLIC, name)); }
  catch { return send(req, res, 404, '없다', 'text/plain; charset=utf-8'); }
  const type = TYPES[path.extname(name).toLowerCase()] || 'application/octet-stream';
  send(req, res, 200, buf, type, { 'Cache-Control': 'no-cache' });
}

async function serveStatic(req, res, urlPath) {
  const rel = urlPath === '/' ? 'index.html' : decodeURIComponent(urlPath).slice(1);
  const file = path.normalize(path.join(PUBLIC, rel));
  if (file !== PUBLIC && !file.startsWith(PUBLIC + path.sep)) {
    return send(req, res, 403, '거부', 'text/plain; charset=utf-8');
  }
  let buf;
  try { buf = await fsp.readFile(file); }
  catch { return send(req, res, 404, '없다', 'text/plain; charset=utf-8'); }
  const type = TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
  const cache = file.includes(path.sep + 'vendor' + path.sep)
    ? 'public, max-age=604800' : 'no-cache';
  send(req, res, 200, buf, type, { 'Cache-Control': cache });
}

// ── 라이브 중계 ──────────────────────────────────────────────────────
// 🔴 **현장 노트북은 rim3 다.** 비행 나갈 때 들고 나가는 PC 가 rim3 이고, FC 는
//    거기에 USB 나 ELRS 백팩으로 붙는다. 이 서버는 FC 를 **직접 못 본다** —
//    rim3 의 livepush.py 가 1초마다 밀어 올리는 것을 받아 들고 있을 뿐이다.
//    그래서 rim3 가 꺼져 있거나 인터넷이 없으면 라이브도 없다. 정상이다.
//
// 🔴 **한 방향뿐이다.** 받기만 하고, 여기서 기체로 나가는 경로는 없다.
//    트래커(mav_live.py)가 소켓에 쓰는 코드 0줄이라는 성질을 웹까지 이어 놓은
//    것이다 — 웹에서 ARM·모드변경을 할 길이 구조적으로 존재하지 않는다.
//
// 메모리에만 둔다. 디스크에 안 쓰는 이유: 라이브는 지금 이 순간의 값이고,
// 재시작하면 rim3 가 다음 초에 다시 보낸다. 정본은 비행 후 .ulg 로 올라온다.
const live = {
  at: 0,            // 마지막으로 받은 시각 (Date.now)
  state: null,      // 마지막 스냅샷 (항적 제외)
  track: [],        // 누적 항적 [[lat,lon,alt], ...]
  dropped: 0,       // 앞에서 버린 점 개수 (증분 프로토콜의 기준)
  pusher: null,     // 어느 PC 가 올렸나
};

// 항적 상한. 트래커와 같은 값이다 — 5Hz 로 40분이면 12000 점.
const LIVE_TRACK_MAX = 12000;

// 이 시간 동안 안 올라오면 「끊김」으로 본다. 중계 주기(1초)의 몇 배로 잡는다 —
// LTE 로 올리면 한두 번은 늦을 수 있다.
const LIVE_STALE_MS = 12000;

function livePushOk(given) {
  if (!LIVE_PUSH_KEY) return false;
  const a = Buffer.from(String(given || ''));
  const b = Buffer.from(LIVE_PUSH_KEY);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

async function handleLivePush(req, res) {
  if (!livePushOk(req.headers['x-live-key'])) {
    return sendJson(req, res, 403, { error: '라이브 키가 맞지 않는다' });
  }
  let raw;
  // 스냅샷 하나는 항적을 빼면 1~2KB 다. 1MB 면 넘치고도 남는다.
  try { raw = await readBody(req, 1024 * 1024); }
  catch { return sendJson(req, res, 413, { error: '너무 크다' }); }

  let snap;
  try { snap = JSON.parse(raw.toString('utf8')); }
  catch { return sendJson(req, res, 400, { error: 'JSON 이 아니다' }); }
  if (!snap || typeof snap !== 'object') {
    return sendJson(req, res, 400, { error: '객체가 아니다' });
  }

  // 🔴 항적은 **증분**으로 온다. `track_from` 이 이 묶음의 첫 점이 전체에서
  //    몇 번째인지 말해 준다. 그것이 우리가 가진 개수와 맞을 때만 이어 붙이고,
  //    어긋나면(서버 재시작·rim3 재시작) 통째로 갈아 끼운다 — 안 그러면
  //    지도에 궤적이 조용히 빠지거나 겹친다.
  const inc = Array.isArray(snap.track) ? snap.track : [];
  const from = Number.isInteger(snap.track_from) ? snap.track_from : 0;
  const have = live.dropped + live.track.length;
  if (from === have) {
    for (const pt of inc) live.track.push(pt);
  } else if (from === 0) {
    live.track = inc.slice();
    live.dropped = 0;
  } else if (from < have) {
    // 겹치는 만큼 건너뛰고 나머지만 붙인다.
    const skip = have - from;
    if (skip < inc.length) for (const pt of inc.slice(skip)) live.track.push(pt);
  } else {
    // 구멍이 생겼다 — 다음 푸시에서 처음부터 받도록 0 을 돌려준다.
    live.track = [];
    live.dropped = 0;
  }
  if (live.track.length > LIVE_TRACK_MAX) {
    const cut = live.track.length - LIVE_TRACK_MAX;
    live.track.splice(0, cut);
    live.dropped += cut;
  }

  delete snap.track;
  live.state = snap;
  live.at = Date.now();
  live.pusher = typeof snap.pusher === 'string' ? snap.pusher.slice(0, 40) : null;

  // 다음에 어디서부터 보내면 되는지 알려 준다.
  return sendJson(req, res, 200, { ok: true, track_n: live.dropped + live.track.length });
}

/** 라이브 페이지가 폴링한다. 트래커의 /api/state 와 **같은 모양**이어야 한다 —
 *  같은 live.js 가 로컬에서도 여기서도 돌기 때문이다. */
function handleLiveState(req, res, url) {
  const stale = !live.state || (Date.now() - live.at) > LIVE_STALE_MS;
  if (!live.state) {
    return sendJson(req, res, 200, {
      live: false, seq: 0, age: null, packets: 0, bytes: 0,
      src: null, link: null, links: {}, sysid: null, uptime: 0,
      d: {}, home: null, mission: [],
      track_n: 0, track_from: 0, track: [], messages: [],
      rec: null, play: null,
      relay: { pusher: null, age: null, note: '아직 아무 PC 도 안 올렸다' },
    });
  }

  let since = parseInt(url.searchParams.get('since') || '0', 10);
  if (!Number.isFinite(since) || since < 0) since = 0;
  const wantTrack = url.searchParams.get('track') !== '0';
  const start = since < live.dropped ? 0 : Math.min(since - live.dropped, live.track.length);

  const ageS = (Date.now() - live.at) / 1000;
  const out = {
    ...live.state,
    // 🔴 중계가 끊기면 화면도 끊긴 것으로 보여야 한다. rim3 가 보낸 마지막
    //    `live: true` 를 그대로 흘리면, 노트북을 닫고 집에 온 뒤에도 웹은
    //    기체가 떠 있는 것처럼 보인다.
    live: stale ? false : !!live.state.live,
    age: stale ? ageS : live.state.age,
    track_n: live.dropped + live.track.length,
    track_from: live.dropped + start,
    track: wantTrack ? live.track.slice(start) : [],
    // 로컬 트래커에는 없는 칸. 어느 PC 가 언제 올렸는지 화면이 말할 수 있게.
    relay: { pusher: live.pusher, age: Math.round(ageS * 10) / 10, note: null },
  };
  // 재생은 로컬 트래커에만 있다. 웹에서는 지난 비행을 /log/<id> 로 본다.
  out.play = null;
  return sendJson(req, res, 200, out);
}

// ── 라우팅 ───────────────────────────────────────────────────────────
const ID_RE = /^[0-9a-f]{16}$/;

async function route(req, res) {
  const url = new URL(req.url, 'http://localhost');
  const p = url.pathname;

  if (p === '/api/health') {
    return sendJson(req, res, 200, {
      ok: true, logs: catalog.size, fingerprint: FINGERPRINT,
      running, queued: queue.length, upload: UPLOAD_PASSWORD ? 'enabled' : 'disabled',
    });
  }

  if (p === '/api/logs' && req.method === 'GET') {
    const all = url.searchParams.get('all') === '1';
    const rows = dedupe([...catalog.values()], all)
      .map(({ file, ...r }) => r)                       // 서버 경로는 내보내지 않는다
      .sort((a, b) => String(b.utc || '').localeCompare(String(a.utc || '')));
    return sendJson(req, res, 200, rows);
  }

  // 🔴 `.ulg` 원본은 내보내지 않는다. 조회가 공개라 링크를 아는 누구나 받아갈 수
  //    있게 되고, 로그에는 비행장 좌표와 기체 전체 텔레메트리가 그대로 들어 있다.
  //    분석에 필요한 것은 sum/trk 로 이미 나가므로 원본을 열 이유가 없다.
  //    버튼만 없애는 것으로는 부족하다 — URL 을 직접 치면 받아지므로 여기서 막는다.
  if (/^\/api\/logs\/[^/]+\/file$/.test(p)) {
    return sendJson(req, res, 403, { error: '원본 다운로드는 제공하지 않는다' });
  }

  const m = /^\/api\/logs\/([^/]+)\/(sum|trk)$/.exec(p);
  if (m && req.method === 'GET') {
    const [, id, kind] = m;
    if (!ID_RE.test(id)) return sendJson(req, res, 400, { error: '잘못된 id' });
    const entry = catalog.get(id);
    if (!entry) return sendJson(req, res, 404, { error: '없는 로그' });
    if (entry.error) return sendJson(req, res, 422, { error: entry.error });
    try { await fsp.access(cachePath(id, kind)); }
    catch {
      try { await ensureCached(id, entry.file); }
      catch (e) { return sendJson(req, res, 422, { error: e.message }); }
    }
    return sendCached(req, res, cachePath(id, kind));
  }

  if (p === '/api/upload' && req.method === 'POST') return handleUpload(req, res);

  // 라이브 — rim3 가 밀어 올리고(POST), 브라우저가 폴링한다(GET).
  if (p === '/api/live/push' && req.method === 'POST') return handleLivePush(req, res);
  if (p === '/api/live/state' && req.method === 'GET') return handleLiveState(req, res, url);

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    return send(req, res, 405, '허용하지 않는 메서드', 'text/plain; charset=utf-8');
  }
  // /log/<id> 는 분석 페이지. 실제 파일은 log.html 이다.
  if (/^\/log\/[0-9a-f]{16}$/.test(p)) return serveStatic(req, res, '/log.html');
  // /live 는 실시간 화면. 로컬 트래커(:4400)와 **같은 파일**을 쓴다.
  if (p === '/live' || p === '/live/') return serveLiveAsset(req, res, '/live/index.html');
  if (LIVE_FILES.has(p)) return serveLiveAsset(req, res, p);
  if (/^\/compare\b/.test(p)) return serveStatic(req, res, '/compare.html');
  return serveStatic(req, res, p);
}

// ── 기동 ─────────────────────────────────────────────────────────────
async function main() {
  for (const d of [DATA, LOGS, CACHE_DIR]) await fsp.mkdir(d, { recursive: true });

  // venv 가 없으면 전부 '파싱 실패' 로 캐시에 굳는다. 아예 뜨지 않는 편이 낫다.
  try {
    const v = require('child_process').execFileSync(
      PY, ['-c', 'import pyulog, numpy, sys; print(sys.version.split()[0])'],
      { encoding: 'utf8', timeout: 20000 }).trim();
    log(`python ${v} (${PY}) — pyulog·numpy OK`);
  } catch (e) {
    console.error(`파이썬을 못 쓴다: ${PY}\n  ${e.message}\n` +
      '  venv 를 만들어라 — PROCEDURE.md "2-0 분석 PC 준비" 참조');
    process.exit(1);
  }

  if (!UPLOAD_PASSWORD) log('⚠️  UPLOAD_PASSWORD 미설정 — 업로드가 막힌 채로 뜬다');
  log(`지문 ${FINGERPRINT}, 로그 ${LOGS}`);
  await reconcile();

  http.createServer((req, res) => {
    route(req, res).catch((e) => {
      log('처리 실패', req.method, req.url, e.message);
      if (!res.headersSent) sendJson(req, res, 500, { error: '서버 오류' });
    });
  }).listen(PORT, BIND, () => log(`http://${BIND}:${PORT} 에서 대기`));
}

process.on('unhandledRejection', (e) => log('unhandledRejection', e && e.message));
process.on('uncaughtException', (e) => log('uncaughtException', e && e.stack));

main().catch((e) => { console.error(e); process.exit(1); });
