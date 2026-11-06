// 关系图：只放人物、地区、势力（可选事件），不放章节和分集。
// 用 force-graph 跑持续的力导向模拟：拖动节点时相连的节点会被连线拉着走，松手后整张图重新找平衡；
// 改筛选时已有节点留在原处，新节点从相连的节点旁边出现。人物之间的连线是共同出场的集数，
// 集数越多，连线越粗、拉得越近。从人物或地区页点「在关系图中查看」会进入以它为中心的模式。
import { D } from './data.js';
import { esc, href, KIND_LABEL } from './util.js';

const TOP_PARTNERS = 6;   // 总览模式下每人保留的同场连线数
const FADED = 0.1;        // 高亮时其余节点的不透明度
const opts = { powers: true, events: false, doctor: false, minEp: 30 };
// 四个力度参数，与 Obsidian 图谱设置里的四个滑块对应
const forces = { center: 0.05, repel: 220, link: 1, distance: 65 };
const SLIDERS = [
  ['center', '中心力', 0, 0.3, 0.01],
  ['repel', '斥力', 20, 600, 10],
  ['link', '连线力', 0, 2, 0.05],
  ['distance', '连线距离', 20, 200, 5],
];

let fg = null, info, box, ro = null, focus = null;
let cache = new Map();   // 节点 id → 节点对象；跨次构建保留，位置不丢
let adj = new Map();     // 节点 id → 相邻节点 id 的集合
let hover = null, selected = null, lastClick = { id: null, t: 0 };
let palette = {}, fadeTimer = null, fitTimer = null, fitPending = false;

const epCount = (c) => c.appear.reduce((n, [, sids]) => n + sids.length, 0);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const nid = (x) => (typeof x === 'object' ? x.id : x);
const clamp = (x) => Math.max(0, Math.min(1, x));

export function mount(el, r) {
  el.innerHTML = `
    <aside class="side panel graph-side">
      <div class="graph-mode"></div>
      <div class="range-row g-min-row">出场 ≥ <input type="range" class="g-min" min="3" max="120" step="1"><b class="g-min-v"></b> 集</div>
      <label class="toggle"><input type="checkbox" class="g-powers">地区与势力</label>
      <label class="toggle"><input type="checkbox" class="g-events">事件</label>
      <label class="toggle"><input type="checkbox" class="g-doctor">博士</label>
      <details class="g-forces"><summary>力度</summary>
        ${SLIDERS.map(([k, label, min, max, step]) => `
          <div class="range-row"><span class="g-f-label">${label}</span>
            <input type="range" data-force="${k}" min="${min}" max="${max}" step="${step}" value="${forces[k]}">
            <b class="g-f-v" data-force-v="${k}">${forces[k]}</b></div>`).join('')}
      </details>
      <div class="actions"><button class="btn g-relayout">重新布局</button><button class="btn g-fit">适应窗口</button></div>
      <div class="legend">
        <span><i style="background:var(--c-operator)"></i>干员</span><span><i style="background:var(--c-npc)"></i>NPC</span>
        <span><i style="background:var(--c-region)"></i>地区</span><span><i style="background:var(--c-faction)"></i>势力</span>
        <span><i style="background:var(--lore)"></i>事件</span>
      </div>
      <p class="muted small">连线越粗，共同出场的集数越多。拖动节点，相连的人物会跟着移动。悬停或点击节点只看它的关联，双击以它为中心。</p>
    </aside>
    <section class="graph-main panel"><div id="fg"></div><div class="graph-info panel" hidden></div></section>`;
  info = el.querySelector('.graph-info');
  box = el.querySelector('#fg');
  const min = el.querySelector('.g-min');
  min.value = opts.minEp;
  el.querySelector('.g-min-v').textContent = opts.minEp;
  min.addEventListener('input', () => { el.querySelector('.g-min-v').textContent = min.value; });
  min.addEventListener('change', () => { opts.minEp = Number(min.value); build(); });
  for (const k of ['powers', 'events', 'doctor']) {
    const cb = el.querySelector(`.g-${k}`);
    cb.checked = opts[k];
    cb.addEventListener('change', () => { opts[k] = cb.checked; build(); });
  }
  el.querySelectorAll('[data-force]').forEach((s) => s.addEventListener('input', () => {
    forces[s.dataset.force] = Number(s.value);
    el.querySelector(`[data-force-v="${s.dataset.force}"]`).textContent = s.value;
    applyForces();
    fg.d3ReheatSimulation();
  }));
  el.querySelector('.g-relayout').addEventListener('click', relayout);
  el.querySelector('.g-fit').addEventListener('click', () => fg.zoomToFit(600, 50));
  initGraph();
  focus = undefined;  // 让第一次 update 也自动适应窗口
  update(r);
}

export function unmount() {
  clearTimeout(fadeTimer);
  clearTimeout(fitTimer);
  ro?.disconnect();
  fg?._destructor();
  fg = ro = null;
  hover = selected = null;
}

export function update(r) {
  const next = r.parts[0] ?? null;
  const changed = next !== focus;
  focus = next;
  document.querySelector('.graph-mode').innerHTML = focus
    ? `<div>以 <b>${esc(label(focus))}</b> 为中心</div><a class="btn" href="#/graph">返回总览</a>`
    : '<div class="muted small">总览：出场较多的人物及其所属</div>';
  document.querySelector('.g-min-row').hidden = !!focus;
  if (changed) cache = new Map();  // 换了中心就重新展开，不沿用上一张图的位置
  build();
}

function label(id) {
  const [type, key] = splitId(id);
  return type === 'power' ? D.powers[key]?.name ?? key : type === 'event' ? D.eventById[key]?.when ?? key : key;
}
function splitId(id) { const i = id.indexOf(':'); return [id.slice(0, i), id.slice(i + 1)]; }

// ---------------------------------------------------------------- 图数据

function collect() {
  const nodes = new Map(), links = new Map();
  const addChar = (n) => {
    const c = D.chars[n];
    if (!c || (c.kind === 'doctor' && !opts.doctor)) return;
    nodes.set(`char:${n}`, { id: `char:${n}`, label: n, type: c.kind, size: epCount(c) });
  };
  const addPower = (p) => {
    if (D.powers[p]) nodes.set(`power:${p}`, { id: `power:${p}`, label: D.powers[p].name, type: D.powers[p].kind, size: 40 });
  };
  const addEvent = (id) => {
    const e = D.eventById[id];
    nodes.set(`event:${id}`, { id: `event:${id}`, label: e.lines[0].slice(0, 14) + (e.lines[0].length > 14 ? '…' : ''), type: 'event', size: 6 });
  };
  const link = (a, b, w, kind) => {
    if (!nodes.has(a) || !nodes.has(b) || a === b) return;
    const id = a < b ? `${a}|${b}` : `${b}|${a}`;
    if (!links.has(id)) links.set(id, { id, source: a, target: b, w, kind });
  };

  if (focus) {
    const [type, key] = splitId(focus);
    if (type === 'char' && D.chars[key]) {
      const c = D.chars[key];
      nodes.set(focus, { id: focus, label: key, type: c.kind, size: epCount(c) });
      c.co.forEach(([n]) => addChar(n));
      if (opts.powers) c.powers.forEach(addPower);
      if (opts.events) c.events.forEach(addEvent);
    } else if (type === 'power' && D.powers[key]) {
      const p = D.powers[key];
      addPower(key);
      p.members.slice(0, 40).forEach(addChar);
      [p.parent, ...p.children].filter(Boolean).forEach(addPower);
      if (opts.events) p.events.forEach(addEvent);
    }
  } else {
    Object.entries(D.chars).filter(([, c]) => epCount(c) >= opts.minEp).forEach(([n]) => addChar(n));
    if (opts.powers) for (const id of [...nodes.keys()]) D.chars[id.slice(5)].powers.forEach(addPower);
    if (opts.events) {
      D.events.filter((e) => e.chars.filter((n) => nodes.has(`char:${n}`)).length >= 2).forEach((e) => addEvent(e.id));
    }
  }

  for (const [id] of nodes) {
    const [type, key] = splitId(id);
    if (type === 'char') {
      const c = D.chars[key];
      const partners = focus ? c.co : c.co.filter(([n]) => nodes.has(`char:${n}`)).slice(0, TOP_PARTNERS);
      partners.forEach(([n, k]) => link(id, `char:${n}`, k, 'co'));
      c.powers.forEach((p) => link(id, `power:${p}`, 3, 'member'));
    } else if (type === 'power') {
      const p = D.powers[key];
      if (p.parent) link(id, `power:${p.parent}`, 3, 'parent');
    } else if (type === 'event') {
      const e = D.eventById[key];
      e.chars.forEach((n) => link(id, `char:${n}`, 1, 'event'));
      e.powers.forEach((p) => link(id, `power:${p}`, 1, 'event'));
    }
  }
  return { nodes, links };
}

function build() {
  if (!fg) return;
  palette = {
    operator: css('--c-operator'), npc: css('--c-npc'), doctor: css('--c-doctor'),
    region: css('--c-region'), faction: css('--c-faction'), event: css('--lore'),
    text: css('--text'), panel: css('--panel'), muted: css('--muted'), accent: css('--accent'),
  };
  const { nodes: specs, links: linkSpecs } = collect();

  adj = new Map([...specs.keys()].map((id) => [id, new Set()]));
  for (const l of linkSpecs.values()) {
    adj.get(l.source).add(l.target);
    adj.get(l.target).add(l.source);
  }
  const maxW = Math.max(1, ...[...linkSpecs.values()].filter((l) => l.kind === 'co').map((l) => l.w));
  const links = [...linkSpecs.values()].map((l) => ({
    ...l, norm: l.kind === 'co' ? Math.log1p(l.w) / Math.log1p(maxW) : 0.3,
  }));

  // 沿用已有节点（保留位置和速度）；新节点放在已有邻居旁边，没有邻居就随机撒在中心附近
  const spread = 30 * Math.sqrt(specs.size);
  const current = new Set(fg.graphData().nodes);
  const nodes = [];
  for (const [id, spec] of specs) {
    let n = cache.get(id);
    const fresh = !n || !current.has(n);
    if (!n) cache.set(id, n = { id });
    Object.assign(n, spec, {
      color: palette[spec.type] ?? palette.muted,
      r: Math.max(4, Math.min(22, 2.5 + Math.sqrt(spec.size) * 1.7)),
    });
    n.fade ??= 1;
    if (fresh) {
      const nb = [...adj.get(id)].map((x) => cache.get(x)).find((x) => x && current.has(x));
      const a = Math.random() * Math.PI * 2, d = nb ? 15 + Math.random() * 20 : Math.sqrt(Math.random()) * spread;
      n.x = (nb?.x ?? 0) + Math.cos(a) * d;
      n.y = (nb?.y ?? 0) + Math.sin(a) * d;
      n.vx = n.vy = 0;
    }
    nodes.push(n);
  }

  hover = null;
  selected = focus && specs.has(focus) ? cache.get(focus) : null;
  // 换数据时 force-graph 会把模拟重新激活到满能量；已有节点占多数时加大阻尼，只做小幅调整，避免整张图炸开
  const kept = nodes.filter((n) => current.has(n)).length;
  calm(kept > nodes.length / 2);
  fg.graphData({ nodes, links });
  applyForces();
  setFades();
  if (selected) showInfo(selected);
  else info.hidden = true;
  fitSoon();
}

function calm(on) {
  fg.d3VelocityDecay(on ? 0.6 : 0.35).d3AlphaDecay(on ? 0.05 : 0.02);
}

// ---------------------------------------------------------------- 力导向模拟

// 向心力：把每个节点按离中心的距离往回拉（d3 的 forceCenter 只平移整体，不会把散开的节点拉回来）
function gravity() {
  let nodes = [];
  const force = (alpha) => {
    const k = forces.center * alpha;
    for (const n of nodes) { n.vx -= n.x * k; n.vy -= n.y * k; }
  };
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

function applyForces() {
  const deg = (x) => adj.get(nid(x))?.size || 1;
  fg.d3Force('charge').strength(-forces.repel).distanceMax(800);
  fg.d3Force('link')
    .distance((l) => forces.distance * (l.kind === 'co' ? 1.3 - 0.6 * l.norm : 1.1))
    .strength((l) => forces.link * (l.kind === 'co' ? 0.15 + 0.55 * l.norm : 0.3) / Math.sqrt(Math.min(deg(l.source), deg(l.target))));
}

function initGraph() {
  fg = ForceGraph()(box)
    .backgroundColor('rgba(0,0,0,0)')
    .nodeId('id')
    .nodeLabel(() => '')
    .nodeCanvasObject(drawNode)
    .nodePointerAreaPaint((n, color, ctx) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r + 2, 0, Math.PI * 2);
      ctx.fill();
    })
    .linkColor(linkColor)
    .linkWidth((l) => (l.kind === 'co' ? 0.4 + l.norm * 2.6 : 0.7) + (isHot(l) ? 0.6 : 0))
    .linkLineDash((l) => (l.kind === 'member' || l.kind === 'parent' ? [3, 3] : null))
    .d3AlphaDecay(0.02)
    .d3VelocityDecay(0.35)
    .cooldownTime(20000)
    .onNodeHover((n) => {
      hover = n;
      box.style.cursor = n ? 'pointer' : '';
      setFades();
    })
    .onNodeClick(onClick)
    .onEngineStop(() => {
      if (fitPending) fg.zoomToFit(700, 50);
      fitPending = false;
      calm(false);  // 恢复正常阻尼，之后拖动节点时手感照旧
    })
    .onBackgroundClick(() => {
      selected = null;
      info.hidden = true;
      setFades();
    });
  fg.d3Force('center', null);
  fg.d3Force('gravity', gravity());
  const resize = () => fg?.width(box.clientWidth).height(box.clientHeight);
  ro = new ResizeObserver(resize);
  ro.observe(box);
  resize();
}

function relayout() {
  const nodes = fg.graphData().nodes;
  const spread = 30 * Math.sqrt(nodes.length);
  for (const n of nodes) {
    const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * spread;
    Object.assign(n, { x: Math.cos(a) * d, y: Math.sin(a) * d, vx: 0, vy: 0 });
  }
  fg.d3ReheatSimulation();
  fitSoon();
}

// 布局刚展开时先粗略适应一次窗口，模拟停稳后再适应一次
function fitSoon() {
  fitPending = true;
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => fg?.zoomToFit(700, 50), 1200);
}

// ---------------------------------------------------------------- 高亮与绘制

const active = () => hover ?? selected;
const isHot = (l) => { const a = active(); return !!a && (l.source === a || l.target === a); };

// 计算每个节点的目标不透明度；绘制时逐帧向目标靠拢，形成渐隐渐显
function setFades() {
  const a = active();
  const near = a ? adj.get(a.id) : null;
  for (const n of fg.graphData().nodes) {
    n.target = !a || n === a || near?.has(n.id) ? 1 : FADED;
    n.emph = !!a && n.target === 1;
  }
  fg.autoPauseRedraw(false);
  clearTimeout(fadeTimer);
  fadeTimer = setTimeout(() => fg?.autoPauseRedraw(true), 700);
}

function drawNode(n, ctx, scale) {
  n.fade += ((n.target ?? 1) - n.fade) * 0.2;
  const r = n.r;
  ctx.globalAlpha = n.fade;
  ctx.fillStyle = n.color;
  ctx.beginPath();
  if (n.type === 'region' || n.type === 'faction') ctx.roundRect(n.x - r, n.y - r, r * 2, r * 2, r * 0.35);
  else if (n.type === 'event') {
    ctx.moveTo(n.x, n.y - r); ctx.lineTo(n.x + r, n.y); ctx.lineTo(n.x, n.y + r); ctx.lineTo(n.x - r, n.y); ctx.closePath();
  } else ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
  ctx.fill();
  if (n === active() || (n === selected && n.emph)) {
    ctx.lineWidth = 2.5 / scale;
    ctx.strokeStyle = palette.accent;
    ctx.stroke();
  }
  // 标签：节点在屏幕上半径 7px 时开始浮现，13px 时完全显示；高亮的节点始终显示
  const show = Math.max(clamp((scale * r - 7) / 6), n.emph ? 1 : 0) * n.fade;
  if (show > 0.03) {
    const fs = 12 / scale;
    ctx.globalAlpha = show;
    ctx.font = `${n.type === 'region' || n.type === 'faction' ? 600 : 400} ${fs}px system-ui, "Microsoft YaHei", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.lineWidth = 3 / scale;
    ctx.strokeStyle = palette.panel;
    ctx.strokeText(n.label, n.x, n.y + r + 2 / scale);
    ctx.fillStyle = palette.text;
    ctx.fillText(n.label, n.x, n.y + r + 2 / scale);
  }
  ctx.globalAlpha = 1;
}

function linkColor(l) {
  const fade = Math.min(l.source.fade ?? 1, l.target.fade ?? 1);
  if (isHot(l)) return rgba(palette.accent, 0.85);
  return l.kind === 'co' ? rgba(palette.muted, 0.38 * fade) : rgba(palette.faction, 0.35 * fade);
}

// 连线每帧都要取颜色，几千条线反复拼字符串很慢；不透明度取到两位小数后缓存
const rgbaCache = new Map();
function rgba(hex, a) {
  const key = `${hex}|${Math.round(a * 100)}`;
  let v = rgbaCache.get(key);
  if (!v) {
    const h = hex.replace('#', '');
    const x = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16));
    rgbaCache.set(key, v = `rgba(${r},${g},${b},${Math.round(a * 100) / 100})`);
  }
  return v;
}

// force-graph 没有双击事件：同一节点 350ms 内点两次算双击
function onClick(n) {
  const now = performance.now();
  if (lastClick.id === n.id && now - lastClick.t < 350) {
    location.hash = `#/graph/${n.id}`;
    return;
  }
  lastClick = { id: n.id, t: now };
  selected = n;
  showInfo(n);
  setFades();
}

function showInfo(node) {
  const [type, key] = splitId(node.id);
  const neighbors = [...(adj.get(node.id) ?? [])].map((id) => cache.get(id)?.label ?? id);
  let body = '';
  if (type === 'char') {
    const c = D.chars[key];
    body = `<div class="muted small">${KIND_LABEL[c.kind]} · 出场 ${epCount(c)} 集 · 事件 ${c.events.length}</div>
      <div class="actions"><a class="btn" href="${href.char(key)}">人物页</a><a class="btn" href="#/graph/${esc(node.id)}">以此为中心</a></div>`;
  } else if (type === 'power') {
    const p = D.powers[key];
    body = `<div class="muted small">${p.kind === 'region' ? '地区' : '势力'} · 成员 ${p.members.length} · 事件 ${p.events.length}</div>
      <div class="actions"><a class="btn" href="${href.power(key)}">详情页</a><a class="btn" href="#/graph/${esc(node.id)}">以此为中心</a></div>`;
  } else {
    const e = D.eventById[key];
    body = `<div class="muted small">${esc(e.when)}</div><p>${esc(e.lines.join(' '))}</p>
      <div class="actions"><a class="btn" href="${href.event(key)}">在时间轴中查看</a></div>`;
  }
  info.hidden = false;
  info.innerHTML = `<h3>${esc(node.label)}</h3>${body}
    <h4>直接关联（${neighbors.length}）</h4><div class="small">${neighbors.map(esc).join('、')}</div>`;
}
