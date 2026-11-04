// 编年史：左侧是卷目、月份和纪事本末，右侧按卷或按事连读。考异默认折叠。
// 路由：#/annals/1097（一卷）、#/annals/1097?e=ev0536（跳到某条）、#/annals/1097?s=正月（跳到某月）、
//      #/annals/本末/<事名>（纪事本末）、#/annals/凡例
import { D } from './data.js';
import { esc, href, charChip } from './util.js';

let side, content, shown = null;

export function mount(el, r) {
  shown = null;
  if (!D.annals?.volumes?.length) {
    el.innerHTML = '<div class="loading">还没有编年史数据。请先运行 python -m pipeline.annals build，再刷新页面。</div>';
    return;
  }
  el.innerHTML = `
    <aside class="side panel"><div class="list an-side"></div></aside>
    <section class="content panel"></section>`;
  side = el.querySelector('.an-side');
  content = el.querySelector('.content');
  update(r);
}

export function update(r) {
  if (!content) return;
  const [a, b] = r.parts;
  let vol = null;
  if (a === '本末' && D.benmoByTitle[b]) renderBenmo(D.benmoByTitle[b]);
  else if (a === '凡例') renderFanli();
  else {
    vol = D.annals.volumes.find((v) => String(v.year) === a) ?? D.annals.volumes[0];
    renderVolume(vol);
  }
  renderSide(vol, a === '本末' ? b : a === '凡例' ? '凡例' : null);
  jump(r.params, vol);
}

export function unmount() {
  content = side = null;
}

// ---------------------------------------------------------------- 左栏

function renderSide(vol, activeOther) {
  const vols = D.annals.volumes.map((v) => {
    const active = vol && v.year === vol.year;
    const toc = active ? v.sections.map((s) => `
      <a class="list-item an-toc" href="#/annals/${v.year}?s=${encodeURIComponent(s.label)}">
        <span class="grow">${esc(s.label)}</span><span class="n">${countGang(s)}</span></a>`).join('') : '';
    return `<a class="list-item${active ? ' active' : ''}" href="${href.annals(v.year)}">
        <span class="grow">${esc(v.title.replace('结晶纪元', ''))}</span><span class="n">${v.stats.gang} 纲</span></a>${toc}`;
  }).join('');
  const benmo = D.annals.benmo.map((b) => `
    <a class="list-item${activeOther === b.title ? ' active' : ''}" href="${href.benmo(b.title)}">
      <span class="grow">${esc(b.title)}</span><span class="n">${b.entries.length} 条</span></a>`).join('');
  side.innerHTML = `
    <div class="list-head">编年 · 按年</div>${vols}
    ${benmo ? `<div class="list-head">纪事本末 · 按事</div>${benmo}` : ''}
    <div class="list-head">说明</div>
    <a class="list-item${activeOther === '凡例' ? ' active' : ''}" href="#/annals/凡例"><span class="grow">凡例</span></a>`;
}

const countGang = (s) => s.days.reduce((n, d) => n + d.entries.reduce((m, e) => m + e.groups.length, 0), 0);

// ---------------------------------------------------------------- 正文

function renderVolume(v) {
  const key = `vol:${v.year}`;
  if (shown === key) return;
  shown = key;
  const i = D.annals.volumes.indexOf(v);
  const prev = D.annals.volumes[i - 1], next = D.annals.volumes[i + 1];
  const st = v.stats;
  content.innerHTML = `<div class="an-body">
    <div class="sub">泰拉编年史</div>
    <h1>${esc(v.title)}</h1>
    <div class="sub">${st.entries} 条年表事件 · ${st.gang} 组纲目 · ${st.quotes} 段原文 · 撰文 ${st.prose.toLocaleString()} 字，引文 ${st.quote_chars.toLocaleString()} 字 · <a href="#/annals/凡例">凡例</a></div>
    ${controls()}
    ${v.sections.map((s) => `
      <section class="an-sec" id="${secId(v.year, s.label)}">
        <h2>${esc(s.label)}</h2>
        ${s.days.map((d) => `${d.label ? `<h3 class="an-day">${esc(d.label)}</h3>` : ''}${d.entries.map((e) => entryHtml(e)).join('')}`).join('')}
      </section>`).join('')}
    <div class="reader-nav">
      ${prev ? `<a class="btn" href="${href.annals(prev.year)}">← ${esc(prev.title)}</a>` : '<span></span>'}
      ${next ? `<a class="btn" href="${href.annals(next.year)}">${esc(next.title)} →</a>` : '<span></span>'}
    </div></div>`;
  wireControls();
}

function renderBenmo(b) {
  const key = `benmo:${b.title}`;
  if (shown === key) return;
  shown = key;
  const entries = b.entries.map(({ id }) => D.annalsEntry[id]).filter(Boolean);
  content.innerHTML = `<div class="an-body">
    <div class="sub">纪事本末</div>
    <h1>${esc(b.title)}</h1>
    <div class="sub">${esc(b.span[0])}${b.span[1] !== b.span[0] ? ` 至 ${esc(b.span[1])}` : ''} · ${entries.length} 条</div>
    ${b.summary.length ? `<div class="synopsis an-summary">${b.summary.map((p) => `<p>${inline(p)}</p>`).join('')}</div>` : ''}
    <details class="an-index"><summary>按时间列出各条纲（${entries.reduce((n, e) => n + e.groups.length, 0)} 组）</summary>
      <ol>${entries.map((e) => e.groups.map((g) => `
        <li><a href="${href.benmo(b.title)}?e=${e.id}"><span class="when">${esc(e.when)}</span>${inline(g.gang)}</a></li>`).join('')).join('')}</ol>
    </details>
    ${controls()}
    ${entries.map((e) => entryHtml(e, true)).join('')}
  </div>`;
  wireControls();
}

function renderFanli() {
  if (shown === 'fanli') return;
  shown = 'fanli';
  content.innerHTML = `<div class="an-body">
    <div class="sub">泰拉编年史</div>
    <h1>凡例</h1>
    <ul class="an-fanli">${D.annals.fanli.map((l) => `<li>${inline(l)}</li>`).join('')}</ul>
    <h4>各卷</h4>
    ${D.annals.volumes.map((v) => `<p><a class="btn" href="${href.annals(v.year)}">${esc(v.title)}</a>
      <span class="muted small">${v.stats.gang} 组纲目，${v.stats.quotes} 段原文</span></p>`).join('')}
    ${D.annals.benmo.length ? `<h4>纪事本末</h4><div class="chips">${D.annals.benmo.map((b) => `<a class="chip chip-plain" href="${href.benmo(b.title)}">${esc(b.title)}</a>`).join('')}</div>` : ''}
  </div>`;
}

function controls() {
  return `<div class="an-controls">
    <label class="toggle"><input type="checkbox" data-ctl="gang"> 只看纲</label>
    <label class="toggle"><input type="checkbox" data-ctl="kaoyi"> 展开全部考异</label>
  </div>`;
}

function wireControls() {
  content.querySelector('[data-ctl=gang]')?.addEventListener('change', (e) => {
    content.classList.toggle('gang-only', e.target.checked);
  });
  content.querySelector('[data-ctl=kaoyi]')?.addEventListener('change', (e) => {
    content.querySelectorAll('details.an-kaoyi').forEach((d) => { d.open = e.target.checked; });
  });
  content.classList.remove('gang-only');
}

const secId = (year, label) => `an-sec-${year}-${label}`;

function jump(params, vol) {
  const e = params.get('e'), s = params.get('s');
  const el = e ? content.querySelector(`#an-${CSS.escape(e)}`)
    : s && vol ? content.querySelector(`#${CSS.escape(secId(vol.year, s))}`) : null;
  if (!el) {
    content.scrollTop = 0;
    return;
  }
  el.scrollIntoView({ block: 'start' });
  if (e) {
    el.classList.remove('flash');
    void el.offsetWidth;  // 重新触发高亮动画
    el.classList.add('flash');
  }
}

// ---------------------------------------------------------------- 条目

function entryHtml(e, withWhen = false) {
  const evLinks = e.ids.filter((i) => D.eventById[i])
    .map((i) => `<a href="${href.event(i)}">时间轴：${esc(D.eventById[i].when)}</a>`);
  const benmo = e.benmo.map((t) => `<a href="${href.benmo(t)}">纪事本末：${esc(t)}</a>`);
  return `<article class="an-entry" id="an-${e.id}">
    ${withWhen ? `<div class="an-when"><a href="${href.annals(e.year, e.id)}">${esc(e.when)}</a></div>` : ''}
    ${e.groups.map((g) => `<div class="an-group">
      <div class="an-gang">${inline(g.gang)}</div>
      ${g.mu.map((p) => `<p class="an-mu">${inline(p)}</p>`).join('')}
      ${g.people.length ? `<div class="chips an-people">${g.people.map(personChip).join('')}</div>` : ''}
      ${g.quotes.map(quoteHtml).join('')}
      ${kaoyiHtml(g.kaoyi)}
    </div>`).join('')}
    <div class="an-meta">${[...evLinks, ...benmo].join('<span class="dot">·</span>')}</div>
  </article>`;
}

// 正文里只有两种标记：**加粗** 和 [[人名]]
function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g, (_, name, label) => (D.chars[name]
      ? `<a class="an-p" href="${href.char(name)}">${label ?? name}</a>` : (label ?? name)));
}

function personChip(token) {
  const m = token.match(/^\[\[([^\]|]+)\]\]$/);
  return m ? charChip(m[1]) : `<span class="chip chip-plain">${inline(token)}</span>`;
}

function quoteHtml(q) {
  if (q.type === 'story') {
    const lines = q.ranges.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(',');
    const body = q.blocks.map((b) => b.map(quoteLine).join('')).join('<div class="ql gap">……</div>');
    return `<blockquote class="an-quote">${body}
      <cite><a href="${href.ep(q.sid)}?l=${lines}" title="在剧情页中查看上下文">——${esc(q.label)}</a></cite></blockquote>`;
  }
  return `<blockquote class="an-quote">${q.paras.map((p) => `<p class="ql pr">${esc(p)}</p>`).join('')}
    <cite><a href="${href.char(q.name)}">——${esc(q.label)}</a></cite></blockquote>`;
}

function quoteLine([k, sp, t]) {
  if (k === 'd') return `<div class="ql d">${sp ? `<span class="sp">${esc(sp)}</span>` : ''}<span>${esc(t)}</span></div>`;
  if (k === 'n') return `<div class="ql n">${esc(t)}</div>`;
  if (k === 'c') return `<div class="ql d c"><span class="sp">${esc(sp)}（选项）</span><span>${esc(t)}</span></div>`;
  if (k === 's') return `<div class="ql s">📍 ${esc(t)}</div>`;
  return '';
}

function kaoyiHtml(items) {
  if (!items.length) return '';
  let html = '', list = [];
  const flush = () => {
    if (list.length) html += `<ul>${list.join('')}</ul>`;
    list = [];
  };
  for (const k of items) {
    if (k.li) list.push(`<li>${inline(k.text)}</li>`);
    else { flush(); html += `<p>${inline(k.text)}</p>`; }
  }
  flush();
  return `<details class="an-kaoyi"><summary>考异</summary>${html}</details>`;
}
