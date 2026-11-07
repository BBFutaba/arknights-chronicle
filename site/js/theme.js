// 主题：内容平面的颜色。颜色本身写在 style.css 开头，这里只管切换和记住。
// index.html 开头有一小段脚本，在首屏画出来之前先套上主题，免得闪一下。
// 这里写死的汉字会被 pipeline/chrome_font.py 切进界面字体，改了字要重跑它。
const THEMES = [
  { id: 'mist', name: '雾蓝' },
  { id: 'sage', name: '鼠尾草' },
  { id: 'lilac', name: '淡紫' },
  { id: 'deep', name: '深灰绿' },
  { id: 'night', name: '夜间' },
];
const KEY = 'kz-theme';
const swatch = (id) => `<i class="theme-dot" style="background:var(--t-${id})"></i>`;

// onChange：换完主题调一次，给需要自己重读颜色的页面用（关系图是画布，不走 CSS）
export function initTheme(onChange) {
  const box = document.getElementById('theme');
  let current = document.documentElement.dataset.theme;
  if (!THEMES.some((t) => t.id === current)) current = 'mist';
  box.innerHTML = `
    <button class="theme-btn" aria-haspopup="listbox" aria-expanded="false" title="切换主题">${swatch(current)}主题</button>
    <div class="theme-menu" role="listbox" aria-label="主题" hidden>
      ${THEMES.map((t) => `<button role="option" data-id="${t.id}" aria-selected="${t.id === current}">${swatch(t.id)}${t.name}</button>`).join('')}
    </div>`;
  const btn = box.querySelector('.theme-btn');
  const menu = box.querySelector('.theme-menu');
  const open = (on) => {
    menu.hidden = !on;
    btn.setAttribute('aria-expanded', on);
  };
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    open(menu.hidden);
  });
  menu.addEventListener('click', (e) => {
    const b = e.target.closest('[data-id]');
    if (!b) return;
    document.documentElement.dataset.theme = b.dataset.id;
    try {
      localStorage.setItem(KEY, b.dataset.id);
    } catch { /* 无痕窗口等存不了，只是下次不记得 */ }
    menu.querySelectorAll('[data-id]').forEach((x) => x.setAttribute('aria-selected', x === b));
    btn.querySelector('.theme-dot').style.background = `var(--t-${b.dataset.id})`;
    open(false);
    onChange?.();
  });
  document.addEventListener('click', () => open(false));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') open(false);
  });
}
