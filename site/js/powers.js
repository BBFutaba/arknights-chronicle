// 地区与势力：左侧层级目录，右侧详情（成员、相关事件、提及的剧情）。
import { D } from './data.js';
import { esc, href, charChip, powerChip, eventItem, groupLabel } from './util.js';

let side, content;
const MEMBER_LIMIT = 80;

export function mount(el, r) {
  el.innerHTML = `<aside class="side panel"><div class="list"></div></aside><section class="content panel"></section>`;
  side = el.querySelector('.side');
  content = el.querySelector('.content');
  update(r);
}

export function update(r) {
  const id = D.powers[r.parts[0]] ? r.parts[0] : 'rhodes';
  renderTree(id);
  renderPower(id);
  content.scrollTop = 0;
}

function renderTree(activeId) {
  const P = D.powers;
  const item = (id, depth) => {
    const p = P[id];
    const kids = p.children.filter((k) => P[k].kind === p.kind);
    return `<a class="list-item${id === activeId ? ' active' : ''}" href="${href.power(id)}" style="padding-left:${8 + depth * 16}px">
        <span class="n" style="color:var(--c-${p.kind})">●</span><span class="grow">${esc(p.name)}</span>
        <span class="n">${p.events.length} 事件</span></a>${kids.map((k) => item(k, depth + 1)).join('')}`;
  };
  const tops = (kind) => Object.keys(P)
    .filter((id) => P[id].kind === kind && (!P[id].parent || P[P[id].parent].kind !== kind))
    .sort((a, b) => P[b].events.length - P[a].events.length);
  side.querySelector('.list').innerHTML =
    `<div class="list-head">地区</div>${tops('region').map((id) => item(id, 0)).join('')}`
    + `<div class="list-head">势力</div>${tops('faction').map((id) => item(id, 0)).join('')}`;
  side.querySelector('.list-item.active')?.scrollIntoView({ block: 'nearest' });
}

function renderPower(id) {
  const p = D.powers[id];
  const evs = p.events.map((e) => D.eventById[e]);
  const mentions = [...p.mentions].sort((a, b) => D.groupById[a[0]].order - D.groupById[b[0]].order);
  const kindLabel = p.kind === 'region' ? '地区' : '势力';
  content.innerHTML = `
    <div class="profile-head"><h1>${esc(p.name)}</h1><span class="chip chip-${p.kind}">${kindLabel}</span></div>
    ${p.parent ? `<div class="sub">上级：${powerChip(p.parent)}</div>` : ''}
    <div class="actions">
      ${evs.length ? `<a class="btn" href="${href.timeline({ power: id })}">在时间轴中查看（${evs.length} 条事件）</a>` : ''}
      <a class="btn" href="${href.graph('power', id)}">在关系图中查看</a>
    </div>
    ${p.children.length ? `<h4>下属</h4><div class="chips">${p.children.map((k) => powerChip(k)).join('')}</div>` : ''}
    ${p.members.length ? `<h4>${p.kind === 'region' ? '出身干员' : '成员'}（${p.members.length}）</h4>
      <div class="chips">${p.members.slice(0, MEMBER_LIMIT).map((n) => charChip(n)).join('')}${p.members.length > MEMBER_LIMIT ? `<span class="muted small">等 ${p.members.length} 人</span>` : ''}</div>` : ''}
    <div class="cols">
      <div>${evs.length ? `<h4>年表中的相关事件（${evs.length}）</h4>${evs.map(eventItem).join('')}` : '<h4>年表中的相关事件</h4><p class="muted">无</p>'}</div>
      <div><h4>提及${p.kind === 'region' ? '此地' : '该势力'}的剧情</h4>
        ${mentions.length ? mentions.map(([gid, eps]) => {
          const g = D.groupById[gid];
          const total = eps.reduce((n, [, c]) => n + c, 0);
          return `<div class="appear-group"><a href="${href.group(gid)}"><b>${esc(groupLabel(g))}</b></a>
            <span class="muted small">提及 ${total} 次</span>
            <div class="chips">${eps.map(([sid, c]) => `<a class="chip chip-plain" href="${href.ep(sid)}">${esc(D.epById[sid].ep.code || D.epById[sid].ep.title)}<span class="n">${c}</span></a>`).join('')}</div></div>`;
        }).join('') : '<p class="muted">无</p>'}</div>
    </div>`;
}
