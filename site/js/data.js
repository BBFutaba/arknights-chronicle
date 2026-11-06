// 数据加载：启动时读取目录类数据，剧本按剧情组按需加载。
export const D = {
  meta: null, groups: [], groupById: {}, epById: {}, chars: {}, powers: {},
  events: [], eventById: {}, threads: {},
  annals: null, annalsEntry: {}, annalsByEvent: {}, benmoByTitle: {}, zhuanByName: {}, annalsByPerson: {},
  bowu: null,
};

async function json(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`加载 ${path} 失败：${r.status}`);
  return r.json();
}

export async function loadAll() {
  const [meta, groups, chars, powers, ev] = await Promise.all([
    json('data/meta.json'), json('data/groups.json'), json('data/characters.json'),
    json('data/powers.json'), json('data/events.json'),
  ]);
  Object.assign(D, { meta, groups, chars, powers, events: ev.events, threads: ev.threads });
  groups.forEach((g, gi) => {
    D.groupById[g.id] = g;
    g.order = gi;
    g.episodes.forEach((e, i) => { D.epById[e.id] = { ep: e, group: g, index: i }; });
  });
  ev.events.forEach((e, i) => { e.order = i; D.eventById[e.id] = e; });
  // 编年史是可选的：还没运行 python -m pipeline.annals build 时没有这个文件
  D.annals = await json('data/annals.json').catch(() => null);
  for (const v of D.annals?.volumes ?? []) {
    for (const s of v.sections) for (const d of s.days) for (const e of d.entries) {
      D.annalsEntry[e.id] = e;
      e.ids.forEach((i) => { D.annalsByEvent[i] = e.id; });
      const people = new Set(e.groups.flatMap((g) => g.people.flatMap((t) => [...t.matchAll(/\[\[([^\]|]+)/g)].map((m) => m[1]))));
      people.forEach((n) => (D.annalsByPerson[n] ??= []).push(e.id));
    }
  }
  // 一人多名：剧本和编年史里写哪个名字，都指向同一个人物页
  D.charAlias = {};
  for (const [name, c] of Object.entries(D.chars)) for (const a of c.aliases) D.charAlias[a] ??= name;
  for (const [a, name] of Object.entries(D.annals?.aliases ?? {})) if (D.chars[name]) D.charAlias[a] ??= name;
  for (const b of D.annals?.benmo ?? []) D.benmoByTitle[b.title] = b;
  for (const z of D.annals?.liezhuan ?? []) D.zhuanByName[z.name] = z;
  // 博物志也是可选的：还没有 bowu.json 时只列地区势力
  D.bowu = await json('data/bowu.json').catch(() => (
    { men: ['地理', '势力', '族裔', '源石', '科技', '人文', '生灵', '远古'], entries: [], powers: {} }));
  // 一人多名：别名和正名共用列传和编年史出场
  for (const [alias, name] of Object.entries(D.annals?.aliases ?? {})) {
    if (D.zhuanByName[name]) D.zhuanByName[alias] = D.zhuanByName[name];
    const both = [...new Set([...(D.annalsByPerson[name] ?? []), ...(D.annalsByPerson[alias] ?? [])])];
    if (both.length) D.annalsByPerson[name] = D.annalsByPerson[alias] = both;
  }
  mergeSupplements();
}

const CN_DIGIT = { 〇: 0, 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
const STORY_LINE = new Set(['主线', '活动', '故事集']);

// 「一〇九七年」逐位读，「泰拉历六百三十一年」按十百千读。读不出（如「约前六千年」）返回 null。
function cnYear(when) {
  const m = /^(?:泰拉历)?([〇一二三四五六七八九十百千]+)年/.exec(when ?? '');
  if (!m) return null;
  if (!/[十百千]/.test(m[1])) return Number([...m[1]].map((c) => CN_DIGIT[c]).join(''));
  let total = 0, digit = 0;
  for (const c of m[1]) {
    if (c === '千' || c === '百' || c === '十') {
      total += (digit || 1) * { 千: 1000, 百: 100, 十: 10 }[c];
      digit = 0;
    } else {
      digit = CN_DIGIT[c];
    }
  }
  return total + digit;
}

// 把一条补条写成时间轴上的事件。故事线规则和 pipeline/site.py 的 export_events 相同。
function supplementEvent(e, year, era) {
  const quotes = e.groups.flatMap((g) => g.quotes ?? []);
  const stories = [...new Set(quotes.filter((q) => q.type === 'story').map((q) => q.sid))].filter((sid) => D.epById[sid]);
  const line = stories.map((sid) => D.epById[sid].group).find((g) => STORY_LINE.has(g.category));
  const lines = e.groups.map((g) => g.gang.replace(/\*\*/g, ''));
  const text = lines.join('');
  const names = e.groups.flatMap((g) => g.people.flatMap((t) => [...t.matchAll(/\[\[([^\]|]+)/g)].map((m) => m[1])));
  return {
    id: e.id, era, when: e.when, year, lines, parallel: false, sup: true,
    notes: ['补条：PRTS 年表不载，由本书据原文补入。'],
    thread: line?.id ?? 'lore',
    sources: [
      ...stories.map((sid) => ({ text: quotes.find((q) => q.sid === sid).label, groups: [D.epById[sid].group.id], stories: [sid] })),
      ...[...new Set(quotes.filter((q) => q.type !== 'story' && q.label).map((q) => q.label))].map((text) => ({ text, groups: [], stories: [] })),
    ],
    chars: [...new Set(names.map((n) => D.charAlias[n] ?? n))].filter((n) => D.chars[n]),
    powers: Object.entries(D.powers).filter(([, p]) => p.name.length > 1 && text.includes(p.name)).map(([id]) => id),
  };
}

// 年表（PRTS）没有、编年史补立的条目也进时间轴：排在书中同年的上一条年表事件之后；
// 这一年在它之前没有年表事件的，排在这一年第一条之前；不系年的排在最后。
function mergeSupplements() {
  const after = new Map(), before = new Map(), tail = [];
  const add = (map, key, ev) => { if (!map.has(key)) map.set(key, []); map.get(key).push(ev); };
  let prev = null;
  for (const v of D.annals?.volumes ?? []) {
    for (const s of v.sections) for (const d of s.days) for (const e of d.entries) {
      const own = e.ids.map((id) => D.eventById[id]).filter(Boolean);
      if (own.length && !e.moved) prev = own.at(-1);
      if (!e.sup) continue;
      const year = cnYear(e.when);
      if (v.year === '不系年') {
        tail.push(supplementEvent(e, null, '不系年'));
      } else if (prev && (year === null || year === prev.year)) {
        add(after, prev.id, supplementEvent(e, prev.year, prev.era));
      } else {
        const next = D.events.find((x) => typeof x.year === 'number' && x.year >= year);
        const ev = supplementEvent(e, year, next?.era ?? prev?.era ?? '');
        if (next) add(before, next.id, ev); else tail.push(ev);
      }
    }
  }
  D.events = [...D.events.flatMap((e) => [...(before.get(e.id) ?? []), e, ...(after.get(e.id) ?? [])]), ...tail];
  D.events.forEach((e, i) => { e.order = i; D.eventById[e.id] = e; });
  // 人物页、势力页、剧情页的相关事件也带上补条
  const touched = new Set();
  const link = (list, id) => { if (list) { list.push(id); touched.add(list); } };
  for (const e of D.events) {
    if (!e.sup) continue;
    e.chars.forEach((n) => link(D.chars[n].events, e.id));
    e.powers.forEach((p) => link(D.powers[p].events, e.id));
    for (const s of e.sources) for (const sid of s.stories) {
      link(D.epById[sid].ep.events, e.id);
      link(D.epById[sid].group.events, e.id);
    }
  }
  touched.forEach((list) => {
    const unique = [...new Set(list)].sort((a, b) => (D.eventById[a]?.order ?? 0) - (D.eventById[b]?.order ?? 0));
    list.splice(0, list.length, ...unique);
  });
}

const storyCache = {};
export function loadStory(gid) {
  storyCache[gid] ??= json(`data/stories/${gid}.json`);
  return storyCache[gid];
}
