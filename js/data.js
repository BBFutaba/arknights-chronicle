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
  buildTimeline();
}

const STORY_LINE = new Set(['主线', '活动', '故事集']);
const uniq = (list) => [...new Set(list)];

// 编年史的一个条目是时间轴的一行：次序、日期、文字都用书里的，PRTS 年表只作参考（row.prts）。
// 分段：单年的卷按年，合卷按书里的小节。
function timelineRow(v, s, d, e, own) {
  const single = typeof v.year === 'number';
  const day = d.label && d.label !== '是月' ? d.label : '';
  const quotes = e.groups.flatMap((g) => g.quotes ?? []);
  const stories = uniq(quotes.filter((q) => q.type === 'story').map((q) => q.sid)).filter((sid) => D.epById[sid]);
  const line = [...stories.map((sid) => D.epById[sid].group.id), ...(e.threads ?? []), ...own.map((p) => p.thread)]
    .find((id) => STORY_LINE.has(D.threads[id]?.category));
  const lines = e.groups.map((g) => g.gang.replace(/\*\*/g, ''));
  const text = lines.join('');
  const names = e.groups.flatMap((g) => g.people.flatMap((t) => [...t.matchAll(/\[\[([^\]|]+)/g)].map((m) => m[1])));
  return {
    id: e.id, era: v.title.replace(/^泰拉历/, ''), year: single ? v.year : null,
    head: single ? v.title.replace(/^泰拉历/, '') : s.label,
    short: !single ? day : s.label === '是岁' ? `是岁 ${day}`.trim() : `${s.label}${day}`,
    when: e.when, lines, prts: own, moved: Boolean(e.moved),
    parallel: own.some((p) => p.parallel),
    notes: [],
    thread: line ?? 'lore',
    sources: [
      ...stories.map((sid) => ({ text: quotes.find((q) => q.sid === sid).label, groups: [D.epById[sid].group.id], stories: [sid] })),
      ...uniq(quotes.filter((q) => q.type !== 'story' && q.label).map((q) => q.label)).map((t) => ({ text: t, groups: [], stories: [] })),
      ...own.flatMap((p) => p.sources).filter((x) => !x.stories.some((sid) => stories.includes(sid))),
    ],
    chars: uniq([...names.map((n) => D.charAlias[n] ?? n), ...own.flatMap((p) => p.chars)]).filter((n) => D.chars[n]),
    powers: uniq([
      ...Object.entries(D.powers).filter(([, p]) => p.name.length > 1 && text.includes(p.name)).map(([id]) => id),
      ...own.flatMap((p) => p.powers),
    ]),
  };
}

// 存目：书里判定于人于事没有推力、不入正文的年表事件。默认不显示，可以在时间轴打开。
function cunmuRow(c, p, anchor) {
  return {
    id: p.id, era: anchor.era, year: anchor.year, head: anchor.head, short: '存目', when: p.when,
    lines: [c.gang.replace(/\*\*/g, '')], prts: [p], cunmu: true, moved: false, parallel: p.parallel,
    notes: ['存目：于人于事没有推力，不入编年史正文。', ...(c.kaoyi ?? []).map((k) => k.text)],
    thread: p.thread, sources: p.sources, chars: p.chars, powers: p.powers,
  };
}

function buildTimeline() {
  if (!D.annals) {
    D.events.forEach((e) => {
      e.head = e.year != null ? `${e.year} 年` : e.era.split(' · ').pop();
      e.short = e.when;
    });
    return;
  }
  const raw = D.events;
  const prtsById = new Map(raw.map((p) => [p.id, p]));
  const rows = [], rowOfPrts = new Map(), cunmu = new Map();
  for (const v of D.annals.volumes) {
    for (const s of v.sections) for (const d of s.days) for (const e of d.entries) {
      const own = e.ids.map((id) => prtsById.get(id)).filter(Boolean);
      const row = timelineRow(v, s, d, e, own);
      rows.push(row);
      own.forEach((p) => rowOfPrts.set(p.id, row));
    }
    for (const c of v.cunmu ?? []) for (const id of c.ids) cunmu.set(id, c);
  }
  // 存目排在年表里它前面那条事件所在的行之后
  const after = new Map();
  let last = rows[0];
  for (const p of raw) {
    const row = rowOfPrts.get(p.id);
    if (row) {
      if (!row.moved) last = row;
    } else if (cunmu.has(p.id)) {
      if (!after.has(last.id)) after.set(last.id, []);
      after.get(last.id).push(cunmuRow(cunmu.get(p.id), p, last));
    }
  }
  D.events = rows.flatMap((r) => [r, ...(after.get(r.id) ?? [])]);
  D.eventById = {};
  D.events.forEach((r, i) => { r.order = i; D.eventById[r.id] = r; });
  for (const [id, row] of rowOfPrts) D.eventById[id] = row;  // 一条合写几件事的，旧链接也能找到

  // 人物页、势力页、剧情页的相关事件也指向这些行
  const holders = [...Object.values(D.chars), ...Object.values(D.powers), ...D.groups, ...D.groups.flatMap((g) => g.episodes)];
  const events = (h) => (h.events ??= []);
  holders.forEach((h) => { h.events = events(h).map((id) => D.eventById[id]?.id ?? id); });
  for (const r of D.events) {
    r.chars.forEach((n) => events(D.chars[n]).push(r.id));
    r.powers.forEach((p) => { if (D.powers[p]) events(D.powers[p]).push(r.id); });
    for (const x of r.sources) for (const sid of x.stories) {
      if (!D.epById[sid]) continue;
      events(D.epById[sid].ep).push(r.id);
      events(D.epById[sid].group).push(r.id);
    }
  }
  holders.forEach((h) => { h.events = uniq(h.events).sort((a, b) => (D.eventById[a]?.order ?? 0) - (D.eventById[b]?.order ?? 0)); });
}

const storyCache = {};
export function loadStory(gid) {
  storyCache[gid] ??= json(`data/stories/${gid}.json`);
  return storyCache[gid];
}
