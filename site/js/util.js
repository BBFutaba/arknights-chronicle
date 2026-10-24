// 共享的小工具：转义、链接、颜色、标签渲染。
import { D } from './data.js';

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const enc = encodeURIComponent;
export const href = {
  char: (n) => `#/chars/${enc(n)}`,
  power: (id) => `#/powers/${enc(id)}`,
  group: (gid) => `#/story/${enc(gid)}`,
  ep: (sid) => `#/story/${enc(D.epById[sid]?.group.id ?? '')}/${enc(sid)}`,
  event: (id) => `#/timeline?ev=${enc(id)}`,
  timeline: (params) => `#/timeline?${new URLSearchParams(params)}`,
  graph: (type, id) => `#/graph/${type}:${enc(id)}`,
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

export function charChip(name, extra = '') {
  const c = D.chars[name];
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

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
