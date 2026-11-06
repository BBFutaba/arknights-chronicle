// 编年史：左侧是卷目和月份，右侧按卷连读。考异默认折叠。条目的渲染也给列传、纪事本末用。
// 路由：#/annals/1097（一卷）、#/annals/1097?e=ev0536（跳到某条）、#/annals/1097?s=正月（跳到某月）
import { D } from './data.js';
import { esc, href, charChip, charOf, pageHead } from './util.js';

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
  const [a] = r.parts;
  const vol = D.annals.volumes.find((v) => String(v.year) === a)
    ?? D.annals.volumes.find((v) => v.year === 1096) ?? D.annals.volumes[0];
  renderVolume(vol);
  renderSide(vol);
  jump(r.params, vol);
}

export function unmount() {
  content = side = null;
}

// ---------------------------------------------------------------- 左栏

function renderSide(vol) {
  // 前纪、外纪在主线之前：分两段显示
  const group = (v) => (v.year === '不系年' ? '不系年' : typeof v.year === 'number' && v.year >= 1096 ? '主线' : '前纪与外纪');
  const vols = D.annals.volumes.map((v, i, all) => {
    const head = i === 0 || group(all[i - 1]) !== group(v) ? `<div class="an-vol-group muted">${group(v)}</div>` : '';
    const active = vol && v.year === vol.year;
    const toc = active ? v.sections.map((s) => `
      <a class="list-item an-toc" href="#/annals/${v.year}?s=${encodeURIComponent(s.label)}">
        <span class="grow">${esc(s.label)}</span><span class="n">${countGang(s)}</span></a>`).join('')
      + (v.cunmu?.length ? `<a class="list-item an-toc" href="#/annals/${v.year}?s=存目">
        <span class="grow muted">存目</span><span class="n">${v.cunmu.length}</span></a>` : '') : '';
    return `${head}<a class="list-item${active ? ' active' : ''}" href="${href.annals(v.year)}">
        <span class="grow">${esc(v.title.replace(/^泰拉历/, ''))}</span><span class="n">${v.stats.gang} 纲</span></a>${toc}`;
  }).join('');
  side.innerHTML = `
    <div class="list-head">编年 · 按年</div>${vols}`;
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
  content.innerHTML = `${pageHead({
    en: `VOLUME ${String(i + 1).padStart(2, '0')}/${D.annals.volumes.length}`,
    title: v.title,
    nums: [
      ['条目', st.entries, '条', 'ENTRIES'], ['纲目', st.gang, '组', 'HEADINGS'], ['原文', st.quotes, '段', 'QUOTES'],
      ['撰文', st.prose, '字', 'WRITTEN'], ['引文', st.quote_chars, '字', 'CITED'],
    ],
  })}<div class="an-body">
    ${controlsHtml()}
    ${v.sections.map((s) => `
      <section class="an-sec" id="${secId(v.year, s.label)}">
        <h2><span>${esc(s.label)}</span></h2>
        ${s.days.map((d) => `${d.label ? `<h3 class="an-day">${esc(d.label)}</h3>` : ''}${d.entries.map((e) => entryHtml(e)).join('')}`).join('')}
      </section>`).join('')}
    ${v.cunmu?.length ? `<section class="an-sec an-cunmu" id="${secId(v.year, '存目')}"><h2><span>存目</span></h2>
      <p class="muted small">以下年表事件于人于事没有推力，不入正文，只存其目。</p>
      <ol>${v.cunmu.map((c) => `<li id="an-${c.id}"><span class="when">${esc(c.prts)}</span>${inline(c.gang)}
        ${c.kaoyi.length ? `<div class="small muted">${c.kaoyi.map((k) => inline(k.text)).join(' ')}</div>` : ''}</li>`).join('')}</ol>
    </section>` : ''}
    <div class="reader-nav">
      ${prev ? `<a class="btn" href="${href.annals(prev.year)}">← ${esc(prev.title)}</a>` : '<span></span>'}
      ${next ? `<a class="btn" href="${href.annals(next.year)}">${esc(next.title)} →</a>` : '<span></span>'}
    </div></div>`;
  wireControls(content);
}

export function controlsHtml() {
  return `<div class="an-controls">
    <label class="toggle"><input type="checkbox" data-ctl="gang"> 只看纲</label>
    <label class="toggle"><input type="checkbox" data-ctl="kaoyi"> 展开全部考异</label>
  </div>`;
}

export function wireControls(el) {
  el.querySelector('[data-ctl=gang]')?.addEventListener('change', (e) => {
    el.classList.toggle('gang-only', e.target.checked);
  });
  el.querySelector('[data-ctl=kaoyi]')?.addEventListener('change', (e) => {
    el.querySelectorAll('details.an-kaoyi').forEach((d) => { d.open = e.target.checked; });
  });
  el.classList.remove('gang-only');
}

const secId = (year, label) => `an-sec-${year}-${label}`;

function jump(params, vol) {
  const s = params.get('s');
  const el = !params.get('e') && s && vol ? content.querySelector(`#${CSS.escape(secId(vol.year, s))}`) : null;
  if (el) el.scrollIntoView({ block: 'start' });
  else jumpToEntry(content, params);
}

export function jumpToEntry(box, params) {
  const e = params.get('e');
  const el = e ? box.querySelector(`#an-${CSS.escape(e)}`) : null;
  if (!el) {
    box.scrollTop = 0;
    return;
  }
  el.scrollIntoView({ block: 'start' });
  el.classList.remove('flash');
  void el.offsetWidth;  // 重新触发高亮动画
  el.classList.add('flash');
}

// ---------------------------------------------------------------- 条目

export function entryHtml(e, withWhen = false) {
  const evLinks = e.ids.filter((i) => D.eventById[i])
    .map((i) => `<a href="${href.event(i)}">时间轴：${esc(D.eventById[i].when)}</a>`);
  const benmo = e.benmo.map((t) => `<a href="${href.benmo(t)}">纪事本末：${esc(t)}</a>`);
  benmo.push(...(e.zhuan ?? []).map((n) => `<a href="${href.zhuan(n)}">列传：${esc(n)}传</a>`));
  if (e.minor) {
    // 附记：只有纲和考异，小字附在当日
    return `<article class="an-entry minor" id="an-${e.id}">
      ${withWhen ? `<div class="an-when"><a href="${href.annals(e.year, e.id)}">${esc(e.when)}</a></div>` : ''}
      ${e.groups.map((g) => `<div class="an-gang"><span class="an-tag">附</span>${inline(g.gang)}</div>${kaoyiHtml(g.kaoyi)}`).join('')}
      <div class="an-meta">${[...evLinks, ...benmo].join('<span class="dot">·</span>')}</div>
    </article>`;
  }
  return `<article class="an-entry" id="an-${e.id}">
    ${withWhen ? `<div class="an-when"><a href="${href.annals(e.year, e.id)}">${esc(e.when)}</a></div>` : ''}
    ${e.groups.map((g) => `<div class="an-group">
      <div class="an-gang">${inline(g.gang)}</div>
      ${g.mu.map((p) => `<p class="an-mu">${inline(p)}</p>`).join('')}
      ${g.people.length ? `<div class="chips an-people">${g.people.map(personChip).join('')}</div>` : ''}
      ${g.intro?.length ? `<div class="an-intro">${g.intro.map((i) => `<div><span class="an-tag">初见</span>${inline(`[[${i.name}]]`)}：${inline(i.text)}</div>`).join('')}</div>` : ''}
      ${g.quotes.map(quoteHtml).join('')}
      ${kaoyiHtml(g.kaoyi)}
    </div>`).join('')}
    <div class="an-meta">${[...evLinks, ...benmo].join('<span class="dot">·</span>')}</div>
  </article>`;
}

// 正文里只有两种标记：**加粗** 和 [[人名]]
// other：不是人物时怎么办，博物志用它把 [[条目]] 也变成链接
export function inline(s, other) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g, (_, name, label) => (charOf(name)
      ? `<a class="an-p" href="${href.char(name)}">${label ?? name}</a>` : (other?.(name, label) ?? label ?? name)));
}

function personChip(token) {
  const m = token.match(/^\[\[([^\]|]+)\]\]$/);
  return m ? charChip(m[1]) : `<span class="chip chip-plain">${inline(token)}</span>`;
}

export function quoteHtml(q) {
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
  if (k === 's') return `<div class="ql s">${esc(t)}</div>`;
  return '';
}

export function kaoyiHtml(items, other) {
  if (!items.length) return '';
  let html = '', list = [];
  const flush = () => {
    if (list.length) html += `<ul>${list.join('')}</ul>`;
    list = [];
  };
  for (const k of items) {
    if (k.li) list.push(`<li>${inline(k.text, other)}</li>`);
    else { flush(); html += `<p>${inline(k.text, other)}</p>`; }
  }
  flush();
  return `<details class="an-kaoyi"><summary>考异</summary>${html}</details>`;
}
