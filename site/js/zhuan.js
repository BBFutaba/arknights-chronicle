// 列传：按人。索引写在 data/annals/列传索引*.md，首见和条数由程序算。
import { D } from './data.js';
import { esc, href, KIND_LABEL } from './util.js';
import { inline, entryHtml, controlsHtml, wireControls, jumpToEntry } from './annals.js';
import { makeShelf, OPTION_NONE, plainFirst, cnYearNumber, volumeOrder } from './shelf.js';

const FATE = { 已: '已盖棺', 未: '未盖棺', 未卜: '生死未卜', 异数: '异数' };
const ERAS = ['前纪与外纪', '一〇八〇至一〇九五年', '一〇九六至一〇九九年', '一一〇〇至一一〇三年', '不系年'];

function eraOf(year) {
  if (year === '不系年') return '不系年';
  if (typeof year !== 'number') return ERAS[0];
  return year < 1096 ? ERAS[1] : year < 1100 ? ERAS[2] : ERAS[3];
}

function fateTag(ix) {
  if (ix.fate === '已') return ix.died && ix.died !== '不详' ? `卒于${ix.died}` : '已盖棺';
  return FATE[ix.fate];
}

let byName = {};

function items() {
  const order = volumeOrder();
  const aliasesOf = {};
  for (const [alias, name] of Object.entries(D.annals?.aliases ?? {})) (aliasesOf[name] ??= []).push(alias);
  byName = {};
  return (D.annals?.liezhuan ?? []).map((z) => {
    const ix = z.index ?? { origin: '未详', place: '', race: '', factions: [], fate: '', died: '', ev: '', note: '' };
    const c = D.chars[z.name];
    const first = z.entries[0]?.year;
    const origin = ix.place ? `${ix.origin} · ${ix.place}` : ix.origin;
    const item = {
      key: z.name, z, ix, name: `${z.name}传`, url: href.zhuan(z.name), n: z.entries.length,
      line: plainFirst(z.summary),
      tags: [origin, ix.race, ...ix.factions, ix.fate ? fateTag(ix) : '', `${z.entries.length} 条`].filter(Boolean),
      text: [z.name, ...(c?.aliases ?? []), ...(aliasesOf[z.name] ?? []), ...z.summary, origin, ix.race, ...ix.factions, ix.note].join(' ').toLowerCase(),
      facets: {
        出身: [ix.origin], 盖棺: ix.fate ? [ix.fate] : [], 族裔: ix.race ? [ix.race] : [], 所属: ix.factions,
        首见: first === undefined ? [] : [eraOf(first)], 身份: c ? [KIND_LABEL[c.kind] ?? c.kind] : [],
      },
      sort: {
        条数: -z.entries.length, 拼音: z.name,
        首见: first === undefined ? Infinity : order[first],
        卒年: cnYearNumber(ix.died),
      },
    };
    byName[z.name] = item;
    return item;
  });
}

function detail(item, el, links) {
  const { z, ix } = item;
  const entries = z.entries.map(({ id }) => D.annalsEntry[id]).filter(Boolean);
  const others = z.others.map(({ id }) => D.annalsEntry[id]).filter(Boolean);
  const chip = (facet, value, text = value) => `<a class="shelf-chip" href="${esc(links.filter(facet, value))}">${esc(facet)}：${esc(text)}</a>`;
  const seeEntry = ix.ev && D.annalsEntry[ix.ev] ? ` <a href="${href.annalsEntry(ix.ev)}">见此条</a>` : '';
  el.innerHTML = `<div class="an-body">
    <a class="shelf-back" href="${esc(links.back)}">← 列传索引</a>
    <div class="sub">列传</div>
    <h1>${esc(z.name)}传</h1>
    <div class="sub">${z.span ? `${esc(z.span[0])}${z.span[1] !== z.span[0] ? ` 至 ${esc(z.span[1])}` : ''} · ` : ''}${entries.length} 条
      · <a href="${href.char(z.name)}">人物页</a></div>
    <div class="shelf-meta">
      ${chip('出身', ix.origin, ix.place ? `${ix.origin} · ${ix.place}` : ix.origin)}
      ${ix.race ? chip('族裔', ix.race) : ''}
      ${ix.factions.map((f) => chip('所属', f)).join('')}
      ${ix.fate ? chip('盖棺', ix.fate, ix.fate === '已' && ix.died ? `已盖棺 · ${ix.died}` : FATE[ix.fate]) : ''}
    </div>
    ${ix.note || seeEntry ? `<div class="shelf-fate">${esc(ix.note)}${seeEntry}</div>` : ''}
    ${z.summary.length ? `<div class="synopsis an-summary">${z.summary.map((p) => `<p>${inline(p)}</p>`).join('')}</div>` : ''}
    ${others.length ? `<details class="an-index"><summary>其他出场（${others.length} 条）</summary>
      <ol>${others.map((e) => `<li><a href="${href.annals(e.year, e.id)}"><span class="when">${esc(e.when)}</span>${inline(e.groups[0].gang)}</a></li>`).join('')}</ol>
    </details>` : ''}
    ${controlsHtml()}
    ${entries.map((e) => entryHtml(e, true)).join('')}
  </div>`;
  wireControls(el);
}

const shelf = makeShelf({
  route: 'zhuan', title: '列传', unit: '篇', placeholder: '搜人名、别名、经历……',
  intro: '<b>出身</b>是这个人生长、来历所在的地区。<b>盖棺</b>取字面意思：已盖棺是书中写明身死，未盖棺是到最后一次出场还活着，生死未卜是下落不明或只有传闻，异数是常人的生死说不清的。左栏可以多选，同一项里是「或」，不同项之间是「且」。',
  facets: [
    { key: '盖棺', order: Object.keys(FATE), open: true, label: (v) => FATE[v] ?? v },
    { key: '出身', open: true },
    { key: '族裔' },
    { key: '所属' },
    { key: '首见', order: ERAS },
    { key: '身份' },
  ],
  groups: ['出身', '盖棺', '族裔', '所属', '首见', '身份', OPTION_NONE],
  sorts: ['条数', '拼音', '首见', '卒年'],
  items,
  resolve: (key) => byName[D.zhuanByName[key]?.name],
  detail,
  jump: jumpToEntry,
});

export const mount = shelf.mount;
export const update = shelf.update;
export const unmount = shelf.unmount;
