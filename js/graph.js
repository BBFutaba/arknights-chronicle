// 关系图：做成侦探办案用的线索板。人物是钉在板上的照片和卡片，同场的人之间拉红线；
// 地区是剪下来的报纸，势力是撕下来的海报，事件是便签。泰拉编和塔卫二编是两块板，不混在一起。
// 只放人物、地区、势力（可选事件），不放章节和分集。
// 用 force-graph 跑持续的力导向模拟：拖动卡片时相连的卡片会被线拉着走，松手后整块板重新找平衡；
// 改筛选时已有卡片留在原处，新卡片从相连的卡片旁边出现。人物之间的红线是共同出场的集数，
// 集数越多，线越粗、拉得越近。从人物或地区页点「在关系图中查看」会进入以它为中心的模式。
//
// 画法：force-graph 只管模拟、缩放、拖动和点选，连线它不画（linkVisibility false），其余都自己画。
//   每帧开始（onRenderFramePre）：铺板面，算出可见范围（范围外的不画），拉平常的线。
//   force-graph 逐个画节点（nodeCanvasObject）：人物卡片和便签，压在线上，照片不被线盖住。
//   每帧最后（onRenderFramePost）：高亮的线 → 拿起来的那张卡片 → 报纸和海报 → 名字条 → 图钉。
//   悬停或选中时它牵出的线压在别的卡片上面，名字条和图钉又压在线上，名字不会被线挡住。
//   线按颜色、粗细、深浅分批，一批一次描边。
import { D, BIANS } from './data.js';
import { esc, href, charName, KIND_LABEL, imgSrc } from './util.js';

const TOP_PARTNERS = 6;   // 总览模式下每人保留的同场连线数
const FADED = 0.12;       // 高亮时其余节点的不透明度
const opts = { powers: true, events: false, doctor: false, minEp: 30 };
// 四个力度参数，与 Obsidian 图谱设置里的四个滑块对应
const forces = { center: 0.05, repel: 220, link: 1, distance: 65 };
const SLIDERS = [
  ['center', '中心力', 0, 0.3, 0.01],
  ['repel', '斥力', 20, 600, 10],
  ['link', '连线力', 0, 2, 0.05],
  ['distance', '连线距离', 20, 200, 5],
];

let fg = null, info, box, ro = null, focus = null, bian = BIANS[0];
let cache = new Map();   // 节点 id → 节点对象；跨次构建保留，位置不丢
let adj = new Map();     // 节点 id → 相邻节点 id 的集合
let hover = null, selected = null, lastClick = { id: null, t: 0 };
let hits = null;         // 「在板上找人」命中的节点 id；没在找时是 null
let palette = {}, fitTimer = null, fitPending = false, wakeUntil = 0, wakeTimer = null;
let view = { x0: -Infinity, y0: -Infinity, x1: Infinity, y1: Infinity };

const epCount = (c) => c.appear.reduce((n, [, sids]) => n + sids.length, 0);
// 关系图一次只画一编，不用再标「终末地」
const personLabel = (name) => charName(name);
// 颜色从关系图自己的平面上读
const css = (v) => getComputedStyle(document.querySelector('.graph-main') ?? document.documentElement).getPropertyValue(v).trim();
const nid = (x) => (typeof x === 'object' ? x.id : x);
const clamp = (x, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
const isPower = (type) => type === 'region' || type === 'faction';

// 每张卡片歪多少、名字条歪多少、线垂多少，都由 id 定下来，每次打开都一样
function rnd(id, salt) {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  h = Math.imul(h ^ (h >>> 15), 2246822507);
  return ((h ^ (h >>> 13)) >>> 0) / 4294967296;
}

export function mount(el, r) {
  el.innerHTML = `
    <aside class="side panel graph-side">
      <label>编 <select class="g-bian">${BIANS.map((b) => `<option>${esc(b)}</option>`).join('')}</select></label>
      <div class="graph-mode"></div>
      <div class="g-find">
        <input type="search" class="g-q" placeholder="在板上找人" autocomplete="off" aria-label="在关系图上找人">
        <div class="g-hits"></div>
      </div>
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
      <div class="g-legend">
        <span class="gl gl-operator"><i></i>干员</span><span class="gl gl-npc"><i></i>NPC</span>
        <span class="gl gl-doctor"><i></i>博士</span><span class="gl gl-region">地区</span>
        <span class="gl gl-faction">势力</span><span class="gl gl-event"><i></i>事件</span>
        <span class="gl gl-yarn"><i></i>同场</span><span class="gl gl-thread"><i></i>所属</span>
      </div>
      <p class="muted small">红线越粗，两人共同出场的集数越多。拖动卡片，相连的人会被线拉着走。悬停或点击只看它牵出的线，双击以它为中心。</p>
    </aside>
    <section class="graph-main panel">
      <div id="fg"></div>
      <div class="g-board-title" aria-hidden="true"><div class="g-bt-paper"><b></b><small></small></div></div>
      <div class="graph-info panel" hidden></div>
    </section>`;
  info = el.querySelector('.graph-info');
  box = el.querySelector('#fg');
  el.querySelector('.g-bian').addEventListener('change', (e) => {
    location.hash = `#/graph?${new URLSearchParams({ bian: e.target.value })}`;
  });
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
  const q = el.querySelector('.g-q');
  q.addEventListener('input', () => find(q.value));
  q.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') el.querySelector('.g-hits [data-node], .g-hits a')?.click();
    if (e.key === 'Escape') { q.value = ''; find(''); }
  });
  el.querySelector('.g-hits').addEventListener('click', (e) => {
    const b = e.target.closest('[data-node]');
    const n = b && cache.get(b.dataset.node);
    if (n) pick(n, true);
  });
  initGraph();
  focus = undefined;  // 让第一次 update 也自动适应窗口
  update(r);
}

export function unmount() {
  clearTimeout(fitTimer);
  clearTimeout(wakeTimer);
  ro?.disconnect();
  fg?._destructor();
  fg = ro = null;
  hover = selected = hits = null;
}

export function update(r) {
  const next = r.parts[0] ?? null;
  const requested = r.params.get('bian');
  const inferred = next?.startsWith('char:终末地·') ? BIANS[1] : BIANS[0];
  const nextBian = next?.startsWith('char:') ? inferred : BIANS.includes(requested) ? requested : inferred;
  const changed = next !== focus || bian !== nextBian;
  bian = nextBian;
  document.querySelector('.g-bian').value = bian;
  focus = next;
  document.querySelector('.graph-mode').innerHTML = focus
    ? `<div>以 <b>${esc(label(focus))}</b> 为中心</div><a class="btn" href="#/graph?${new URLSearchParams({ bian })}">返回总览</a>`
    : '<div class="muted small">总览：出场较多的人物及其所属</div>';
  document.querySelector('.g-min-row').hidden = !!focus;
  if (changed) cache = new Map();  // 换了中心就重新展开，不沿用上一张图的位置
  build();
}

function label(id) {
  const [type, key] = splitId(id);
  return type === 'power' ? D.powers[key]?.name ?? key : type === 'event' ? D.eventById[key]?.when ?? key : personLabel(key);
}
function splitId(id) { const i = id.indexOf(':'); return [id.slice(0, i), id.slice(i + 1)]; }

// ---------------------------------------------------------------- 图数据

export function collect() {
  const nodes = new Map(), links = new Map();
  const addChar = (n, isFocus = false) => {
    const c = D.chars[n];
    if (!c || n.startsWith('终末地·') !== (bian === BIANS[1]) || (c.kind === 'doctor' && !opts.doctor && !isFocus)) return;
    nodes.set(`char:${n}`, { id: `char:${n}`, label: personLabel(n), type: c.kind, size: epCount(c), avatar: c.avatar ? imgSrc(c.avatar) : null });
  };
  const addPower = (p) => {
    if (D.powers[p]) nodes.set(`power:${p}`, { id: `power:${p}`, label: D.powers[p].name, type: D.powers[p].kind, size: 40 });
  };
  const addEvent = (id) => {
    const e = D.eventById[id];
    if (!e || (e.bian ?? BIANS[0]) !== bian) return;
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
      addChar(key, true);
      c.co.forEach(([n]) => addChar(n));
      if (opts.powers) c.powers.forEach(addPower);
      if (opts.events) c.events.forEach(addEvent);
    } else if (type === 'power' && D.powers[key]) {
      const p = D.powers[key];
      addPower(key);
      p.members.slice(0, 40).forEach((n) => addChar(n));
      [p.parent, ...p.children].filter(Boolean).forEach(addPower);
      if (opts.events) p.events.forEach(addEvent);
    }
  } else {
    Object.entries(D.chars).filter(([, c]) => epCount(c) >= opts.minEp).forEach(([n]) => addChar(n));
    if (opts.powers) {
      for (const id of [...nodes.keys()]) D.chars[id.slice(5)].powers.forEach(addPower);
      // 上级也钉上去（清波寨→武陵→文明环带），哪怕板上没有直接属于它的人
      for (const id of [...nodes.keys()].filter((k) => k.startsWith('power:'))) {
        for (let p = D.powers[id.slice(6)].parent; p && !nodes.has(`power:${p}`); p = D.powers[p]?.parent) addPower(p);
      }
    }
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
  readPalette();
  const { nodes: specs, links: linkSpecs } = collect();

  adj = new Map([...specs.keys()].map((id) => [id, new Set()]));
  for (const l of linkSpecs.values()) {
    adj.get(l.source).add(l.target);
    adj.get(l.target).add(l.source);
  }
  const maxW = Math.max(1, ...[...linkSpecs.values()].filter((l) => l.kind === 'co').map((l) => l.w));
  const links = [...linkSpecs.values()].map((l) => ({
    ...l, norm: l.kind === 'co' ? Math.log1p(l.w) / Math.log1p(maxW) : 0.3, sag: rnd(l.id, 7),
  }));

  // 沿用已有节点（保留位置和速度）；新节点放在已有邻居旁边，没有邻居就随机撒在中心附近
  const spread = 30 * Math.sqrt(specs.size);
  const current = new Set(fg.graphData().nodes);
  const nodes = [];
  for (const [id, spec] of specs) {
    let n = cache.get(id);
    const fresh = !n || !current.has(n);
    if (!n) cache.set(id, n = { id });
    Object.assign(n, spec, { r: Math.max(4, Math.min(22, 2.5 + Math.sqrt(spec.size) * 1.7)) });
    shape(n);
    n.fade ??= 1;
    n.lift ??= 0;
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
  boardTitle(nodes, links);
  const q = document.querySelector('.g-q');
  if (q?.value.trim()) find(q.value);
  else setFades();
  if (selected) showInfo(selected);
  else info.hidden = true;
  fitSoon();
}

function calm(on) {
  fg.d3VelocityDecay(on ? 0.6 : 0.35).d3AlphaDecay(on ? 0.05 : 0.02);
}

// 板子左上角贴一张标题：哪一编，板上几个人、几根红线
function boardTitle(nodes, links) {
  const el = document.querySelector('.g-board-title');
  if (!el) return;
  const people = nodes.filter((n) => n.person).length;
  const strings = links.filter((l) => l.kind === 'co').length;
  el.querySelector('b').textContent = focus ? label(focus) : bian;
  el.querySelector('small').textContent = `${focus ? bian : 'CASE BOARD'} · ${people} 人 · ${strings} 线`;
}

// ---------------------------------------------------------------- 卡片的尺寸

const FONT = '"Inter Tight", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif';
// 名字是拿笔写在胶带上的：有楷体用楷体，没有就退回黑体
const HAND = '"Kaiti SC", STKaiti, KaiTi, "AR PL UKai CN", "PingFang SC", "Microsoft YaHei", serif';
// 报纸的标题用宋体
const SERIF = '"Songti SC", STSong, "Noto Serif CJK SC", "Source Han Serif SC", SimSun, serif';
const BUST = new Path2D('M.5 .14a.19 .19 0 1 0 0 .38a.19 .19 0 1 0 0 -.38zM.13 .9c0 -.2 .17 -.32 .37 -.32s.37 .12 .37 .32z');
const TAG_GAP = 3;      // 卡片之间至少留这么宽
const ruler = document.createElement('canvas').getContext('2d');

// 名字量一次存下来（按 100px 字号），比每帧量省
function measure(text, font) {
  ruler.font = `${font === FONT ? 900 : 700} 100px ${font}`;
  return ruler.measureText(text).width;
}

// 人物：拍立得照片（没有照片时是一张卡片），名字写在贴在下沿的胶带上，图钉钉在上沿正中。
// 地区：剪下来的一块报纸，标题就是名字。势力：撕下来的海报。事件：一张便签。
// cw/ch 是卡片的宽高，tagW/tagH 是防重叠用的半宽半高（连名字条一起算），pinY 是图钉离中心多远。
function shape(n) {
  n.person = !isPower(n.type) && n.type !== 'event';
  n.rot ??= (rnd(n.id, 1) - 0.5) * 0.2;
  if (n.person) {
    n.cw = n.r * 2.5;
    n.ch = n.cw * 1.17;
    n.fs = n.r * 0.72;
    n.labelW ??= measure(n.label, HAND);
    n.labelRot ??= (rnd(n.id, 2) - 0.5) * 0.12 - n.rot * 0.5;
    n.pinY = -n.ch / 2 + n.cw * 0.1;
    const lw = n.labelW * n.fs / 100 + n.fs * 1.1;
    n.tagW = Math.max(n.cw, lw) / 2;
    n.tagH = n.ch / 2 + n.fs * 0.85;
  } else if (n.type === 'event') {
    n.cw = n.ch = n.r * 2.2;
    n.pinY = -n.ch / 2 + n.cw * 0.16;
    n.tagW = n.tagH = n.cw / 2 + 1;
  } else {
    const region = n.type === 'region';
    n.fs = n.r * (region ? 0.92 : 1);
    n.labelW ??= measure(n.label, region ? SERIF : FONT);
    n.cw = n.labelW * n.fs / 100 + n.fs * (region ? 1.3 : 1.5);
    n.ch = n.fs * (region ? 2.8 : 2.1);
    n.pinY = -n.ch / 2 + n.fs * 0.1;
    n.jag ??= Array.from({ length: 16 }, (_, i) => rnd(n.id, 10 + i));
    n.tagW = n.cw / 2;
    n.tagH = n.ch / 2;
  }
  n.reach = Math.hypot(n.tagW, n.tagH) * 1.6 + 6;
}

// ---------------------------------------------------------------- 力导向模拟

// 向心力：把每个节点按离中心的距离往回拉（d3 的 forceCenter 只平移整体，不会把散开的节点拉回来）。
// 板子是横的就上下拉得紧些、左右松些，摊开后正好铺满；手机竖屏反过来
function gravity() {
  let nodes = [];
  const force = (alpha) => {
    const k = forces.center * alpha;
    const r = Math.sqrt(clamp((box?.clientWidth || 4) / (box?.clientHeight || 3), 0.5, 2.2));
    const kx = k / r, ky = k * r;
    for (const n of nodes) { n.vx -= n.x * kx; n.vy -= n.y * ky; }
  };
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

// 防重叠：卡片按矩形算。按左边缘排序，左边缘已经越过 a 右边缘的就不用再比（扫描线）
function collide() {
  let nodes = [];
  const force = () => {
    for (const n of nodes) n.left = n.x - n.tagW;
    const order = nodes.slice().sort((p, q) => p.left - q.left);
    for (let i = 0; i < order.length; i++) {
      const a = order[i], right = a.x + a.tagW + TAG_GAP;
      for (let j = i + 1; j < order.length; j++) {
        const b = order[j];
        if (b.left > right) break;
        const dx = b.x + b.vx - a.x - a.vx, dy = b.y + b.vy - a.y - a.vy;
        const ox = a.tagW + b.tagW + TAG_GAP - Math.abs(dx);
        const oy = a.tagH + b.tagH + TAG_GAP - Math.abs(dy);
        if (ox <= 0 || oy <= 0) continue;
        // 往重叠少的方向推，一个 tick 推开一部分，不然会抖
        if (ox < oy) {
          const s = (dx < 0 ? -1 : 1) * ox * 0.25;
          a.vx -= s; b.vx += s;
        } else {
          const s = (dy < 0 ? -1 : 1) * oy * 0.25;
          a.vy -= s; b.vy += s;
        }
      }
    }
  };
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

function applyForces() {
  const deg = (x) => adj.get(nid(x))?.size || 1;
  // 人多时斥力粗算一些（Barnes-Hut 的 theta 调大），全员上板时每帧省下两三毫秒
  fg.d3Force('charge').strength(-forces.repel).distanceMax(800).theta(adj.size > 400 ? 1.2 : 0.9);
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
      // 名字条比卡片宽，点名字条上任何地方都要算点中
      const hw = n.hitW ?? n.tagW, hh = n.hitH ?? n.tagH;
      ctx.fillStyle = color;
      ctx.fillRect(n.x - hw, n.y - hh, hw * 2, hh * 2);
    })
    .linkVisibility(false)   // 线自己画，见 drawStrings
    .onRenderFramePre(drawBoard)
    .onRenderFramePost(drawOverlay)
    .minZoom(0.02)
    .maxZoom(8)
    .d3AlphaDecay(0.02)
    .d3VelocityDecay(0.35)
    // 能量降到 d3 默认的下限就停，不再空转到 20 秒：全员上板时每帧要算七八毫秒的力
    .d3AlphaMin(0.001)
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
  fg.d3Force('collide', collide());
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

// 模拟停下后 force-graph 不再重画；渐隐、照片载入这些自己的动画要它多画一会儿
function wake(ms) {
  if (!fg) return;
  wakeUntil = Math.max(wakeUntil, performance.now() + ms);
  fg.autoPauseRedraw(false);
  clearTimeout(wakeTimer);
  wakeTimer = setTimeout(() => fg?.autoPauseRedraw(true), wakeUntil - performance.now());
}

// ---------------------------------------------------------------- 在板上找人

function find(text) {
  const out = document.querySelector('.g-hits');
  const q = text.trim().toLowerCase();
  if (!q || !fg) {
    hits = null;
    if (out) out.innerHTML = '';
    setFades();
    return;
  }
  const names = (n) => [n.label, ...(n.person ? D.chars[splitId(n.id)[1]]?.aliases ?? [] : [])].map((s) => charName(s).toLowerCase());
  const rank = (list) => (list.includes(q) ? 0 : list.some((s) => s.startsWith(q)) ? 1 : 2);
  const board = fg.graphData().nodes;
  const onBoard = new Set(board.map((n) => n.id));
  const on = board
    .map((n) => [n, names(n)]).filter(([, l]) => l.some((s) => s.includes(q)))
    .sort((a, b) => rank(a[1]) - rank(b[1]) || b[0].size - a[0].size).map(([n]) => n);
  // 板上没有的人：给一个「以他为中心」的入口
  const off = on.length >= 6 ? [] : Object.entries(D.chars)
    .filter(([name, c]) => name.startsWith('终末地·') === (bian === BIANS[1]) && !onBoard.has(`char:${name}`)
      && [name, ...c.aliases].some((s) => charName(s).toLowerCase().includes(q)))
    .sort((a, b) => epCount(b[1]) - epCount(a[1])).slice(0, 6 - on.length).map(([name]) => name);
  hits = new Set(on.map((n) => n.id));
  out.innerHTML = on.slice(0, 8).map((n) => `<button class="g-hit" data-node="${esc(n.id)}">${esc(n.label)}</button>`).join('')
    + off.map((name) => `<a class="g-hit g-off" href="${href.graph('char', name)}">${esc(charName(name))}<small>不在板上</small></a>`).join('')
    || '<span class="muted small">没有找到</span>';
  setFades();
}

// 选中一个节点。从「找人」来的挪到中间并放大；手机上档案卡从底下弹出来，把选中的卡片挪到上半截
function pick(n, center) {
  selected = n;
  showInfo(n);
  setFades();
  const narrow = box.clientWidth < 600;
  if (!center && !narrow) return;
  const k = center ? Math.max(fg.zoom(), 1.8) : fg.zoom();
  if (k !== fg.zoom()) fg.zoom(k, 700);
  fg.centerAt(n.x, n.y + (narrow ? box.clientHeight * 0.22 / k : 0), 700);
}

// ---------------------------------------------------------------- 高亮

const active = () => hover ?? selected;
const isHot = (l) => { const a = active(); return !!a && (l.source === a || l.target === a); };

// 计算每个节点的目标不透明度；绘制时逐帧向目标靠拢，形成渐隐渐显。
// emph 的卡片挪到红线上面画；当前悬停或选中的那张还会被「拿起来」一点：转正、放大、影子变长。
// loud 的名字缩小了也放大到读得清：它自己、找到的人、地区势力，和同场最多的十几个人。
// 邻居全放大的话，阿米娅这样连着五十个人的会叠成一团
const LOUD = 14;
function setFades() {
  if (!fg) return;
  const { nodes, links } = fg.graphData();
  const a = active();
  const near = a ? adj.get(a.id) : null;
  const strong = new Set();
  if (a) {
    links.filter((l) => l.kind === 'co' && (l.source === a || l.target === a))
      .sort((p, q) => q.w - p.w).slice(0, box.clientWidth < 600 ? LOUD / 2 : LOUD)
      .forEach((l) => strong.add(l.source === a ? l.target : l.source));
  }
  for (const n of nodes) {
    n.target = a ? (n === a || near?.has(n.id) ? 1 : FADED) : hits ? (hits.has(n.id) ? 1 : FADED) : 1;
    n.emph = (!!a || !!hits) && n.target === 1;
    n.loud = n.emph && (n === a || !a || strong.has(n) || isPower(n.type));
    n.liftTarget = n === a ? 1 : 0;
  }
  wake(800);
}

// ---------------------------------------------------------------- 颜色和素材

// 颜色都写在 style.css 末尾的 --g-*，五个主题各一套；要能解析成十六进制
function readPalette() {
  const v = css;
  const next = {
    board: v('--g-board'), boardDk: v('--g-board-dk'), boardLt: v('--g-board-lt'), felt: v('--g-felt') === '1',
    yarn: v('--g-yarn'), yarnHot: v('--g-yarn-hot'), thread: v('--g-thread'), noteThread: v('--g-note-thread'),
    card: v('--g-card'), cardLine: v('--g-card-line'), cardRed: v('--g-card-red'), pencil: v('--g-pencil'),
    manila: v('--g-manila'), manilaLine: v('--g-manila-line'),
    news: v('--g-news'), newsFg: v('--g-news-fg'), newsLine: v('--g-news-line'),
    poster: v('--g-poster'), tape: v('--g-tape'), sticky: v('--g-sticky'), ink: v('--g-ink'), lime: v('--lime'),
    pin: v('--g-pin'), pinPower: v('--g-pin-power'), pinEvent: v('--g-pin-event'),
  };
  const key = JSON.stringify(next);
  if (key === palette.key) return;
  palette = { ...next, key };
  tex = { board: makeBoard(palette), pattern: null, pins: {} };
}

// 画布不走 CSS，换主题后要重读一遍颜色、重做板面再画
export function retheme() {
  if (!fg) return;
  readPalette();
  setFades();
}

let tex = { board: null, pattern: null, pins: {} };
const TILE = 512;

function seeded(seed) {
  return () => {
    seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// 板面：一块能无缝平铺的图块。浅色主题是软木（大小不一的颗粒），深色主题是绒布（细短的纤维）
function makeBoard(p) {
  const c = document.createElement('canvas');
  c.width = c.height = TILE;
  const g = c.getContext('2d');
  const R = seeded(20261112);
  g.fillStyle = p.board || '#b38a5c';
  g.fillRect(0, 0, TILE, TILE);
  // 贴着边的颗粒在对边再画一份，平铺时看不出接缝
  const wrap = (x, y, r, fn) => {
    for (const dx of [-TILE, 0, TILE]) for (const dy of [-TILE, 0, TILE]) {
      const X = x + dx, Y = y + dy;
      if (X + r >= 0 && X - r <= TILE && Y + r >= 0 && Y - r <= TILE) fn(X, Y);
    }
  };
  // 大块的深浅斑
  for (let i = 0; i < 46; i++) {
    const x = R() * TILE, y = R() * TILE, r = 40 + R() * 90, dark = R() < 0.5, a = 0.05 + R() * 0.07;
    wrap(x, y, r, (X, Y) => {
      const gr = g.createRadialGradient(X, Y, 0, X, Y, r);
      gr.addColorStop(0, hexA(dark ? p.boardDk : p.boardLt, a));
      gr.addColorStop(1, hexA(dark ? p.boardDk : p.boardLt, 0));
      g.fillStyle = gr;
      g.fillRect(X - r, Y - r, r * 2, r * 2);
    });
  }
  if (p.felt) {
    g.lineCap = 'round';
    for (let i = 0; i < 16000; i++) {
      const x = R() * TILE, y = R() * TILE, a = R() * Math.PI, len = 2 + R() * 7;
      const ux = Math.cos(a) * len / 2, uy = Math.sin(a) * len / 2;
      g.strokeStyle = R() < 0.5 ? p.boardLt : p.boardDk;
      g.globalAlpha = 0.08 + R() * 0.16;
      g.lineWidth = 0.5 + R() * 0.7;
      wrap(x, y, len, (X, Y) => { g.beginPath(); g.moveTo(X - ux, Y - uy); g.lineTo(X + ux, Y + uy); g.stroke(); });
    }
  } else {
    for (let i = 0; i < 15000; i++) {
      const x = R() * TILE, y = R() * TILE, r = 0.6 + R() ** 2.2 * 3, rr = r * (0.55 + R() * 0.45), a = R() * Math.PI;
      g.fillStyle = R() < 0.56 ? p.boardDk : p.boardLt;
      g.globalAlpha = 0.16 + R() * 0.4;
      wrap(x, y, r, (X, Y) => { g.beginPath(); g.ellipse(X, Y, r, rr, a, 0, Math.PI * 2); g.fill(); });
    }
    // 旧图钉留下的小孔
    g.fillStyle = p.boardDk;
    for (let i = 0; i < 30; i++) {
      const x = R() * TILE, y = R() * TILE, r = 0.9 + R() * 0.8;
      g.globalAlpha = 0.55;
      wrap(x, y, r, (X, Y) => { g.beginPath(); g.arc(X, Y, r, 0, Math.PI * 2); g.fill(); });
    }
  }
  g.globalAlpha = 1;
  const d = g.getImageData(0, 0, TILE, TILE), px = d.data, amp = p.felt ? 9 : 16;
  for (let i = 0; i < px.length; i += 4) {
    const v = (R() - 0.5) * amp;
    px[i] += v; px[i + 1] += v; px[i + 2] += v;
  }
  g.putImageData(d, 0, 0);
  return c;
}

// 图钉：一个带高光和影子的圆头，按颜色各画一次存下来。头的圆心在 (28,28)，半径 18
function pinSprite(color) {
  let c = tex.pins[color];
  if (c) return c;
  c = tex.pins[color] = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const sh = g.createRadialGradient(35, 37, 2, 35, 37, 21);
  sh.addColorStop(0, 'rgba(0,0,0,0.5)');
  sh.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = sh;
  g.fillRect(0, 0, 64, 64);
  const head = g.createRadialGradient(22, 21, 1, 28, 28, 18);
  head.addColorStop(0, mix(color, '#ffffff', 0.75));
  head.addColorStop(0.28, mix(color, '#ffffff', 0.15));
  head.addColorStop(0.75, color);
  head.addColorStop(1, mix(color, '#000000', 0.45));
  g.fillStyle = head;
  g.beginPath();
  g.arc(28, 28, 18, 0, Math.PI * 2);
  g.fill();
  return c;
}

function rgbOf(hex) {
  const h = (hex || '#000').replace('#', '');
  const x = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16) || 0);
}
function mix(a, b, t) {
  const p = rgbOf(a), q = rgbOf(b);
  return `rgb(${p.map((v, i) => Math.round(v + (q[i] - v) * t)).join(',')})`;
}
// 连线每帧都要取颜色，反复拼字符串很慢；不透明度取到两位小数后缓存
const rgbaCache = new Map();
function hexA(hex, a) {
  const key = `${hex}|${Math.round(a * 100)}`;
  let v = rgbaCache.get(key);
  if (!v) rgbaCache.set(key, v = `rgba(${rgbOf(hex).join(',')},${Math.round(a * 100) / 100})`);
  return v;
}

// 照片：用到时才载入（屏幕上至少十来个像素大）。头像是透明底的，载入后垫一块证件照式的底色合成一张，
// 再缩一张 32 像素的，远看时用它，省得每帧缩大图、缩出锯齿。底色按人挑四种之一，像是不同时候拍的。
// 没有照片、载入失败时，人物用一张写着名字的卡片
const photos = new Map();
const BACKDROPS = [['#a9b4bb', '#6f7c86'], ['#b5b9a4', '#7a806a'], ['#bcb0a4', '#857669'], ['#9fb3b3', '#62797b']];
function photoOf(n, onScreen) {
  let p = photos.get(n.avatar);
  if (p || onScreen < 10) return p ?? null;
  photos.set(n.avatar, p = { ready: false });
  const img = new Image();
  img.decoding = 'async';
  img.onload = () => {
    const s = 128, t = document.createElement('canvas');
    t.width = t.height = s;
    const g = t.getContext('2d');
    const [top, bottom] = BACKDROPS[Math.floor(rnd(n.avatar, 5) * BACKDROPS.length)];
    const grad = g.createLinearGradient(0, 0, 0, s);
    grad.addColorStop(0, top);
    grad.addColorStop(1, bottom);
    g.fillStyle = grad;
    g.fillRect(0, 0, s, s);
    const w = img.naturalWidth, h = img.naturalHeight, side = Math.min(w, h);
    // 头像多是方的；不是方的就取上半截正中
    g.drawImage(img, (w - side) / 2, h > w ? 0 : (h - side) / 2, side, side, 0, 0, s, s);
    const half = document.createElement('canvas'), small = document.createElement('canvas');
    half.width = half.height = 64;
    small.width = small.height = 32;
    half.getContext('2d').drawImage(t, 0, 0, 64, 64);
    small.getContext('2d').drawImage(half, 0, 0, 32, 32);
    Object.assign(p, { big: t, small, ready: true });
    wake(300);
  };
  img.onerror = () => { p.failed = true; };
  img.src = n.avatar;
  return p;
}

// ---------------------------------------------------------------- 绘制

let base = null;   // 每帧开始时的画布变换（图坐标 → 像素）

// 每帧开始：铺板面，记下可见范围。板面跟着平移，缩放时纹理也缩放，但只在一个范围内，免得太碎或太糊
function drawBoard(ctx, scale) {
  base = ctx.getTransform();
  const W = ctx.canvas.width, H = ctx.canvas.height;
  view = {
    x0: -base.e / base.a, y0: -base.f / base.d,
    x1: (W - base.e) / base.a, y1: (H - base.f) / base.d,
  };
  if (!tex.board) return;
  tex.pattern ??= ctx.createPattern(tex.board, 'repeat');
  const dpr = base.a / scale, s = clamp(scale, 0.55, 2.2) * dpr * 0.5;
  tex.pattern.setTransform(new DOMMatrix([s, 0, 0, s, base.e, base.f]));
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = tex.pattern;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();
  // 平常的线垫在卡片底下，照片不被线盖住；高亮的线留到最后压在卡片上面画
  if (fg) {
    const { nodes, links } = fg.graphData();
    for (const n of nodes) pinAt(n, scale);
    drawStrings(ctx, scale, links, false);
  }
}

const seen = (n) => n.x + n.reach > view.x0 && n.x - n.reach < view.x1 && n.y + n.reach > view.y0 && n.y - n.reach < view.y1;

// force-graph 逐个调用：只画人物卡片和便签。拿起来的那张留到最后再画
function drawNode(n, ctx, scale) {
  n.fade += ((n.target ?? 1) - n.fade) * 0.2;
  n.lift += ((n.liftTarget ?? 0) - n.lift) * 0.25;
  if (isPower(n.type) || n === active() || !seen(n)) return;
  drawCard(n, ctx, scale);
}

// 每帧最后：高亮的线、拿起来的卡片、报纸海报、名字条、图钉
function drawOverlay(ctx, scale) {
  if (!fg) return;
  const { nodes, links } = fg.graphData();
  const a = active();
  for (const n of nodes) pinAt(n, scale);
  // 悬停或选中时，它牵出的线压在别的卡片上面，一眼看得出连到谁
  if (a) drawStrings(ctx, scale, links, true);
  // 拿起来的那张又压在线上面，照片不被自己的线盖住；线看上去是从卡片底下穿到图钉
  if (a && !isPower(a.type) && seen(a)) drawCard(a, ctx, scale);
  for (const n of nodes) if (isPower(n.type) && !n.emph && seen(n)) drawPaper(n, ctx, scale);
  for (const n of nodes) if (isPower(n.type) && n.emph && n !== a && seen(n)) drawPaper(n, ctx, scale);
  if (a && isPower(a.type) && seen(a)) drawPaper(a, ctx, scale);
  for (const n of nodes) if (!n.emph && seen(n)) drawName(n, ctx, scale);
  for (const n of nodes) if (n.emph && !n.loud && seen(n)) drawName(n, ctx, scale);
  for (const n of nodes) if (n.loud && n !== a && seen(n)) drawName(n, ctx, scale);
  if (a && seen(a)) drawName(a, ctx, scale);
  for (const n of nodes) if (seen(n)) drawPin(n, ctx, scale);
  ctx.globalAlpha = 1;
}

// 报纸和海报远看时会放大，免得缩小后读不了；k 是放大倍数
function paperScale(n, scale) {
  let fs = n.fs;
  if (n.loud) fs = Math.max(fs, 12 / scale);
  else if (scale * n.r >= 6) fs = Math.max(fs, 11 / scale);
  return fs / n.fs;
}

// 图钉的位置：卡片上沿正中，跟着卡片转。红线都拴在图钉上
function pinAt(n, scale) {
  const k = isPower(n.type) ? paperScale(n, scale) : 1 + n.lift * 0.08;
  const rot = n.rot * (1 - n.lift * 0.8), d = n.pinY * k;
  n.px = n.x - Math.sin(rot) * d;
  n.py = n.y + Math.cos(rot) * d;
  n.k = k;
}

function shadow(ctx, w, h, scale, lift) {
  const o = 1.2 / scale + w * (0.022 + lift * 0.05);
  ctx.fillStyle = 'rgba(0,0,0,0.16)';
  ctx.fillRect(-w / 2 + o * 0.2, -h / 2 + o * 0.5, w + o * 0.9, h + o * 1.1);
  ctx.fillStyle = 'rgba(0,0,0,0.2)';
  ctx.fillRect(-w / 2 + o * 0.3, -h / 2 + o * 0.6, w, h);
}

// 人物卡片和便签
function drawCard(n, ctx, scale) {
  const P = palette, w = n.cw, h = n.ch, onScreen = w * scale, small = onScreen < 6;
  ctx.globalAlpha = n.fade;
  // 全员上板缩得很小时，卡片只有几个像素：不转、不画影子，直接一个色块，省下上千次变换
  if (small && n.lift < 0.01) {
    ctx.fillStyle = n.type === 'event' ? P.sticky : n.type === 'doctor' ? P.ink : n.type === 'npc' ? P.manila : P.card;
    ctx.fillRect(n.x - w / 2, n.y - h / 2, w, h);
    return;
  }
  ctx.save();
  ctx.translate(n.x, n.y);
  ctx.rotate(n.rot * (1 - n.lift * 0.8));
  if (n.lift > 0.01) ctx.scale(1 + n.lift * 0.08, 1 + n.lift * 0.08);
  if (!small) shadow(ctx, w, h, scale, n.lift);
  if (n.type === 'event') {
    ctx.fillStyle = P.sticky;
    ctx.fillRect(-w / 2, -h / 2, w, h);
    if (!small) {
      // 便签右下角翘起来一点
      ctx.fillStyle = 'rgba(0,0,0,0.14)';
      ctx.beginPath();
      ctx.moveTo(w / 2, h / 2 - w * 0.28); ctx.lineTo(w / 2, h / 2); ctx.lineTo(w / 2 - w * 0.28, h / 2);
      ctx.fill();
    }
    ctx.restore();
    return;
  }
  const photo = n.avatar && !small && n.type !== 'doctor' ? photoOf(n, onScreen) : null;
  const ready = photo?.ready;
  ctx.fillStyle = n.type === 'doctor' ? P.ink : n.type === 'npc' && !ready ? P.manila : P.card;
  ctx.fillRect(-w / 2, -h / 2, w, h);
  if (!small) {
    const m = w * 0.075, s = w - 2 * m, top = -h / 2 + m;
    if (ready) {
      // 拍立得：白边里一张方照片
      ctx.drawImage(s * scale > 40 ? photo.big : photo.small, -w / 2 + m, top, s, s);
      if (P.felt) {   // 深色主题下照片也压暗一点，和纸一起
        ctx.fillStyle = 'rgba(16,18,24,0.16)';
        ctx.fillRect(-w / 2 + m, top, s, s);
      }
    } else {
      // 没有照片：一张卡片，上面铅笔画个半身像，下面几道横线；干员的卡片顶上多一道红线
      const hair = Math.max(0.6 / scale, w * 0.012);
      if (n.type !== 'doctor') {
        ctx.fillStyle = n.type === 'npc' ? P.manilaLine : P.cardLine;
        for (let i = 0; i < 3; i++) ctx.fillRect(-w / 2 + m, top + s * (0.7 + i * 0.13), s, hair);
        if (n.type === 'operator') {
          ctx.fillStyle = P.cardRed;
          ctx.fillRect(-w / 2 + m, top + s * 0.08, s, hair);
        }
      }
      const b = s * 0.62;
      ctx.save();
      ctx.translate(-b / 2, top + s * 0.12);
      ctx.scale(b, b);
      ctx.fillStyle = n.type === 'doctor' ? P.lime : hexA(P.pencil, 0.55);
      ctx.fill(BUST);
      ctx.restore();
    }
  }
  ctx.restore();
}

// 报纸（地区）和海报（势力）：撕下来的纸，上下边参差。名字就是标题
function drawPaper(n, ctx, scale) {
  const P = palette, region = n.type === 'region', hot = n === active();
  const k = n.k ?? 1, w = n.cw * k, h = n.ch * k, fs = n.fs * k;
  const named = fs * scale >= 7.5, small = w * scale < 8;
  ctx.globalAlpha = n.fade;
  ctx.save();
  ctx.translate(n.x, n.y);
  ctx.rotate(n.rot * 0.6 * (1 - n.lift * 0.8));
  if (!small) shadow(ctx, w, h, scale, n.lift);
  ctx.fillStyle = region ? P.news : P.poster;
  if (small) ctx.fillRect(-w / 2, -h / 2, w, h);
  else {
    const j = n.jag, amp = h * (region ? 0.05 : 0.07), steps = 7;
    ctx.beginPath();
    for (let i = 0; i <= steps; i++) ctx.lineTo(-w / 2 + (w * i) / steps, -h / 2 + (j[i] - 0.5) * amp);
    for (let i = steps; i >= 0; i--) ctx.lineTo(-w / 2 + (w * i) / steps, h / 2 + (j[i + 8] - 0.5) * amp * 1.4);
    ctx.closePath();
    ctx.fill();
  }
  const left = -w / 2 + fs * (region ? 0.65 : 0.75);
  if (region) {
    // 标题下面两栏「正文」，远看是几道灰线
    if (!small) {
      const colW = (w - fs * 1.3 - fs * 0.5) / 2, y0 = -h / 2 + fs * 1.72;
      ctx.fillStyle = P.newsLine;
      for (let r = 0; r < 3; r++) for (let c = 0; c < 2; c++) {
        const lw = colW * (r === 2 ? 0.4 + 0.5 * n.jag[r + c * 3] : 1);
        ctx.fillRect(left + c * (colW + fs * 0.5), y0 + r * fs * 0.34, lw, fs * 0.14);
      }
    }
    if (hot) {
      ctx.fillStyle = hexA(P.lime, 0.9);
      ctx.fillRect(left - fs * 0.2, -h / 2 + fs * 0.32, n.labelW * fs / 100 + fs * 0.4, fs * 1.12);
    }
    if (named) {
      ctx.font = `700 ${fs}px ${SERIF}`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = P.newsFg;
      ctx.fillText(n.label, left, -h / 2 + fs * 0.9);
    } else if (!small) {
      ctx.fillStyle = P.newsFg;
      ctx.fillRect(left, -h / 2 + fs * 0.5, n.labelW * fs / 100, fs * 0.8);
    }
  } else {
    // 海报：黑纸荧光绿大字，底下一道绿杠
    if (hot) {
      ctx.fillStyle = P.lime;
      ctx.fillRect(-w / 2 + fs * 0.35, -h / 2 + fs * 0.3, w - fs * 0.7, fs * 1.3);
    }
    if (named) {
      ctx.font = `900 ${fs}px ${FONT}`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = hot ? P.ink : P.lime;
      ctx.fillText(n.label, left, -h / 2 + fs * 0.98);
    } else if (!small) {
      ctx.fillStyle = P.lime;
      ctx.fillRect(left, -h / 2 + fs * 0.55, n.labelW * fs / 100, fs * 0.85);
    }
    if (!small) {
      ctx.fillStyle = P.lime;
      ctx.fillRect(left, h / 2 - fs * 0.5, w - fs * 1.5, Math.max(fs * 0.1, 1 / scale));
    }
  }
  // 两角各贴一小段胶带
  if (!small && named) {
    ctx.fillStyle = hexA(P.tape, 0.78);
    for (const sx of [-1, 1]) {
      ctx.save();
      ctx.translate(sx * (w / 2 - fs * 0.3), -h / 2 + fs * 0.05);
      ctx.rotate(sx * 0.7);
      ctx.fillRect(-fs * 0.6, -fs * 0.22, fs * 1.2, fs * 0.44);
      ctx.restore();
    }
  }
  ctx.restore();
  n.hitW = w / 2 + 1 / scale;
  n.hitH = h / 2 + 1 / scale;
}

// 一截撕下来的胶带：两头是锯齿
function tapePath(ctx, w, h) {
  const t = h * 0.13, teeth = 4;
  ctx.beginPath();
  ctx.moveTo(-w / 2, -h / 2);
  ctx.lineTo(w / 2, -h / 2);
  for (let i = 1; i <= teeth; i++) ctx.lineTo(w / 2 - (i % 2 ? t : 0), -h / 2 + (h * i) / teeth);
  ctx.lineTo(-w / 2, h / 2);
  for (let i = teeth - 1; i >= 0; i--) ctx.lineTo(-w / 2 + (i % 2 ? t : 0), -h / 2 + (h * i) / teeth);
  ctx.closePath();
}

// 名字：人物的写在卡片下沿的胶带上，选中时胶带换成荧光绿；事件的写在便签下面的纸条上
function drawName(n, ctx, scale) {
  if (isPower(n.type)) return;
  const P = palette, hot = n === active();
  if (n.type === 'event') {
    const show = Math.max(clamp((scale * n.r - 7) / 6), n.loud ? 1 : 0) * n.fade;
    if (show <= 0.03) return;
    const fs = 11 / scale, top = n.y + n.ch / 2 + 3 / scale;
    ctx.globalAlpha = show;
    ctx.font = `600 ${fs}px ${FONT}`;
    const w = ctx.measureText(n.label).width + 10 / scale, h = fs + 6 / scale;
    ctx.fillStyle = hot ? P.lime : P.card;
    ctx.fillRect(n.x - w / 2, top, w, h);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = P.ink;
    ctx.fillText(n.label, n.x, top + h / 2 + 0.5 / scale);
    n.hitW = Math.max(n.cw / 2, w / 2);
    n.hitH = n.ch / 2 + h + 3 / scale;
    return;
  }
  let fs = n.fs;
  if (n.loud) fs = Math.max(fs, 12 / scale);
  if (fs * scale < 7.5) {   // 太小读不了就不写名字，只留卡片
    n.hitW = n.cw / 2;
    n.hitH = n.ch / 2;
    return;
  }
  const w = n.labelW * fs / 100 + fs * 1.1, h = fs * 1.5;
  const rot = n.rot * (1 - n.lift * 0.8), d = n.ch / 2 * (1 + n.lift * 0.08) - h * 0.22;
  ctx.globalAlpha = n.fade;
  ctx.save();
  ctx.translate(n.x - Math.sin(rot) * d, n.y + Math.cos(rot) * d);
  ctx.rotate(n.labelRot * (1 - n.lift * 0.8));
  tapePath(ctx, w, h);
  ctx.fillStyle = hot ? P.lime : hexA(P.tape, 0.94);
  ctx.fill();
  ctx.font = `700 ${fs}px ${HAND}`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = P.ink;
  ctx.fillText(n.label, 0, fs * 0.06);
  ctx.restore();
  n.hitW = Math.max(n.cw / 2, w / 2);
  n.hitH = n.ch / 2 + h * 0.8;
}

function drawPin(n, ctx, scale) {
  const ref = isPower(n.type) ? n.ch * (n.k ?? 1) : n.cw;
  if (ref * scale < 7) return;
  const pr = Math.max(ref * (isPower(n.type) ? 0.11 : n.type === 'event' ? 0.13 : 0.085), 2.4 / scale);
  const P = palette;
  const color = n.type === 'doctor' ? P.lime : n.person ? P.pin : n.type === 'event' ? P.pinEvent : P.pinPower;
  ctx.globalAlpha = n.fade;
  const size = pr * 64 / 18;
  ctx.drawImage(pinSprite(color), n.px - pr * 28 / 18, n.py - pr * 28 / 18, size, size);
}

// 线：同场是红毛线，所属是深色细线，事件是白线。都从图钉拉到图钉，中间往下垂一点。
// 同一种颜色、粗细、深浅的线攒成一条路径，一次描边；先画一遍影子。
// 浏览器描超过 1 像素宽的线很慢（一千条粗线就只剩十来帧），1 像素以内的细线却很快。
// 所以每帧最多 THICK 条线按真实粗细画，挑最粗的；其余的压到 1 像素，影子也只用细线。
// 粗线再按位置切成三百来像素见方的小块描边，整条大路径描粗线更慢。
const THICK = 240;
function drawStrings(ctx, scale, links, hotPass) {
  const P = palette, a = active();
  const zoomW = Math.pow(clamp(scale, 0.35, 3), 0.5);
  const groups = new Map();
  const { x0, y0, x1, y1 } = view;
  for (const l of links) {
    const s = l.source, t = l.target;
    if (s.px === undefined || t.px === undefined) continue;
    if ((s.px < x0 && t.px < x0) || (s.px > x1 && t.px > x1) || (s.py < y0 && t.py < y0) || (s.py > y1 + 80 && t.py > y1 + 80)) continue;
    const hot = !!a && (s === a || t === a);
    if (hot !== hotPass) continue;
    const q = hot ? 10 : Math.round(Math.min(s.fade, t.fade) * 10);
    if (q <= 0) continue;
    const kind = l.kind === 'co' ? 'co' : l.kind === 'event' ? 'ev' : 'mb';
    const wc = l.kind === 'co' ? Math.round(l.norm * 4) : 0;
    const key = `${hot ? 1 : 0}${kind}${wc}|${q}`;
    let g = groups.get(key);
    if (!g) groups.set(key, g = { hot, kind, wc, q, list: [] });
    g.list.push(l);
  }
  // 定每组的屏幕线宽；粗线名额先给最粗的组
  let budget = THICK;
  const thickFirst = [...groups.values()].sort((p, q) => q.hot - p.hot || q.wc - p.wc || q.q - p.q);
  for (const g of thickFirst) {
    let px = g.kind === 'co'
      ? (0.7 + g.wc * 0.45) * zoomW * (g.hot ? 1.45 : 1)
      : (g.kind === 'ev' ? 0.6 : 0.75) * zoomW * (g.hot ? 1.8 : 1);
    if (px > 1) {
      if ((g.kind !== 'co' && !g.hot) || g.list.length > budget) px = 1;   // 所属和事件的细线本来就该细
      else budget -= g.list.length;
    }
    g.px = px;
  }
  const order = [...groups.values()].sort((p, q) => p.hot - q.hot || p.q - q.q || p.px - q.px);
  ctx.lineCap = 'round';
  ctx.globalAlpha = 1;
  for (const g of order) {
    const alpha = g.q / 10, lw = g.px / scale;
    const color = g.kind === 'co' ? (g.hot ? P.yarnHot : P.yarn) : g.kind === 'ev' ? P.noteThread : P.thread;
    const shade = alpha >= 0.5 && scale > 0.4 ? hexA('#000000', (g.hot ? 0.38 : 0.24) * alpha) : null;
    // 弱的红线淡一些，总览时不至于一片红
    const ink = hexA(color, (g.kind === 'co' ? (g.hot ? 1 : 0.42 + g.wc * 0.11) : g.hot ? 0.95 : g.kind === 'ev' ? 0.32 : 0.55) * alpha);
    const cell = g.px > 1 ? 300 / scale : Infinity;
    const list = g.list.map((l) => {
      const s = l.source, t = l.target;
      const dx = t.px - s.px, dy = t.py - s.py, len = Math.hypot(dx, dy) || 1;
      const sag = Math.min(len * (0.04 + 0.05 * l.sag), 90) * (0.3 + 0.7 * Math.abs(dx) / len);
      const cx = (s.px + t.px) / 2, cy = (s.py + t.py) / 2 + sag * 2;
      return { s, t, cx, cy, key: cell === Infinity ? 0 : Math.floor(cy / cell) * 4096 + Math.floor(cx / cell) };
    });
    if (cell !== Infinity) list.sort((p, q) => p.key - q.key);
    let path = null, bx0 = 0, by0 = 0, bx1 = 0, by1 = 0;
    const flush = () => {
      if (!path) return;
      if (shade) {
        // 影子：往右下错开一点
        ctx.save();
        ctx.translate(1.1 / scale + lw * 0.4, 1.8 / scale + lw * 0.6);
        ctx.strokeStyle = shade;
        ctx.lineWidth = Math.min(lw, 1 / scale);
        ctx.stroke(path);
        ctx.restore();
      }
      ctx.strokeStyle = ink;
      ctx.lineWidth = lw;
      ctx.stroke(path);
      path = null;
    };
    for (const { s, t, cx, cy } of list) {
      if (cell !== Infinity) {
        const ax = Math.min(s.px, t.px), ay = Math.min(s.py, t.py, cy), bx = Math.max(s.px, t.px), by = Math.max(s.py, t.py, cy);
        if (path && (Math.max(bx1, bx) - Math.min(bx0, ax) > cell || Math.max(by1, by) - Math.min(by0, ay) > cell)) flush();
        if (!path) { bx0 = ax; by0 = ay; bx1 = bx; by1 = by; }
        bx0 = Math.min(bx0, ax); by0 = Math.min(by0, ay); bx1 = Math.max(bx1, bx); by1 = Math.max(by1, by);
      }
      path ??= new Path2D();
      path.moveTo(s.px, s.py);
      path.quadraticCurveTo(cx, cy, t.px, t.py);
    }
    flush();
  }
}

// force-graph 没有双击事件：同一节点 350ms 内点两次算双击
function onClick(n) {
  const now = performance.now();
  if (lastClick.id === n.id && now - lastClick.t < 350) {
    location.hash = `#/graph/${n.id}?${new URLSearchParams({ bian })}`;
    return;
  }
  lastClick = { id: n.id, t: now };
  pick(n, false);
}

// 选中后右上角贴一张档案卡
function showInfo(node) {
  const [type, key] = splitId(node.id);
  const neighbors = [...(adj.get(node.id) ?? [])].map((id) => cache.get(id)?.label ?? id);
  let body = '';
  if (type === 'char') {
    const c = D.chars[key];
    body = `${c.avatar ? `<img class="g-info-photo" src="${esc(imgSrc(c.avatar))}" alt="" decoding="async" onerror="this.remove()">` : ''}
      <div class="muted small">${KIND_LABEL[c.kind]} · 出场 ${epCount(c)} 集 · 事件 ${c.events.length}</div>
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
