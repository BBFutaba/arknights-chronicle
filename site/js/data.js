// 数据加载：启动时读取目录类数据，剧本按剧情组按需加载。
export const D = {
  meta: null, groups: [], groupById: {}, epById: {}, chars: {}, powers: {},
  events: [], eventById: {}, threads: {},
  annals: null, annalsEntry: {}, annalsByEvent: {}, benmoByTitle: {}, zhuanByName: {}, annalsByPerson: {},
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
  // 一人多名：别名和正名共用列传和编年史出场
  for (const [alias, name] of Object.entries(D.annals?.aliases ?? {})) {
    if (D.zhuanByName[name]) D.zhuanByName[alias] = D.zhuanByName[name];
    const both = [...new Set([...(D.annalsByPerson[name] ?? []), ...(D.annalsByPerson[alias] ?? [])])];
    if (both.length) D.annalsByPerson[name] = D.annalsByPerson[alias] = both;
  }
}

const storyCache = {};
export function loadStory(gid) {
  storyCache[gid] ??= json(`data/stories/${gid}.json`);
  return storyCache[gid];
}
