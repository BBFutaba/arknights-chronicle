// 共享的小工具：转义、链接、颜色、标签渲染。
import { D } from './data.js';

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const enc = encodeURIComponent;
export const href = {
  char: (n) => `#/chars/${enc(D.charAlias?.[n] ?? n)}`,
  // 地区势力在博物志里只有一页：写了条目的用条目名，没写的用自己的名字
  power: (id) => `#/bowu/${enc(D.bowu?.powers[id]?.entry ?? D.powers[id]?.name ?? id)}`,
  wu: (name) => (name ? `#/bowu/${enc(name)}` : '#/bowu'),
  group: (gid) => `#/story/${enc(gid)}`,
  ep: (sid) => `#/story/${enc(D.epById[sid]?.group.id ?? '')}/${enc(sid)}`,
  event: (id) => `#/timeline?ev=${enc(id)}`,
  timeline: (params) => `#/timeline?${new URLSearchParams(params)}`,
  graph: (type, id) => `#/graph/${type}:${enc(id)}`,
  annals: (year, entry) => `#/annals/${year}${entry ? `?e=${entry}` : ''}`,
  annalsEntry: (id) => `#/annals/${D.annalsEntry[id]?.year ?? ''}?e=${id}`,
  benmo: (title) => `#/benmo/${enc(title)}`,
  zhuan: (name) => `#/zhuan/${enc(name)}`,
};

export const KIND_LABEL = { operator: '干员', npc: 'NPC', doctor: '博士' };
export const CAT_ORDER = ['主线', '活动', '故事集', '设定'];

// 故事线颜色：按剧情组顺序用黄金角取色，相邻的组颜色差别大；设定与档案用灰色。
export function threadColor(tid) {
  if (tid === 'lore') return 'var(--lore)';
  const g = D.groupById[tid];
  const i = g ? g.order : 0;
  const hue = (i * 137.508 + 20) % 360;
  return g?.category === '主线' ? `hsl(${hue} 70% 48%)` : `hsl(${hue} 52% 52%)`;
}

export function epLabel(ep) {
  const name = [ep.code, ep.title].filter(Boolean).join(' ');
  return ep.avg ? `${name}（${ep.avg}）` : name;
}

export function groupLabel(g) {
  return g.chapter != null ? `${g.label} ${g.name}` : g.name;
}

// 人物：name 可以是正名，也可以是别名
export function charOf(name) {
  return D.chars[name] ?? D.chars[D.charAlias?.[name]];
}

export function charChip(name, extra = '') {
  const c = charOf(name);
  const cls = c ? `chip chip-${c.kind}` : 'chip chip-plain';
  return c ? `<a class="${cls}" href="${href.char(name)}">${esc(name)}${extra}</a>`
    : `<span class="${cls}">${esc(name)}${extra}</span>`;
}

export function powerChip(id, extra = '') {
  const p = D.powers[id];
  if (!p) return '';
  return `<a class="chip chip-${p.kind}" href="${href.power(id)}">${esc(p.name)}${extra}</a>`;
}

export function threadChip(tid, linkTo = 'timeline') {
  const t = D.threads[tid];
  if (!t) return '';
  const url = linkTo === 'timeline' ? href.timeline({ thread: tid }) : href.group(tid);
  return `<a class="thread-chip" href="${url}" style="--c:${threadColor(tid)}">${esc(t.name)}</a>`;
}

export function eventItem(ev) {
  const more = ev.lines.length > 1 ? `<span class="muted">（共 ${ev.lines.length} 条）</span>` : '';
  return `<a class="event-item" href="${href.event(ev.id)}">
    <span class="when">${esc(ev.when)}</span>${threadChip(ev.thread)}
    <span class="text">${esc(ev.lines[0] ?? '')}${more}</span></a>`;
}

// 页头：压在内容区顶上的一条灰纸，和左栏标题块同一个语法，轨道接着左栏的走。
// nums 是 [标签, 数字, 单位, 英文单位] 的数组，空值跳过；aside 放在右边，代替数字列。
// rail 为假时不画轨道，由调用的页面自己画（时间轴的横轴要吸顶，不能跟页头一起滚走）。
export function pageHead({ en = '', title, back = null, sub = '', tags = '', note = '', nums = [], aside = '', rail = true }) {
  const fmt = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : esc(v));
  const cols = nums.filter(Boolean).map(([label, v, unit, unitEn]) => `<div class="ph-num">
      <span class="ph-num-l">${esc(label)}</span>
      <div class="ph-num-v"><b>${fmt(v)}</b><span><i>${esc(unit)}</i><em>${esc(unitEn)}</em></span></div>
    </div>`).join('');
  return `<header class="ph">
    <div class="ph-body">
      <div class="ph-main">
        <i class="ph-stem"></i><i class="ph-cap"></i>
        ${back ? `<a class="ph-back" href="${esc(back[0])}">${esc(back[1])}</a>` : ''}
        ${en ? `<div class="ph-en">${esc(en)}</div>` : ''}
        <h1>${esc(title)}</h1>
        ${sub ? `<div class="ph-sub">${sub}</div>` : ''}
        ${tags ? `<div class="ph-tags">${tags}</div>` : ''}
        ${note ? `<div class="ph-note">${note}</div>` : ''}
      </div>
      ${aside || (cols ? `<div class="ph-nums">${cols}</div>` : '')}
    </div>
    ${rail ? '<div class="ph-track"></div>' : ''}
  </header>`;
}

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
