// 关系图：只放人物、地区、势力（可选事件），不放章节和分集。
// 人物之间的连线是共同出场的集数；默认只显示出场较多的人物，每人只连最常同场的几位。
// 从人物或地区页点「在关系图中查看」会进入以它为中心的模式，显示它的直接关联。
import { D } from './data.js';
import { esc, href, KIND_LABEL } from './util.js';

const TOP_PARTNERS = 6;   // 总览模式下每人保留的同场连线数
let cy = null, info, focus = null;
const opts = { powers: true, events: false, doctor: false, minEp: 30 };

const epCount = (c) => c.appear.reduce((n, [, sids]) => n + sids.length, 0);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

export function mount(el, r) {
  el.innerHTML = `
    <aside class="side panel graph-side">
      <div class="graph-mode"></div>
      <div class="range-row">出场 ≥ <input type="range" class="g-min" min="3" max="120" step="1"><b class="g-min-v"></b> 集</div>
      <label class="toggle"><input type="checkbox" class="g-powers">地区与势力</label>
      <label class="toggle"><input type="checkbox" class="g-events">年表事件</label>
      <label class="toggle"><input type="checkbox" class="g-doctor">博士</label>
      <button class="btn g-relayout">重新布局</button>
      <div class="legend">
        <span><i style="background:var(--c-operator)"></i>干员</span><span><i style="background:var(--c-npc)"></i>NPC</span>
        <span><i style="background:var(--c-region)"></i>地区</span><span><i style="background:var(--c-faction)"></i>势力</span>
        <span><i style="background:var(--lore)"></i>事件</span>
      </div>
      <p class="muted small">连线越粗，共同出场的集数越多。点击节点查看详情，双击以它为中心。</p>
    </aside>
    <section class="graph-main panel"><div id="cy"></div><div class="graph-info panel" hidden></div></section>`;
  info = el.querySelector('.graph-info');
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
  el.querySelector('.g-relayout').addEventListener('click', () => runLayout());
  update(r);
}

export function unmount() {
  cy?.destroy();
  cy = null;
}

export function update(r) {
  focus = r.parts[0] ?? null;
  document.querySelector('.graph-mode').innerHTML = focus
    ? `<div>以 <b>${esc(label(focus))}</b> 为中心</div><a class="btn" href="#/graph">返回总览</a>`
    : '<div class="muted small">总览：出场较多的人物及其所属</div>';
  document.querySelector('.range-row').hidden = !!focus;
  build();
}

function label(id) {
  const [type, key] = splitId(id);
  return type === 'power' ? D.powers[key]?.name ?? key : type === 'event' ? D.eventById[key]?.when ?? key : key;
}
function splitId(id) { const i = id.indexOf(':'); return [id.slice(0, i), id.slice(i + 1)]; }

function build() {
  const nodes = new Map(), edges = new Map();
  const addChar = (n) => {
    const c = D.chars[n];
    if (!c || (c.kind === 'doctor' && !opts.doctor)) return false;
    nodes.set(`char:${n}`, { id: `char:${n}`, label: n, type: c.kind, size: epCount(c) });
    return true;
  };
  const addPower = (p) => {
    if (!D.powers[p]) return false;
    nodes.set(`power:${p}`, { id: `power:${p}`, label: D.powers[p].name, type: D.powers[p].kind, size: 40 });
    return true;
  };
  const addEvent = (id) => {
    const e = D.eventById[id];
    nodes.set(`event:${id}`, { id: `event:${id}`, label: e.lines[0].slice(0, 14) + (e.lines[0].length > 14 ? '…' : ''), type: 'event', size: 6 });
  };
  const link = (a, b, w, kind) => {
    if (!nodes.has(a) || !nodes.has(b) || a === b) return;
    const id = a < b ? `${a}|${b}` : `${b}|${a}`;
    if (!edges.has(id)) edges.set(id, { id, source: a, target: b, w, kind });
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
    if (opts.powers) {
      for (const id of [...nodes.keys()]) D.chars[id.slice(5)].powers.forEach(addPower);
    }
    if (opts.events) {
      D.events.filter((e) => e.chars.filter((n) => nodes.has(`char:${n}`)).length >= 2).forEach((e) => addEvent(e.id));
    }
  }

  // 连线
  for (const [id, nd] of nodes) {
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

  const color = { operator: css('--c-operator'), npc: css('--c-npc'), doctor: css('--c-doctor'),
    region: css('--c-region'), faction: css('--c-faction'), event: css('--lore') };
  const elements = [
    ...[...nodes.values()].map((n) => ({ data: { ...n, color: color[n.type], d: Math.max(10, Math.min(46, 6 + Math.sqrt(n.size) * 3.2)) } })),
    ...[...edges.values()].map((e) => ({ data: { ...e, width: Math.min(7, 0.6 + Math.log2(1 + e.w) * 0.9) } })),
  ];
  cy?.destroy();
  cy = cytoscape({
    container: document.getElementById('cy'),
    elements,
    wheelSensitivity: 0.25,
    style: [
      { selector: 'node', style: {
        'background-color': 'data(color)', width: 'data(d)', height: 'data(d)', label: 'data(label)',
        'font-size': 11, color: css('--text'), 'text-valign': 'bottom', 'text-margin-y': 3,
        'text-outline-color': css('--panel'), 'text-outline-width': 2, 'min-zoomed-font-size': 7 } },
      { selector: 'node[type = "region"], node[type = "faction"]', style: { shape: 'round-rectangle', 'font-weight': 600 } },
      { selector: 'node[type = "event"]', style: { shape: 'diamond', 'font-size': 9 } },
      { selector: 'edge', style: { width: 'data(width)', 'line-color': css('--line'), 'curve-style': 'haystack', opacity: 0.9 } },
      { selector: 'edge[kind = "member"], edge[kind = "parent"]', style: { 'line-style': 'dashed', 'line-color': css('--c-faction'), opacity: 0.45 } },
      { selector: '.faded', style: { opacity: 0.12 } },
      { selector: 'node.hl', style: { 'border-width': 3, 'border-color': css('--accent') } },
      { selector: 'edge.hl', style: { 'line-color': css('--accent'), opacity: 1 } },
    ],
    layout: { name: 'preset' },
  });
  runLayout();
  cy.on('tap', 'node', (e) => showInfo(e.target));
  cy.on('dbltap', 'node', (e) => { location.hash = `#/graph/${e.target.id()}`; });
  cy.on('tap', (e) => { if (e.target === cy) clearHighlight(); });
  if (focus && cy.getElementById(focus).nonempty()) showInfo(cy.getElementById(focus));
  else info.hidden = true;
}

function runLayout() {
  cy?.layout({ name: 'cose', animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 90,
    nodeOverlap: 12, gravity: 0.6, numIter: 1500, randomize: true }).run();
}

function clearHighlight() {
  cy.elements().removeClass('faded hl');
  info.hidden = true;
}

function showInfo(node) {
  cy.elements().removeClass('faded hl');
  const hood = node.closedNeighborhood();
  cy.elements().not(hood).addClass('faded');
  hood.addClass('hl');
  const [type, key] = splitId(node.id());
  const neighbors = node.neighborhood('node').map((n) => n.data('label'));
  let body = '';
  if (type === 'char') {
    const c = D.chars[key];
    body = `<div class="muted small">${KIND_LABEL[c.kind]} · 出场 ${epCount(c)} 集 · 事件 ${c.events.length}</div>
      <div class="actions"><a class="btn" href="${href.char(key)}">人物页</a><a class="btn" href="#/graph/${esc(node.id())}">以此为中心</a></div>`;
  } else if (type === 'power') {
    const p = D.powers[key];
    body = `<div class="muted small">${p.kind === 'region' ? '地区' : '势力'} · 成员 ${p.members.length} · 事件 ${p.events.length}</div>
      <div class="actions"><a class="btn" href="${href.power(key)}">详情页</a><a class="btn" href="#/graph/${esc(node.id())}">以此为中心</a></div>`;
  } else {
    const e = D.eventById[key];
    body = `<div class="muted small">${esc(e.when)}</div><p>${esc(e.lines.join(' '))}</p>
      <div class="actions"><a class="btn" href="${href.event(key)}">在时间轴中查看</a></div>`;
  }
  info.hidden = false;
  info.innerHTML = `<h3>${esc(node.data('label'))}</h3>${body}
    <h4>直接关联（${neighbors.length}）</h4><div class="small">${neighbors.map(esc).join('、')}</div>`;
}
