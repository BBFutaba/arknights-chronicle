// 时间轴：竖向的分叉时间线。
// 最左边的灰线是「主世界线」，只有设定资料出处的事件画在上面；每个剧情组是一条故事线，
// 从主世界线分出、结束时合回。同一时期有几条故事线并行，就分出几条。
// 一条故事线的两个事件之间隔得太远（超过 GAP 行）时会先合回再重新分出，避免一条线占满整列。
import { D } from './data.js';
import { esc, href, threadColor, threadChip, charChip, powerChip, epLabel, groupLabel, CAT_ORDER } from './util.js';

const ROW = 34;
const GAP = 16;
const PAD = 12;

let root, scroller, canvas, detail;
let items = [];      // 当前显示的行：{ year } 或 { ev }
let rowOf = {};      // 事件 id → 行号
let visible = [];    // 当前筛选后的事件，用于上一条/下一条
let selected = null;
let lastFilterKey = null;
const state = { q: '', cats: new Set(CAT_ORDER), parallel: true, char: null, power: null, thread: null };

export function mount(el, r) {
  root = el;
  el.innerHTML = `
    <aside class="tl-side panel">
      <input class="tl-q" type="search" placeholder="筛选事件文字…">
      <div class="tl-toggles">
        ${CAT_ORDER.map((c) => `<label class="toggle"><input type="checkbox" value="${c}" ${state.cats.has(c) ? 'checked' : ''}>${c}</label>`).join('')}
        <label class="toggle"><input type="checkbox" class="tl-par" ${state.parallel ? 'checked' : ''}>平行世界</label>
      </div>
      <div class="tl-active"></div>
      <div class="tl-count muted"></div>
      <nav class="tl-eras"></nav>
      <p class="muted small">↑↓ 键切换事件。日期为 PRTS 社区根据剧情推测，可能有偏差。</p>
    </aside>
    <section class="tl-main"><div class="tl-scroll"><div class="tl-canvas"></div></div></section>
    <aside class="tl-detail panel"></aside>`;
  scroller = el.querySelector('.tl-scroll');
  canvas = el.querySelector('.tl-canvas');
  detail = el.querySelector('.tl-detail');

  const q = el.querySelector('.tl-q');
  q.value = state.q;
  q.addEventListener('input', () => { state.q = q.value; render(); });
  el.querySelectorAll('.tl-toggles input[value]').forEach((cb) => cb.addEventListener('change', () => {
    cb.checked ? state.cats.add(cb.value) : state.cats.delete(cb.value);
    render();
  }));
  el.querySelector('.tl-par').addEventListener('change', (e) => { state.parallel = e.target.checked; render(); });
  canvas.addEventListener('click', (e) => {
    const row = e.target.closest('.tl-row');
    if (row) choose(row.dataset.ev, false);
  });
  el.querySelector('.tl-eras').addEventListener('click', (e) => {
    const a = e.target.closest('[data-row]');
    if (a) scroller.scrollTo({ top: Number(a.dataset.row) * ROW, behavior: 'smooth' });
  });
  document.addEventListener('keydown', onKey);
  lastFilterKey = null;
  update(r);
}

export function unmount() {
  document.removeEventListener('keydown', onKey);
}

export function update(r) {
  const p = r.params;
  state.char = p.get('char');
  state.power = p.get('power');
  state.thread = p.get('thread');
  const key = JSON.stringify([state.char, state.power, state.thread]);
  if (key !== lastFilterKey) {
    lastFilterKey = key;
    render();
  }
  select(p.get('ev'), true);
}

// ------------------------------------------------------------------ 筛选与布局
function matches(e) {
  const cat = D.threads[e.thread]?.category ?? '设定';
  if (!state.cats.has(cat)) return false;
  if (!state.parallel && e.parallel) return false;
  if (state.char && !e.chars.includes(state.char)) return false;
  if (state.power && !e.powers.includes(state.power)) return false;
  if (state.thread && !(e.thread === state.thread || e.sources.some((s) => s.groups.includes(state.thread)))) return false;
  const q = state.q.trim();
  return !q || e.lines.some((l) => l.includes(q)) || e.when.includes(q);
}

function yearKey(e) { return e.year != null ? `y${e.year}` : e.era; }
function yearLabel(e) {
  if (e.year == null) return e.era.split(' · ').pop();
  return e.year < 0 ? `前 ${-e.year} 年` : `${e.year} 年`;
}
function shortWhen(e) {
  if (e.year == null || e.year < 0) return e.when;
  const rest = e.when.startsWith(`${e.year} 年`) ? e.when.slice(`${e.year} 年`.length).trim() : e.when;
  return rest.replace(/^（(.*)）$/, '$1') || '全年';
}

function layout() {
  const threadRows = new Map();
  items.forEach((it, r) => {
    if (it.ev && it.ev.thread !== 'lore') {
      if (!threadRows.has(it.ev.thread)) threadRows.set(it.ev.thread, []);
      threadRows.get(it.ev.thread).push(r);
    }
  });
  const segs = [];
  for (const [tid, rows] of threadRows) {
    let cur = { tid, start: rows[0], end: rows[0], rows: [rows[0]] };
    for (const r of rows.slice(1)) {
      if (r - cur.end > GAP) { segs.push(cur); cur = { tid, start: r, end: r, rows: [r] }; }
      else { cur.end = r; cur.rows.push(r); }
    }
    segs.push(cur);
  }
  segs.sort((a, b) => a.start - b.start || a.end - b.end);
  const laneEnd = [Infinity];  // 第 0 列是主世界线
  const lastLane = {};
  const free = (l, s) => laneEnd[l] < s.start - 1;
  for (const s of segs) {
    let lane = lastLane[s.tid];
    if (!(lane && free(lane, s))) {
      lane = laneEnd.findIndex((_, l) => l > 0 && free(l, s));
      if (lane < 0) lane = laneEnd.length;
    }
    laneEnd[lane] = s.end;
    s.lane = lane;
    lastLane[s.tid] = lane;
  }
  return { segs, lanes: laneEnd.length };
}

function render() {
  visible = D.events.filter(matches);
  items = [];
  rowOf = {};
  let lastKey = null;
  for (const e of visible) {
    if (yearKey(e) !== lastKey) {
      lastKey = yearKey(e);
      items.push({ year: yearLabel(e), era: e.era });
    }
    rowOf[e.id] = items.length;
    items.push({ ev: e });
  }
  const { segs, lanes } = layout();
  const laneW = Math.max(6, Math.min(13, 240 / Math.max(lanes, 1)));
  const x = (l) => PAD + l * laneW;
  const y = (r) => r * ROW + ROW / 2;
  const width = x(lanes - 1) + PAD + 4;
  const height = items.length * ROW;
  const laneOfRow = {};
  for (const s of segs) for (const r of s.rows) laneOfRow[r] = s.lane;

  const paths = segs.map((s) => {
    const x0 = x(0), xl = x(s.lane), y0 = y(s.start), y1 = y(s.end);
    const d = `M${x0},${y0 - ROW * 0.95} C${x0},${y0 - ROW * 0.45} ${xl},${y0 - ROW * 0.55} ${xl},${y0}`
      + ` L${xl},${y1} C${xl},${y1 + ROW * 0.55} ${x0},${y1 + ROW * 0.45} ${x0},${y1 + ROW * 0.95}`;
    return `<path class="seg" data-tid="${s.tid}" d="${d}" stroke="${threadColor(s.tid)}"/>`;
  }).join('');
  const dots = items.map((it, r) => {
    if (!it.ev) return '';
    const lane = laneOfRow[r] ?? 0;
    const lore = it.ev.thread === 'lore';
    const main = D.threads[it.ev.thread]?.category === '主线';
    return `<circle class="dot${lore ? ' lore' : ''}${main ? ' main' : ''}" data-ev="${it.ev.id}" cx="${x(lane)}" cy="${y(r)}" r="${main ? 4.8 : 4}" fill="${lore ? 'var(--panel)' : threadColor(it.ev.thread)}"/>`;
  }).join('');

  const rows = items.map((it) => {
    if (!it.ev) return `<div class="tl-year" style="padding-left:${width + 8}px">${esc(it.year)}</div>`;
    const e = it.ev;
    const t = D.threads[e.thread];
    const g = D.groupById[e.thread];
    const tag = e.thread === 'lore' ? '' : `<span class="tl-tag" style="--c:${threadColor(e.thread)}" title="${esc(t.name)}">${esc(g?.chapter != null ? g.label : t.name)}</span>`;
    const more = e.lines.length > 1 ? `<span class="muted"> +${e.lines.length - 1}</span>` : '';
    const par = e.parallel ? '<span class="badge">平行</span>' : '';
    return `<div class="tl-row${e.id === selected ? ' sel' : ''}" data-ev="${e.id}" style="padding-left:${width + 8}px">
      <span class="when">${esc(shortWhen(e))}</span>${tag}${par}<span class="text">${esc(e.lines[0] ?? '')}${more}</span></div>`;
  }).join('');

  canvas.style.height = `${height}px`;
  canvas.innerHTML = `<svg class="tl-svg" width="${width}" height="${height}">
      <line class="trunk" x1="${x(0)}" y1="0" x2="${x(0)}" y2="${height}"/>${paths}${dots}</svg>
    <div class="tl-rows">${rows}</div>`;

  renderSide(lanes);
}

function renderSide(lanes) {
  const active = [];
  const without = (k) => {
    const p = new URLSearchParams({ char: state.char ?? '', power: state.power ?? '', thread: state.thread ?? '' });
    p.delete(k);
    for (const [kk, v] of [...p]) if (!v) p.delete(kk);
    return `#/timeline${p.size ? `?${p}` : ''}`;
  };
  if (state.char) active.push(`<a class="filter-chip" href="${without('char')}">人物：${esc(state.char)} ×</a>`);
  if (state.power) active.push(`<a class="filter-chip" href="${without('power')}">地区/势力：${esc(D.powers[state.power]?.name ?? state.power)} ×</a>`);
  if (state.thread) active.push(`<a class="filter-chip" href="${without('thread')}">故事线：${esc(D.threads[state.thread]?.name ?? state.thread)} ×</a>`);
  root.querySelector('.tl-active').innerHTML = active.join('');
  root.querySelector('.tl-count').textContent = `显示 ${visible.length} / ${D.events.length} 条事件，最多 ${lanes - 1} 条故事线并行`;

  const eras = [];
  items.forEach((it, r) => {
    if (!it.ev) return;
    const name = it.ev.era.split(' · ').pop();
    if (eras.at(-1)?.name !== name) eras.push({ name, row: r - 1, n: 0 });
    eras.at(-1).n++;
  });
  root.querySelector('.tl-eras').innerHTML = eras.map((e) =>
    `<button data-row="${Math.max(e.row, 0)}">${esc(e.name)}<span class="muted">${e.n}</span></button>`).join('');
}

// ------------------------------------------------------------------ 选中与详情
function choose(id, scroll) {
  select(id, scroll);
  const p = new URLSearchParams(location.hash.split('?')[1] ?? '');
  p.set('ev', id);
  history.replaceState(null, '', `#/timeline?${p}`);
}

function select(id, scroll) {
  const ev = id && D.eventById[id];
  canvas.querySelectorAll('.sel').forEach((n) => n.classList.remove('sel'));
  if (!ev) {
    selected = null;
    detail.innerHTML = `<div class="muted pad">点击左侧事件查看详情。<br><br>
      颜色代表故事线（剧情组），灰色空心点是只有设定资料出处的事件。</div>`;
    return;
  }
  selected = id;
  canvas.querySelectorAll(`[data-ev="${id}"]`).forEach((n) => n.classList.add('sel'));
  if (scroll && rowOf[id] != null) {
    scroller.scrollTop = rowOf[id] * ROW - scroller.clientHeight / 3;
  }
  renderDetail(ev);
}

function renderDetail(ev) {
  const i = visible.indexOf(ev);
  const nav = (j, label) => visible[j]
    ? `<a class="btn" href="${href.event(visible[j].id)}" data-nav="${visible[j].id}">${label}</a>` : `<span class="btn disabled">${label}</span>`;
  const sources = ev.sources.map((s) => {
    const links = s.stories.length
      ? s.stories.map((sid) => D.epById[sid] ? `<a href="${href.ep(sid)}">▶ ${esc(epLabel(D.epById[sid].ep))}</a>` : '').join('')
      : s.groups.map((gid) => `<a href="${href.group(gid)}">▶ ${esc(groupLabel(D.groupById[gid]))}</a>`).join('');
    return `<li><div>${esc(s.text)}</div>${links ? `<div class="src-links">${links}</div>` : ''}</li>`;
  }).join('');
  const filters = [
    ...ev.chars.map((n) => `<a href="${href.timeline({ char: n })}">${esc(n)}</a>`),
    ...ev.powers.map((p) => `<a href="${href.timeline({ power: p })}">${esc(D.powers[p]?.name ?? p)}</a>`),
    ev.thread !== 'lore' ? `<a href="${href.timeline({ thread: ev.thread })}">故事线「${esc(D.threads[ev.thread].name)}」</a>` : '',
  ].filter(Boolean).join('');

  detail.innerHTML = `
    <div class="ev-nav">${nav(i - 1, '↑ 上一条')}${nav(i + 1, '下一条 ↓')}</div>
    <div class="ev-when">${esc(ev.when)}</div>
    <div class="muted small">${esc(ev.era)}</div>
    <div class="ev-tags">${ev.thread === 'lore' ? '<span class="thread-chip" style="--c:var(--lore)">设定与档案</span>' : threadChip(ev.thread, 'group')}${ev.parallel ? '<span class="badge">平行世界</span>' : ''}</div>
    <div class="ev-lines">${ev.lines.map((l) => `<p>${esc(l)}</p>`).join('')}</div>
    ${D.annalsByEvent[ev.id] ? `<div class="actions"><a class="btn" href="${href.annalsEntry(D.annalsByEvent[ev.id])}">📜 编年史中的记述</a></div>` : ''}
    ${ev.notes.length ? `<div class="note">${ev.notes.map(esc).join('<br>')}</div>` : ''}
    ${ev.chars.length || ev.powers.length ? `<h4>涉及</h4><div class="chips">${ev.chars.map((n) => charChip(n)).join('')}${ev.powers.map((p) => powerChip(p)).join('')}</div>` : ''}
    ${filters ? `<h4>在时间轴中只看</h4><div class="filter-links">${filters}</div>` : ''}
    <h4>出处</h4><ul class="sources">${sources || '<li class="muted">无</li>'}</ul>`;
  detail.querySelectorAll('[data-nav]').forEach((a) => a.addEventListener('click', (e) => {
    e.preventDefault();
    choose(a.dataset.nav, true);
  }));
}

function onKey(e) {
  if (e.target.matches('input, textarea') || !visible.length) return;
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  e.preventDefault();
  const i = selected ? visible.findIndex((v) => v.id === selected) : -1;
  const j = Math.min(visible.length - 1, Math.max(0, i + (e.key === 'ArrowDown' ? 1 : -1)));
  choose(visible[j].id, true);
}
