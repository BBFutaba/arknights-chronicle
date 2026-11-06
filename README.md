# 刻舟录

《明日方舟》剧情的编年史，同人整理，非官方作品。纲目体，按年分卷，穿插原文片段，另有纪事本末（按事）、列传（按人）和博物志。取材于国服的主线、活动（含隐藏剧情）、故事集和干员密录，兼及官方的书外材料。

- 网页：<https://bbfutaba.github.io/arknights-chronicle/>
- 单文件版：[GitHub Releases](https://github.com/BBFutaba/arknights-chronicle/releases/latest)

## 网页内容

- **时间轴**：竖向分叉时间线。灰线是主世界线，每个剧情组是一条故事线，从主世界线分出、结束时合回。一行是编年史的一个条目，次序、日期和文字都以书为准；PRTS「泰拉年表」只作参考，列在详情里，书中不录的存目打开开关才显示。可按人物、地区势力、故事线和文字筛选，↑↓ 键逐条浏览。
- **编年史**：全书二十九卷，从外纪到一一〇三年。每条先列纲（一句提要），再写目（始末），然后是人物和原文，最后是考异（默认折叠）。原文出处可以点开，在剧情页高亮被引的行。
- **纪事本末**：一件事一页，按事连读。索引可按时期、地区、性质、了局（已了、未了、悬案）筛选和分组。
- **列传**：一人一篇。索引可按出身、盖棺（盖棺定论、来日方长、生死未卜、异数）、族裔、所属、首见、身份筛选和分组。
- **剧情**：章节和活动目录 → 分集阅读（官方简介、出场人物、相关事件、剧本全文）。
- **人物**：干员档案、敌人图鉴里的 NPC 简介、列传、出场剧情、相关事件、常同场人物。
- **博物志**：地理、势力、族裔、源石、科技、人文、生灵、远古八门的百科，可搜可筛。地理、势力两门列出全部地区势力，一地一页，还没写正文的标「尚未成文」。每条底部的「书中提及」统计编年史纲目和列传里写到它的地方。
- **关系图**：人物、地区、势力（可选事件）；连线越粗、拉得越近，共同出场的集数越多。布局参数可调，可以以任意节点为中心查看。
- **凡例**：全书体例，以及转载和再创作的约定。

公开版没有剧本全文和干员档案正文，见下文「公开版」。

## 数据来源与版权

- 剧本、干员档案、敌人图鉴：[Kengxxiao/ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData)，版权归鹰角网络。
- 参考的年表：[PRTS「泰拉年表」](https://prts.wiki/w/泰拉年表)，CC BY-NC-SA 4.0。日期是社区根据剧情推测的，可能有偏差。
- 书外材料：设定集《大地巡旅》、官方影片、官方漫画、微博图文《泰拉记事》，版权归鹰角网络。原件和 OCR 全文放在 `Raw Data/`，不进 git，不进公开版；书里只录短引。
- 编者文字：纲、目、考异、纪事本末、列传和博物志的正文，按 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans) 发布，转载和再创作的约定见网页的「凡例」页。

## 协议

| 内容 | 协议 |
|---|---|
| 代码：`pipeline/`、`site/` 的网页代码 | MIT，见 [LICENSE](LICENSE) |
| 书的文字：`data/annals/`、`data/curated/` | CC BY-NC-SA 4.0，见 [data/LICENSE.md](data/LICENSE.md) |
| 书中引用的游戏内容 | 版权归鹰角网络，不在上述授权之内 |
| 关系图库 `site/vendor/force-graph.min.js` | MIT，见 [site/vendor/force-graph.LICENSE](site/vendor/force-graph.LICENSE) |

## 使用

需要 Python 3.12+、git 和 curl，不依赖第三方 Python 库。所有命令在项目根目录运行。

```bash
python -m pipeline.fetch     # 下载或更新游戏数据（约 320MB）；PRTS 年表已有缓存就不再抓取
python -m pipeline.build     # 解析全部剧情和年表，生成 site/data/
python -m pipeline.serve     # 在 http://127.0.0.1:8765 打开浏览器
python -m pipeline.check     # 年表出处对应情况、网页数据引用检查、需要人工处理的说话人
```

### 公开版

本地版（`site/`）和 `刻舟录-完整版.html` 含剧本全文，**只在本地使用，不要公开发布**。

```bash
python -m pipeline.publish          # 生成公开版到 dist/，去掉剧本全文和干员档案正文
python -m pipeline.bundle --public  # 打成单文件 刻舟录-公开版.html
python -m pipeline.deploy           # 发布当前提交：推送 main，更新 gh-pages 和 GitHub Release
```

公开版只含编年史、博物志和它们引用的片段；剧情页只显示官方简介、出场人物和相关事件。

### 书稿

- 卷稿在 `data/annals/<年份>/`（一〇八〇年以前合为 `外纪`、`前纪甲`、`前纪乙`、`前纪丙`，原文和年表都无年份的放 `不系年`）。列传在 `列传.md`，纪事本末在 `纪事本末.md`，博物志在 `博物志/`。
- 引文只写出处指令（分集 id + 行号 + 锚点），不写原文；构建时程序从剧本里取出原文并核对锚点。导出的 `site/data/` 和 `annals/<年份>.md` 含剧本原文，不提交。
- 体例见 `data/annals/凡例.md`，写法见 `写作规范.md`、`博物志须知.md`、`列传索引须知.md`，进度和待改进事项见 `路线图.md`。

```bash
python -m pipeline.annals build                   # 检查并导出编年史和博物志（pipeline.build 结束时也会运行）
python -m pipeline.annals check <稿件路径>        # 检查一个卷稿或博物志文件
python -m pipeline.annals show <分集id> [起 止]   # 带行号列出一集剧本
python -m pipeline.annals find "<正则>" [组id]    # 在剧本里搜索
python -m pipeline.annals                         # 列出全部子命令
```

## 目录结构

```
pipeline/
  fetch.py build.py check.py serve.py             命令入口，见「使用」
  gamedata.py script.py entities.py analyze.py    读游戏数据，解析剧本，归一说话人，统计每集出场
  prts.py chronicle.py linker.py                  PRTS 年表：抓取、解析，对应出处、人物和地区势力
  profiles.py site.py                             干员档案和 NPC 简介；导出 site/data/*.json
  annals.py timeclues.py                          编年史和博物志：查剧本、取引文、校验、导出；提取时间线索
  publish.py bundle.py deploy.py                  公开版；单文件版；上线
  comics.py records.py ocr_gpu.py ocr_tool.py     书外材料：下载官方漫画和《泰拉记事》，OCR
data/
  annals/          书稿（只含出处指令和短引，不含全文）
  curated/entities.toml  人工维护：别名、同名区分、路人过滤、单字名字、补充的地区势力
  raw/             游戏数据和 PRTS 缓存（git 忽略）
  structured/      构建的中间产物（git 忽略）
site/
  index.html, style.css, js/   网页（原生 JS 模块，不需要打包）
  vendor/force-graph.min.js    关系图库（force-graph 1.52.0）
  data/                        生成的数据（git 忽略）
```

`Raw Data/`（书外材料）、`annals/`（导出的成书）、`dist/`（公开版）也都在 git 之外。

## 剧情范围

| 分类 | 来源 | 组 id | 分集 id |
|---|---|---|---|
| 主线、活动、故事集 | `story_review_table`（游戏内「剧情回顾」） | `main_9`、`act13side` 等 | 游戏的 storyId，如 `act13side_level_act13side_01_beg` |
| 活动隐藏剧情 | `story_review_meta_table` 的活动档案，并入所属活动组、排在原有分集之后 | 所属活动 | `组id_剧本文件名`，如 `act13side_level_act13side_hidden_st01` |
| 干员密录 | `handbook_info_table` 的 `handbookAvgList`，一位干员一个组，组名是干员名 | 干员 id，如 `char_427_vigil` | 游戏的 storyId，如 `story_vigil_set_2_story_1` |
| 集成战略、生息演算、其他文本 | 原始 `story/` 目录里剧情回顾之外的文本（结局、月度记录、记录点、活动任务和手册、部分愚人节活动），标题来自各数据表 | `rogue_4`、`sandbox_1`、`record_main_13` 等 | `组id_文件名` |

- 隐藏剧情游戏里没有关卡代号，按 PRTS 的写法编作 `NL-HD-1` 等，分集类型记作「幕间」。目前只有《长夜临光》的「逃离」「选择」「路漫漫」三篇。
- 不收教程、训练和关卡内对话。
- 这是剧本库的范围，比书宽；入不入书看凡例，如联动活动不入正史。

## 识别规则

- **说话人 → 人物**：先查 `entities.toml` 的 `[aliases]` 和 `data/annals/别名.md`（一人多名，合成一个人物页，如 Logos = 逻各斯、恩希欧迪斯 = 银灰），再匹配干员名；异格干员并入本体；「A&B」拆成两人，「阿米娅？」归到阿米娅；剧本选项算博士的台词。路人（「整合运动成员」「士兵A」）、以势力名说话的、「？？？」不建人物。同一个名字在不同剧情里指不同的人时，在 `entities.toml` 的 `[scoped_aliases]` 里按分集或组改写。
- **立绘**：对得上干员 id 的，没说话也算出场。
- **提及地区势力**：名字在一集台词和旁白里出现至少 2 次。
- **PRTS 年表**：事件描述按名字最长优先匹配人物和地区势力；出处按「编号 标题/BEG|END|NBT」或「干员/干员密录/第几套[-第几篇]」对应到分集。

`python -m pipeline.check` 会列出疑似干员的说话人写法和被过滤的高频说话人，确认后写进 `entities.toml`。

## 进度

- 剧本库 2,809 集：主线 429、活动 1,104（含隐藏剧情 3）、故事集 132、干员密录 399、集成战略 260、生息演算 270、其他文本 215。
- 全书 29 卷 1056 条（附记 391），列传 279 篇，纪事本末 37 件，博物志 317 条，已对照原文核对（未核完的部分见 `data/annals/路线图.md`）。

待办（书稿的细项见路线图）：

- [ ] 加入《明日方舟：终末地》的时间线
- [ ] 平行时间线（PRTS「泰拉年表/平行时间线」）
- [ ] 同名 NPC、说话人别名的全面人工审核（目前逐案处理）
