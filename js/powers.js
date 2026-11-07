// 地区势力的资料：上级、下属、成员、相关事件、提及的剧情。接在博物志页面的正文下面。
import { D } from './data.js';
import { esc, href, charChip, powerChip, eventItem, groupLabel } from './util.js';

const MEMBER_LIMIT = 80;

export function powerSections(id) {
  const p = D.powers[id];
  const evs = p.events.map((e) => D.eventById[e]);
  const mentions = [...p.mentions].sort((a, b) => D.groupById[a[0]].order - D.groupById[b[0]].order);
  return `
    ${p.parent ? `<div class="sub">上级：${powerChip(p.parent)}</div>` : ''}
    <div class="actions">
      ${evs.length ? `<a class="btn" href="${href.timeline({ power: id })}">在时间轴中查看（${evs.length} 条事件）</a>` : ''}
      <a class="btn" href="${href.graph('power', id)}">在关系图中查看</a>
    </div>
    ${p.children.length ? `<h4>下属</h4><div class="chips">${p.children.map((k) => powerChip(k)).join('')}</div>` : ''}
    ${p.members.length ? `<h4>${p.kind === 'region' ? '出身干员' : '成员'}（${p.members.length}）</h4>
      <div class="chips">${p.members.slice(0, MEMBER_LIMIT).map((n) => charChip(n)).join('')}${p.members.length > MEMBER_LIMIT ? `<span class="muted small">等 ${p.members.length} 人</span>` : ''}</div>` : ''}
    <div class="cols">
      <div>${evs.length ? `<h4>相关事件（${evs.length}）</h4>${evs.map(eventItem).join('')}` : '<h4>相关事件</h4><p class="muted">无</p>'}</div>
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
