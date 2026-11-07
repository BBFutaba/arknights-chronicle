// 入口：加载数据，按 hash 路由切换标签页。
// 路由形如 #/timeline?ev=ev0541、#/annals/1097?e=ev0536、#/benmo/太师案、#/zhuan/霜星、#/story/main_1/<分集 id>?l=12-18、#/chars/阿米娅、#/bowu/龙门、#/graph/char:陈
import { D, loadAll } from './data.js';
import { esc, href } from './util.js';
import { initSearch } from './search.js';
import { initStage, setStation } from './station.js';
import { initTheme } from './theme.js';
import * as timeline from './timeline.js';
import * as story from './story.js';
import * as chars from './chars.js';
import * as bowu from './bowu.js';
import * as graph from './graph.js';
import * as annals from './annals.js';
import * as benmo from './benmo.js';
import * as zhuan from './zhuan.js';
import * as xieyi from './xieyi.js';

const VIEWS = { timeline, annals, benmo, zhuan, story, chars, bowu, graph, xieyi };
const view = document.getElementById('view');
let current = null;

function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qs] = raw.split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return { name: VIEWS[parts[0]] ? parts[0] : 'timeline', parts: parts.slice(1), params: new URLSearchParams(qs) };
}

function route() {
  // 地区与势力并进了博物志：旧链接转到对应的页面，不留历史记录
  const old = location.hash.match(/^#\/?powers(?:\/([^?]*))?/);
  if (old) {
    location.replace(old[1] ? href.power(decodeURIComponent(old[1])) : href.wu());
    return;
  }
  // 凡例撤掉了，现在是鸣谢与协议：旧链接转过去
  if (/^#\/?fanli\b/.test(location.hash)) {
    location.replace('#/xieyi');
    return;
  }
  const r = parseRoute();
  // 凡例更早还在编年史标签下
  if (r.name === 'annals' && r.parts[0] === '凡例') {
    location.replace('#/xieyi');
    return;
  }
  // 列传、纪事本末原来在编年史标签下，旧链接转过去
  const moved = r.name === 'annals' && { 本末: href.benmo, 传: href.zhuan }[r.parts[0]];
  if (moved && r.parts[1]) {
    const qs = r.params.toString();
    location.replace(`${moved(r.parts[1])}${qs ? `?${qs}` : ''}`);
    return;
  }
  document.querySelectorAll('#tabs a').forEach((a) => a.classList.toggle('active', a.dataset.view === r.name));
  const mod = VIEWS[r.name];
  const fresh = !(current === r.name && mod.update);
  if (fresh) {
    if (current) VIEWS[current].unmount?.();
    view.innerHTML = '';
    view.className = `view-${r.name}`;
    mod.mount(view, r);
    current = r.name;
  } else {
    mod.update(r);
  }
  setStation(r.name, view, fresh);
}

function initAbout() {
  const dlg = document.getElementById('about');
  const m = D.meta;
  dlg.innerHTML = `<h2>关于</h2>
    <p>剧本、干员档案和敌人图鉴来自 <a href="https://github.com/Kengxxiao/ArknightsGameData" target="_blank" rel="noopener">ArknightsGameData</a>（国服，版本 ${esc(m.data_version)}），版权归鹰角网络所有。编年史的纲、目、考异和博物志的正文是同人撰写；博物志另有几句短引，出自官方设定集《大地巡旅》、官方影片、漫画和微博图文《泰拉记事》，版权同样归鹰角网络。</p>
    <p>时间轴以本书编年史为准。<a href="https://prts.wiki/w/泰拉年表" target="_blank" rel="noopener">PRTS「泰拉年表」</a>（修订 ${esc(m.prts.revid)}，${esc(m.prts.timestamp.slice(0, 10))}）只作参考，列在时间轴的详情里，按 CC BY-NC-SA 4.0 协议使用。年表中的日期为社区根据剧情推测，可能有偏差。</p>
    <p>共 ${m.stats.groups} 个剧情组、${m.stats.episodes} 集、${m.stats.events} 条事件、${m.stats.characters} 个人物。构建于 ${esc(m.built_at)}。${m.public
      ? '这是同人整理的公开版，非官方作品，只收编年史和它引用的片段，不收剧本和干员档案全文。转载和再创作的约定见<a href="#/xieyi" onclick="this.closest(\'dialog\').close()">鸣谢与协议</a>。如有不妥，请在 GitHub 仓库提 issue。'
      : '这是含剧本全文的本地版，仅供个人浏览，请勿公开发布。'}</p>
    <form method="dialog"><button>关闭</button></form>`;
  document.getElementById('about-btn').addEventListener('click', () => dlg.showModal());
}

try {
  await loadAll();
  initSearch();
  initAbout();
  initStage();
  initTheme(() => VIEWS[current]?.retheme?.());
  window.addEventListener('hashchange', route);
  route();
} catch (err) {
  view.innerHTML = `<div class="loading">加载失败：${esc(err.message)}<br>请先运行 python -m pipeline.build，再用 python -m pipeline.serve 打开。</div>`;
  throw err;
}
