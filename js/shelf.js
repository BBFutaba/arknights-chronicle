// 书架：列传和纪事本末共用。左栏是搜索、索引和结果，右栏是索引页或单篇。
// 筛选都写在地址里（#/zhuan?出身=乌萨斯&身后=已），可以收藏，也可以转发；点标签页回到不筛选的状态。
// cfg：route、title、unit（篇/件）、placeholder、intro（索引页的说明）
//      items()：[{ key, url, name, text（搜索用）, facets: {索引项: [值]}, line（索引页的一行身份）, tags（一行短标签）, n（条数）, sort: {排序名: 值} }]
//      facets：[{ key, order?（固定顺序）, open?, was?（改名前的旧名，收藏过的旧链接还能用） }]；groups：可选的分组；sorts：[排序名]，第一个是默认
//      resolve(key)：地址里的名字 → item；detail(item, el, params)：渲染单篇
import { D } from './data.js';
import { esc, pageHead } from './util.js';

export const OPTION_NONE = '不分组';
const OPTION_GROUP = '分组', OPTION_SORT = '排序', OPTION_Q = 'q';
const collator = new Intl.Collator('zh-u-co-pinyin');
const compare = (a, b) => (typeof a === 'number' && typeof b === 'number' ? a - b : collator.compare(String(a), String(b)));

export function makeShelf(cfg) {
  let side, content, items = null, shown = null;
  let state = freshState();

  function freshState() {
    return { q: '', group: cfg.groups[0], sort: cfg.sorts[0], picks: {} };
  }

  function readState(params) {
    state = freshState();
    state.q = params.get(OPTION_Q) ?? '';
    const group = cfg.facets.find((f) => f.was && f.was === params.get(OPTION_GROUP))?.key ?? params.get(OPTION_GROUP);
    state.group = cfg.groups.includes(group) ? group : cfg.groups[0];
    state.sort = cfg.sorts.includes(params.get(OPTION_SORT)) ? params.get(OPTION_SORT) : cfg.sorts[0];
    for (const f of cfg.facets) {
      const vals = [...params.getAll(f.key), ...(f.was ? params.getAll(f.was) : [])];
      if (vals.length) state.picks[f.key] = new Set(vals);
    }
  }

  // 索引页的地址；change 是对当前筛选的改动
  function indexUrl(change = {}) {
    const next = { ...state, picks: { ...state.picks }, ...change };
    const p = new URLSearchParams();
    if (next.q) p.set(OPTION_Q, next.q);
    if (next.group !== cfg.groups[0]) p.set(OPTION_GROUP, next.group);
    if (next.sort !== cfg.sorts[0]) p.set(OPTION_SORT, next.sort);
    for (const [k, set] of Object.entries(next.picks)) for (const v of set) p.append(k, v);
    const qs = p.toString();
    return `#/${cfg.route}${qs ? `?${qs}` : ''}`;
  }

  function toggled(key, value) {
    const set = new Set(state.picks[key] ?? []);
    if (set.has(value)) set.delete(value);
    else set.add(value);
    const picks = { ...state.picks };
    if (set.size) picks[key] = set;
    else delete picks[key];
    return indexUrl({ picks });
  }

  // skip：算某一项的计数时，不算这一项自己的筛选，这样同项的其他值还能看到数字
  function matches(item, skip) {
    const q = state.q.trim().toLowerCase();
    if (q && !item.text.includes(q)) return false;
    return Object.entries(state.picks).every(([k, set]) => k === skip || (item.facets[k] ?? []).some((v) => set.has(v)));
  }

  function results() {
    const by = state.sort;
    const list = items.filter((it) => matches(it));
    return list.sort((a, b) => compare(a.sort[by], b.sort[by]) || collator.compare(a.name, b.name));
  }

  // ---------------------------------------------------------------- 左栏

  function renderFacets() {
    const box = side.querySelector('.shelf-facets');
    const open = new Set([...box.querySelectorAll('details[open]')].map((d) => d.dataset.key));
    const first = !box.childElementCount;
    box.innerHTML = cfg.facets.map((f) => {
      const counts = new Map();
      for (const it of items) {
        if (matches(it, f.key)) for (const v of it.facets[f.key] ?? []) counts.set(v, (counts.get(v) ?? 0) + 1);
      }
      for (const v of state.picks[f.key] ?? []) if (!counts.has(v)) counts.set(v, 0);
      const vals = f.order ? f.order.filter((v) => counts.has(v))
        : [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || collator.compare(a, b));
      const picked = state.picks[f.key]?.size;
      const isOpen = first ? f.open || picked : open.has(f.key) || picked;
      return `<details data-key="${esc(f.key)}"${isOpen ? ' open' : ''}>
        <summary>${esc(f.key)}${picked ? `<span class="shelf-picked">${picked}</span>` : ''}</summary>
        <div class="shelf-chips">${vals.map((v) => `<a class="shelf-chip${state.picks[f.key]?.has(v) ? ' active' : ''}" href="${esc(toggled(f.key, v))}">${esc(f.label?.(v) ?? v)}<span class="n">${counts.get(v)}</span></a>`).join('')}</div>
      </details>`;
    }).join('');
  }

  function renderList(activeKey) {
    const list = results();
    const filtered = state.q || Object.keys(state.picks).length;
    side.querySelector('.shelf-count').innerHTML = `${filtered ? `筛出 ${list.length} / ${items.length} ${cfg.unit}` : `共 ${items.length} ${cfg.unit}`}
      ${filtered ? `<a class="shelf-clear" href="#/${cfg.route}">清除</a>` : ''}`;
    side.querySelector('.shelf-list').innerHTML = list.map((it) => `
      <a class="list-item${it.key === activeKey ? ' active' : ''}" href="${esc(it.url)}">
        <span class="grow">${esc(it.name)}</span><span class="n">${it.n} 条</span></a>`).join('')
      || '<div class="muted small shelf-empty">没有符合的条目。</div>';
  }

  // ---------------------------------------------------------------- 索引页

  function renderIndex() {
    shown = null;
    const list = results();
    const groups = new Map();
    for (const it of list) {
      const keys = state.group === OPTION_NONE ? [''] : it.facets[state.group]?.length ? it.facets[state.group] : ['未标'];
      for (const k of keys) (groups.get(k) ?? groups.set(k, []).get(k)).push(it);
    }
    const facet = cfg.facets.find((f) => f.key === state.group);
    const heads = facet?.order ? facet.order.filter((v) => groups.has(v)).concat([...groups.keys()].filter((v) => !facet.order.includes(v)))
      : [...groups.keys()].sort((a, b) => groups.get(b).length - groups.get(a).length || collator.compare(a, b));
    // 页头的数字跟着筛选走：当前筛出来的条目，按一个分面数
    const hn = cfg.headNums;
    const tally = (v) => list.filter((it) => it.facets[hn.facet]?.includes(v)).length;
    content.innerHTML = `${pageHead({
      en: 'INDEX',
      title: cfg.title,
      note: cfg.intro,
      nums: hn.order.map((v) => [hn.label?.(v) ?? v, tally(v), hn.unit, hn.unitEn]),
    })}<div class="an-body shelf-index">
      <div class="shelf-groups">${heads.map((k) => `<section>
        ${k ? `<h2 class="shelf-head">${esc(facet?.label?.(k) ?? k)}<span class="n">${groups.get(k).length}</span></h2>` : ''}
        ${groups.get(k).map(rowHtml).join('')}
      </section>`).join('') || '<p class="muted">没有符合的条目。</p>'}</div>
    </div>`;
    content.scrollTop = 0;
  }

  function rowHtml(it) {
    return `<a class="shelf-row" href="${esc(it.url)}">
      <div class="shelf-row-head"><span class="shelf-name">${esc(it.name)}</span>
        <span class="shelf-tags">${it.tags.map((t) => `<span>${esc(t)}</span>`).join('')}</span></div>
      ${it.line ? `<div class="shelf-line">${esc(it.line)}</div>` : ''}
    </a>`;
  }

  // ---------------------------------------------------------------- 路由

  function update(r) {
    if (!content) return;
    const [key] = r.parts;
    const item = key ? cfg.resolve(key) : null;
    if (item) {
      // 看单篇时，左栏保留进来时的筛选
      if ([...r.params.keys()].some((k) => k !== 'e')) readState(r.params);
      syncControls();
      renderFacets();
      renderList(item.key);
      if (shown !== item.key) {
        shown = item.key;
        cfg.detail(item, content, links());
      }
      cfg.jump(content, r.params);
      return;
    }
    readState(r.params);
    syncControls();
    renderFacets();
    renderList(null);
    renderIndex();
  }

  // 单篇页面上的链接：回到进来时的索引；点标签只按这一项筛选
  const links = () => ({
    back: indexUrl(),
    filter: (facet, value) => `#/${cfg.route}?${new URLSearchParams({ [facet]: value })}`,
  });

  function syncControls() {
    const q = side.querySelector('.shelf-q');
    if (document.activeElement !== q) q.value = state.q;
    side.querySelector('[data-opt=group]').value = state.group;
    side.querySelector('[data-opt=sort]').value = state.sort;
  }

  function mount(el, r) {
    items = cfg.items();
    if (!items.length) {
      el.innerHTML = '<div class="loading">还没有数据。请先运行 python -m pipeline.annals build，再刷新页面。</div>';
      return;
    }
    el.innerHTML = `
      <aside class="side panel shelf-side">
        <input class="shelf-q" type="search" placeholder="${esc(cfg.placeholder)}">
        <div class="shelf-opts">
          <label>分组 <select data-opt="group">${cfg.groups.map((g) => `<option value="${esc(g)}">${esc(g === OPTION_NONE ? '不分组' : g)}</option>`).join('')}</select></label>
          <label>排序 <select data-opt="sort">${cfg.sorts.map((s) => `<option>${esc(s)}</option>`).join('')}</select></label>
        </div>
        <div class="shelf-facets"></div>
        <div class="shelf-count muted small"></div>
        <div class="list shelf-list"></div>
      </aside>
      <section class="content panel"></section>`;
    side = el.querySelector('.shelf-side');
    content = el.querySelector('.content');
    side.querySelector('.shelf-q').addEventListener('input', (e) => {
      state.q = e.target.value;
      renderFacets();
      if (shown) {
        renderList(shown);
      } else {
        renderList(null);
        renderIndex();
        history.replaceState(null, '', indexUrl());
      }
    });
    side.querySelector('[data-opt=group]').addEventListener('change', (e) => { location.hash = indexUrl({ group: e.target.value }); });
    side.querySelector('[data-opt=sort]').addEventListener('change', (e) => { location.hash = indexUrl({ sort: e.target.value }); });
    state = freshState();
    update(r);
  }

  function unmount() {
    side = content = null;
    shown = null;
  }

  return { mount, update, unmount };
}

// ---------------------------------------------------------------- 索引共用的小工具

const DIGITS = '〇一二三四五六七八九';

export function cnYear(year) {
  return `${String(year).replace(/\d/g, (d) => DIGITS[d])}年`;
}

// 「约一〇九一年」「一〇九七年正月四日」→ 1091、1097；读不出的排在最后
export function cnYearNumber(text) {
  const m = String(text ?? '').match(/[〇一二三四五六七八九]{3,4}(?=年)/);
  return m ? Number([...m[0]].map((c) => DIGITS.indexOf(c)).join('')) : Infinity;
}

// 卷在全书的先后：前纪、外纪在前，不系年在后
export function volumeOrder() {
  return Object.fromEntries((D.annals?.volumes ?? []).map((v, i) => [v.year, i]));
}

// 概述的第一句，去掉标记，放在索引页上说明此人是谁
export function plainFirst(summary, limit = 80) {
  const s = (summary[0] ?? '').replace(/\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g, (_, name, label) => label ?? name).replace(/\*\*/g, '');
  const end = s.indexOf('。');
  const first = end >= 0 ? s.slice(0, end + 1) : s;
  return first.length > limit ? `${first.slice(0, limit)}……` : first;
}
