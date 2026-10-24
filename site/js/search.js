// 顶栏全局搜索：人物、地区势力、剧情组、分集、年表事件。
import { D } from './data.js';
import { esc, href, epLabel, groupLabel, KIND_LABEL } from './util.js';

let index = [];

function buildIndex() {
  index = [];
  for (const [name, c] of Object.entries(D.chars)) {
    index.push({ cat: '人物', keys: [name, ...c.aliases, c.appellation].filter(Boolean), label: name,
      sub: KIND_LABEL[c.kind] + (c.appear.length ? ` · 出场 ${c.appear.reduce((n, a) => n + a[1].length, 0)} 集` : ''),
      url: href.char(name), weight: c.appear.length + c.events.length });
  }
  for (const [id, p] of Object.entries(D.powers)) {
    index.push({ cat: '地区与势力', keys: [p.name], label: p.name, sub: p.kind === 'region' ? '地区' : '势力',
      url: href.power(id), weight: 100 });
  }
  for (const g of D.groups) {
    index.push({ cat: '剧情', keys: [g.name], label: groupLabel(g), sub: `${g.category} · ${g.episodes.length} 集`,
      url: href.group(g.id), weight: 50 });
    for (const e of g.episodes) {
      index.push({ cat: '剧情', keys: [e.code, e.title].filter(Boolean), label: epLabel(e), sub: g.name,
        url: href.ep(e.id), weight: 1 });
    }
  }
  for (const ev of D.events) {
    index.push({ cat: '事件', keys: [ev.lines.join(' ')], label: ev.lines[0], sub: ev.when,
      url: href.event(ev.id), weight: 0 });
  }
}

function query(q) {
  q = q.trim().toLowerCase();
  if (!q) return [];
  const scored = [];
  for (const item of index) {
    let best = -1;
    for (const k of item.keys) {
      const s = k.toLowerCase();
      if (s === q) best = Math.max(best, 3);
      else if (s.startsWith(q)) best = Math.max(best, 2);
      else if (s.includes(q)) best = Math.max(best, 1);
    }
    if (best >= 0) scored.push([best, item]);
  }
  scored.sort((a, b) => b[0] - a[0] || b[1].weight - a[1].weight);
  const perCat = {};
  return scored.map((x) => x[1]).filter((it) => (perCat[it.cat] = (perCat[it.cat] ?? 0) + 1) <= 6);
}

export function initSearch() {
  buildIndex();
  const box = document.getElementById('search');
  const input = box.querySelector('input');
  const results = box.querySelector('.search-results');
  let items = [], active = 0;

  const render = () => {
    items = query(input.value);
    results.hidden = !input.value.trim();
    if (!items.length) { results.innerHTML = '<div class="muted pad">没有结果</div>'; return; }
    let cat = '';
    results.innerHTML = items.map((it, i) => {
      const head = it.cat !== cat ? `<div class="sr-cat">${(cat = it.cat)}</div>` : '';
      return `${head}<a class="sr-item${i === active ? ' active' : ''}" href="${it.url}" data-i="${i}">
        <span class="sr-label">${esc(it.label)}</span><span class="sr-sub">${esc(it.sub)}</span></a>`;
    }).join('');
  };
  const close = () => { results.hidden = true; input.blur(); };

  input.addEventListener('input', () => { active = 0; render(); });
  input.addEventListener('focus', () => input.value.trim() && render());
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % Math.max(items.length, 1);
      render();
    } else if (e.key === 'Enter' && items[active]) {
      location.hash = items[active].url.slice(1);
      close();
    } else if (e.key === 'Escape') close();
  });
  results.addEventListener('click', (e) => { if (e.target.closest('a')) close(); });
  window.addEventListener('hashchange', () => { results.hidden = true; });
  document.addEventListener('click', (e) => { if (!box.contains(e.target)) results.hidden = true; });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); input.focus(); }
  });
}
