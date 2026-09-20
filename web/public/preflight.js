// 비행 전 점검 화면.
//
// 🔴 **판정을 여기서 하지 않는다.** 서버가 준 level/verdict 를 그대로 그린다.
//    임계값은 tools/preflight/preflight.py 의 EXPECT 한 곳에만 있다.
'use strict';

const $ = (id) => document.getElementById(id);

// 등급 → 화면 말. preflight.py 의 GROUP_VERDICT 와 같은 짝이다.
// 🔴 색만으로 말하지 않는다 — 글자로도 같은 것을 적는다 (색각 이상·인쇄).
const LEVEL = {
  blk:  { word: 'NO-GO', cls: 'blk',  mark: '✖' },
  warn: { word: '확인',   cls: 'warn', mark: '▲' },
  ok:   { word: 'GO',    cls: 'ok',   mark: '✔' },
  info: { word: '참고',   cls: 'info', mark: '·' },
};

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

function setNote(text, cls) {
  const n = $('note');
  n.textContent = text || '';
  n.className = 'pf-note' + (cls ? ' ' + cls : '');
}

function clear() {
  $('groups').textContent = '';
  $('fail').hidden = true;
  $('fail').textContent = '';
  $('standing').hidden = true;
  $('standingList').textContent = '';
  $('verdict').hidden = true;
}

/** 붙지 못했거나 서버가 막힌 경우. 🔴 이때 GO 를 그리지 않는다. */
function renderFail(d) {
  const box = $('fail');
  box.hidden = false;
  box.appendChild(el('div', 'pf-failtitle', d.error || '점검하지 못했다'));
  for (const n of d.notes || []) box.appendChild(el('div', 'pf-failnote', '· ' + n));
  if (d.hints && d.hints.length) {
    box.appendChild(el('div', 'pf-failhead', '확인할 것'));
    for (const h of d.hints) box.appendChild(el('div', 'pf-failnote', '· ' + h));
  }
}

function renderVerdict(d) {
  const sec = $('verdict');
  sec.hidden = false;
  const cls = d.verdict === 'GO' ? 'ok' : (d.verdict === 'NO-GO' ? 'blk' : 'warn');
  sec.className = 'pf-verdict ' + cls;
  $('vtext').textContent = d.verdict || '—';

  const c = d.counts || {};
  const bits = [];
  if (c.blk) bits.push(`진행 불가 ${c.blk}`);
  if (c.warn) bits.push(`확인 필요 ${c.warn}`);
  if (c.ok) bits.push(`정상 ${c.ok}`);
  if (d.how) bits.push(d.how);
  if (d.agent) bits.push(d.agent);
  if (d.elapsed != null) bits.push(`${d.elapsed}초`);
  if (d.at) bits.push(d.at.replace('T', ' ').slice(0, 19));
  $('vmeta').textContent = bits.join('  ·  ');
}

function renderGroups(groups) {
  const wrap = $('groups');
  groups.forEach((g, i) => {
    const lv = LEVEL[g.level] || LEVEL.info;
    const sec = el('section', 'pf-group ' + lv.cls);

    const head = el('header', 'pf-ghead');
    head.appendChild(el('span', 'pf-gnum', String(i + 1) + '.'));
    head.appendChild(el('span', 'pf-gname', g.name));
    head.appendChild(el('span', 'pf-gdots'));
    // 글자로 판정을 적는다. 색은 거드는 것이지 혼자 말하지 않는다.
    head.appendChild(el('span', 'pf-gverdict', g.verdict));
    sec.appendChild(head);

    const list = el('div', 'pf-items');
    for (const it of g.items) {
      const ilv = LEVEL[it.level] || LEVEL.info;
      const row = el('div', 'pf-item ' + ilv.cls);
      row.appendChild(el('span', 'pf-mark', ilv.mark));
      row.appendChild(el('span', 'pf-iname', it.name));
      row.appendChild(el('span', 'pf-idetail', it.detail));
      if (it.why) {
        // 왜 막혔는지가 다음 행동을 정한다. 접지 않는다 (터미널도 안 접는다).
        row.appendChild(el('div', 'pf-why', it.why));
      }
      list.appendChild(row);
    }
    sec.appendChild(list);
    wrap.appendChild(sec);
  });
}

function renderStanding(rows) {
  if (!rows || !rows.length) return;
  $('standing').hidden = false;
  const dl = $('standingList');
  for (const r of rows) {
    dl.appendChild(el('dt', null, r.name));
    dl.appendChild(el('dd', null, r.text));
  }
}

async function run() {
  const pw = $('pw').value;
  if (!pw) { setNote('암호를 넣어라', 'bad'); $('pw').focus(); return; }

  const btn = $('go');
  btn.disabled = true;
  clear();
  setNote('FC 에 붙는 중…', 'dim');

  const t0 = Date.now();
  // 수집 시간만큼은 최소로 걸린다. 그 동안 무엇을 기다리는지 말해 준다.
  const tick = setInterval(() => {
    setNote(`점검 중… ${((Date.now() - t0) / 1000).toFixed(0)}초`, 'dim');
  }, 500);

  try {
    const res = await fetch('/api/preflight?t=' + encodeURIComponent($('secs').value), {
      method: 'POST',
      headers: { 'X-Preflight-Password': pw },
    });
    const d = await res.json().catch(() => ({ error: '응답을 읽지 못했다' }));

    if (res.status === 401) { setNote('암호가 틀렸다', 'bad'); return; }

    if (d.verdict) renderVerdict(d);
    if (d.error) renderFail(d);
    if (d.groups && d.groups.length) renderGroups(d.groups);
    renderStanding(d.standing);

    if (!d.error) {
      setNote('', '');
      // 암호가 맞았으면 이번 탭에서는 다시 안 묻는다. 현장에서 한 손으로
      // 누르는 버튼이라 매번 치게 하면 실제로 안 누르게 된다.
      try { sessionStorage.setItem('pf_pw', pw); } catch { /* 사설 모드 */ }
    } else {
      setNote(d.error, 'bad');
    }
  } catch (e) {
    setNote('서버에 닿지 못했다: ' + e.message, 'bad');
  } finally {
    clearInterval(tick);
    btn.disabled = false;
  }
}

$('go').addEventListener('click', run);
$('pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') run(); });
try {
  const saved = sessionStorage.getItem('pf_pw');
  if (saved) $('pw').value = saved;
} catch { /* 사설 모드에서는 sessionStorage 가 던진다 */ }
