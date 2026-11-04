// 剧情：左侧剧情组目录，右侧是剧情组概览或分集阅读。
import { D, loadStory } from './data.js';
import { esc, href, epLabel, groupLabel, charChip, powerChip, eventItem, threadColor } from './util.js';

let root, side, content, cat = '主线', filter = '', renderToken = 0;

export function mount(el, r) {
  root = el;
  el.innerHTML = `
    <aside class="side panel">
      <div class="seg-ctrl">${['主线', '活动', '故事集', '干员密录'].map((c) => `<button data-cat="${c}">${c}</button>`).join('')}</div>
      <input type="search" class="st-q" placeholder="筛选剧情组…">
      <div class="list"></div>
    </aside>
    <section class="content panel"></section>`;
  side = el.querySelector('.side');
  content = el.querySelector('.content');
  side.querySelector('.seg-ctrl').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b) { cat = b.dataset.cat; renderList(); }
  });
  const q = side.querySelector('.st-q');
  q.addEventListener('input', () => { filter = q.value.trim(); renderList(); });
  update(r);
}

export function update(r) {
  const [gid, sid] = r.parts;
  const g = D.groupById[gid] ?? D.groups[0];
  cat = g.category;
  renderList(g.id);
  if (sid && D.epById[sid]) renderEpisode(sid, parseLines(r.params.get('l')));
  else renderGroup(g);
  content.scrollTop = 0;
}

function renderList(activeId) {
  activeId ??= side.querySelector('.list-item.active')?.dataset.gid;
  side.querySelectorAll('.seg-ctrl button').forEach((b) => b.classList.toggle('active', b.dataset.cat === cat));
  const gs = D.groups.filter((g) => (filter ? g.name.includes(filter) : g.category === cat));
  side.querySelector('.list').innerHTML = gs.map((g) => `
    <a class="list-item${g.id === activeId ? ' active' : ''}" data-gid="${g.id}" href="${href.group(g.id)}">
      <span class="n" style="color:${threadColor(g.id)}">●</span>
      <span class="grow">${esc(groupLabel(g))}</span>
      <span class="n">${g.chapter != null ? `${g.episodes.length} 集` : esc(g.date?.slice(0, 7) ?? '')}</span></a>`).join('');
  side.querySelector('.list-item.active')?.scrollIntoView({ block: 'nearest' });
}

function aggregate(g) {
  const lines = {}, eps = {};
  for (const e of g.episodes) for (const [n, c] of e.chars) { lines[n] = (lines[n] ?? 0) + c; eps[n] = (eps[n] ?? 0) + 1; }
  return Object.keys(lines).sort((a, b) => lines[b] - lines[a] || eps[b] - eps[a]).map((n) => [n, lines[n], eps[n]]);
}

function renderGroup(g) {
  renderToken++;
  const chars = aggregate(g);
  const powers = {};
  for (const e of g.episodes) for (const [p, c] of e.powers) powers[p] = (powers[p] ?? 0) + c;
  const evs = g.events.map((id) => D.eventById[id]);
  content.innerHTML = `
    <h1>${esc(g.name)}</h1>
    <div class="sub">${esc(g.category)} · ${g.chapter != null ? esc(g.label) : `${esc(g.date ?? '')} 开放`} · 共 ${g.episodes.length} 集</div>
    <div class="actions">
      <a class="btn" href="${href.ep(g.episodes[0].id)}">从第一集开始读</a>
      ${evs.length ? `<a class="btn" href="${href.timeline({ thread: g.id })}">在时间轴中查看（${evs.length} 条事件）</a>` : ''}
    </div>
    <h4>出场人物（按台词数）</h4>
    <div class="chips">${chars.slice(0, 40).map(([n, l]) => charChip(n, `<span class="n">${l}</span>`)).join('')}</div>
    ${Object.keys(powers).length ? `<h4>提及的地区与势力</h4><div class="chips">${Object.entries(powers).sort((a, b) => b[1] - a[1]).map(([p, c]) => powerChip(p, `<span class="n">${c}</span>`)).join('')}</div>` : ''}
    <h4>分集</h4>
    <div class="ep-list">${g.episodes.map((e) => `
      <a class="ep-item" href="${href.ep(e.id)}">
        <span><span class="code">${esc(e.code || e.title)}</span><span class="avg">${esc(e.code ? e.title : '')} ${esc(e.avg)}</span></span>
        <span class="syn">${esc(e.synopsis)}</span></a>`).join('')}</div>
    ${evs.length ? `<h4>年表中的相关事件</h4>${evs.map(eventItem).join('')}` : ''}`;
}

// ?l=12-18,20-22 → 要高亮的行号集合（编年史引文跳转过来时用）
function parseLines(spec) {
  const hl = new Set();
  for (const part of (spec ?? '').split(',').filter(Boolean)) {
    const [a, b = a] = part.split('-').map(Number);
    for (let i = a; i <= b; i++) hl.add(i);
  }
  return hl;
}

async function renderEpisode(sid, hl = new Set()) {
  const { ep, group: g, index } = D.epById[sid];
  const prev = g.episodes[index - 1], next = g.episodes[index + 1];
  const nav = `<div class="reader-nav">
      ${prev ? `<a class="btn" href="${href.ep(prev.id)}">← ${esc(epLabel(prev))}</a>` : '<span></span>'}
      ${next ? `<a class="btn" href="${href.ep(next.id)}">${esc(epLabel(next))} →</a>` : `<a class="btn" href="${href.group(g.id)}">返回目录</a>`}</div>`;
  const evs = ep.events.map((id) => D.eventById[id]);
  content.innerHTML = `
    <div class="sub"><a href="${href.group(g.id)}">${esc(groupLabel(g))}</a> · 第 ${index + 1} / ${g.episodes.length} 集</div>
    <h1>${esc(epLabel(ep))}</h1>
    ${ep.synopsis ? `<div class="synopsis">${esc(ep.synopsis)}</div>` : ''}
    <div class="chips">${ep.chars.map(([n, l]) => charChip(n, l ? `<span class="n">${l}</span>` : '')).join('')}</div>
    ${ep.others.length ? `<div class="small muted" style="margin-top:6px">其他说话人：${ep.others.map(([n, c]) => `${esc(n)} ${c}`).join(' · ')}</div>` : ''}
    ${ep.stamps.length ? `<div class="small" style="margin-top:6px">📍 ${ep.stamps.map((s) => esc(s.filter(Boolean).join(' · '))).join('；')}</div>` : ''}
    ${evs.length ? `<h4>年表中的相关事件</h4>${evs.map(eventItem).join('')}` : ''}
    ${nav}
    <div class="script muted">正在加载剧本…</div>
    ${nav}`;
  const token = ++renderToken;
  const story = await loadStory(g.id);
  const box = content.querySelector('.script');
  if (token !== renderToken || !box) return;  // 加载期间已跳到别的页面
  box.classList.remove('muted');
  box.innerHTML = story[sid].lines.map((ln, i) => renderLine(ln)
    .replace('<div class="ln', `<div id="L${i + 1}" class="ln${hl.has(i + 1) ? ' hl' : ''}`)).join('');
  if (hl.size) box.querySelector('.ln.hl')?.scrollIntoView({ block: 'center' });
}

function renderLine([k, sp, t]) {
  if (k === 'd') {
    const c = D.chars[sp];
    const cls = c ? c.kind : 'plain';
    const name = sp ? (c ? `<a href="${href.char(sp)}">${esc(sp)}</a>` : esc(sp)) : '（画外音）';
    return `<div class="ln d"><span class="sp ${cls}" title="${esc(sp)}">${name}</span><span>${esc(t)}</span></div>`;
  }
  if (k === 'n') return `<div class="ln n">${esc(t)}</div>`;
  if (k === 'c') return `<div class="ln c"><span class="small muted">博士的选项</span>${t.map((o) => `<span class="opt">▸ ${esc(o)}</span>`).join('')}</div>`;
  if (k === 'b') return `<div class="ln b">〔选项 ${esc(t)} 的分支〕</div>`;
  if (k === 's') return `<div class="ln s">📍 ${esc(t)}</div>`;
  return '';
}
