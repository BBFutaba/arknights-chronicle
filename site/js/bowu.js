// 博物志：左侧按门列目录，门下有层级就缩进；右侧是条目。
// 一地一页：地理、势力两门列出全部地区势力，还没写正文的标「尚未成文」；条目写了 关: 的，正文下面接地区势力的资料。
// 路由：#/bowu/<条目名或别名>。旧路由 #/powers/<id> 在 main.js 里转到这里。
import { D } from './data.js';
import { esc, href, powerChip, eventItem, pageHead } from './util.js';

const MEN_EN = { 地理: 'GEOGRAPHY', 势力: 'POWERS', 族裔: 'PEOPLES', 源石: 'ORIGINIUM', 科技: 'SCIENCE', 人文: 'CULTURE', 生灵: 'CREATURES', 远古: 'ANTIQUITY' };
import { inline, quoteHtml, kaoyiHtml } from './annals.js';
import { powerSections } from './powers.js';

let side, content, nodes = null, nodeByKey = {};
let q = '', men = '', onlyWritten = false;

// ---------------------------------------------------------------- 目录数据

const eventCount = (pid) => (pid ? D.powers[pid].events.length : -1);

// 每一页是一个节点：有条目的用条目名，没有的用地区势力的名字。
function buildNodes() {
  if (nodes) return;
  const P = D.powers;
  const pageOfPower = (pid) => D.bowu.powers[pid]?.entry ?? P[pid].name;
  const parentOfPower = (pid) => (P[pid].parent ? pageOfPower(P[pid].parent) : null);
  const list = D.bowu.entries.map((w) => {
    const pid = w.main[0] ?? null;
    return { name: w.name, men: w.men, entry: w, pid, keys: [w.name, ...w.aliases, ...w.main.map((p) => P[p].name)],
      up: w.parent ?? (pid ? parentOfPower(pid) : null) };
  });
  for (const [pid, p] of Object.entries(P)) {
    if (D.bowu.powers[pid]?.entry) continue;
    list.push({ name: p.name, men: p.kind === 'region' ? '地理' : '势力', entry: null, pid, keys: [p.name], up: parentOfPower(pid) });
  }
  // 地区势力按事件多少排，和原来一样；别的条目按稿件顺序排在后面
  list.sort((a, b) => eventCount(b.pid) - eventCount(a.pid));
  for (const n of list) nodeByKey[n.name] = n;
  for (const n of list) for (const k of n.keys) nodeByKey[k] ??= n;  // 别名，和地区势力自己的名字
  for (const n of list) n.kids = [];
  for (const n of list) {
    const up = nodeByKey[n.up];
    n.parentNode = up && up.men === n.men ? up : null;  // 上级在别的门：这里算顶层，页面上仍写明上级
    n.parentNode?.kids.push(n);
  }
  nodes = list;
}

function resolve(name) {
  if (!name) return nodeByKey['罗德岛'] ?? nodes[0];
  return nodeByKey[name] ?? nodeByKey[D.powers[name]?.name];
}

// ---------------------------------------------------------------- 视图

export function mount(el, r) {
  buildNodes();
  el.innerHTML = `
    <aside class="side panel bw-side">
      <input type="search" class="bw-q" placeholder="筛选条目（名字、别名）…">
      <div class="seg-ctrl bw-men">${['', ...D.bowu.men].map((m) => `<button data-m="${m}">${m || '全部'}</button>`).join('')}</div>
      <label class="toggle bw-written"><input type="checkbox"> 只看已成文</label>
      <div class="list"></div>
    </aside>
    <section class="content panel"></section>`;
  side = el.querySelector('.side');
  content = el.querySelector('.content');
  const qi = side.querySelector('.bw-q');
  qi.value = q;
  qi.addEventListener('input', () => { q = qi.value.trim(); renderList(); });
  side.querySelector('.bw-men').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b) { men = b.dataset.m; renderList(); }
  });
  const wi = side.querySelector('.bw-written input');
  wi.checked = onlyWritten;
  wi.addEventListener('change', () => { onlyWritten = wi.checked; renderList(); });
  // 页头的八门：点一门，左栏只列这一门
  content.addEventListener('click', (e) => {
    const t = e.target.closest('.men-tile');
    if (t) { men = t.dataset.m; renderList(); }
  });
  update(r);
}

export function update(r) {
  const n = resolve(r.parts[0]);
  renderList(n?.name);
  if (n) renderPage(n);
  else content.innerHTML = `${pageHead({ en: 'NOT FOUND', title: r.parts[0] })}<p class="muted">博物志里没有这个条目。</p>`;
  content.scrollTop = 0;
}

export function unmount() {
  side = content = null;
}

// ---------------------------------------------------------------- 左栏

function renderList(activeName) {
  activeName ??= side.querySelector('.list-item.active')?.dataset.name;
  side.querySelectorAll('.bw-men button').forEach((b) => b.classList.toggle('active', b.dataset.m === men));
  const ql = q.toLowerCase();
  const filtering = q || onlyWritten;
  const hit = (n) => (!onlyWritten || n.entry) && (!q || n.keys.some((k) => k.toLowerCase().includes(ql)));
  const item = (n, depth) => {
    const color = n.pid ? `var(--c-${D.powers[n.pid].kind})` : 'var(--accent)';
    return `<a class="list-item${n.name === activeName ? ' active' : ''}" data-name="${esc(n.name)}" href="${href.wu(n.name)}"
        style="padding-left:${8 + depth * 16}px"${n.entry ? '' : ' title="尚未成文"'}>
        <span class="n" style="color:${color}">${n.entry ? '●' : '○'}</span><span class="grow${n.entry ? '' : ' muted'}">${esc(n.name)}</span>
        ${n.pid ? `<span class="n">${D.powers[n.pid].events.length} 事件</span>` : ''}</a>`;
  };
  const tree = (n, depth) => item(n, depth) + n.kids.map((k) => tree(k, depth + 1)).join('');
  const sections = D.bowu.men.filter((m) => !men || m === men).map((m) => {
    const own = nodes.filter((n) => n.men === m);
    const body = filtering ? own.filter(hit).map((n) => item(n, 0)).join('')
      : own.filter((n) => !n.parentNode).map((n) => tree(n, 0)).join('');
    if (filtering && !body) return '';
    return `<div class="list-head">${m} <span class="n">${own.filter((n) => n.entry).length} / ${own.length}</span></div>
      ${body || '<div class="muted small bw-empty">尚无条目</div>'}`;
  }).join('');
  side.querySelector('.list').innerHTML = sections || '<div class="muted small bw-empty">没有符合的条目</div>';
  side.querySelector('.list-item.active')?.scrollIntoView({ block: 'nearest' });
}

// ---------------------------------------------------------------- 条目

function renderPage(n) {
  const w = n.entry;
  const P = D.powers;
  const mains = w ? w.main : [n.pid];
  const others = w ? w.powers.filter((p) => !w.main.includes(p)) : [];
  const related = mains.flatMap((p) => D.bowu.powers[p]?.related ?? []);
  const kind = n.pid ? P[n.pid].kind : 'plain';
  const named = w ? w.main.filter((p) => P[p].name !== n.name) : [];
  const subs = [
    w?.aliases.length ? `别名：${w.aliases.map(esc).join('、')}` : '',
    named.length ? `对应：${named.map((p) => esc(P[p].name)).join('、')}` : '',
    w?.parent && !w.main.length ? `上级：<a class="bw-link" href="${href.wu(w.parent)}">${esc(w.parent)}</a>` : '',
  ].filter(Boolean);
  content.innerHTML = `${pageHead({
    en: MEN_EN[n.men] ?? 'ENCYCLOPEDIA',
    title: n.name,
    sub: subs.join(' · '),
    tags: `<span class="chip chip-${kind}">${esc(n.men)}</span>${w ? '' : '<span class="chip chip-plain bw-unwritten">尚未成文</span>'}`,
    aside: `<div class="men-tiles">${D.bowu.men.map((m) => `<button class="men-tile${m === n.men ? ' hot' : ''}" data-m="${m}">
      <span>${esc(m)}</span><em>${MEN_EN[m] ?? ''}</em></button>`).join('')}</div>`,
  })}
    ${w ? `<div class="bw-text">${entryBody(w)}</div>` : ''}
    ${mains.map((p) => `${w ? `<h3 class="bw-part">${esc(P[p].name)}的资料</h3>` : ''}${powerSections(p)}`).join('')}
    ${others.length ? `<h3 class="bw-part">相关的地区势力</h3>${others.map((p) => `
      <details class="bw-related"><summary>${esc(P[p].name)}</summary>
        <div class="chips">${powerChip(p)}</div>${powerSections(p)}</details>`).join('')}` : ''}
    ${related.length ? `<h4>相关条目</h4><div class="chips">${related.map((name) => `<a class="chip chip-plain" href="${href.wu(name)}">${esc(name)}</a>`).join('')}</div>` : ''}
    ${mentionsHtml(w ? w.mentions : D.bowu.powers[n.pid]?.mentions)}`;
}

function entryBody(w) {
  const b = w.blocks;
  return `${blocksHtml(b.shi)}
    ${b.shuo.length ? `<h4>各家说法</h4>${blocksHtml(b.shuo)}` : ''}
    ${b.yange.length ? `<h4>沿革</h4>${blocksHtml(b.yange)}` : ''}
    ${seeHtml(w)}
    ${kaoyiHtml(w.kaoyi, wuLink)}`;
}

// 正文里的 [[名字]]：人物优先，其次是博物志条目和地区势力
function wuLink(name, label) {
  return resolve(name) ? `<a class="bw-link" href="${href.wu(name)}">${label ?? name}</a>` : null;
}

function blocksHtml(items) {
  return items.map((x) => (typeof x === 'string' ? `<p class="an-mu">${inline(x, wuLink)}</p>` : anyQuote(x))).join('');
}

function anyQuote(q) {
  if (q.type === 'book') return bookQuote(q);
  if (q.type === 'video' || q.type === 'comic' || q.type === 'record') {
    const where = q.type === 'video' ? `《${esc(q.title)}》${esc(q.time)}`
      : q.type === 'record' ? `《泰拉记事·${esc(q.title)}》`
      : `《${esc(q.title)}》${esc(q.ep)} ${esc(q.page)}`;
    return `<blockquote class="an-quote"><p class="ql">${esc(q.text)}</p>
      <cite class="bw-cite">——${q.who ? `${esc(q.who)} · ` : ''}${where}</cite></blockquote>`;
  }
  return quoteHtml(q);
}

// 设定集是世界观内的人物写的：埃里克森的正文署本人名字，凯尔希的手写批注用另一种样式
function bookQuote(q) {
  const src = `《${esc(q.title)}》${esc(q.page)}`;
  if (q.style === 'note') {
    return `<aside class="bw-note"><p>${esc(q.text)}</p><cite class="bw-cite">${esc(q.sign)} · ${src}</cite></aside>`;
  }
  return `<blockquote class="bw-book${q.style === 'author' ? ' bw-author' : ''}"><p>${esc(q.text)}</p>
    <cite class="bw-cite">——${q.sign ? `${esc(q.sign)} · ` : ''}${src}</cite></blockquote>`;
}

const plain = (s) => s.replace(/\*\*/g, '').replace(/\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g, (_, a, b) => b ?? a);

function seeEvent(id) {
  const e = D.annalsEntry[D.annalsByEvent[id] ?? id];
  if (e) {
    return `<a class="event-item bw-row" href="${href.annalsEntry(e.id)}"><span class="when">${esc(e.when)}</span>
      <span class="text">${esc(plain(e.groups[0].gang))}</span></a>`;
  }
  return D.eventById[id] ? eventItem(D.eventById[id]) : '';
}

function seeHtml(w) {
  const s = w.see;
  const chips = [
    ...s.zhuan.map((n) => `<a class="chip chip-plain" href="${D.zhuanByName[n] ? href.zhuan(n) : href.char(n)}">${esc(n)}${D.zhuanByName[n] ? '传' : ''}</a>`),
    ...s.shi.map((t) => `<a class="chip chip-plain" href="${href.benmo(t)}">${esc(t)}</a>`),
    ...s.wu.map((n) => `<a class="chip chip-plain" href="${href.wu(n)}">${esc(n)}</a>`),
  ];
  if (!chips.length && !s.events.length && !w.blocks.see.length) return '';
  return `<h4>参见</h4>
    ${chips.length ? `<div class="chips">${chips.join('')}</div>` : ''}
    ${s.events.map(seeEvent).join('')}
    ${blocksHtml(w.blocks.see)}`;
}

function mentionsHtml(m) {
  if (!m) return '';
  if (!m.total) return '<h4>书中提及</h4><p class="muted small">编年史的纲目和列传里没有写到。</p>';
  const counts = [m.annals ? `纲目 ${m.annals} 条` : '', m.zhuan ? `列传 ${m.zhuan} 篇` : ''].filter(Boolean).join('、');
  const items = m.items.map((it) => `
    <a class="event-item bw-row" href="${it.kind === 'annals' ? href.annalsEntry(it.ref) : href.zhuan(it.ref)}">
      <span class="when">${esc(it.when)}</span>
      <span class="text">${esc(it.pre)}<mark class="bw-hit">${esc(it.hit)}</mark>${esc(it.post)}</span></a>`).join('');
  return `<h4>书中提及（共 ${m.total} 处：${counts}${m.total > m.items.length ? `；列出 ${m.items.length} 处` : ''}）</h4>${items}`;
}
