// 立体时间轴：中轴是时间（z），同一时刻的事件散在横截面（x、y）上，关联近的靠在一起。
// 布局由 pipeline/timeline3d.py 预先算好，存在 data/timeline3d.json；这里只管画和操作。
// 画法：手写的透视投影，画在 Canvas2D 上，不用第三方库（单文件版要离线可用）。
// 颜色从 CSS 变量读，经一个探针元素换算成 rgb（color-mix 也认得），换主题后 retheme 重读。
// 纵轴不按比例，两编之间断开，塔罗斯历元年处标明对应的泰拉历原文未载；规则写在左栏「怎么读」。
import { D, BIANS } from './data.js';
import { esc, href, threadColor, charName } from './util.js';

const R = 6;                          // 横向半径：布局归一后九成五的点在 1 以内，乘上它
const NEAR = 0.5;                     // 离镜头比这近的不画
const HOME = { yaw: -2.5, pitch: 0.42, dist: 26 };
const outExpo = (x) => (x >= 1 ? 1 : 1 - 2 ** (-10 * x));
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// 渲染耗时，验证性能时读：frames 帧数，ms 累计毫秒，last 最近一帧
export const stats = { frames: 0, ms: 0, last: 0, points: 0 };

let L = null;                         // timeline3d.json
let loading = null;
let P = [];                           // 点：一条编年史条目一个
let byId = new Map();
let zOrder = [];                      // 按 z 排好的点下标
let px, py, pd, ps, pa, depthOrder;   // 每帧的投影结果
let path = null;                      // 按人物或本末筛选时，把选中的点按时间串起来

let root = null, stage, canvas, ctx, tip, hud, rail, countEl, loadingEl;
let W = 0, H = 0, DPR = 1;
const cam = { ...HOME, fz: null };
let B = null;                         // 这一帧的镜头基
let tween = null, raf = 0, ro = null, token = 0, pendingRoute = null;
let hover = -1, pinned = -1;
let pal = null, font = null;
let gesture = null;
const ptrs = new Map();
const filter = { bian: '', benmo: '', char: '' };
let lastHud = '', lastRail = '';

// ------------------------------------------------------------------ 挂载
export function mount(el, r) {
  root = el;
  const my = ++token;
  el.innerHTML = `
    <aside class="t3-side panel">
      <div class="seg-ctrl t3-switch"><a class="t3-to2d" href="#/timeline">平面</a><button class="active" aria-pressed="true">立体</button></div>
      <div class="t3-filters">
        <label>编<select class="t3-bian"><option value="">两编</option>${BIANS.map((b) => `<option>${esc(b)}</option>`).join('')}</select></label>
        <label>纪事本末<select class="t3-benmo"><option value="">全部</option></select></label>
        <label>人物<input class="t3-char" type="search" list="t3-people" placeholder="输入人名" autocomplete="off"></label>
        <datalist id="t3-people"></datalist>
      </div>
      <div class="t3-count muted small"></div>
      <nav class="t3-eras"></nav>
      <details class="t3-read">
        <summary>怎么读</summary>
        <div class="t3-read-body"></div>
      </details>
    </aside>
    <section class="t3-main content">
      <canvas class="t3-canvas" tabindex="0" aria-label="立体时间轴：拖动旋转，滚轮缩放，方向键沿时间移动"></canvas>
      <div class="t3-hud" aria-live="polite"></div>
      <div class="t3-rail" title="拖动沿时间移动"></div>
      <div class="t3-tip" hidden></div>
      <div class="t3-btns"><button class="btn t3-home" title="回到默认视角">复位</button><button class="btn t3-all" title="看整根时间轴">全览</button></div>
      <div class="t3-help small"><span class="t3-help-mouse">拖动旋转 · 右键或 Shift 拖动沿时间走 · 滚轮缩放 · ↑↓ 键前后 · 点事件打开</span><span class="t3-help-touch">单指旋转 · 双指缩放、上下拖动沿时间走 · 点一下看，再点打开</span></div>
      <div class="t3-loading muted">正在载入布局…</div>
    </section>`;
  stage = el.querySelector('.t3-main');
  canvas = el.querySelector('.t3-canvas');
  ctx = canvas.getContext('2d');
  tip = el.querySelector('.t3-tip');
  hud = el.querySelector('.t3-hud');
  rail = el.querySelector('.t3-rail');
  countEl = el.querySelector('.t3-count');
  loadingEl = el.querySelector('.t3-loading');
  lastHud = lastRail = '';
  hover = pinned = -1;
  pendingRoute = r;
  if (!D.annals) {
    loadingEl.textContent = '还没有编年史数据，先运行 python -X utf8 -m pipeline.build。';
    return;
  }
  ensureLayout().then(() => {
    if (my !== token) return;  // 等数据时已经换了页面
    loadingEl.remove();
    setup();
    update(pendingRoute);
  }).catch((err) => {
    if (my !== token) return;
    loadingEl.textContent = `没有立体时间轴的布局数据（${err.message}）。先运行 python -X utf8 -m pipeline.timeline3d。`;
  });
}

export function unmount() {
  token++;
  cancelAnimationFrame(raf);
  raf = 0;
  tween = null;
  ro?.disconnect();
  ro = null;
  document.removeEventListener('keydown', onKey);
  root = null;
}

export function retheme() {
  if (!root || !L) return;
  readPalette();
  request();
}

function ensureLayout() {
  if (L) return Promise.resolve(L);
  loading ??= fetch('data/timeline3d.json').then((res) => {
    if (!res.ok) throw new Error(`加载 data/timeline3d.json 失败：${res.status}`);
    return res.json();
  }).then((data) => {
    L = data;
    buildPoints();
    return L;
  }).catch((err) => {
    loading = null;
    throw err;
  });
  return loading;
}

// ------------------------------------------------------------------ 数据
const PEOPLE = /\[\[([^\]|]+)/g;
const hash = (s) => [...s].reduce((h, c) => Math.imul(h ^ c.codePointAt(0), 16777619) >>> 0, 2166136261) / 4294967296;

function hslRgb(css) {
  const m = /hsl\(([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\)/.exec(css);
  if (!m) return null;
  const h = Number(m[1]) / 360, s = Number(m[2]) / 100, l = Number(m[3]) / 100;
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  const f = (t) => {
    t = (t + 1) % 1;
    const v = t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p;
    return Math.round(v * 255);
  };
  return `rgb(${f(h + 1 / 3)},${f(h)},${f(h - 1 / 3)})`;
}

function buildPoints() {
  const at = new Map(L.ids.map((id, i) => [id, i]));
  const aliases = D.annals.aliases ?? {};
  P = [];
  let prev = null;
  for (const v of D.annals.volumes) for (const s of v.sections) for (const d of s.days) for (const e of d.entries) {
    const li = at.get(e.id);
    let x, y, z;
    if (li != null) {
      x = L.x[li];
      y = L.y[li];
      z = L.z[li];
    } else {  // 布局之后才写进书的条目：先放在前一条旁边，重跑 pipeline.timeline3d 后归位
      const a = hash(e.id) * Math.PI * 2;
      x = Math.cos(a);
      y = Math.sin(a);
      z = prev ? prev.z + 0.3 : 0;
    }
    const row = D.eventById[e.id];
    const thread = row?.thread ?? 'lore';
    const people = new Set(e.groups.flatMap((g) => g.people.flatMap((t) => [...t.matchAll(PEOPLE)].map((m) => aliases[m[1]] ?? m[1]))));
    const color = thread === 'lore' ? null : hslRgb(threadColor(thread));
    const p = {
      id: e.id, e, li, x: x * R, y: y * R, z, thread, people, color,
      hollow: !color || Boolean(e.minor), bian: e.bian ?? BIANS[0],
      gang: (e.groups[0]?.gang ?? '').replace(/\*\*/g, ''), more: e.groups.length - 1,
      rel: [], match: true,
    };
    P.push(p);
    prev = p;
  }
  byId = new Map(P.map((p, k) => [p.id, k]));
  for (const p of P) if (p.li != null) p.rel = L.rel[p.li].map((li) => byId.get(L.ids[li])).filter((k) => k != null);
  zOrder = P.map((_, k) => k).sort((a, b) => P[a].z - P[b].z || a - b);
  const n = P.length;
  px = new Float32Array(n);
  py = new Float32Array(n);
  pd = new Float32Array(n);
  ps = new Float32Array(n);
  pa = new Float32Array(n);
  depthOrder = new Uint32Array(n);
  stats.points = n;
}

const zMin = () => -3;
const zMax = () => L.length + 3;

// 离 z 最近的点
function nearestZ(z) {
  let lo = 0, hi = zOrder.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (P[zOrder[mid]].z < z) lo = mid + 1; else hi = mid;
  }
  const a = zOrder[lo], b = zOrder[Math.max(0, lo - 1)];
  return Math.abs(P[a].z - z) <= Math.abs(P[b].z - z) ? a : b;
}

function eraAt(z) {
  let best = L.eras[0];
  for (const e of L.eras) if (e.z0 - 1.5 <= z) best = e;
  return best;
}

// ------------------------------------------------------------------ 界面
function setup() {
  const side = root.querySelector('.t3-side');
  // 纪事本末：两编分组，带条数
  const count = {};
  for (const p of P) for (const t of p.e.benmo ?? []) count[`${p.bian}:${t}`] = (count[`${p.bian}:${t}`] ?? 0) + 1;
  const benmo = root.querySelector('.t3-benmo');
  benmo.innerHTML = '<option value="">全部</option>' + BIANS.map((b) => {
    const list = (D.annals.benmo ?? []).filter((x) => (x.bian ?? BIANS[0]) === b && count[`${b}:${x.title}`]);
    return list.length ? `<optgroup label="${esc(b)}">${list.map((x) =>
      `<option value="${esc(`${b}:${x.title}`)}">${esc(x.title)}（${count[`${b}:${x.title}`]}）</option>`).join('')}</optgroup>` : '';
  }).join('');
  // 人物：按出场条数排
  const people = {};
  for (const p of P) for (const n of p.people) people[n] = (people[n] ?? 0) + 1;
  const names = Object.keys(people).sort((a, b) => people[b] - people[a] || a.localeCompare(b, 'zh'));
  root.querySelector('#t3-people').innerHTML = names.map((n) =>
    `<option value="${esc(n)}">${esc(charName(n))}${n.startsWith('终末地·') ? '（终末地）' : ''} · ${people[n]} 条</option>`).join('');
  root.querySelector('.t3-eras').innerHTML = L.eras.map((e) =>
    `<button data-z="${e.z0}" class="${e.bian === BIANS[1] ? 'talos' : ''}">${esc(/^\d+$/.test(e.label) ? `${e.label} 年` : e.title)}<span class="muted">${e.n}</span></button>`).join('');
  const cal = L.calendar;
  root.querySelector('.t3-read-body').innerHTML = `
    <p><b>纵轴是时间</b>，从远古一直到塔罗斯历一五二年，但不按比例：${esc(L.scale.text)}</p>
    <p><b>横向按关联远近</b>：共有的人物、纪事本末、故事线、地域越多，或考异里互相引用，就靠得越近；没有关联的散在轴外一圈。悬停一条，细线连到和它最相关的几条。</p>
    <p><b>颜色</b>是故事线，和平面时间轴一样；空心方块是只有设定资料出处的条目和附记。</p>
    <p><b>没有年份的</b>放在虚线标出的区段：开头「年代不详」，泰拉编末尾「不系年」，塔卫二编里「塔罗斯历以前」「年份不书」。</p>
    <p><b>两种历法</b>：泰拉编用泰拉历，塔卫二编用塔罗斯历。${esc(cal.note)}塔罗斯历元年处画一圈绿框，标着「${esc(cal.terra)}」。</p>`;
  if (matchMedia('(min-width: 761px) and (min-height: 700px)').matches) root.querySelector('.t3-read').open = true;

  side.querySelector('.t3-bian').addEventListener('change', (ev) => setFilter({ bian: ev.target.value }));
  benmo.addEventListener('change', (ev) => setFilter({ benmo: ev.target.value }));
  const charInput = side.querySelector('.t3-char');
  charInput.addEventListener('change', () => {
    const v = charInput.value.trim();
    const name = people[v] ? v : names.find((n) => charName(n) === v) ?? (v ? null : '');
    if (name === null) {
      charInput.setCustomValidity('书里没有这个人物');
      charInput.reportValidity();
      return;
    }
    charInput.setCustomValidity('');
    setFilter({ char: name });
  });
  root.querySelector('.t3-eras').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-z]');
    if (b) flyTo(Number(b.dataset.z) + 2);
  });
  side.querySelector('.t3-to2d').addEventListener('click', (ev) => {
    const k = pinned >= 0 ? pinned : hover;
    const p = k >= 0 ? P[k] : P[nearestZ(cam.fz)];
    ev.currentTarget.href = `#/timeline?${new URLSearchParams({ ev: p.id, bian: p.bian })}`;
  });
  root.querySelector('.t3-home').addEventListener('click', () => {
    flyTo(cam.fz, { ...HOME });
  });
  root.querySelector('.t3-all').addEventListener('click', () => {
    // 侧面看整根轴：可见宽度 = 距离 × 画面宽 / 焦距
    const F = Math.min(Math.max(W, H) * 0.75, Math.min(W, H) * 1.25);
    flyTo(L.length / 2, { yaw: -Math.PI / 2, pitch: 0.3, dist: ((L.length + 10) * F) / Math.max(200, W - 120) });
  });
  buildRail();
  bindPointer();
  document.addEventListener('keydown', onKey);
  ro = new ResizeObserver(resize);
  ro.observe(stage);
  document.fonts?.ready.then(request);
  readPalette();
  resize();
}

function buildRail() {
  const span = zMax() - zMin();
  const at = (z) => `${((z - zMin()) / span) * 100}%`;
  const eras = L.eras.map((e) => `<i class="t3-rail-t${e.bian === BIANS[1] ? ' talos' : ''}" style="top:${at(e.z0)}"></i>`).join('');
  const gaps = [...L.breaks.map((b) => `<i class="t3-rail-gap" style="top:${at(b.z0)};height:calc(${at(b.z1)} - ${at(b.z0)})"></i>`),
    ...L.bands.map((b) => `<i class="t3-rail-band" style="top:${at(b.z0 - 0.5)};height:calc(${at(b.z1 + 0.5)} - ${at(b.z0 - 0.5)})"></i>`)].join('');
  const cal = L.calendar.z != null ? `<i class="t3-rail-cal" style="top:${at(L.calendar.z)}" title="${esc(L.calendar.label)}：${esc(L.calendar.terra)}"></i>` : '';
  rail.innerHTML = `<div class="t3-rail-track">${gaps}<i class="t3-rail-fill"></i>${eras}${cal}<i class="cross on t3-rail-mark"></i></div><div class="t3-rail-labels"></div>`;
  placeRailLabels();
}

// 轨道旁的年代名：放得下才放，大的先放
function placeRailLabels() {
  const box = rail.querySelector('.t3-rail-labels');
  const h = rail.clientHeight;
  if (!h) return;
  const span = zMax() - zMin();
  const pri = (e) => (['外纪', '1080', '1097', '1100', '1103', '不系年', '塔卫二前纪', '塔152'].includes(e.label) ? 1000 : 0) + e.n;
  const placed = [];
  const out = [];
  for (const e of [...L.eras].sort((a, b) => pri(b) - pri(a))) {
    const y = ((e.z0 - zMin()) / span) * h;
    if (placed.some((p) => Math.abs(p - y) < 13)) continue;
    placed.push(y);
    out.push(`<span class="${e.bian === BIANS[1] ? 'talos' : ''}" style="top:${y}px">${esc(e.label)}</span>`);
  }
  if (L.calendar.z != null) {
    const y = ((L.calendar.z - zMin()) / span) * h;
    if (!placed.some((p) => Math.abs(p - y) < 13)) out.push(`<span class="cal" style="top:${y}px">塔元年</span>`);
  }
  box.innerHTML = out.join('');
}

function setRail() {
  const t = clamp((cam.fz - zMin()) / (zMax() - zMin()), 0, 1);
  const key = t.toFixed(4);
  if (key === lastRail) return;
  lastRail = key;
  rail.style.setProperty('--at', `${t * 100}%`);
}

function setHud() {
  const era = eraAt(cam.fz);
  const k = nearestZ(cam.fz);
  const p = P[k];
  const brk = L.breaks.find((b) => cam.fz > b.z0 + 0.5 && cam.fz < b.z1 - 0.5);
  const band = L.bands.find((b) => cam.fz >= b.z0 - 1 && cam.fz <= b.z1 + 1);
  const cal = L.calendar.z != null && Math.abs(cam.fz - L.calendar.z) < 4;
  const big = brk ? '断开' : era.label;
  const lines = brk ? [brk.label, '泰拉历之后接塔罗斯历'] : [
    /^塔?\d+$/.test(era.label) ? p.e.when : `${era.title.split(' · ').pop()} · ${p.e.when}`,
    band ? `${band.label}：${band.note}` : cal ? `${L.calendar.label}：${L.calendar.terra}` : era.bian,
  ];
  const html = `<b>${esc(big)}</b>${lines.map((l) => `<span>${esc(l)}</span>`).join('')}`;
  if (html === lastHud) return;
  lastHud = html;
  hud.innerHTML = html;
  hud.classList.toggle('talos', era.bian === BIANS[1] && !brk);
}

// ------------------------------------------------------------------ 路由与筛选
export function update(r) {
  if (!L || !P.length) {
    pendingRoute = r;
    return;
  }
  const q = r.params;
  const benmo = q.get('benmo') ?? '';
  const next = {
    bian: BIANS.includes(q.get('bian')) ? q.get('bian') : '',
    benmo: benmo && !benmo.includes(':') ? `${q.get('bian') || BIANS[0]}:${benmo}` : benmo,
    char: q.get('char') ?? '',
  };
  const changed = Object.keys(next).some((k) => next[k] !== filter[k]);
  Object.assign(filter, next);
  root.querySelector('.t3-bian').value = filter.bian;
  root.querySelector('.t3-benmo').value = filter.benmo;
  root.querySelector('.t3-char').value = filter.char;
  applyFilter();
  const e = q.get('e');
  const k = e != null ? byId.get(e) ?? byId.get(D.annalsByEvent[e]) : undefined;
  if (k != null) {
    pinned = k;
    if (cam.fz == null || Math.abs(cam.fz - P[k].z) > 2) cam.fz = P[k].z;
    showTip(k);
  } else if (cam.fz == null) {
    const start = L.eras.find((x) => x.label === '1097') ?? L.eras[0];
    cam.fz = start.z0 + 4;
  }
  if (changed && k == null) focusMatches();
  request();
}

function setFilter(part) {
  Object.assign(filter, part);
  applyFilter();
  focusMatches();
  writeUrl();
  request();
}

function writeUrl(extra = {}) {
  const p = new URLSearchParams();
  if (filter.bian) p.set('bian', filter.bian);
  if (filter.benmo) p.set('benmo', filter.benmo);
  if (filter.char) p.set('char', filter.char);
  for (const [k, v] of Object.entries(extra)) if (v) p.set(k, v);
  history.replaceState(null, '', `#/timeline3d${p.size ? `?${p}` : ''}`);
}

function applyFilter() {
  const [bb, bt] = filter.benmo ? [filter.benmo.slice(0, filter.benmo.indexOf(':')), filter.benmo.slice(filter.benmo.indexOf(':') + 1)] : [];
  let n = 0;
  for (const p of P) {
    p.match = (!filter.bian || p.bian === filter.bian)
      && (!filter.benmo || (p.bian === bb && (p.e.benmo ?? []).includes(bt)))
      && (!filter.char || p.people.has(filter.char));
    if (p.match) n++;
  }
  path = filter.benmo || filter.char ? zOrder.filter((k) => P[k].match) : null;
  const what = [filter.bian, filter.benmo && `本末「${filter.benmo.split(':').pop()}」`, filter.char && `人物「${charName(filter.char)}」`].filter(Boolean);
  countEl.innerHTML = `显示 ${n} / ${P.length} 条${what.length ? `：${esc(what.join('，'))} <button class="t3-clear">清除</button>` : ''}`;
  countEl.querySelector('.t3-clear')?.addEventListener('click', () => {
    root.querySelector('.t3-char').value = '';
    setFilter({ bian: '', benmo: '', char: '' });
    root.querySelector('.t3-bian').value = '';
    root.querySelector('.t3-benmo').value = '';
  });
  if (pinned >= 0 && !P[pinned].match) unpin();
}

// 筛选后，眼前没有选中的点就飞到最近的一个
function focusMatches() {
  if (!filter.bian && !filter.benmo && !filter.char) return;
  let bz = null, bd = Infinity;
  for (const p of P) {
    const d = Math.abs(p.z - cam.fz);
    if (p.match && d < bd) { bd = d; bz = p.z; }
  }
  if (bz == null) return;
  if (path?.length) {
    if (bd > 8) flyTo(P[path[0]].z + 2);  // 本末、人物：从头看起
  } else if (bd > 6) {
    flyTo(bz);
  }
}

// ------------------------------------------------------------------ 镜头
function flyTo(z, to = {}) {
  const from = { fz: cam.fz, yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist };
  const target = { fz: clamp(z, zMin(), zMax()), yaw: to.yaw ?? cam.yaw, pitch: to.pitch ?? cam.pitch, dist: to.dist ?? cam.dist };
  if (reduced()) {
    Object.assign(cam, target);
    tween = null;
  } else {
    tween = { from, target, t0: performance.now(), dur: 650 };
  }
  request();
}

function stopTween() {
  tween = null;
}

function stepTween(now) {
  if (!tween) return;
  const t = outExpo(Math.min(1, (now - tween.t0) / tween.dur));
  for (const k of ['fz', 'yaw', 'pitch', 'dist']) cam[k] = tween.from[k] + (tween.target[k] - tween.from[k]) * t;
  if (t >= 1) tween = null;
}

function basis() {
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
  const ox = cam.dist * cp * Math.sin(cam.yaw), oy = cam.dist * sp, oz = cam.dist * cp * Math.cos(cam.yaw);
  const f = [-ox / cam.dist, -oy / cam.dist, -oz / cam.dist];
  const rl = Math.hypot(f[2], f[0]) || 1;
  const r = [-f[2] / rl, 0, f[0] / rl];
  const u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
  const F = Math.min(Math.max(W, H) * 0.75, Math.min(W, H) * 1.25);
  // 雾：离镜头比焦点远出这么多以后渐隐
  const fogStart = cam.dist * 0.9, fogLen = Math.max(28, cam.dist * 1.7);
  return { C: [ox, oy, cam.fz + oz], f, r, u, F, cx: W / 2, cy: H / 2, fogStart, fogLen };
}

const out = { x: 0, y: 0, d: 0 };
function proj(x, y, z) {
  const dx = x - B.C[0], dy = y - B.C[1], dz = z - B.C[2];
  const d = dx * B.f[0] + dy * B.f[1] + dz * B.f[2];
  if (d < NEAR) return false;
  out.x = B.cx + ((dx * B.r[0] + dy * B.r[1] + dz * B.r[2]) / d) * B.F;
  out.y = B.cy - ((dx * B.u[0] + dy * B.u[1] + dz * B.u[2]) / d) * B.F;
  out.d = d;
  return true;
}

function fog(d) {
  const far = d <= B.fogStart ? 1 : Math.max(0, 1 - (d - B.fogStart) / B.fogLen);
  return d < 2.5 ? far * clamp((d - NEAR) / 2, 0, 1) : far;
}

// ------------------------------------------------------------------ 颜色
function readPalette() {
  const probe = document.createElement('i');
  probe.style.display = 'none';
  stage.appendChild(probe);
  const rgb = (v) => {
    probe.style.color = '';
    probe.style.color = `var(${v})`;
    const c = getComputedStyle(probe).color;
    const n = (c.match(/[\d.]+/g) ?? ['0', '0', '0']).map(Number);
    const scale = c.startsWith('color(') ? 255 : 1;  // color-mix 的结果写成 color(srgb r g b)
    return `rgb(${Math.round(n[0] * scale)},${Math.round(n[1] * scale)},${Math.round(n[2] * scale)})`;
  };
  pal = {
    bg: rgb('--panel'), text: rgb('--text'), muted: rgb('--muted'), line: rgb('--line'), lore: rgb('--lore'),
    tick: rgb('--tick'), accent: rgb('--accent'), lime: rgb('--lime'), ink: rgb('--ink'),
    tagBg: rgb('--tag-bg'), tagFg: rgb('--tag-fg'), paper: rgb('--paper'), paperFg: rgb('--paper-fg'),
  };
  probe.remove();
  const css = getComputedStyle(document.documentElement);
  font = { num: css.getPropertyValue('--f-num').trim() || 'sans-serif', body: css.getPropertyValue('--f-body').trim() || 'sans-serif' };
}

// ------------------------------------------------------------------ 画
function resize() {
  if (!root) return;
  const r = stage.getBoundingClientRect();
  W = Math.max(1, Math.round(r.width));
  H = Math.max(1, Math.round(r.height));
  DPR = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(W * DPR);
  canvas.height = Math.round(H * DPR);
  placeRailLabels();
  request();
}

function request() {
  if (!raf && root) raf = requestAnimationFrame(frame);
}

function frame(now) {
  raf = 0;
  if (!root || !L) return;
  const t0 = performance.now();
  stepTween(now);
  draw();
  stats.last = performance.now() - t0;
  stats.ms += stats.last;
  stats.frames++;
  if (tween) request();
}

function draw() {
  B = basis();
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.clearRect(0, 0, W, H);
  // 轴在屏幕上是一条直线：取它的方向和法线（朝上的一侧放年份）
  let ax = 1, ay = 0;
  if (proj(0, 0, cam.fz)) {
    const x0 = out.x, y0 = out.y;
    if (proj(0, 0, cam.fz + 1)) {
      const dx = out.x - x0, dy = out.y - y0, l = Math.hypot(dx, dy);
      if (l > 1e-3) { ax = dx / l; ay = dy / l; }
    }
  }
  let nx = -ay, ny = ax;
  if (ny > 0 || (Math.abs(ny) < 1e-3 && nx > 0)) { nx = -nx; ny = -ny; }
  const axis = { ax, ay, nx, ny };
  normal = { nx, ny };

  projectPoints();
  const labels = [];
  drawFrames(labels);
  drawAxis(axis, labels);
  drawPath();
  drawPoints();
  const active = pinned >= 0 ? pinned : hover;
  if (active >= 0) drawActive(active, axis, labels);
  drawLabels(labels);
  drawFocus();
  setHud();
  setRail();
  if (active >= 0) placeTip(active);
}

function projectPoints() {
  const n = P.length;
  let m = 0;
  const base = 0.13 * B.F;
  for (let k = 0; k < n; k++) {
    const p = P[k];
    if (!proj(p.x, p.y, p.z)) { pa[k] = 0; continue; }
    const a = fog(out.d);
    pa[k] = a;
    if (a <= 0.01) continue;
    px[k] = out.x;
    py[k] = out.y;
    pd[k] = out.d;
    ps[k] = clamp(base / out.d, 1.3, 7);
    if (out.x < -20 || out.x > W + 20 || out.y < -20 || out.y > H + 20) continue;
    depthOrder[m++] = k;
  }
  const order = depthOrder.subarray(0, m);
  order.sort((a, b) => pd[b] - pd[a]);
  projectPoints.count = m;
}

function drawPoints() {
  const order = depthOrder.subarray(0, projectPoints.count);
  ctx.lineWidth = 1;
  for (const k of order) {
    const p = P[k];
    const a = p.match ? pa[k] : pa[k] * 0.13;
    if (a <= 0.01) continue;
    const s = ps[k], x = px[k], y = py[k];
    ctx.globalAlpha = a;
    if (p.hollow) {
      ctx.fillStyle = pal.bg;
      ctx.fillRect(x - s, y - s, s * 2, s * 2);
      ctx.strokeStyle = p.color ?? pal.lore;
      ctx.lineWidth = s > 2.5 ? 1.4 : 1;
      ctx.strokeRect(x - s + 0.5, y - s + 0.5, s * 2 - 1, s * 2 - 1);
    } else {
      ctx.fillStyle = p.color;
      ctx.fillRect(x - s, y - s, s * 2, s * 2);
      if (s > 2.2 && p.match) {
        ctx.strokeStyle = pal.bg;
        ctx.lineWidth = 1;
        ctx.strokeRect(x - s - 0.5, y - s - 0.5, s * 2 + 1, s * 2 + 1);
      }
    }
  }
  ctx.globalAlpha = 1;
}

// 每卷开头一个横截面的四个角（裁切角标）；塔罗斯历元年是一整圈绿框
function drawFrames(labels) {
  const S = R * 1.18, arm = S * 0.22;
  const corners = [[1, 1], [1, -1], [-1, -1], [-1, 1]];
  ctx.lineWidth = 1;
  for (const e of L.eras) {
    const z = e.z0 - 0.6;
    if (!proj(0, 0, z)) continue;
    const a = fog(out.d);
    if (a <= 0.03) continue;
    // 四个角都在镜头前才画，免得一条边穿到镜头后面
    const pts = [];
    for (const [sx, sy] of corners) {
      if (!proj(sx * S, sy * S, z)) break;
      pts.push([out.x, out.y]);
    }
    if (pts.length < 4) continue;
    ctx.globalAlpha = a * 0.55;
    ctx.strokeStyle = pal.line;
    ctx.beginPath();
    pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.stroke();
    ctx.globalAlpha = a * 0.9;
    ctx.strokeStyle = pal.text;
    ctx.beginPath();
    for (const [sx, sy] of corners) {
      if (!proj(sx * S - sx * arm, sy * S, z)) continue;
      ctx.moveTo(out.x, out.y);
      if (!proj(sx * S, sy * S, z)) continue;
      ctx.lineTo(out.x, out.y);
      if (!proj(sx * S, sy * S - sy * arm, z)) continue;
      ctx.lineTo(out.x, out.y);
    }
    ctx.stroke();
  }
  const cz = L.calendar.z;
  if (cz != null && proj(0, 0, cz - 0.7)) {
    const a = fog(out.d);
    if (a > 0.03) {
      ctx.globalAlpha = a;
      ctx.strokeStyle = pal.lime;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      let first = true;
      for (const [sx, sy] of [...corners, corners[0]]) {
        if (!proj(sx * S, sy * S, cz - 0.7)) { first = true; continue; }
        if (first) ctx.moveTo(out.x, out.y); else ctx.lineTo(out.x, out.y);
        first = false;
      }
      ctx.stroke();
      ctx.lineWidth = 1;
      ctx.strokeStyle = pal.text;
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

function drawAxis(axis, labels) {
  const { nx, ny } = axis;
  const pieces = [];
  const gaps = L.breaks.map((b) => [b.z0, b.z1]);
  const bands = L.bands.map((b) => [b.z0 - 0.6, b.z1 + 0.6]);
  const STEP = 1.5;
  for (let z = zMin(); z < zMax(); z += STEP) {
    const z1 = Math.min(z + STEP, zMax());
    const mid = (z + z1) / 2;
    const gap = gaps.some(([a, b]) => mid > a && mid < b);
    const band = bands.some(([a, b]) => mid > a && mid < b);
    pieces.push([z, z1, gap ? 'gap' : band ? 'band' : 'line']);
  }
  ctx.lineCap = 'butt';
  for (const [z0, z1, kind] of pieces) {
    // 近平面裁剪：两头都在镜头后面就跳过，一头在后面就截到近平面
    let a0 = z0, a1 = z1;
    const d0 = depthAt(a0), d1 = depthAt(a1);
    if (d0 < NEAR && d1 < NEAR) continue;
    if (d0 < NEAR) a0 = a0 + (a1 - a0) * (NEAR - d0) / (d1 - d0) + 1e-3;
    if (d1 < NEAR) a1 = a1 - (a1 - a0) * (NEAR - d1) / (d0 - d1) - 1e-3;
    if (!proj(0, 0, a0)) continue;
    const x0 = out.x, y0 = out.y, fa = fog(out.d);
    if (!proj(0, 0, a1)) continue;
    const x1 = out.x, y1 = out.y, fb = fog(out.d);
    const alpha = Math.max(fa, fb);
    if (alpha <= 0.02) continue;
    ctx.globalAlpha = alpha * (kind === 'gap' ? 0.4 : 1);
    ctx.strokeStyle = pal.text;
    ctx.setLineDash(kind === 'line' ? [] : kind === 'band' ? [5, 4] : [2, 6]);
    ctx.lineWidth = kind === 'line' ? 2 : 1.5;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    if (kind === 'line') {  // 轨道的第二根细线
      ctx.lineWidth = 1;
      ctx.globalAlpha = alpha * 0.5;
      ctx.beginPath();
      ctx.moveTo(x0 + nx * 4, y0 + ny * 4);
      ctx.lineTo(x1 + nx * 4, y1 + ny * 4);
      ctx.stroke();
    }
  }
  ctx.setLineDash([]);

  // 刻度：年长、月中、日短，都在轴的上侧
  const len = { year: 9, sec: 6, day: 3.5 };
  ctx.lineWidth = 1;
  ctx.strokeStyle = pal.text;
  const eraStart = new Set(L.eras.map((e) => `${e.z0}|${e.label}`));
  for (const [z, label, kind] of L.ticks) {
    if (!proj(0, 0, z)) continue;
    const a = fog(out.d);
    if (a <= 0.03 || out.x < -40 || out.x > W + 40 || out.y < -40 || out.y > H + 40) continue;
    const x = out.x, y = out.y, l = len[kind];
    ctx.globalAlpha = a;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + nx * l, y + ny * l);
    ctx.stroke();
    if (eraStart.has(`${z}|${label}`)) continue;  // 卷首的年份由卷名标出
    if (kind === 'year') labels.push({ pri: 4, x, y, d: out.d, a, text: label, style: 'year', off: 20, side: 1 });
    else if (kind === 'sec') labels.push({ pri: 3, x, y, d: out.d, a, text: label, style: 'sec', off: 13, side: -1 });
    else labels.push({ pri: 2, x, y, d: out.d, a, text: label, style: 'day', off: 13, side: -1 });
  }
  ctx.globalAlpha = 1;
  for (const e of L.eras) {
    if (!proj(0, 0, e.z0)) continue;
    const a = fog(out.d);
    if (a <= 0.05) continue;
    labels.push({ pri: 5, x: out.x, y: out.y, d: out.d, a, text: e.label, style: e.bian === BIANS[1] ? 'era-talos' : 'era', off: 30, side: 1 });
  }
  for (const b of L.bands) {
    if (!proj(0, 0, b.z0 - 0.6)) continue;
    const a = fog(out.d);
    if (a > 0.05) labels.push({ pri: 6, x: out.x, y: out.y, d: out.d, a, text: b.label, style: 'band', off: 26, side: -1 });
  }
  // 断开处：两头各一道斜杠，中间一个标签
  for (const b of L.breaks) {
    for (const z of [b.z0, b.z1]) {
      if (!proj(0, 0, z)) continue;
      const a = fog(out.d);
      if (a <= 0.03) continue;
      ctx.globalAlpha = a;
      ctx.lineWidth = 2;
      ctx.strokeStyle = pal.text;
      ctx.beginPath();
      for (const o of [-3, 3]) {
        const cx = out.x + axis.ax * o, cy = out.y + axis.ay * o;
        ctx.moveTo(cx - nx * 9 - axis.ax * 4, cy - ny * 9 - axis.ay * 4);
        ctx.lineTo(cx + nx * 9 + axis.ax * 4, cy + ny * 9 + axis.ay * 4);
      }
      ctx.stroke();
    }
    if (proj(0, 0, (b.z0 + b.z1) / 2)) {
      const a = fog(out.d);
      if (a > 0.05) labels.push({ pri: 7, x: out.x, y: out.y, d: out.d, a, text: b.label, style: 'break', off: 24, side: -1 });
    }
  }
  const cz = L.calendar.z;
  if (cz != null && proj(0, 0, cz - 0.7)) {
    const a = fog(out.d);
    if (a > 0.05) labels.push({ pri: 8, x: out.x, y: out.y, d: out.d, a, text: L.calendar.label, sub: L.calendar.terra, style: 'cal', off: 44, side: 1 });
  }
  ctx.globalAlpha = 1;
  ctx.lineWidth = 1;
}

function depthAt(z) {
  return (0 - B.C[0]) * B.f[0] + (0 - B.C[1]) * B.f[1] + (z - B.C[2]) * B.f[2];
}

function drawPath() {
  if (!path || path.length < 2) return;
  ctx.strokeStyle = pal.accent;
  ctx.lineWidth = 1.2;
  let prev = -1;
  for (const k of path) {
    if (pa[k] > 0.02 && prev >= 0 && pa[prev] > 0.02) {
      ctx.globalAlpha = 0.55 * Math.min(pa[k], pa[prev]);
      ctx.beginPath();
      ctx.moveTo(px[prev], py[prev]);
      ctx.lineTo(px[k], py[k]);
      ctx.stroke();
    }
    prev = k;
  }
  ctx.globalAlpha = 1;
}

// 悬停或选中的一条：细线连到最相关的几条，垂线落到轴上，轴上标出它的日期
function drawActive(k, axis, labels) {
  if (pa[k] <= 0.01) return;
  const p = P[k];
  ctx.lineWidth = 1;
  ctx.strokeStyle = pal.text;
  for (const j of p.rel) {
    if (pa[j] <= 0.01) continue;
    ctx.globalAlpha = 0.6 * Math.max(0.35, Math.min(pa[k], pa[j]));
    ctx.beginPath();
    ctx.moveTo(px[k], py[k]);
    ctx.lineTo(px[j], py[j]);
    ctx.stroke();
    const s = ps[j] + 2.5;
    ctx.strokeRect(px[j] - s, py[j] - s, s * 2, s * 2);
  }
  ctx.globalAlpha = 1;
  if (proj(0, 0, p.z)) {
    const ax = out.x, ay = out.y;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(px[k], py[k]);
    ctx.lineTo(ax, ay);
    ctx.stroke();
    ctx.setLineDash([]);
    cross(ax, ay, 11);
    labels.push({ pri: 9, x: ax, y: ay, d: out.d, a: 1, text: p.e.when, style: 'when', off: 18, side: -1 });
  }
  const s = ps[k] + 2;
  ctx.fillStyle = pal.lime;
  ctx.fillRect(px[k] - s, py[k] - s, s * 2, s * 2);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = pal.ink;
  ctx.strokeRect(px[k] - s, py[k] - s, s * 2, s * 2);
}

// 十字方块：轨道上的锚点
function cross(x, y, size) {
  const h = size / 2;
  ctx.fillStyle = pal.lime;
  ctx.fillRect(x - h, y - h, size, size);
  ctx.lineWidth = 1;
  ctx.strokeStyle = pal.ink;
  ctx.strokeRect(x - h + 0.5, y - h + 0.5, size - 1, size - 1);
  ctx.beginPath();
  ctx.moveTo(x, y - h + 2.5);
  ctx.lineTo(x, y + h - 2.5);
  ctx.moveTo(x - h + 2.5, y);
  ctx.lineTo(x + h - 2.5, y);
  ctx.stroke();
}

function drawFocus() {
  if (!proj(0, 0, cam.fz)) return;
  ctx.globalAlpha = 1;
  const x = Math.round(out.x) + 0.5, y = Math.round(out.y) + 0.5;
  ctx.fillStyle = pal.bg;
  ctx.fillRect(x - 6, y - 6, 12, 12);
  ctx.lineWidth = 1;
  ctx.strokeStyle = pal.text;
  ctx.strokeRect(x - 6, y - 6, 12, 12);
  ctx.beginPath();
  ctx.moveTo(x, y - 3.5);
  ctx.lineTo(x, y + 3.5);
  ctx.moveTo(x - 3.5, y);
  ctx.lineTo(x + 3.5, y);
  ctx.stroke();
}

const STYLES = {
  era: { font: (f) => `800 13px ${f.num}`, bg: 'tagBg', fg: 'tagFg', pad: 6, h: 20 },
  'era-talos': { font: (f) => `800 13px ${f.num}`, bg: 'tagBg', fg: 'lime', pad: 6, h: 20 },
  year: { font: (f) => `700 11px ${f.num}`, bg: 'tagBg', fg: 'tagFg', pad: 4, h: 16 },
  sec: { font: (f) => `700 11px ${f.body}`, fg: 'text', pad: 1, h: 14 },
  day: { font: (f) => `500 10.5px ${f.body}`, fg: 'muted', pad: 1, h: 13 },
  band: { font: (f) => `700 11.5px ${f.body}`, bg: 'bg', fg: 'text', border: 'text', dash: true, pad: 5, h: 18 },
  break: { font: (f) => `700 11.5px ${f.body}`, bg: 'paper', fg: 'paperFg', border: 'text', pad: 6, h: 19 },
  cal: { font: (f) => `800 12.5px ${f.body}`, bg: 'lime', fg: 'ink', border: 'ink', pad: 7, h: 36 },
  when: { font: (f) => `800 11.5px ${f.body}`, bg: 'lime', fg: 'ink', border: 'ink', pad: 5, h: 18 },
};

// 标签：重要的、近的先放，放不下的不放（发丝线 + 黑底标签）
function drawLabels(labels) {
  labels.sort((a, b) => b.pri - a.pri || a.d - b.d);
  // 左上角的当前时刻、右边的时间轨道、右下的按钮不压字
  const placed = [
    { x: hud.offsetLeft - 6, y: hud.offsetTop - 6, w: hud.offsetWidth + 12, h: hud.offsetHeight + 12 },
    { x: rail.offsetLeft - 8, y: 0, w: W, h: H },
    { x: 0, y: H - 44, w: W, h: 44 },
  ];
  const hit = (r) => placed.some((q) => r.x < q.x + q.w + 3 && r.x + r.w + 3 > q.x && r.y < q.y + q.h + 2 && r.y + r.h + 2 > q.y);
  ctx.textBaseline = 'middle';
  let count = 0;
  for (const l of labels) {
    if (l.a < 0.18 || count > 90) continue;
    const st = STYLES[l.style];
    ctx.font = st.font(font);
    const tw = Math.max(ctx.measureText(l.text).width, l.sub ? (ctx.font = `600 11px ${font.body}`, ctx.measureText(l.sub).width) : 0);
    ctx.font = st.font(font);
    const w = tw + st.pad * 2, h = st.h;
    // 放在轴的一侧：side 1 朝上（法线方向），-1 朝下
    const { nx, ny } = normal;
    const ox = l.x + nx * l.off * l.side, oy = l.y + ny * l.off * l.side;
    const r = { x: ox - w / 2, y: oy - h / 2, w, h };
    if (r.x > W || r.x + w < 0 || r.y > H || r.y + h < 0) continue;
    if (hit(r)) continue;
    placed.push(r);
    count++;
    ctx.globalAlpha = Math.min(1, l.a * 1.15);
    if (st.bg) {
      ctx.strokeStyle = pal.text;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(l.x + nx * 3 * l.side, l.y + ny * 3 * l.side);
      ctx.lineTo(ox - nx * (h / 2) * l.side, oy - ny * (h / 2) * l.side);
      ctx.stroke();
      ctx.fillStyle = pal[st.bg];
      ctx.fillRect(r.x, r.y, w, h);
      if (st.border) {
        ctx.setLineDash(st.dash ? [3, 2] : []);
        ctx.strokeStyle = pal[st.border];
        ctx.strokeRect(r.x + 0.5, r.y + 0.5, w - 1, h - 1);
        ctx.setLineDash([]);
      }
    }
    ctx.fillStyle = pal[st.fg];
    ctx.textAlign = 'center';
    if (l.sub) {
      ctx.fillText(l.text, ox, oy - 8);
      ctx.font = `600 11px ${font.body}`;
      ctx.fillText(l.sub, ox, oy + 8);
    } else {
      ctx.fillText(l.text, ox, oy + 0.5);
    }
  }
  ctx.globalAlpha = 1;
  ctx.textAlign = 'start';
}

let normal = { nx: 0, ny: -1 };

// ------------------------------------------------------------------ 提示框
function showTip(k) {
  const p = P[k];
  const e = p.e;
  const shared = reasons(p);
  const touch = matchMedia('(hover: none)').matches;
  tip.innerHTML = `
    <div class="t3-tip-when">${esc(e.when)}<span>${esc(p.bian)}</span></div>
    <div class="t3-tip-gang">${esc(p.gang)}${p.more ? `<span class="muted">（另 ${p.more} 条）</span>` : ''}</div>
    ${(e.benmo ?? []).length ? `<div class="t3-tip-meta">本末：${esc(e.benmo.join('、'))}</div>` : ''}
    ${shared ? `<div class="t3-tip-meta">细线连到相关的 ${p.rel.length} 条：${esc(shared)}</div>` : ''}
    <a class="t3-tip-open" href="${href.annalsEntry(p.id)}">${touch || k === pinned ? '打开这一条 →' : '点击打开'}</a>`;
  tip.hidden = false;
  tip.classList.toggle('pinned', k === pinned);
  tip.querySelector('.t3-tip-open').addEventListener('click', (ev) => {
    ev.preventDefault();
    open(k);
  });
}

// 为什么相关：数一数最相关的几条共有什么
function reasons(p) {
  const cnt = new Map();
  const add = (key) => cnt.set(key, (cnt.get(key) ?? 0) + 1);
  for (const j of p.rel) {
    const q = P[j];
    for (const b of p.e.benmo ?? []) if ((q.e.benmo ?? []).includes(b)) add(`同属「${b}」`);
    for (const n of p.people) if (q.people.has(n)) add(charName(n));
    if (q.thread === p.thread && p.thread !== 'lore') add('同一故事线');
  }
  const list = [...cnt].sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k]) => k);
  const groups = list.filter((x) => x.startsWith('同'));
  const names = list.filter((x) => !x.startsWith('同'));
  return [...groups, names.length ? `同有${names.join('、')}` : ''].filter(Boolean).join('，');
}

function placeTip(k) {
  if (tip.hidden) return;
  if (pa[k] <= 0.01) {
    tip.style.visibility = 'hidden';
    return;
  }
  tip.style.visibility = '';
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let x = px[k] + 16, y = py[k] - th - 12;
  if (x + tw > W - 90) x = px[k] - tw - 16;
  if (y < 8) y = py[k] + 16;
  tip.style.left = `${clamp(x, 8, Math.max(8, W - tw - 8))}px`;
  tip.style.top = `${clamp(y, 8, Math.max(8, H - th - 8))}px`;
}

function unpin() {
  pinned = -1;
  if (hover < 0) tip.hidden = true;
  else showTip(hover);
}

function open(k) {
  const p = P[k];
  writeUrl({ e: p.id });
  location.hash = href.annalsEntry(p.id);
}

// ------------------------------------------------------------------ 操作
function pick(x, y, radius) {
  let best = -1, bs = Infinity;
  const n = projectPoints.count ?? 0;
  for (let i = 0; i < n; i++) {
    const k = depthOrder[i];
    if (!P[k].match || pa[k] < 0.08) continue;
    const r = radius + ps[k];
    const dx = px[k] - x, dy = py[k] - y, d2 = dx * dx + dy * dy;
    if (d2 > r * r) continue;
    const score = d2 + pd[k] * 0.5;  // 一样近时取离镜头近的
    if (score < bs) { bs = score; best = k; }
  }
  return best;
}

function setHover(k) {
  if (k === hover) return;
  hover = k;
  canvas.classList.toggle('on-point', k >= 0);
  if (pinned < 0) {
    if (k >= 0) showTip(k); else tip.hidden = true;
  }
  request();
}

function grabScale() {
  // 屏幕上沿轴移动一像素，相当于 z 走多少
  if (!proj(0, 0, cam.fz)) return null;
  const x0 = out.x, y0 = out.y;
  if (!proj(0, 0, cam.fz + 1)) return null;
  const vx = out.x - x0, vy = out.y - y0, l2 = vx * vx + vy * vy;
  return l2 < 4 ? null : { vx, vy, l2 };
}

function flyBy(dx, dy, g, dist) {
  // 抓着轴拖：沿轴方向的位移换成 z；没有抓手（双指、镜头几乎顺着轴看）时往上拖是往后走
  return g ? -(dx * g.vx + dy * g.vy) / g.l2 : (-dy * dist) / H * 1.5;
}

function bindPointer() {
  canvas.addEventListener('contextmenu', (ev) => ev.preventDefault());
  canvas.addEventListener('pointerdown', (ev) => {
    canvas.focus({ preventScroll: true });
    canvas.setPointerCapture(ev.pointerId);
    ptrs.set(ev.pointerId, { x: ev.offsetX, y: ev.offsetY });
    stopTween();
    B = basis();
    if (ptrs.size === 1) {
      gesture = {
        mode: ev.button === 2 || ev.shiftKey ? 'fly' : 'orbit', type: ev.pointerType,
        x0: ev.offsetX, y0: ev.offsetY, yaw0: cam.yaw, pitch0: cam.pitch, fz0: cam.fz, moved: 0, g: grabScale(),
      };
    } else if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()];
      gesture = {
        mode: 'pinch', type: ev.pointerType, d0: Math.hypot(a.x - b.x, a.y - b.y) || 1, dist0: cam.dist,
        mx0: (a.x + b.x) / 2, my0: (a.y + b.y) / 2, fz0: cam.fz, moved: 99,
      };
    }
    canvas.classList.add('dragging');
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (!ptrs.has(ev.pointerId)) {
      if (ev.pointerType === 'mouse' && !tween) setHover(pick(ev.offsetX, ev.offsetY, 6));
      return;
    }
    ptrs.set(ev.pointerId, { x: ev.offsetX, y: ev.offsetY });
    const g = gesture;
    if (!g) return;
    if (g.mode === 'pinch' && ptrs.size >= 2) {
      const [a, b] = [...ptrs.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      cam.dist = clamp(g.dist0 * g.d0 / d, 4, (L.length + 10) * 1.3);
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      cam.fz = clamp(g.fz0 + flyBy(mx - g.mx0, my - g.my0, null, g.dist0), zMin(), zMax());
    } else {
      const dx = ev.offsetX - g.x0, dy = ev.offsetY - g.y0;
      g.moved = Math.max(g.moved, Math.abs(dx) + Math.abs(dy));
      if (g.mode === 'orbit') {
        cam.yaw = g.yaw0 - dx * 0.0065;
        cam.pitch = clamp(g.pitch0 + dy * 0.0065, -1.45, 1.45);
      } else {
        cam.fz = clamp(g.fz0 + flyBy(dx, dy, g.g, cam.dist), zMin(), zMax());
      }
    }
    if (hover >= 0) setHover(-1);
    request();
  });
  const end = (ev) => {
    if (!ptrs.has(ev.pointerId)) return;
    ptrs.delete(ev.pointerId);
    const g = gesture;
    if (ptrs.size === 1 && g?.mode === 'pinch') {
      // 双指松开一指：从剩下那指接着转，免得跳
      const [[, q]] = [...ptrs];
      gesture = { mode: 'orbit', type: g.type, x0: q.x, y0: q.y, yaw0: cam.yaw, pitch0: cam.pitch, fz0: cam.fz, moved: 99 };
      return;
    }
    if (ptrs.size) return;
    gesture = null;
    canvas.classList.remove('dragging');
    if (ev.type === 'pointerup' && g && g.mode !== 'pinch' && g.moved < 6) tapAt(ev.offsetX, ev.offsetY, g.type);
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('pointerleave', (ev) => {
    if (ev.pointerType === 'mouse' && !ptrs.size) setHover(-1);
  });
  canvas.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    stopTween();
    const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? H : 1;
    const dy = ev.deltaY * unit;
    if (ev.shiftKey || (ev.deltaX && Math.abs(ev.deltaX) > Math.abs(ev.deltaY))) {
      const d = ev.shiftKey ? dy || ev.deltaX * unit : ev.deltaX * unit;
      cam.fz = clamp(cam.fz + d * cam.dist / H * 0.6, zMin(), zMax());
    } else {
      cam.dist = clamp(cam.dist * Math.exp(dy * (ev.ctrlKey ? 0.01 : 0.0015)), 4, (L.length + 10) * 1.3);
    }
    if (hover >= 0) setHover(-1);
    request();
  }, { passive: false });
  canvas.addEventListener('dblclick', (ev) => ev.preventDefault());

  // 右边的时间轨道：拖动或点击沿时间移动
  const railTrack = rail;
  railTrack.addEventListener('pointerdown', (ev) => {
    railTrack.setPointerCapture(ev.pointerId);
    const toZ = (e) => {
      const r = rail.querySelector('.t3-rail-track').getBoundingClientRect();
      return zMin() + clamp((e.clientY - r.top) / r.height, 0, 1) * (zMax() - zMin());
    };
    flyTo(toZ(ev));
    const move = (e) => {
      stopTween();
      cam.fz = toZ(e);
      request();
    };
    const up = () => {
      railTrack.removeEventListener('pointermove', move);
      railTrack.removeEventListener('pointerup', up);
      railTrack.removeEventListener('pointercancel', up);
    };
    railTrack.addEventListener('pointermove', move);
    railTrack.addEventListener('pointerup', up);
    railTrack.addEventListener('pointercancel', up);
  });
}

function tapAt(x, y, type) {
  const k = pick(x, y, type === 'mouse' ? 6 : 16);
  if (k < 0) {
    if (pinned >= 0) {
      unpin();
      writeUrl();
      request();
    }
    return;
  }
  if (type === 'mouse' || k === pinned) {
    open(k);
    return;
  }
  pinned = k;
  showTip(k);
  writeUrl({ e: P[k].id });
  request();
}

function onKey(ev) {
  if (!root || !L || ev.target.matches?.('input, textarea, select') || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const step = Math.max(1.5, cam.dist * 0.18);
  const keys = {
    ArrowUp: () => flyTo(cam.fz + step), ArrowDown: () => flyTo(cam.fz - step),
    PageUp: () => flyTo(cam.fz + step * 4), PageDown: () => flyTo(cam.fz - step * 4),
    w: () => flyTo(cam.fz + step), s: () => flyTo(cam.fz - step),
    ArrowLeft: () => flyTo(cam.fz, { yaw: cam.yaw + 0.2 }), ArrowRight: () => flyTo(cam.fz, { yaw: cam.yaw - 0.2 }),
    '+': () => flyTo(cam.fz, { dist: clamp(cam.dist / 1.25, 4, (L.length + 10) * 1.3) }),
    '=': () => flyTo(cam.fz, { dist: clamp(cam.dist / 1.25, 4, (L.length + 10) * 1.3) }),
    '-': () => flyTo(cam.fz, { dist: clamp(cam.dist * 1.25, 4, (L.length + 10) * 1.3) }),
    Home: () => flyTo(zMin() + 3), End: () => flyTo(zMax() - 3),
    Escape: () => { if (pinned >= 0) { unpin(); writeUrl(); request(); } },
    Enter: () => { if (pinned >= 0) open(pinned); },
  };
  const fn = keys[ev.key];
  if (!fn) return;
  ev.preventDefault();
  fn();
}
