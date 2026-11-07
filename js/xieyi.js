// 鸣谢与协议：单独一个标签页，文字在 data/annals/鸣谢与协议.md，页脚附 GitHub 仓库。
import { D } from './data.js';
import { inline } from './annals.js';

const REPO = 'https://github.com/BBFutaba/arknights-chronicle';

function prose(text) {
  return inline(text).replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

function bodyHtml() {
  let html = '', inList = false;
  for (const { type, text } of D.annals?.xieyi ?? []) {
    if (inList && type !== 'item') { html += '</ul>'; inList = false; }
    if (type === 'head') html += `<h2>${prose(text)}</h2>`;
    else if (type === 'text') html += `<p>${prose(text)}</p>`;
    else {
      if (!inList) { html += '<ul class="xieyi-list">'; inList = true; }
      html += `<li>${prose(text)}</li>`;
    }
  }
  return inList ? `${html}</ul>` : html;
}

export function mount(el) {
  el.innerHTML = `<section class="panel xieyi-page">
    <article class="xieyi-body">
      <div class="sub">刻舟录</div>
      <h1>鸣谢与协议</h1>
      ${bodyHtml()}
      <footer class="xieyi-foot">
        《刻舟录》· 双叶 撰 · <a href="${REPO}" target="_blank" rel="noopener">GitHub 仓库</a> · <a href="${REPO}/issues" target="_blank" rel="noopener">提 issue</a>
      </footer>
    </article>
  </section>`;
}
