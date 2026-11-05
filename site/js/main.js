// 入口：加载数据，按 hash 路由切换标签页。
// 路由形如 #/timeline?ev=ev0541、#/annals/1097?e=ev0536、#/story/main_1/<分集 id>?l=12-18、#/chars/阿米娅、#/powers/kazimierz、#/graph/char:陈
import { D, loadAll } from './data.js';
import { esc } from './util.js';
import { initSearch } from './search.js';
import * as timeline from './timeline.js';
import * as story from './story.js';
import * as chars from './chars.js';
import * as powers from './powers.js';
import * as graph from './graph.js';
import * as annals from './annals.js';

const VIEWS = { timeline, annals, story, chars, powers, graph };
const view = document.getElementById('view');
let current = null;

function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qs] = raw.split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return { name: VIEWS[parts[0]] ? parts[0] : 'timeline', parts: parts.slice(1), params: new URLSearchParams(qs) };
}

function route() {
  const r = parseRoute();
  document.querySelectorAll('#tabs a').forEach((a) => a.classList.toggle('active', a.dataset.view === r.name));
  const mod = VIEWS[r.name];
  if (current === r.name && mod.update) {
    mod.update(r);
  } else {
    if (current) VIEWS[current].unmount?.();
    view.innerHTML = '';
    view.className = `view-${r.name}`;
    mod.mount(view, r);
    current = r.name;
  }
}

function initAbout() {
  const dlg = document.getElementById('about');
  const m = D.meta;
  dlg.innerHTML = `<h2>关于</h2>
    <p>剧本、干员档案和敌人图鉴来自 <a href="https://github.com/Kengxxiao/ArknightsGameData" target="_blank" rel="noopener">ArknightsGameData</a>（国服，版本 ${esc(m.data_version)}），版权归鹰角网络所有。编年史的纲、目、考异是同人撰写。</p>
    <p>时间轴事件来自 <a href="https://prts.wiki/w/泰拉年表" target="_blank" rel="noopener">PRTS「泰拉年表」</a>（修订 ${esc(m.prts.revid)}，${esc(m.prts.timestamp.slice(0, 10))}），按 CC BY-NC-SA 4.0 协议使用。年表中的日期为社区根据剧情推测，可能有偏差。</p>
    <p>共 ${m.stats.groups} 个剧情组、${m.stats.episodes} 集、${m.stats.events} 条事件、${m.stats.characters} 个人物。构建于 ${esc(m.built_at)}。${m.public
      ? '这是同人整理的公开版，非官方作品，只收编年史和它引用的片段，不收剧本和干员档案全文。如有不妥，请在 GitHub 仓库提 issue。'
      : '这是含剧本全文的本地版，仅供个人浏览，请勿公开发布。'}</p>
    <form method="dialog"><button>关闭</button></form>`;
  document.getElementById('about-btn').addEventListener('click', () => dlg.showModal());
}

try {
  await loadAll();
  initSearch();
  initAbout();
  window.addEventListener('hashchange', route);
  route();
} catch (err) {
  view.innerHTML = `<div class="loading">加载失败：${esc(err.message)}<br>请先运行 python -m pipeline.build，再用 python -m pipeline.serve 打开。</div>`;
  throw err;
}
