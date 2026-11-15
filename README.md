# 刻舟录

《明日方舟》剧情的编年史，同人整理，非官方作品。纲目体，按年分卷，穿插原文片段，另有纪事本末（按事）、列传（按人）和博物志。取材于国服的主线、活动（含隐藏剧情）、故事集和干员密录，兼及官方的书外材料；塔卫二编收《明日方舟：终末地》。

- 网页：<https://bbfutaba.github.io/arknights-chronicle/>
- 单文件版：[Releases](https://github.com/BBFutaba/arknights-chronicle/releases/latest) 里的 `kezhoulu-Ox.x.html`，下载后用浏览器打开，不用联网。

这个仓库就是网页本身，GitHub Pages 从 `main` 发布。里面的文件由编者在本地从书稿生成，不在这里直接修改。勘误、补遗和异议请提 [issue](https://github.com/BBFutaba/arknights-chronicle/issues)。

## 网页内容

- **时间轴**：竖向分叉时间线，主世界线上分出各条故事线；另有立体视图。可按人物、地区势力、故事线和文字筛选。
- **编年史**：泰拉编从外纪到一一〇三年，塔卫二编以塔罗斯历系年。每条先列纲，再写目，然后是人物和原文，最后是考异。
- **纪事本末**：一件事一页，按事连读。
- **列传**：一人一篇。
- **剧情**：章节和活动目录，分集显示官方简介、出场人物和相关事件。
- **人物**：立绘和头像、基础档案、列传、出场剧情、相关事件。
- **博物志**：地理、势力、族裔、源石、科技、人文、生灵、远古八门的百科。
- **关系图**：人物、地区、势力和事件的线索板。
- **鸣谢与协议**：鸣谢、贡献者，以及转载和再创作的约定。

网页不含剧本全文和干员档案正文，只有书中引用的原文片段。

## 文件

```
index.html  style.css  js/   网页（原生 JS 模块）
data/                        书和索引的数据
fonts/  vendor/              字体子集；关系图库 force-graph
img/                         干员立绘和头像
```

## 数据来源与版权

- 剧本、干员档案、敌人图鉴：[Kengxxiao/ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData)，版权归鹰角网络。
- 干员立绘和头像：[yuanyan3060/ArknightsGameResource](https://github.com/yuanyan3060/ArknightsGameResource)、[555me/EndfieldAssets](https://github.com/555me/EndfieldAssets)，版权归鹰角网络。
- 参考的年表：[PRTS「泰拉年表」](https://prts.wiki/w/泰拉年表)，CC BY-NC-SA 4.0。

## 协议

| 内容 | 协议 |
|---|---|
| 网页代码：`index.html`、`style.css`、`js/` | MIT，见 [LICENSE](LICENSE) |
| 书的文字：`data/` 里编者撰写的纲、目、考异、纪事本末、列传、博物志和人物志，以及系年和编排 | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans) |
| 书中引用的游戏内容、`img/` 里的立绘和头像 | 版权归鹰角网络，不在上述授权之内 |
| `fonts/` 的字体 | SIL Open Font License 1.1，见各字体的 LICENSE |
| `vendor/force-graph.min.js` | MIT，见 [vendor/force-graph.LICENSE](vendor/force-graph.LICENSE) |

转载、摘录、翻译、改写、再创作都不必事先询问；要注明出自《刻舟录》，署编撰者双叶，附网页链接，说明改动了什么，不用于商业目的，改编的作品以相同协议发布。详见网页的「鸣谢与协议」页。

《刻舟录》是爱好者编写的非营利同人作品，与鹰角网络没有关系。
