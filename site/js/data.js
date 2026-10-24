// 数据加载：启动时读取目录类数据，剧本按剧情组按需加载。
export const D = {
  meta: null, groups: [], groupById: {}, epById: {}, chars: {}, powers: {},
  events: [], eventById: {}, threads: {},
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
}

const storyCache = {};
export function loadStory(gid) {
  storyCache[gid] ??= json(`data/stories/${gid}.json`);
  return storyCache[gid];
}
