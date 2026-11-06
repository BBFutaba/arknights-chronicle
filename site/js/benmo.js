// 纪事本末：按事。索引写在 data/annals/本末索引.md，时期和条数由程序算。
import { D } from './data.js';
import { esc, href, charChip, pageHead } from './util.js';
import { inline, entryHtml, controlsHtml, wireControls, jumpToEntry } from './annals.js';
import { makeShelf, OPTION_NONE, volumeOrder, cnYear } from './shelf.js';

const ENDS = ['已了', '未了', '悬案'];
const EARLY = '一〇九七年以前';
const PERIODS = [EARLY, ...[1097, 1098, 1099, 1100, 1101, 1102, 1103].map(cnYear)];

// 一件事可能追溯很远，时期看条目最多的那一年；一样多时取晚的，早的多是前因
function mainYear(b) {
  const counts = new Map();
  for (const { year } of b.entries) if (typeof year === 'number') counts.set(year, (counts.get(year) ?? 0) + 1);
  let best = null;
  for (const [year, n] of counts) if (best === null || n > counts.get(best) || (n === counts.get(best) && year > best)) best = year;
  return best;
}

const periodOf = (year) => (year === null || year < 1097 ? EARLY : cnYear(year));

function topPeople(entries) {
  const counts = new Map();
  for (const e of entries) {
    const names = new Set(e.groups.flatMap((g) => g.people.flatMap((t) => [...t.matchAll(/\[\[([^\]|]+)/g)].map((m) => m[1]))));
    for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
  }
  return [...counts.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).map(([name]) => name);
}

let byTitle = {};

function items() {
  const order = volumeOrder();
  byTitle = {};
  return (D.annals?.benmo ?? []).map((b) => {
    const ix = b.index ?? { regions: [], kind: '', end: '', note: '' };
    const entries = b.entries.map(({ id }) => D.annalsEntry[id]).filter(Boolean);
    const people = topPeople(entries);
    const year = mainYear(b);
    const span = `${b.span[0]}${b.span[1] !== b.span[0] ? ` 至 ${b.span[1]}` : ''}`;
    const item = {
      key: b.title, b, ix, entries, people, name: b.title, url: href.benmo(b.title), n: b.entries.length,
      line: ix.note,
      tags: [...ix.regions, ix.kind, ix.end, span, `${b.entries.length} 条`].filter(Boolean),
      text: [b.title, ...b.summary, ...ix.regions, ix.kind, ix.note, ...people].join(' ').toLowerCase(),
      facets: { 时期: [periodOf(year)], 地区: ix.regions, 性质: ix.kind ? [ix.kind] : [], 了局: ix.end ? [ix.end] : [] },
      sort: { 时间: year === null ? order[b.entries[0]?.year] ?? 0 : order[year], 条数: -b.entries.length, 拼音: b.title },
    };
    byTitle[b.title] = item;
    return item;
  });
}

function detail(item, el, links) {
  const { b, ix, entries, people } = item;
  const chip = (facet, value) => `<a class="shelf-chip" href="${esc(links.filter(facet, value))}">${esc(facet)}：${esc(value)}</a>`;
  el.innerHTML = `${pageHead({
    en: 'TOPIC, START TO END',
    title: b.title,
    back: [links.back, '← 纪事本末索引'],
    sub: `${esc(b.span[0])}${b.span[1] !== b.span[0] ? ` 至 ${esc(b.span[1])}` : ''}`,
    tags: [...ix.regions.map((r) => chip('地区', r)), ix.kind ? chip('性质', ix.kind) : '', ix.end ? chip('了局', ix.end) : ''].join(''),
    note: ix.note ? esc(ix.note) : '',
    nums: [['条目', entries.length, '条', 'ENTRIES'], people.length ? ['人物', people.length, '人', 'PEOPLE'] : null],
  })}<div class="an-body">
    ${b.summary.length ? `<div class="synopsis an-summary">${b.summary.map((p) => `<p>${inline(p)}</p>`).join('')}</div>` : ''}
    ${people.length ? `<details class="an-index"><summary>主要人物（${people.length} 人）</summary><div class="chips">${people.map((n) => charChip(n)).join('')}</div></details>` : ''}
    <details class="an-index"><summary>按时间列出各条纲（${entries.reduce((n, e) => n + e.groups.length, 0)} 组）</summary>
      <ol>${entries.map((e) => e.groups.map((g) => `
        <li><a href="${href.benmo(b.title)}?e=${e.id}"><span class="when">${esc(e.when)}</span>${inline(g.gang)}</a></li>`).join('')).join('')}</ol>
    </details>
    ${controlsHtml()}
    ${entries.map((e) => entryHtml(e, true)).join('')}
  </div>`;
  wireControls(el);
}

const shelf = makeShelf({
  route: 'benmo', title: '纪事本末', unit: '件', placeholder: '搜事名、人名、地名……',
  headNums: { facet: '了局', order: ENDS, unit: '事', unitEn: 'EVENTS' },
  intro: '<b>时期</b>看这件事条目最多的那一年。<b>了局</b>：已了是有明确结局，未了是到书末余波还在，悬案是结果或真相不明。左栏可以多选，同一项里是「或」，不同项之间是「且」。',
  facets: [
    { key: '时期', order: PERIODS, open: true },
    { key: '地区', open: true },
    { key: '性质', open: true },
    { key: '了局', order: ENDS, open: true },
  ],
  groups: ['时期', '地区', '性质', '了局', OPTION_NONE],
  sorts: ['时间', '条数', '拼音'],
  items,
  resolve: (key) => byTitle[key],
  detail,
  jump: jumpToEntry,
});

export const mount = shelf.mount;
export const update = shelf.update;
export const unmount = shelf.unmount;
