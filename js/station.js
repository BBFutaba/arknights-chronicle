// 舞台：九站的标题块和顶栏轨道。语法来自一分钟介绍片。
// 这里写死的汉字会被 pipeline/chrome_font.py 切进界面字体，改了字要重跑它。
import { D } from './data.js';
import { esc } from './util.js';

const size = (x) => (Array.isArray(x) ? x.length : Object.keys(x ?? {}).length);
const annalsEntries = () => (D.annals?.volumes ?? []).reduce((n, v) => n + (v.stats?.entries ?? 0), 0);

const STATIONS = [
  { id: 'timeline', en: 'TIMELINE', title: '时间轴', unit: '条', unitEn: 'ENTRIES', count: annalsEntries },
  { id: 'annals', en: 'ANNALS', title: '编年史', unit: '卷', unitEn: 'VOLUMES', count: () => size(D.annals?.volumes) },
  { id: 'benmo', en: 'TOPICS', title: '纪事本末', unit: '事', unitEn: 'EVENTS', count: () => size(D.annals?.benmo) },
  { id: 'zhuan', en: 'BIOGRAPHIES', title: '列传', unit: '传', unitEn: 'LIVES', count: () => size(D.annals?.liezhuan) },
  { id: 'story', en: 'STORIES', title: '剧情', unit: '集', unitEn: 'EPISODES', count: () => D.meta?.stats?.episodes },
  { id: 'chars', en: 'CHARACTERS', title: '人物', unit: '名', unitEn: 'NAMES', count: () => D.meta?.stats?.characters },
  { id: 'bowu', en: 'ENCYCLOPEDIA', title: '博物志', unit: '条', unitEn: 'ENTRIES', count: () => size(D.bowu?.entries) },
  { id: 'graph', en: 'GRAPH', title: '关系图' },
  { id: 'xieyi', en: 'CREDITS', title: '鸣谢与协议', lines: ['爱好者编写的非营利同人作品，不是官方作品。', '转载、翻译、再创作，<u>不必事先询问</u>。', '注明出自《刻舟录》，署编撰者双叶，附本站链接，并说明改动。'] },
];

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const outExpo = (x) => (x >= 1 ? 1 : 1 - 2 ** (-10 * x));

// 标尺分八段，九个长刻度正好是九站，加号就落在长刻度上
const TICKS = Array.from({ length: 17 }, (_, k) => `<i class="st-t${k % 2 ? '' : ' major'}" style="--k:${k}"></i>`).join('');
let lastStation = 0;

function stationHtml(s, i, from) {
  const n = s.count?.();
  const chars = [...s.title].map((c, k) => `<span style="--i:${k}">${esc(c)}</span>`).join('');
  return `<div class="station">
    <i class="st-stem"></i><i class="st-cap"></i>
    <div class="st-en">${String(i + 1).padStart(2, '0')}/09  ${s.en}</div>
    <div class="st-title">${chars}</div>
    ${n != null ? `<div class="st-num"><b>${n}</b><span class="st-u"><i>${s.unit}</i><em>${s.unitEn}</em></span></div>` : ''}
    ${s.lines ? `<div class="st-lines">${s.lines.map((l) => `<p>${l}</p>`).join('')}</div>` : ''}
    <div class="st-track" style="--i:${from}">${TICKS}<i class="st-fill"></i><i class="cross on"></i></div>
  </div>`;
}

// 数字从 0 猛地计到终值。先写终值，面板隐藏、动画不跑时也是对的。
function countUp(el, val) {
  el.style.minWidth = `${el.offsetWidth}px`;
  if (reduced()) return;
  const start = performance.now();
  const tick = (now) => {
    const p = Math.min(1, (now - start) / 800);
    el.textContent = String(Math.round(val * outExpo(p)));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function placeTrack() {
  const track = document.getElementById('track');
  const box = track.getBoundingClientRect();
  const center = (a) => {
    const r = a.getBoundingClientRect();
    return r.left + r.width / 2 - box.left;
  };
  document.querySelectorAll('#tabs a').forEach((a, i) => {
    track.querySelectorAll('.track-stop')[i].style.left = `${center(a)}px`;
  });
  const active = document.querySelector('#tabs a.active');
  if (!active) return;
  track.querySelector('.track-fill').style.width = `${center(active)}px`;
  track.querySelector('.track-mark').style.left = `${center(active)}px`;
}

// 左栏标题块跟页头一样高，两边的轨道才接得上。页头的高度随内容变，所以每次量一下
function alignHead() {
  const view = document.getElementById('view');
  const ph = view.querySelector('.ph');
  // 时间轴的轨道不在页头里，紧贴在页头下面，要把它的 21px 算上
  const rail = ph?.querySelector('.ph-track') ? 0 : 21;
  if (ph) view.style.setProperty('--st-sync', `${ph.getBoundingClientRect().height + rail - 18}px`);
  else view.style.removeProperty('--st-sync');
}

function placeStage() {
  placeTrack();
  alignHead();
}

export function initStage() {
  const track = document.getElementById('track');
  track.innerHTML = `<i class="track-fill"></i>${STATIONS.map(() => '<i class="track-stop"></i>').join('')}<i class="cross on track-mark"></i>`;
  window.addEventListener('resize', placeStage);
  document.fonts?.ready.then(placeStage);
}

// 每次路由都调；fresh 表示刚换了一站，页面是新挂上去的
export function setStation(name, view, fresh) {
  const i = STATIONS.findIndex((s) => s.id === name);
  const s = STATIONS[i];
  placeStage();
  if (!fresh) return;
  const from = lastStation;
  lastStation = i;
  const host = view.querySelector('aside');
  if (host) {
    host.insertAdjacentHTML('afterbegin', stationHtml(s, i, from));
  } else {
    view.insertAdjacentHTML('afterbegin', `<aside class="side panel station-rail">${stationHtml(s, i, from)}</aside>`);
  }
  // 标题块是新挂上去的：先停在上一站，再走到这一站
  const ruler = view.querySelector('.st-track');
  if (ruler && from !== i) {
    void ruler.offsetWidth;
    ruler.style.setProperty('--i', i);
  }
  const num = view.querySelector('.st-num b');
  const n = s.count?.();
  if (num && n) countUp(num, n);
}
