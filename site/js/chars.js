// 人物：左侧可筛选的人物列表，右侧人物卡片（档案、出场、相关事件、常同场人物）。
import { D } from './data.js';
import { esc, href, KIND_LABEL, charChip, powerChip, eventItem, groupLabel } from './util.js';

const LIST_LIMIT = 600;
let side, content, kind = 'all', sort = 'appear', q = '', power = '';

const epCount = (c) => c.appear.reduce((n, [, sids]) => n + sids.length, 0);
const epShort = (ep) => (ep.code || ep.title) + ({ 行动前: ' 前', 行动后: ' 后' }[ep.avg] ?? '');

export function mount(el, r) {
  el.innerHTML = `
    <aside class="side panel">
      <input type="search" class="ch-q" placeholder="搜索人物（名字、别名、英文名）…">
      <div class="seg-ctrl ch-kind">${[['all', '全部'], ['operator', '干员'], ['npc', 'NPC']].map(([k, l]) => `<button data-k="${k}">${l}</button>`).join('')}</div>
      <select class="ch-power"><option value="">全部地区与势力</option>${Object.entries(D.powers)
        .sort((a, b) => a[1].kind.localeCompare(b[1].kind) || a[1].name.localeCompare(b[1].name, 'zh'))
        .map(([id, p]) => `<option value="${id}">${p.kind === 'region' ? '地区' : '势力'}：${esc(p.name)}</option>`).join('')}</select>
      <select class="ch-sort">
        <option value="appear">按出场集数</option><option value="lines">按台词数</option>
        <option value="events">按年表事件数</option><option value="name">按名字</option></select>
      <div class="list"></div>
    </aside>
    <section class="content panel"></section>`;
  side = el.querySelector('.side');
  content = el.querySelector('.content');
  const qi = side.querySelector('.ch-q');
  qi.value = q;
  qi.addEventListener('input', () => { q = qi.value.trim(); renderList(); });
  side.querySelector('.ch-kind').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b) { kind = b.dataset.k; renderList(); }
  });
  const ps = side.querySelector('.ch-power');
  ps.value = power;
  ps.addEventListener('change', () => { power = ps.value; renderList(); });
  const ss = side.querySelector('.ch-sort');
  ss.value = sort;
  ss.addEventListener('change', () => { sort = ss.value; renderList(); });
  update(r);
}

export function update(r) {
  const asked = r.parts[0] && (D.chars[r.parts[0]] ? r.parts[0] : D.charAlias[r.parts[0]]);
  const name = asked || '阿米娅';
  renderList(name);
  renderProfile(name);
  content.scrollTop = 0;
}

function renderList(activeName) {
  activeName ??= side.querySelector('.list-item.active')?.dataset.name;
  side.querySelectorAll('.ch-kind button').forEach((b) => b.classList.toggle('active', b.dataset.k === kind));
  const ql = q.toLowerCase();
  let arr = Object.entries(D.chars).filter(([n, c]) =>
    (kind === 'all' ? c.kind !== 'doctor' || !q : c.kind === kind)
    && (!power || c.powers.includes(power))
    && (!q || [n, ...c.aliases, c.appellation].some((s) => s && s.toLowerCase().includes(ql))));
  const key = { appear: ([, c]) => epCount(c), lines: ([, c]) => c.lines, events: ([, c]) => c.events.length };
  arr.sort(sort === 'name' ? (a, b) => a[0].localeCompare(b[0], 'zh') : (a, b) => key[sort](b) - key[sort](a) || a[0].localeCompare(b[0], 'zh'));
  const shown = arr.slice(0, LIST_LIMIT);
  const metric = (c) => sort === 'lines' ? `${c.lines} 句` : sort === 'events' ? `${c.events.length} 事件` : `${epCount(c)} 集`;
  side.querySelector('.list').innerHTML = shown.map(([n, c]) => `
    <a class="list-item${n === activeName ? ' active' : ''}" data-name="${esc(n)}" href="${href.char(n)}">
      <span class="n" style="color:var(--c-${c.kind})">●</span><span class="grow">${esc(n)}</span>
      <span class="n">${metric(c)}</span></a>`).join('')
    + (arr.length > LIST_LIMIT ? `<div class="muted small pad">共 ${arr.length} 人，只显示前 ${LIST_LIMIT} 个，请用搜索缩小范围。</div>` : '');
}

function renderProfile(name) {
  const c = D.chars[name];
  const prof = c.profile;
  const appear = [...c.appear].sort((a, b) => D.groupById[a[0]].order - D.groupById[b[0]].order);
  const evs = c.events.map((id) => D.eventById[id]);
  const basic = prof?.basic ? Object.entries(prof.basic) : [];
  const stars = c.rarity ? '★'.repeat(c.rarity) : '';
  content.innerHTML = `
    <div class="profile-head">
      <h1>${esc(name)}</h1>
      ${c.appellation ? `<span class="muted">${esc(c.appellation)}</span>` : ''}
      <span class="tags"><span class="chip chip-${c.kind}">${KIND_LABEL[c.kind]}</span>
        ${c.profession ? `<span class="chip chip-plain">${esc(c.profession)} ${stars}</span>` : ''}</span>
    </div>
    ${c.aliases.length ? `<div class="sub">别名 / 异格：${c.aliases.map(esc).join('、')}</div>` : ''}
    <div class="actions">
      ${evs.length ? `<a class="btn" href="${href.timeline({ char: name })}">在时间轴中查看（${evs.length} 条事件）</a>` : ''}
      <a class="btn" href="${href.graph('char', name)}">在关系图中查看</a>
      ${D.zhuanByName[name]?.entries.length ? `<a class="btn" href="${href.zhuan(name)}">📜 ${esc(name)}传</a>` : ''}
    </div>
    ${c.powers.length ? `<h4>所属</h4><div class="chips">${c.powers.map((p) => powerChip(p)).join('')}</div>` : ''}
    ${c.description ? `<h4>敌人图鉴</h4><p>${esc(c.description)}</p>` : ''}
    ${basic.length ? `<h4>基础档案</h4><dl class="kv">${basic.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
    ${prof?.sections?.length ? `<h4>干员档案</h4>${prof.sections.map((s) => `
      <details ${s.title === '客观履历' ? 'open' : ''}><summary>${esc(s.title)}</summary><div class="prose">${esc(s.text)}</div></details>`).join('')}` : ''}
    <div class="cols">
      <div>
        <h4>出场剧情（${epCount(c)} 集，台词 ${c.lines} 句）</h4>
        ${appear.length ? appear.map(([gid, sids]) => {
          const g = D.groupById[gid];
          return `<div class="appear-group"><a href="${href.group(gid)}"><b>${esc(groupLabel(g))}</b></a>
            <span class="muted small">${esc(g.category)} · ${sids.length} 集</span>
            <div class="chips">${sids.map((sid) => `<a class="chip chip-plain" href="${href.ep(sid)}">${esc(epShort(D.epById[sid].ep))}</a>`).join('')}</div></div>`;
        }).join('') : '<p class="muted">没有在主线和活动剧情中出场。</p>'}
      </div>
      <div>
        ${c.co.length ? `<h4>常同场人物（共同出场集数）</h4><div class="chips">${c.co.map(([n, k]) => charChip(n, `<span class="n">${k}</span>`)).join('')}</div>` : ''}
        ${annalsSection(name)}
        ${evs.length ? `<h4>年表中的相关事件（${evs.length}）</h4>${evs.map(eventItem).join('')}` : ''}
      </div>
    </div>`;
}

// 编年史中写到此人的条目（【人物】里有他的）；立了传的另有按钮
function annalsSection(name) {
  const ids = D.annalsByPerson[name] ?? [];
  if (!ids.length) return '';
  const item = (id) => {
    const e = D.annalsEntry[id];
    return `<a class="event-item" href="${href.annalsEntry(id)}"><span class="when">${esc(e.when.replace('结晶纪元', ''))}</span>
      <span></span><span class="text">${esc(e.groups[0].gang.replace(/\*\*/g, ''))}</span></a>`;
  };
  const head = ids.slice(0, 8).map(item).join('');
  const rest = ids.length > 8 ? `<details><summary>其余 ${ids.length - 8} 条</summary>${ids.slice(8).map(item).join('')}</details>` : '';
  return `<h4>编年史中的记述（${ids.length}）</h4>${head}${rest}`;
}
