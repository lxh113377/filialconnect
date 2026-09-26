# Changelog

本项目所有值得注意的变更都记录在此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed
- **一条判据崩掉时，整条链的结论会一起消失**（第 31 轮由「真加一篇教程」实测暴露）。
  `main()` 裸调每个 `t_*`，而 `tools/package-offline.py` 在 staging 集不完整时
  `raise SystemExit`——于是此前**已收集的 5 条 roster 失败没打印出来、后面 8 个判据根本没跑、
  连 `N/M checks failed` 这行总结都没有**，屏幕上只剩一行消息。一个变红的判据销毁了其它所有判据的证据。
  现在 `main()` 捕获 `SystemExit`/`Exception`：记成一条带判据姓名的失败、继续跑完其余判据、
  并额外打印 `ABORTED JUDGES: …` 点名（拒绝打包的语义不变，仍然红）。
- `tools/judge_coverage.py` 用正则找「判据登记表」时只认 `for fn in (...)` 这一种写法，
  把它改成 `JUDGES = (...)`（同一份代码、换一种拼写）就让解析返回空、守卫死在 `None.group(1)`。
  改为 AST 结构解析（两种写法都认），解析不到就**显式拒绝猜测**而非静默返回空；
  selftest 从 3 例涨到 7 例（含两种拼写的正例与「无登记表→读为空」的反例）。

## [1.11.0] - 2026-09-26

第三十二轮（同一命令第 24 次重发 = 完整重执行）。补完第 30 轮留下的那一半：`manual` 名单当时只是
「不接管」，于是**首页、404、求助页、防骗页这四张最常被打开的页在中文下标签页仍是英文**。
本轮给手写标题补真正的双语对，而不是把它们硬塞进派生规则（硬派生会改写英文＝回归）。

### Added
- 显式页面标题键 `page.title.<slug>`（en/zh 各 4 个）：`en` 半边**必须与静态 `<title>` 逐字节相同**
  （"英文不动"的可跑证明），`zh` 半边须含汉字且不得等于英文。四个中文值里三个直接复用字典已有字符串
  （`呼叫求助`／`防骗提醒`／`找不到这个页面`），只有首页那条是新增译文。
- 判据三条：① 出厂 meta 必须等于生成器契约（手改 meta 会被抓）；② `manual` 页必须真有双语键且中英不同；
  ③ **动态豁免要交租**——运行时从生成 meta 里切片取键名，孤儿键扫描（`data-i18n` 与 `t('a.b')` 两种）
  都看不见，故豁免集由 `build.dynamic_dict_keys()` 单点提供，CI 侧 `check-i18n.py` 与本地判据 import
  同一函数（不再各抄一份），而"被声明为动态却没有任何出厂页面真的声明它"的键直接判红。

### Fixed
- 中文浏览器首访（本地无偏好）时首页标签页由 `FilialConnect - Digital Bridge for Seniors`
  变为 `孝心联 - 长者的数字桥梁`，求助页变为 `呼叫求助 - 孝心联`；英文侧浏览器实测逐字节未变。

## [1.10.0] - 2026-09-26

第三十一轮（同一命令第 23 次重发 = 完整重执行）。把上一轮「文案要在它承诺的语言里兑现」推到
**读屏器听到的那一层**：实测中文页面上最结构化的两处播报——主导航 landmark 与移动端菜单按钮——
仍是英文（`aria-label` 没有字典键，`data-i18n-aria-label` 体系从不覆盖它们）。对一个发布无障碍声明、
CI 跑 axe 的适老站，这是 WCAG 3.1.2（内容目的语言）级别的缺陷。

### Fixed
- **中文页面的 ARIA 播报标签此前一直是英文**：主导航、移动端菜单开关、教程步骤、上下页导航、
  按主题筛选、防骗条目风险等级、面包屑导航。静态英文仍是首屏兜底，现在每处都带
  `data-i18n-aria-label`，切语言时由 `applyTranslations` 改写；两处由运行时自己赋值的标签
  （语言开关、随机协助码）不强行派生，改为**显式豁免并点名赋值代码**。
- **`Breadcrumb` 这条是真浏览器抓出来的**：判据初版谓词要求「≥2 个英文单词」，单个词的标签直接漏网，
  在中文页面实跑观测才发现。谓词收紧为「含英文词且无汉字」，并留一条单词反例守住这个洞
  —— 谓词不是规格，观测才是。

### Added
- 判据 `t_aria_locale`：每个会被读出/悬停显示的属性（`aria-label`、`placeholder`、`alt`）若仍是英文，
  必须带 main.js **真正会换**的标记，否则必须落在带理由的豁免表里；豁免项一旦不再命中任何属性即判红
  （防豁免表长成万能后门）。同时断言「main.js 的交换表与本判据是同一份清单」，并把
  `data-i18n-title` 这类运行时根本不处理的标记判红——HTML 看着本地化了、浏览器里没换，
  比没有标记更坏（假安全感）。变异电池含一条「加了正确标记」的**不得转红**反例。

## [1.9.0] - 2026-09-26

第三十轮（同一命令第 22 次重发 = 完整重执行）。主轴把前几轮的「文案要有代码撑着」推进到
「文案要在它承诺的语言里兑现」：实测到一个面向中文长者的真实缺陷——切到中文后正文全翻译，
但浏览器标签页标题仍是英文（`<title>` 无 i18n、`applyTranslations` 从不碰 `document.title`）。
本轮以零英文回归、零新字典键修好（10 页派生、4 页手写标题标 manual 不接管），并留下一条
会拒绝「谎报 derived」的判据 `t_page_title`（5 条变异逐条转红）。

### Fixed
- **浏览器标签页标题此前只跟语言切换的正文走，切到中文标签仍是英文**（第 30 轮实测）。
  正文所有 `data-i18n` 节点都翻了，但 `<title>` 没有 i18n、`applyTranslations` 也从没碰
  `document.title`——对中文长者用户，标签页/书签/浏览器历史都是英文，是用户可见面的漏配。
  现在 `derived` 页在切语言时用「本页已翻译的 `<h1>` + 本地化品牌」重算 `document.title`；
  品牌后缀 `nav.brand`（FilialConnect / 孝心联）双语早已存在，**不新增任何字典键**
  （避免制造「标题的第二权威」）。`manual` 页（index / 404 / call-help / fraud-database）的静态标题
  本就 `≠ h1+品牌`，强制派生会改写它们的英文标签＝回归，故 main.js 对这四页**不接管**。
  **英文逐字节不变**：`derived` 页的静态标题恰好等于 `h1.en + ' - ' + brand.en`，重算结果与原文相同。
  浏览器实测两向：hospital 页 EN=`How to Book a Doctor Appointment - FilialConnect`、
  切换后 ZH=`如何预约挂号 - 孝心联`；index 页（manual）跨切换恒为 `FilialConnect - Digital Bridge for Seniors`。

### Added
- **`t_page_title` 判据**（新增断言，条数以 `python tools/test_build.py` 实跑输出为准，不抄进散文）：每页必须声明 `derived|manual`；`manual` 集合
  恰为那四个手写标题页；`derived` 数量有下限（关掉某页本地化是决策不是手滑）；每个 `derived` 页的
  静态 `<title>` 必须逐字节等于 `h1.en + ' - ' + brand.en`（否则判据红，逼着要么改标题要么显式转
  `manual`）；`derived` 的 h1 中英不得相同（标题没本地化）；h1 含 `<br>` 也判红（标签渲染不了换行）。
- **每页 HEAD-META 增加 `<meta name="filialconnect:page-title" content="derived|manual">`**，
  由 `build.py` 依 `PAGE_TITLE_MANUAL` 集合单向生成（页面不再各自手标模式）。

### 自纠（本轮）
- `t_page_title` 第一版的「中文标题==英文」断言**构造上永假**：它比的是拼好品牌的整串
  （`brand_en` 恒 ≠ `brand_zh`，故 `want_zh` 永不可能等于 `want_en`）。是变异 C4 跑出
  「被别的判据抢先命中、自己这条没响应」才暴露——与第 26/27 轮记过的"构造上永真/自比"同族。
  改成比较 **h1 本身**是否中英相同（真正的未本地化形态），C4 随即由本判据点名转红。

## [1.8.2] - 2026-09-26

第二十九轮（同一命令第 21 次重发 = 完整重执行）。主轴承接第 28 轮的「判据可信度」，把最后一条靠惯性挂账的债变成规则：每个被部署的资产都必须有理由，否则判红（#145 结案），部署集逐字节未变（实测 before==after==101，delta 为空）。另归因纠正一条被追错的账：桌面 SEO 0.63 来自 404.html 上刻意排除预算的 is-crawlable，不是待修缺陷。

### Added
- **#145 结案（挂账变规则）**：`assets/` 一直按整目录部署，结构上挡不住一个无人引用的散件混进线上——
  第 26 轮那条「logo 没人引用却仍随站点部署」的挂账本质就是这个。新增 `t_deploy_reasons`：每个被部署、
  被跟踪、非构建产物的 assets 文件，必须能被「页面引用 / og:image / manifest / 运行时 fetch 模式 /
  显式带理由白名单」解释，否则判红。配套 `tools/stage-site.py explain <path>` 回答「这个文件凭什么被服务」。
  **部署集逐字节未变（实测 before==after==101，delta 为空）**，变的是一件事：下一张随手丢进 assets/ 的图
  现在会让构建变红，而不是悄悄跟着上线。
- `SHIPPED_WITHOUT_REFERENCE` 把三处「决定」写进代码（`assets/locales/{en,zh}.json` 是给离线包保留的
  字典源、`logo-future-designer.png` 是 5fbe651 有意入库的大赛 logo）——**没有**为了让账面干净而删它：
  入库是有意的，规则要的是「写下理由」，不是「消灭例外」。

### Fixed
- **本轮先写坏了一版 #145 并回滚**：第一版把 `ALWAYS_SHIP_DIRS=('assets',)` 直接换成「按引用决定部署集」，
  实测部署集从 101 掉到 **82**——`assets/css/main.css`、6 张教程图、3 个 js 全部下线（等于把整站打空）。
  是靠**先存快照、改完比集合**发现的，不是靠推理。改成「生产规则不动 + 事后审计」的写法才对。
  教训与第 28 轮同源：能改变线上文件集的东西，必须先证明等价再落地。

### 归因（不新增代码，纠正一条被追错的账）
- **桌面 SEO 0.63 不是待修项，是刻意排除项**：`reports/perf-baseline.json` 里 `min.seo=0.63` 来自
  `404.html` 的 `is-crawlable`（权重 4.04）失败，而 `lighthouserc.json` 第二行矩阵本就对 `404.html`
  设 `seo:"off"`——它不进预算，也不该进「待修」。真正的非预算失败是若干页的
  `cumulative-layout-shift score=0.73`（性能类，已在 `unstable_pages` 记账）。下一轮不必再为 0.63 起跑。
  已知缺口如实记：baseline 里失败审计的 `why` 字段是空的（`'? ::'`），要拿到 target/node 明细得在
  **失败的那次 run** 里跑 hand-only 的 `ci-audit-nodes.py`，本地重跑一次 Lighthouse 不在本轮成本内。

## [1.8.1] - 2026-09-26

本版本含**两轮**工具改动：第二十七轮未随 v1.8.0 发走的发版护栏条目（其页面与文案变更已在 v1.8.0 发布），以及第二十八轮（同一命令第 20 次重发 = 完整重执行）。

第二十八轮主轴只有一个：**判据链自身的信任基础**。peer 侧 73 分钟内除星数什么都没变（离线 ZIP 作为 Release 资产仍是 9 个 peer 中唯一），台账却在一天内三次把 CI 判红。本轮不再换字段，而是禁止「属于别人的量」进入台账（字段集合钉死 + AST 级 selftest 接进 CI），并把接线判据升级为按 step 分类——新规则立刻查出一条「看着接了线、其实永远判不红」的假象。另新增一格对标维度：10 仓中仅 axe-core 与本仓写出数字响应时限，而本仓那句承诺此前只是话，现已入判据。链条数不写在此处：`python tools/test_build.py` 自己会打印，抄进散文就是下一个会腐烂的数字。

### Fixed
- **判据台账第三次把「别人拥有的量」抄进自己的报告，第三次把 CI 判红**（第二十八轮）。
  时间线全部实测：① `pagefind_shards_local`（有索引 52 / 无索引 0）→ ② 换成 `deploy_profile_files`
  （101 / 49，同病）→ ③ 换成「committed 文件数」并跑过「无索引对照」，仍然在 `765ce89` 上红：
  那次提交**新增了一个已跟踪文件**，49 就变 50。剩下的错不在字段选得不对，而在**习惯性地把
  属于别处的量冻结成第二权威**。现在台账顶层字段被 `t_judge_ledger` 钉成固定集合（6 个），
  多一个派生计数即红；包体成员数回归 `package-offline.members()` 现场执行。
- **`--selftest` 自己的两个缺陷**：① 首版拿**正文字符串**做规则，`notes` 里写着
  `package-offline.members()` 这句话，于是它报「measure() 引了别人的成员数」而 measure() 并无此调用
  （扫描器把自身文本当缺陷，本仓第三次）；② 改成 AST 后又发现 `measure()` 里真有一处
  **死掉的 `staging_sets()` 调用**——规则第一次跑就抓到了真东西。现在规则只看 AST 里的调用与模块名。
- **接线判据的强度补了一格**：`gate_wiring` 原来只问「CI 里有没有提到这个工具」，
  于是删掉某个 step 里的一行调用、只要兄弟行还提到同一个工具，就仍算「已接线」（变异 R5 实测仍瞎）。
  现按 **step 分类**，`continue-on-error: true` 的 step **不再算接线证据**。
  该规则**立刻抓出一条真的**：`ci-audit-nodes.py` 名义上是 CI 判据，实际待在一个
  `continue-on-error` step 里，它的结论永远不能把构建判红——正是第 7 轮 `warn` 级预算把
  SEO 0.63 藏了六轮的同一形状。已如实降为 hand-only 并写进 AGENTS.md（诊断件，失败时去日志读）。

### Added
- **`tools/judge_coverage.py --selftest`**（接进 CI 与 AGENTS.md 动手前清单）：台账生成器的
  `measure()` 不得从 git / 文件系统 / 别的工具成员数取数；三条自证（正例必须开、真文件必须静、
  禁词表不得为空）。
- **安全响应时限成为有判据的承诺**（第 28 轮 peers 新维度）：10 个仓里只有 axe-core 与本仓在仓内
  写出**数字**时限（24 工作小时 / 7 天），而本仓那句「维护者会在 7 天内回复」此前和 README 里
  腐烂的数字属于同一类——只是话。`t_documented_numbers` 现钉住 SECURITY.md 的数字时限，并要求
  SUPPORT.md 若给数字必须与之一致（另记缺口：SUPPORT.md 现在写的是 "within a week"，无数字，
  判据对非数字表述刻意放行）。
- **可移植性对照**（`_internal/test_round28_ledger_portability.py`）：三种树状态下台账字节必须完全
  相同——含 ③「多一个已提交文件」，即今天 CI 真实踩到的那一态。

链条数不在这里重复（它已被本行以下的内容改动过两次，正是本仓禁止散文写数字的理由）；变异电池：第 27 轮 5/5 与 6/6 复跑通过（N5 的期望名随本次重构更新），
第 28 轮 R1-R4 转红、R5 记为**已声明的盲区**；工具接线台账 ci=12 / test=5 / hand=1。


## [1.8.0] - 2026-09-26

本版本带走两个轮次的工具改动：第二十六轮刻意留作「随下次发版带走」的发版护栏，与第二十七轮全部条目。

第二十七轮对标：主轴是**「文案说的有没有代码撑着」**。功能面与 peers 打平（离线 ZIP 交付仍是 9 个 peer 中唯一），真实产出全部落在判据可信度上：撤回 5 处无实现的屏幕共享承诺、把违禁词表升级为能力→证据判据、verify-live 三态分明并停止用本地哈希名冒充线上事实、README 五处腐烂数字钉死、防「判据没接线」的判据入仓、覆盖面台账去手抄。链 1,963 → 2,013，变异 11 条，自我纠错 13 处。

### Added
- **发版护栏现在点名 `verify-live` 作业**（第二十六轮批注追加执行）。原先 `release.py::ci_verdict`
  把所有 check-run 混成一坨，只看"有没有红、有没有跑完"，看不见"该探测线上的作业根本没存在"——
  实测 v1.6.1 那次发版的 commit 上只有 `quality` + `deploy`，**线上从未被探测过也照样算绿**。
  现在 `classify_checks()` 三态分明：required 作业缺席 = `unknown`；`verify-live` 在 deploy 已 success
  的前提下缺席 = `unknown`（**`--allow-pending` 放宽不了 unknown**）；它 queued = `pending`；失败 = `red`。
  反证用的是真实历史数据：对 v1.7.0 的 commit 判 `green`，对 v1.6.1 的判
  `unknown: verify-live is absent although deploy succeeded - the live site was never probed`。
  作业名取自 `gh api .../check-runs` 实测（是**作业名**不是 workflow 名，也不是 step 标题）。
  新增 16 条判据（7 个夹具 × 2 断言 + 3 条接线断言）：其中"分类器任何输入都不得抛异常"是把
  一次 `KeyError` 崩溃**转成具名红**得来的——变异体 X3 最初只是崩，不算被抓住。
  5 条变异 X1-X5 逐条实测转红、还原 0 红。纯工具改动，按 #123 规矩不制造版本号，随下次发版带走。

### Fixed
- **远程协助页的屏幕共享承诺被撤回（第二十七轮，反复缺陷类 1 的第五次现行犯）**。该页此前写
  「让孩子看到你的屏幕并画箭头」「只有你批准的人能连接」「随时一键结束会话」「旧码不可复用」，
  而 `git ls-files | xargs grep -l 'getDisplayMedia|RTCPeerConnection|getUserMedia|WebSocket'`
  实测**零命中**——没有任何实现代码。更难看的是无障碍声明 `a11s.l1` 早就写明「远程协助连接码为
  演示功能」，同一站点两处文本互相打脸。现在整页按真实能力重写（话术 + 指路到系统/微信自带的
  共享屏幕），演示面板加 `status-demo` 标记与独立披露段；EN/ZH 各重写 26 条 + 新增 2 条。
- **`tools/verify-live.py` 的两处判据缺陷**：① 无代理时 101 次 × 30s 超时**零输出挂死 300s**
  （rc=124），现在先探一次可达性，不可达即 `UNVERIFIED` + `exit 2`（不冒充绿也不冤枉红）；
  ② 构建产物一半的分母取的是**本地** `pagefind/` 哈希名，而哈希名属于最后一次构建它的人——
  实测线上清单 `en_7dc82bf894` 与本地 `en_96b08b50ce` 不同，于是它对 CI 刚判过 `PASS: live site
  matches 081ea3d` 的同一个提交报了 4/101 假红。现在向线上清单要它真正发布的路径再探测。
- **README 里第五个腐烂数字**：本轮修前四个（13 页 / 28 条规则 / 11 个子页面 / 14 个 init 模块，
  实测 14 / 27 / 12 / 16）时，我自己的度量式 `^\s{4}init[A-Z][A-Za-z]*\(\);$` 漏掉了
  `initI18n`（`[A-Za-z]*` 跨不过数字），把 16 数成 15 并差点据此把文档改错。**修的是模式，不是文档**。

### Added
- **`t_capability_claims`**：把「文案承诺 = 代码事实」从违禁词表升级为**证据表**。违禁词只会在
  事故发生后变长（本轮 5 条全不在表内），而能力短语必须能在具体文件里找到实现（`tel:` /
  `speechSynthesis` / `pagefind` / `window.print()` ...），实现消失即红。判据先写自己的阳性对照
  文件再扫，因为「扫了个空集合」会打印"没有未实现承诺"并变绿。5 条变异 N1-N5 逐条转红。
- **`t_documented_numbers`**：泛化的散文数字判据（缺陷类 7 的老判据只匹配 `test_build.py … 条`，
  所以同一份 README 里 4 个数字全腐烂）。5 条 `(句子, 测量函数)` 表 + 覆盖面自证 + WCAG 等级唯一性
  （`WCAG 2.4.11` 是成功标准不是版本号，计数前先归因）。无障碍声明 3 处 meta 与 README 1 处的
  `WCAG 2.1` 统一为 2.2。
- **`tools/gate_wiring.py`**：防「判据没接线」的那个判据自己没接线——原 `_internal/verify_gates_wired.py`
  在仓外、硬编码 Windows 绝对路径、16 个工具只覆盖 4 个、且没有任何东西跑它。现在每个工具必须
  声明唯一消费者类别（ci / test / release / hand），**磁盘与声明必须互为子集**，声明 ci/test 却没被
  真实调用 = `silent_gap`，hand-only 必须写进 AGENTS.md。顺带抓出一条真的：AGENTS.md 让人跑
  `tools/contrast_coverage.py --check`，CI 从来没跑过——现在它是个 CI step。
- **`tools/judge_coverage.py`**：覆盖面台账改为**生成**而非手抄（第 26 轮那份记着离线包 77 条目 /
  28 源文件，实测 82 / 33，已漂移）。同时把 `_internal/round26` 台账的 `checks_last_run: null`
  挂账明确为「由 `tools/test_build.py` 自己打印」，不再生成第二个真相源。
- **`t_perf_provenance`**：`perf-probe.mjs` 保持 hand-only（写进 AGENTS.md），但它喂给阻断预算的输入
  必须可追溯——逐页记录里的 Lighthouse 版本必须等于 `package-lock.json` 的 pin，且声明采样轮数。
- CI 新增一个 step 跑 `gate_wiring.py --check` + `judge_coverage.py --check`。
- **本轮我自己造了 13 处判据缺陷并全部当场归因修掉**（不粉饰）：最有价值的三条——① 变异 N5 跑出
  MISS：我把「台账 vs 实测」写成 `measure()` 与 `measure()` 自比，构造上永真，正是第 26 轮刚记过的
  "构造上永真的断言"，改为「已提交台账 vs 活测量」才转成具名红；② 变异 N4 的反例 `pagefind` →
  `xpagefind` 保留了被搜串，改完仍绿，测的是夹具不是判据（换成 `searchkit` 才有效）；③ **新接进 CI 的
  `judge_coverage.py --check` 在 `e0a04c0` 上判红**（committed 101 vs computed 49）：我把只在单机成立的
  量写进了台账（`pagefind_shards_local` 与 `deploy_profile_files` 都随索引是否存在变化），而这正是第 26 轮
  刚写进全局技能的第 ⑥ 条判据；第一次只删了前者，两种状态各实测一次才确认修净（有/无索引 `--check`
  输出逐字节相同）。其余为模式转义、全角逗号、`WCAG 2.4.11` 被当版本号、并发编辑撞上整轮变异等。

自测链 1,963 → **2,013**；变异体 11 条（P0-A 5 条 + 新判据 6 条）逐条转红、未变异对照 0 红；
其中 2 条变异体第一版是**假反例**（一条测夹具、一条自比永真），修正后重跑才计数。

## [1.7.0] - 2026-09-26

第二十六轮对标：主轴是**交付链最后一段的口径一致性**——"仓库里绿"与"线上对"之间此前没有任何判据，
而"哪些文件算站点"这件事被两份手抄清单分别决定。全部结论带实测与变异体，覆盖面台账见
`reports/round26-judge-coverage.json`。

### Added
- **`tools/stage-site.py`：站点文件集合的唯一枚举器**。原先 `deploy-pages.yml` 与 `ci.yml`
  各存一份手写 `cp -r` 清单，且**已经漂移**（CI 拷 `content/`＝生成器输入，没人 fetch；
  Pages 拷 `sw.js`/`pagefind/`，CI 因此从没测过 Service Worker 那条路）。
  现在两份清单都由它派生：`--profile deploy` 给 Pages，`--profile probe` 给 CI 的本地服务器，
  台账落 `reports/deploy-staging.json` 并进 CI 漂移门禁。
  派生集合与旧手抄清单**逐文件相同**（101 个），唯一差异是 `assets/images/.gitkeep`——
  实测 GitHub Pages 对点文件回 404（`--compressed` 取回 404 页），它本来就不算交付物。
  覆盖面：页面引用枚举 28 条（下限 20）、动态模式 10 条、逐页断言 14 条。
  **写这个工具的过程中我自己引入过一次回归并被实测抓住**：只按 HTML `src/href` 枚举会漏掉
  ① manifest.json 的四个图标（PWA 装机图标）② 只以绝对 URL 出现的 `og-*.png`（社交卡片图），
  共 12 个文件会被静默不部署——修法是 `ALWAYS_SHIP_DIRS` 与 `manifest_refs()`，
  并新增"绝对自站 URL 也算引用"的解析（站点基址从 `sitemap.xml` 读，不在第二处重述）。
- **判据 `t_deploy_staging`（32 条）+ 变异体 6 条各自转红**：页面引用一个没人部署的路径 /
  workflow 不再调枚举器 / 手抄清单回潮 / 台账被改数 / `sw.js` 指向不存在的 workbox 块 /
  整目录不再全拷。**过程中删掉一条永真断言**：refs 原本被无条件并入 deploy 集，
  导致 `refs_not_staged` 在构造上不可能红——改成"引用必须落进部署集"后 M1 才真正转红。
- **`tools/verify-live.py`：线上态 == 仓库态**。按部署集逐个取回线上文件比 sha256
  （已提交的比字节，构建产物只比可达——pagefind 索引由部署作业现建，哈希名本就不该跨构建相等），
  并核对名单的**传输字节**是否还是 README 写的那个数、GitHub 仓外元数据是否还是那句被作废的话。
  2026-09-26 实测：`deploy` 集 101 项里 49 个已提交文件逐个一致、52 个索引分片全部可达，
  名单线上 `Content-Length: 532283` + `Content-Encoding: gzip` + `Vary: Accept-Encoding`
  ⇒ **挂了一轮的 #135 就此结案**（本机直连 github.io 全天 000，走代理 200 才拿到证据）。
  接进 `deploy-pages.yml` 的新 `verify-live` 作业（`needs: deploy`，只在 main 推送后跑：
  CDN 抖动不许拦住无关 PR）。
- **判据 `t_public_metadata`（8 条）**：把 About 描述钉成期望值 `reports/repo-metadata.json`，
  与仓内**同一份**违禁口号名单回问（原先名单写在 `t_promises` 里，两份实现的坑本仓记过）。
  描述里的页数交叉核对花名册、主题须为 GitHub 实际存储的小写 slug、homepage 须等于 sitemap origin。
- **GitHub Release 开始挂离线 ZIP 资产**（`tools/package-offline.py` + `release.py` 上传）。
  7 个已发布 Release 的 `assets=0`，而本站卖点是离线可用——离线包此前只存在于一台机器的私有归档仓。
  打包器现在住在这个仓里，任何人 clone 后可复现，且 `--verify` 实测**同一提交两次构建逐字节相同**
  （时间戳钉在 ZIP epoch、条目排序、名全 ASCII）。
  ⚠️ 诚实记录一次被实测推翻的假设：我原以为"peer 都发产物资产"，实跑 8 个对等仓后只有
  Pagefind 挂（它分发二进制），其余全是 0。所以本条的依据是**我们自己的交付路径**，不是惯例。

### Changed
- **打包规则从私有仓搬进本仓**：`tools/package-offline.py` 成为 ZIP 内容的唯一主人，
  私有归档仓的 `build_zip.py` 降级为薄调用者（只负责交付物的日期命名）。
  同时收掉一条老红因：`t_search_ui` 原先无条件读 `../_internal/build_zip.py`——第 11 轮 CI
  就是因为这个 `FileNotFoundError` 红了 22 秒（"只能在一个人机器上跑的判据不算判据"）。
  判据改读仓内文件，并新增 `the offline packager is the only owner of the ZIP membership`。
  私有侧 `verify_zip_parity.py` 第一次跑就抓到两条真缺口：离线包少了
  `lighthouserc.json` / `lighthouserc.mobile.json`（预算声明是"怎么自证达标"的入口），
  以及"台账未提交就打包"→ 与 HEAD 不一致；两条都已修（包 80 → 82 条目）。
  验证器自己补两条：找不到 ZIP 直接 SystemExit、距今 >7 天判 FAILED。
- **文档不再写死可测数字**：README 的"1100+ 条"/"1,426 条"与 CONTRIBUTING 的"1100+ 条"
  全部改为指向打印该数字的命令，并加判据 `documents do not restate the self-test count as prose`
  防止新数字被手抄回去（本仓第五类反复缺陷"文案承诺能力"的数字版）。
- **CI 的本地探测服务器不再拷 `content/`**（生成器输入，无页面 fetch），改为 `--profile probe`；
  由此 `probe ⊆ deploy` 成为可断言的关系。
- `xmlbuilder2` 3.1.1 → 4.0.3（#132，第二十五轮登记，按规矩随下一次发版带走）。
- 仓库元数据线上修正：About 描述去掉被作废的口号、补 `offline-first` 主题（`gh api` PATCH +
  `topics` 端点，读回核对）。
- 发版前清单写进 CONTRIBUTING（含 `perf-probe --runs=3`，第二十五轮计划项 3 的收尾）。

### 账面
- 门禁链 1,879 → **1,940 条**（+61：32 部署集 + 8 元数据 + 10 离线包 + 若干交叉断言与文案钉）。
- AGENTS.md 反复缺陷清单从 5 类涨到 **7 类**（新增"手抄两份的清单会失真"、"散文里的数字会烂"）。

### 环境事故（如实记录，未影响交付）
- 本轮编辑期间 `security-scan` 的 PostToolUse L1 钩子自行崩溃
  （`runtime: cannot allocate memory` + `findstr ... qodersec-version.json` 不被识别），
  编辑均已落盘；判据链改由本仓门禁自证，不依赖该钩子。


## [1.6.1] - 2026-09-25

### Added
- **基线本身入门禁 `t_perf_measurement`**（第二十五轮下半，v1.6.0 之后）。上一轮的教训是"分数能过而
  采样次数藏住双峰"，所以这次钉的不是代码而是**那份被提交的测量记录**：`runs_per_url >= 3`、
  必须写明测的是哪个 server、桌面/移动页数必须等于预算声明的 14/4、每页必须有逐样本 LCP 极差、
  **每页的最坏样本也要过预算**（不是中位数）、unstable 页必须在 summary 里点名、
  且 `unstable` 字段**缺失不等于稳定**（缺字段一样红，防空判通过）。
  12 条变异逐条实测各自转红：改 runs=1 / 删 server / 删一页 / 删一条 LCP 极差 / 删 unstable 键 /
  最坏样本调成 0.4 / 删 worst_sample_breaches / summary 少点一个名 / 摘掉预热优先级 /
  预热改挂回空闲回调 / 删掉 paste 意图。未变异对照与还原后 0 红。
  **最强的那次对照用的是真实历史数据**：把修好前的那份基线（fraud 桌面 worst LCP 1685 ms）放回去，
  判据立刻报 `worst-sample LCP under 900ms: 1685`——它本可以在两轮前就抓住这个缺陷。
- **每页最坏样本 LCP 上限入门禁**：桌面 900 ms、移动 4,000 ms（按 2026-09-25 实测
  桌面最坏 526 ms / 移动 2,406 ms 留约 1.7 倍余量，避免换台慢电脑就误报）。
- **`perf-probe` 把"最坏样本"提升为一等公民**：summary 新增 `worst_sample_breaches`；
  `unstable`（极差 > 0.05）降级为诊断，因为实测 14 页里有 3 页在 100 分附近摆动 ≤0.07
  而每个样本都过预算——真正的决策线是"最坏样本有没有越预算"，不是"分数抖不抖"。
- **`AGENTS.md` 落进仓内规则**：门禁命令清单、五类反复出现的缺陷（文案承诺能力 / 分母缩水 /
  静默降级 / 空判通过 / 工具没接阻断链）、归因先于动作、Git 与路径纪律。
  同时把它接进"禁复用零依赖口号"扫描的公开文件清单（变异实测：往 AGENTS.md 写"零依赖"→ 判据立刻红）。

### Fixed
- **反诈自查页不再在长者还没碰它时就下载 1.5 MB 名单**（桌面该页 LCP 1685 ms → 523 ms，
  与其余 13 页 483-524 ms 同量级；performance 0.94 → 1.00）。原实现是"空闲时预热"：
  `requestIdleCallback` 只推迟**发起时刻**、不降低**优先级**，1,488 KiB 的响应体仍与渲染抢连接，
  13 次采样里 3 次把 LCP 推到 9.75 s（0.96 → 0.73），而基线只跑 1 次采样所以看不出来。
  现改为**意图触发**：聚焦 / 粘贴 / 输入任一项才预热（`saveData` 与 2G 仍跳过）。
  「检查」按钮**故意不算触发点**——点它的人已经在等，若从那儿预热，点击就会排在刚启动的
  低优先级下载后面，把这条路的紧急度丢掉；该路径仍按 high 自己加载并显示进度
  （判据里有一条反向断言钉住"按钮不得挂静默预热"）。
  真浏览器取证：加载后请求数 **0**（原为 1，1,523,537 字节）、打字后 1 次、
  再点检查**不新增请求**且判定仍正确（`is-bad` 命中 `0.feixue316p.cloudns.biz`）。
- **空输入点「检查」也要花掉 1.5 MB 下载**（与上面同一类）。`check()` 原先"先下载、
  在回调里再解析"，所以粘贴框空着点一下就传输整份名单（resource timing 实测 1,523,537 字节），
  **然后**才回一句「无法识别网址」。现改为解析在前、下载在后：空输入 → 请求数 0；
  打字 → 1 次；再点「检查」→ 不新增请求，判定仍正确。
  判据 `check() parses the host before downloading the list` 按源码顺序钉住它
  （变异实测：把顺序改回下载优先 → 报 `hostOf at 403, loadDomains at 305` 红）。
- **装到主屏后离线再打开，页面是没样式也没行为的空壳**。预缓存清单只有 14 页 + `manifest.json`，
  而 `runtimeCaching` 里没有一条匹配 `.css`/`.js`：按页面自身引用枚举出来是
  **6 个同源脚本/样式表，其中 0 个离线拿得到**（README 却写着「完全离线可用」，
  正是本仓记过四次的"文案承诺能力"同类缺陷）。补一条 `StaleWhileRevalidate` 路由——
  不用 `CacheFirst`：资源 URL 无内容哈希，新 HTML 会配着旧 `main.js` 服役；
  也不扩大预缓存：装机时多下约 250 KB 会重演刚修掉的抢带宽。
  覆盖面同时变成判据：`node tools/build.mjs check` 用**路由自己那份谓词**逐个回问
  "这个引用离线拿得到吗"，并带下限断言（枚举数 < 5 直接红）。变异实测四条各自转红：
  删掉该路由 / 把谓词改成永不匹配 / 处理器降级成 `NetworkOnly`（它匹配请求但什么都不存，
  所以不算离线覆盖）/ 把枚举正则改成永不匹配 → 报 "found 0 asset refs, expected >= 5"。
- **清掉两个没人引用的 workbox 运行块，并让"残留"变成会红的事**。workbox 把运行时块写在 `sw.js`
  旁边、按内容哈希命名，所以每次重生成都可能留下上一版：本次磁盘上同时有 3 个块
  （`09092d88` 是仓库里跟踪的那个、`158bc35c` 是中间产物、`35e4679f` 才是 `sw.js` 真正 import 的）。
  离线 ZIP 打包的是磁盘，所以"三个不同 worker"会一起进交付物。
  `checkSw` 现在双向对账：`sw.js` import 的块必须存在（缺 → 红），磁盘上的 `workbox-*.js`
  必须全部被 import（多 → 红），且 import 数为 0 也算红（防止把判据喂成空集）。
  两个方向都实测转红：塞一个 `workbox-deadbeef.js` → 报 stale；把真块挪走 → 报 missing chunk。
- **#135 当场结掉一半**：README 与注释里的"gzip 后 532 KB"经实测**成立**
  （gzip -9 = 530,652 字节，差 0.3%），所以不当估算处理了——加两条断言把条数与字节数钉到文件本身
  （变异实测：改成 900 KB / 90,000 条 各自转红）。仍待取证的只剩"线上到底发不发 content-encoding"。
- **本轮再纠一次自己的记录**：`v1.6.0` 发版说明里写着"桌面仍稳定慢 1.16 s、记录不修"，
  本节把它改成已修并附前后数字——旧结论按实测更新，不做静默保留。

## [1.6.0] - 2026-09-25

### Fixed
- **反诈自查页的名单预热把 LCP 从 2.25 s 拖到 9.7 s（间歇性，中位值把它藏住了）**。
  `loadDomains()` 的后台预热用默认优先级抓 1,488 KiB 名单，和页面自己的渲染抢同一条连接：
  13 次采样里 3 次 LCP≈9.6-9.8 s、performance 0.73，其余 2253 ms、0.96。
  改法 = 预热走 `priority: 'low'`，而**按下「检查」的那条路仍是 high**（那时用户就在等）；
  修后 6/6 次采样稳定 2254 ms。对照实验：临时摘掉预热 3/3 快，装回原样 1/3 慢——
  所以这条不是"名单太大"的猜测，是被 A/B 钉住的归因。非 Chromium 引擎忽略该选项，行为不变。
- **`perf-probe` 的两个"数字来自两次不同采样"错误**：分数取中位数而 `cwv` 取**CLS 最差**那次
  样本，表格于是把 9.7 s 的 LCP 和 0.96 的分数印在同一行（本轮就是被这行误导过）。
  现在所有数字统一取自中位数样本，另出 `cwv_range`（min/median/max）、`unstable_pages`
  （性能极差 > 0.05 即点名）与 `worst_sample`；`--runs=1` 时显式提示"偶尔慢的页面读起来是健康的"。
  基线头部新增 `server` 一行，说明本地 `python -m http.server` 不压缩、单线程，
  绝对值只用于页间与次间比较，不等于 CDN 数字。
- **测量覆盖面重新对账**：桌面预算确实覆盖 14/14 页，**移动端只覆盖 4 页**——原以为"全站实测"
  其实一半是采样。新判据 `t_perf_coverage` 把两份配置的分母钉住：桌面必须等于花名册、
  移动样本必须是 4 页且含首页、URL 必须 loopback 且落在站点基路径下、不得重复。
  8 条断言逐条变异实测（M1-M8：删一页 / 指向幽灵页 / 重复一条 / 换非 loopback 主机 /
  丢首页 / 移出基路径），未变异对照 0 红，还原后配置字节级一致。

### Added
- **教程页「上一篇 / 下一篇」顺序导航**（第二十五轮，对标 starlight / Docsify 等文档站的分页导航）。
  顺序即 `content/tutorials.json` 的列表顺序，两端页缺方向就只渲染另一边；
  标题**复用目标页自己的** `tut-detail.<slug>.h1` 键而不是再抄一份文案，所以改名不会留下旧标题。
  渲染态实测（375px 定宽 iframe，译文生效后）：「上一篇教程 / 如何预约挂号」，
  链接 `tutorial-hospital.html`、`tutorial-wechat.html`，可见宽 332/360px，
  对比度 dir 9.78、title 8.57（深色档；浅色档由 CI 的 axe 兜底）。
  新判据 `t_page_nav` 逐页核对方向存在性、指向 slug、标题键复用（40 条）；
  变异体实测：把 train 的 prev 换成 banking → `FAIL: train prev points at hospital`
- **对比度覆盖面台账 `reports/contrast-coverage.json`**（#124①）。审计只判"能解析出前后景"的配对，
  分母缩小意味着一次绿通过的含义在变窄却无人知晓。现把 7 个数字随代码提交，
  `tools/contrast_coverage.py --check` 与门禁 `t_contrast_coverage` 双向钉住：
  台账必须等于当前样式表的重算值，且分母为正、两个 pass 都无低于 AA 项。
  当前值：同块 36 对（33 可判、3 半透明不可判）、继承 3 对（3 可判）、低于阈值 0。
  变异体实测：给样式表加一条半透明背景规则而不重算台账 → 判据红，字节级还原后 1,771 绿

### Fixed
- 本轮自纠三处工具写法失误：往源码里写代码时用了非原始字符串，反斜杠 b 被解释成**真退格符**、
  反斜杠 n 被解释成**真换行**，同族第三次。做法随之改变——新逻辑落成独立模块
  `tools/contrast_coverage.py`，补丁脚本改用 Write 工具而非 shell 内联字符串；
  被写坏的 `contrast_audit.py` 用 `git checkout` 回退并做字节级复扫（控制字节 none）后才继续

- **静态对比度审计支持跨块继承**（#119）。`contrast_audit` 原先只算"同一规则块内同时声明前景与背景"
  的配对，页脚那个 1.55:1 因此对它完全隐形、只有 CI 里的 axe 抓到。新增 `surfaces()` /
  `surface_for()` / `inherited_pairs()`：前景单独声明时，沿**选择器前缀**找到祖先块的不透明底色再算，
  半透明前景由新增的 `composite()` 合成（页脚判据原本自己写了一份 alpha 数学，已改为调用它，
  消灭"两处实现只修一处"）。`--inherited` 先按**顾问模式**跑：14 页样式表得 3 个配对、
  0 未解析、0 误报，量完才接成阻断判据
- **源码控制符判据**：非原始字符串里 `\b` 被写成**真退格符 U+0008**，静默让 `STATE_RE`
  失效（伪类过滤没生效、审计照出漂亮数字却在看错的集合上）。这条同族坑第六次，这次落成字节级判据：
  `tools/ assets/js/ assets/css/` 下 .py/.js/.mjs/.css 不得含 0x08 等控制字节


- 上述 `STATE_RE` 已被修回 `\b`；`composite()` 对 `rgba(255,255,255,.7)` over `#1A3A6E` 得
  `#BAC4D4`，与本仓解算器和 axe 三方一致（1.55 / 6.37 两个数都对得上）

## [1.5.0] - 2026-09-25

### Fixed
- **页脚链接在深色页脚底上只有 1.55:1**（第十六轮我自己引入的缺陷，第二十二~二十三轮定位）。
  axe 在 CI 报 `color-contrast` score=0，元素 `footer.site-footer > div.footer-bottom > p.footer-report > a`，
  fg `#2B5797`（全局链接色）压在 bg `#1A3A6E` 上、19px 常规字重。本仓静态解算器复算同为 **1.55**
  —— 与 axe 逐位吻合，说明缺的不是算法而是**覆盖面**：它只算"同一规则块内同时声明前景与背景"的配对，
  跨块继承看不见。修法取同类层：给 `.site-footer a` 一个基底色 `rgba(255,255,255,.7)`
  （两配色合成 `#BAC4D4`，实测 **6.37:1**），而不是只补我这次漏的那一条选择器；
  判据复用 `contrast_audit` 自己的原语（不再抄第二份比值算法），两个变异体实测会红：
  删规则 → 1 条红；把 alpha 降到 0.35 → 两 palette 各报 2.75:1 红
- **CI 诊断脚本自身崩溃**（同一轮暴露）：`details.items` 结构随 Lighthouse 版本变化，
  遇到非字典 item 时整段 Traceback。改为逐项 try/except，诊断绝不让中途报错吃掉后面的页面

：workbox 按 `glob` 返回顺序写出，那是宿主
  平台的属性而不是站点的属性。实测本地顺序为 `index.html, 404.html, pages/tutorials.html,
  pages/tutorial-wechat.html`（非字母序），CI 的 Linux runner 会爬出另一套顺序 —— 于是
  「重生成后逐字节比对」的漂移判据**只在 CI 红、每台开发机都绿**，把发版卡住。改用 workbox 自带的
  `manifestTransforms` 排序（不去改它写出的文本），并补 `t_deterministic_sw`：条目数、顺序、
  每条 revision 等于该文件 md5 三项都要对。判据有效性用直接攻击法实测——把 sw.js 头两条交换即判红
  （上一轮那次"变异体"其实正则没匹配、文件根本没被改，当时的绿灯不算证据，这轮作废并重来）

### Added
- **每一页页脚都有「报告这一页的问题」链接**（第十六轮）。无障碍声明此前写着"每页页脚有链接"，
  实测全站 14 页 `issues/new` 命中数为 **0** —— 这是本项目第 8 个"文案承诺超过代码能力"的缺陷，
  且偏偏写在无障碍反馈那一句里。现在链接由 `footer_for(is_index, fp)` 逐页生成，
  `?title=[page] pages/call-help.html` 直接点名是哪一页（仓库地址从 `SITE_BASE` 推导，不第二处硬编码）。
  对端一手：starlight 有 `EditLink.astro`（并带 `print:hidden`），a11yproject 文档里也有 edit 出口
- **判据把承诺和实现对齐**：`t_feedback_exit` 逐页校验链接在 `<footer>` 内、`rel=noopener`、
  `data-i18n` 标签、且 title 参数等于本页路径；另加一条"声明提到页脚链接 ⟹ 14/14 页必须都有"，
  即要么代码追上文案，要么文案改掉。变异体实测：删掉一个 `rel="noopener"` → 该页判缺失 + 两条漂移判据同红
### Added
- **教程页「最近更新」戳**（第十五轮，#58 落地）。每篇教程页尾一行 `<time>` + schema.org `dateModified`，
  日期来自 `reports/last-updated.json`：由 `tools/last-updated.py` 在**本地**（有完整 git 历史）算出并**提交进仓**，
  键是每篇内容自己的 sha256 —— 改 hospital 只有它换日期，其余五篇实测 `unchanged`。
  为什么不让 CI 现算：`actions/checkout` 默认浅克隆，实测一个真实有 12 次提交历史的页面只剩 1 条、
  日期一律=构建当天，那会在一个以"可信"为卖点的站上声称全站今天刚更新。
  CI 侧改为**不需要 git** 的核对：重算内容哈希 ≠ 账本就判 stale，并校验页面显示的日期、JSON-LD 的
  `dateModified` 与账本三者一致（`t_last_updated`，共 27 条）。对比度两配色实测 6.34 / 9.78，字号 18px
- **贡献文档新增"重戳"一步**，并订正两处过时页数（13 页）；门禁从"检查一句话"升级为
  "文档里每个 `N 页` 都必须等于花名册长度"（本轮正是它抓到第二处 13）

### Fixed
- **排除一个看着像缺陷的假信号**：移动端离屏菜单（`position: fixed` + `translateX(100%)`）在 320px
  定宽 iframe 里量得 `scrollWidth` 598 / `clientWidth` 305，像是全站横溢 293px；实测定死 ——
  把 `scrollLeft` 置 999 后仍是 **0**，用户滚不动，**不是缺陷**。记这条是因为它的形状与本项目反复
  抓到的"看起来坏了/看起来完成了"完全相同：**属性数字不等于用户能不能做到**

## [1.4.2] - 2026-09-25

### Added
- **加一篇教程 = 改一个文件**（第十三轮可扩展性实测）。旧行为：往 `content/tutorials.json`
  追加第 7 篇后重跑 `tools/build.py build`，磁盘**零变化、零警告**（14 built files），
  因为页面清单来自 `os.listdir('pages')`，内容来自 JSON，两者从不核对 —— 新条目根本没进那条遍历。
  现在 `page_roster()` 取「磁盘 ∪ 内容」，缺的页直接生成；`locale_outputs()` 把 content 里
  已带 `{en,zh}` 的派生键（每篇每语言 18 个：h1/intro/img.alt/每步 title+正文/related）
  同步进 `assets/locales/*.json`，手写键一律不碰；`do_check` 三向报错
  （MISSING 有内容无页 / DRIFT 内容改了没重跑 / STALE 有页无内容）
- **卡片与分类进数据**：`pages/tutorials.html` 的卡片含每篇手绘 SVG，仍由人写（这是刻意保留的，
  不打算把插画降级成占位图），但 `category` 字段进了 content，且三条门禁钉住两侧一致：
  slug 集合相等、每卡 `data-category` 等于 `content.category`、category 必须存在于筛选 chips。
  此前分类口径只活在 HTML 里，内容侧完全不知道
- **`tools/*.py` 顶层 def 重名门禁**（ast 扫全部脚本）。触发它的实测缺陷：`build.py` 里有
  **两个** `all_pages()`（第 511 行是死代码，第 748 行才生效），改前者等于没改

### Fixed
- **同类出口本轮逐条核过**（不只是修被点名那一处）：content→页（已生成 + 双向 check）、
  页→字典键（已派生）、页→sitemap/precache/Lighthouse URL 矩阵（Node 侧按磁盘遍历且 `checkSw`
  断言每个磁盘页都在 precache 里）、页→部署（`cp -r pages` 是目录）、页→离线 ZIP（`os.walk`）、
  内容↔卡片与↔筛选口径（新门禁）。结论：只有卡片需要人手，其余全自动，且忘了会被指名
- **贡献文档在教人做无效操作**：`CONTRIBUTING.md` 让人去改 `assets/js/i18n.js`（Node 生成物，
  改完下次 build 就被覆盖），并且写着「加一篇教程 = 追加一条 + 跑一次 build 即可」——而第十四轮
  实测那次 build 一个文件都没生成。现改成 4 步真实流程，并加 4 条门禁把文档钉在事实上：
  生成物不得作为编辑目标、两个生成器都得被点名、卡片步骤不得省略、「全站 N 页」必须等于花名册长度
  （实测 14；把它改成 13 即红）

## [1.4.1] - 2026-09-25

### Fixed
- **同一判据两处实现，只修了一处**：`tools/test_build.py` 的词典孤儿规则上一轮刚扩到全部脚本，
  CI 里另跑的 `tools/check-i18n.py` 仍只扫 `main.js` 的 `t('key')`，于是 `052dd92`（v1.4.0 发版提交）
  被它判红，报 `search.fulltext.found/none/offline` 三个"孤儿键"。**本地绿 ≠ CI 绿**第二次发生
  （第一次是第十轮判据读仓外路径）。修法：规则收进 `check-i18n.py::js_key_refs()` 一处，
  `test_build.py` 用 importlib 加载它并断言两侧引用集合相同 + 一条正样本；变异体实测——把该函数
  退回"只扫 main.js"，两条新断言同时红（2/1490），工具自身也报回那三个键
- **`tools/release.py` 过去不看流水线**：v1.4.0 的 tag 因此落在一个 CI 红的提交上，而 tag 推上去
  就搬不动。现在它先取 `check-runs` 结论并打印 `ci verdict`：red 直接拒，pending 须显式
  `--allow-pending`（HEAD 只动发布元数据时用）。三态均在真实提交上取证：
  `052dd92`→red、`7e494b9`→green、运行中的 HEAD→pending

### Added
- **交付物终于有版本标记**：`manifest.json` 加 `"version"`，并由 `t_release` 断言它等于
  `package.json` 的 version。根因是本轮取证发现的：离线 ZIP 实测 70 个文件里**没有** `package.json`，
  `manifest.json` 又是 PWA 与离线包都会带的那一个 —— 发出去的一份拷贝此前无法回答"这是哪一版"。
  变异体实测：只把 `package.json` 改成 1.4.2 → 门禁红（同时报 CHANGELOG 与 manifest 两处漂移）

## [1.4.0] - 2026-09-25

### Added
- **检索结果对读屏可感知**（第十三轮，对标 starlight/Pagefind UI 的 status 区）。补 `#fulltext-live`
  （`role="status"` + `aria-live="polite"` + `aria-atomic`）播报三种状态：命中数
  「全文检索找到 {n} 条相关内容」、零命中「没有找到与「{q}」相关的内容，可以试试上面的分类筛选」、
  降级「这台设备上没有全文索引（离线包不含索引），上面的分类筛选照常可用」。
  两个非显然的点：① live region **必须在 `hidden` 面板之外** —— `[hidden]` 里的内容会整棵离开
  无障碍树，放进去等于没做；② 播报只在防抖后的那一次响应里写，实测 4 次按键 → live 区域
  **变异 1 次**（不是每键播），降级播报实测两次按键只播 1 次。三状态 + 中英双语均在真实浏览器取证
- **全站全文检索：Pagefind 1.5.2 接进教程库**（第十、十一轮）。此前「搜索」只是 `main.js`
  对 6 张卡片的子串过滤，中文读者输「挂号」在 zh 页面得到 0 结果 —— 索引里根本没有中文语料。
  现在两套**单语言**索引（本 Pagefind 构建无 `setLanguage`，混建只会让英文索引服务不了中文）：
  `pagefind/en` 14 页来自真实页面，`pagefind/zh` 11 页来自 `tools/build-search.mjs` 生成的语料，
  语料页带 `<meta name="robots" content="noindex">` 与 `data-pagefind-meta="link:<真实页>#<锚点>"`，
  命中的是真实页面段落而不是语料副本。索引合计 1226 KiB，不进仓、不进 ZIP（构建产物）
- **教程库搜索面板 `assets/js/search.js`**：随 `documentElement.lang` 选索引，250 ms 防抖 +
  序号票据丢旧响应，结果节点一律 `textContent` 构建（无 innerHTML 注入面），只有条数写进
  `#fulltext-status`，面板标题走 `data-i18n`，无结果即整块 `hidden`
- **降级状态可观测 `data-fulltext=ready|unavailable`**（第十二轮）：面板藏起来不等于降级发生，
  第十轮就是靠「隐藏」这个间接证据把「file:// 用不了」写进了代码
- **检索链入门禁**：`tools/build-search.mjs check` 幂等校验（CI 每次重算语料哈希）、
  `t_search_corpus`（语料须等于 deploy 清单里的真实页，且不得被 Workbox 吸进 precache）、
  `t_search_ui`（宿主页面须真加载 `search.js`、面板三元素齐备、双语字典有标题键）。
  自测链 1,440 → **1,488**（第十~十三轮）

### Fixed
- **Workbox 会把 11 个检索语料页吸进 precache**（15 → 26 条）：`globPatterns` 是 `**/*.html`，
  语料页落在站点目录内就一起进缓存，等于把 `noindex` 的构建中间产物推给真实访客。
  `globIgnores` 补 `_search/** pagefind/** tools/** reports/** .github/**`，并由 `t_search_corpus` 盯住
- **`data-pagefind-meta` 逗号写法吞掉锚点**：`"link:页,anchor:段"` 解析后 `meta.link` 只剩 `页`，
  命中链接退化成整页顶部。改成单值 `link:<页>#<锚点>`（改后仍一度读到旧值，实为 HTTP 缓存，
  换端口取证才确认修好）
- **CI 判据读仓外路径，红 22 秒**：`t_search_ui` 无条件读 `../_internal/build_zip.py`，
  `actions/checkout` 的检出里没有这个文件。判据改成条件式并打印说明，ZIP 的保证回到建 ZIP 的地方执行
- **离线 ZIP 的降级方式**（第十二轮）：第十一轮按「file:// 不能 fetch 索引分片」写死协议判断，
  本机实测证伪 —— 这套测试浏览器开着文件访问权限，`file://` 下 `fetch` 与检索**都能成功**，
  协议猜测反而把一个能用的搜索框关掉。改为**首次加载失败即闭锁**（`degraded` 置位后不再重试），
  两种浏览器下行为都对。取证：把站点副本去掉 `pagefind/` 目录起服务，敲一次「挂号」后
  `data-fulltext` 由 `ready` 变 `unavailable`、面板保持隐藏、控制台只剩浏览器自己的 404

### Changed
- **本节自身就是修好的那条**：第十二轮盘点发现「已上线功能未记 CHANGELOG」（`v1.3.0` 之后三轮
  功能全无条目），补齐后按 `tools/release.py` 的要求把 Unreleased 改写成 `## [1.4.0] - 2026-09-25`
  再切发布 —— 该脚本只读指定版本号那一节、不搬 Unreleased，照旧裸跑就会发一个不提搜索的版
- **词典孤儿判据扩到全部脚本**：原 `t_i18n` 只把 `data-i18n` 属性与 `main.js` 里的 `t('key')`
  算作"已使用"，任何由其它脚本消费的键都会被误判为孤儿（本轮三个新键即中招）。改为扫
  `assets/js/*.js`（跳过生成的 `i18n.js` 自身）里的带点键名。判据变宽后仍做过反例：
  临时塞入 `bogus.orphan.key` → 门禁照红，删除 → 绿

## [1.3.0] - 2026-09-25

### Added
- **静态双配色对比度解算 `tools/contrast_audit.py`**（第八轮）：读样式表而不是读渲染结果 ——
  解算 `:root` 与深色块两套令牌表，扫出同一规则块内同时声明前景与背景的 **33 个配对**，
  两套配色各算一次 WCAG 相对亮度比，按字号取 4.5 / 3.0 门槛。**不是自证**：axe 当场报过的
  三个值（2.28 / 3.90 / 2.84）作为 `--selfcheck` 夹具，复算逐项对上才算模型可信。
  取代第七轮"加 `data-theme` 钩子让 CI 测深色"的方案 —— 那要把 28 行深色令牌复制一份，
  为补检查缺口而新开漂移面，方向反了。门禁另加 3 条防呆（深色须真覆盖 ≥20 令牌、
  可解算配对 ≥30、模型须与 axe 夹具对表），因为这个解算器坏过两次、两次都产出看着完全
  合理的表格（浅色表被深色块污染致两列恒等；`@charset` 被算进选择器致只剩 1 个令牌而
  `failures: 0`）。自测链 1,437 → **1,440**
- **性能实测能力 `tools/perf-probe.mjs`**：六轮以来「性能」维度只有「CI 没变红」这一种证据，
  而 CI 只打印未达标的项，从不打印分数。探针逐页输出 Performance / Accessibility /
  Best-Practices / SEO 真实分数与 LCP / CLS / TBT，落 `reports/perf-baseline.json`，
  支持 `--runs` / `--profile` / `--lang` / `--only`。两处取证坑写死在脚本里并附实测依据：
  ① 共用一个 Chrome profile 时 Service Worker 会用上一轮的旧缓存回答后续页面（同一份 CSS，
  共享 profile 测得 a11y 0.96、干净 profile 测得 1.00），故**逐页起停浏览器**；
  ② 端口被上一台服务器占着会静默测到旧拷贝，故**测量前先比对服务端字节与磁盘字节**，
  不一致直接拒跑而不是产出一份看起来正常的基线
- **逐文件 gzip 字节预算入门禁**（对标 withastro/starlight 的 `size-limit`）：HTML 8 KiB /
  CSS 16 KiB / JS 30 KiB / JSON 12 KiB / PNG 64 KiB，另加除名单外总量 640 KiB。上限按实测分布
  标定为最坏页的 1.5 倍（HTML min 2.4 / median 3.7 / max 5.3 KiB）；诈骗名单是上游数据而非代码，
  单独给 640 KiB 并在报错文案里要求"裁决分片或档位"，不允许改数字凑绿
- **橙底元素对比度断言**：任何 `background: var(--color-accent)` 的规则都不得让前景读
  会随主题翻转的 `--color-text`。该判据先经实测证明能咬住 `.call-button` 才收录，
  并配一条"扫描到的橙底规则数 ≥3"的兜底断言，防止判据自己空转成假通过
- **`actions/dependency-review-action` 工作流**：`#49` 把检查工具收进 package.json 之后，
  本仓与跑门禁的机器之间第一次真实存在 379 个传递依赖包，而仓内此前没有任何供应链扫描
  （`grep codeql|dependency-review|zizmor .github` = 0 命中）。action SHA 由
  `gh api …/git/ref/tags/v5.0.0` 远端解析得到，不按注释照抄
- **无障碍声明页与 README 的分数口径改为可复核表述**：不再写「Lighthouse 无障碍 1.0」，
  改为写明门禁级别、页面数与「浅色深色两套配色均已实测」

### Changed
- **DOM 级审计 `tools/verify-dom.mjs`（cheerio 只读不写）**：把每页当解析后的 DOM 重读一遍，
  与 `assets/locales/en.json` 对账 —— ① 每个 `[data-i18n]` 文本、`placeholder/aria-label/alt`
  属性等于字典值；② 每页 canonical / og:url / 分档 og:image / manifest / apple-touch-icon /
  twitter:card 符合规则；③ 用了字典里没有的键即报错。动机：head 与兜底文本由 `build.py`
  用正则**写**，而正则读者与正则作者会共享盲区。实测覆盖 **810 个 `[data-i18n]` 节点 / 14 页**；
  三类负样本（改兜底文本、改 canonical、塞入无字典键）全部指名"页面+键+期望/实际"转红，
  还原后 14 页全清。已同时挂进 `test_build.py`（1,376 → **1,377**）与 CI 步骤

### Changed
- **派生件工具链改用成熟库**（用户 2026-09-25 撤销「零依赖」口径后）：新增 `tools/build.mjs`，
  接管 `assets/js/i18n.js`（由 `assets/locales/{en,zh}.json` 生成，JSON 成为字典唯一来源）、
  `sitemap.xml`（xmlbuilder2）、`lighthouserc.json` / `.mobile.json`（URL 改为**从生成的 sitemap 反推**，
  页面清单由 3 份收敛为 1 份）、`sw.js`（**workbox-build** `generateSW`，NetworkFirst 页面/名单、
  CacheFirst 图片/manifest，`sourcemap:false`）；`build.py` 交还这 4 类所有权，只管 14 个页面
- **运行时 i18n 改用 i18next + browser-languagedetector**（`assets/vendor/` 入库，不远程拉取）；
  库不可用时回退直读字典，老年用户设备不受扩展拦截影响
- 文案随事实更新：站点现在确实加载入库的第三方库，故 README/SECURITY/CONTRIBUTING 的
  「不加载任何第三方脚本」改为「只从本站自身取资源，第三方库入库并锁版本，不远程拉取」

### Fixed
- **浅色下 `.status-offline` 对比度 4.35:1 —— 一处任何浏览器端手段都看不见的缺陷**（第八轮，
  由新的静态解算器上线即抓出）。该徽标只在 JS 检测到无法连接时才挂进 DOM，axe 跑的是加载后的
  快照，看不见它；第七轮刚加的审计级 `color-contrast` error 断言对它同样无能为力。
  `--color-text-muted` 浅色由 `#6E6E82` 改 `#676777`（解算 4.85:1），并用真 axe 复验浅色 5 页
  `color-contrast` 全 = 1、`a11y` 全 = 1.00（防"静态算对但浏览器里另有合成背景"的解算盲区）
- **`blocks()` 会把深色媒体块里的 `:root` 当成顶层 `:root`**（同轮发现并修）：浅色令牌表被
  深色值污染，静态解算因此对 33 个配对算出 `light == dark` 的恒等结果 —— 表格看着完全合理，
  实际只测了一套配色。现先摘出深色块再解析顶层 `:root`，并加断言"深色须真覆盖 ≥20 个令牌"
- **浅色配色下状态徽标对比度 3.90:1**（第七轮新断言上线后 CI 第一次跑就抓出来的）：
  `remote-assist.html` 的 `.status-badge.status-online` 在浅色下 `color-contrast` = 0（两次同值，
  确定性）。根因与橙底缺陷同形 —— 品牌状态色既当填充又当"自己浅色底上的文字色"，实测
  success 3.90:1、warning 2.84:1（小字号需 4.5:1），全仓同类误用 7 处。改指新增的
  `--color-success-text` / `--color-warning-text` / `--color-danger-text`（浅色加深、深色保留
  现有已通过取值不顺手改），并增 6 条门禁禁止该形态（先对改前 CSS 实测命中 7 处才收录）。
  强制浅色镜像复测 14 页 `color-contrast` 全 = 1；CI run 36074542884 在审计级断言下转绿
- **紧急呼叫按钮在深色模式下对比度 2.28:1（WCAG AA 大字要求 3:1）**。深色块逐个选择器手工
  钉前景色（`.btn-accent` / `.nav-cta`），漏了 `.call-button` —— 它的 `color` 读 `--color-text`，
  该令牌在深色下翻成 `#ECEAF2`，而背景 `--color-accent` 不翻。改为读不随主题翻转的
  `--color-on-accent` 单源令牌，并删掉深色侧的 `!important` 钉色副本（复测 a11y 0.96 → **1.00**）。
  404 页 `.error-code` 同源：用水印 `opacity: 0.35` 使前景随背景合成、无法静态判定，
  改为明暗各一且均 >3:1 的 `--color-watermark`
- **SEO 断言一直是 `warn` 级，404.html 实测 0.63 六轮无人看见**。`noindex` 使
  `is-crawlable` 恒失败，占 SEO 权重 4.04/13.04，分数上限就是 0.63。现 SEO 与 Best-Practices
  升 `error` 级，404 按 URL 显式豁免并写明理由——豁免是记录下来的决定，不是音量旋钮。
  生成器内置矩阵自检：任一 URL 命中 0 个或多个断言上下文即构建失败，
  防止「按页豁免」退化成「按页漏检」
- **中文浏览器首访排版抖动（CLS 最高 0.262）**。页面先以英文兜底完成首屏，再由 i18n 整页换成
  中文，中文更短导致全站重排。`main.js` 位于 `</body>` 前，节点已齐备，故把语种应用提到
  `ready()` 之外同步执行。zh-CN 全量复测 **14 页 CLS 全部归零**，printable-guides 的
  perf 随之从 0.87 回到 1.00（此前它是本仓唯一一处真实预算破线）。
  过程中订正一次自己的误判：中间某次扫描显示 tutorial-medical / ride / train 仍为 0.1597，
  据此写下的「残留三页、根因待查」是单次采样噪声，最终全量扫描证否——三页同因同解
- **`<article role="listitem">` 是 axe 判定的非法 ARIA 组合**（`aria-allowed-role` score 0），
  命中 index 与 tutorials 两页。改为 `<div role="listitem">` 并保留 `role="list"` 容器，
  复测两页 a11y 0.99 → **1.00**
- **类别阈值吞掉单项失败**：`color-contrast` 在 accessibility 分类里权重 7，归零后整类仍是
  0.96，落在 0.95 的 error 门禁内 —— 这才是那处紧急按钮缺陷逃过 CI 的**已证实**机制。
  （初稿把它归因于"CI runner 渲染浅色所以深色分支根本不执行"，该推断**未经证实且部分错误**：
  本机注入回归后 A/B 做 `colorScheme: dark` 与 `light` 两次**都**报 0.96，说明两次渲染的都是
  深色（Windows `AppsUseLightTheme=0x0`），Lighthouse 的 `emulatedMedia` 只是回显进
  `configSettings`、并未改变页面实际方案。）现新增 `color-contrast` / `aria-allowed-role`
  两项**审计级** error 满分断言，使"某一项彻底失败"不可能再被整类平均分吸收
- **`@lhci/cli` 0.14.0 → 0.15.1**（PR#7）：第六轮以「换 Lighthouse 大版本可能翻预算」暂缓，
  本轮查到该 PR 分支 CI 已 completed success，顾虑有实测反证，按证据合并
- **门禁静默失效**：`build.py` 交还 sw.js 后，原 SHELL 断言随之消失 —— 把 sw.js 换成空壳
  仍报 1,369 全绿。现由 `node tools/build.mjs check` 重新生成到临时目录**逐字节比对**并校验
  每个页面都在预缓存清单内（负样本：空壳 sw.js → 立即 FAIL）
- **i18next 从未初始化**：守卫里写的插件全局名 `window.LanguageDetector` 不存在（UMD 真名为
  `i18nextBrowserLanguageDetector`），init 被整段跳过、`t()` 静默走回退。浏览器实测
  `initialized:false` 暴露后修正，并新增 6 项静态门禁：main.js 必须引用 vendor 文件**实际导出**的全局名
- `lighthouserc.json` 的 404 URL 此前被列两次（15→14 条）

### Added
- 新依赖精确锁版本：cheerio / xmlbuilder2 / workbox-build / i18next / i18next-browser-languagedetector
  （由本轮自建的"禁 `^~*x`"门禁当场拦下 npm 默认写入的 `^` 后修正）
- 部署与交付：`deploy-pages.yml` 纳入 `workbox-*.js`；ZIP 交付物 57 → 63 文件（含 vendor 与 locales）；
  `.gitignore` 忽略 `*.map`
- 自测 1,368 → **1,376**（vendor 全局名 6 项、文案与运行时一致性 1 项、拆分所有权断言 1 项）

### Changed
- **CI 检查工具纳入清单**：新增 `package.json`（`devDependencies`: htmlhint@1.9.2 / linkinator@8.1.0 /
  @lhci/cli@0.14.0，`dependencies` 留空）+ `package-lock.json`（379 包，含上次弄红 CI 的 undici）；
  CI 由四处 `npx --yes <tool>@ver` / `npm i -g` 改为 `npm ci` + `node_modules/.bin/*`；
  dependabot 增 `npm` 生态。站点自身仍不需要 `npm install`
- **措辞**：README / CONTRIBUTING 不再以「零依赖」作为优点词，改为具体属性
  （浏览器不请求第三方资源 / 无构建步骤 / 改文案不用装环境）

### Fixed
- **`actions/setup-node` 注释谎报版本**：原 pin `249970729…` 实为 **v6.5.0**，注释写 `# v7.0.0`；
  现改为真正的 v7.0.0 SHA `82076278…`。同批把 deploy workflow 里三个可变 tag
  （configure-pages / upload-pages-artifact / deploy-pages）也钉到 commit
- **诈骗名单匹配召回率**：旧规则只比对「域名末两段」，导致名单里 16,417 条（19.8%）深层
  条目只能靠逐字粘贴才可能命中；改为从完整 host 逐级上溯到根域（`listed()`），
  命中面覆盖到深层条目的子域名，且不把根域条目放大成通配（不误伤 `*.github.io`）
- **覆盖范围文案纠偏**：页面与 SOURCES 原称「不含中国大陆域名 / 实测 0 条」，实测名单含
  `.cn` 653 条（`.com.cn` 387 条，合计 0.79%）；文案改为「境内域名不到 1%」，并把该说法
  与 `fraud-feeds-meta.json` 的实测计数做进同一门禁断言

### Added
- **名单快照摘要与新鲜度门禁**：`fetch-fraud-feeds.py --check`（离线）复核 `snapshot_sha256`、
  条数与拉取年龄（>30 天判失败），CI 每次构建都跑，定时任务停摆会直接变红而非悄悄过期
- **CI 工具版本固定**：`htmlhint@1.9.2` / `linkinator@8.1.0` / `@lhci/cli@0.14.0`
  （与当日浮动的 latest 同版本，仅消除不可复现）；CI node 由 20 升至 22，
  因 linkinator 8 的传递依赖 undici 8 要求 `node >= 22.19`——这正是浮动依赖的典型故障：
  仓库零改动，上游发一版就把 CI 弄红
- **匹配器一致性测试**：`test_build.py` 直接抽取浏览器实际加载的 `hostOf()`+`listed()`
  在 node 中对真实名单跑 6  fixture（含反向对照），自测由 1,331 项增至 1,342 项
- **workflow 钉版门禁**：新增静态断言——所有 `uses:` 必须钉 40 位 commit 且带 `# vX.Y.Z`
  注释（可变 tag 会悄悄在 CI 底下移动，与 undici 事件同类）；负样本实测把
  `deploy-pages@v5` 改回可变 tag → 2 项转红，还原后 1,365 项全绿。
  自测最终 **1,365 项**；本轮增量链：1,331 →（文案对账 +1）1,332 →（匹配器 +10）1,342 →
  （公域后缀金丝雀 +1）1,343 →（dev 清单与锁一致性 +5）1,348 →（workflow 钉版 +17）1,365
- **公域后缀误伤金丝雀**：`listed()` 会上溯到根域，因此名单里若出现 `blogspot.com`
  这类免费托管域会把整片合法站点判为诈骗；断言 20 个常见托管/短链域永不出现在快照中
  （注入 `blogspot.com` 实测该断言转红，复原后 1,343 项全绿）
- Actions 依赖由 dependabot 生成的 5 个 PR 全部合入（checkout 7.0.1 / setup-python 7.0.0 /
  configure-pages 6 / upload-pages-artifact 5 / deploy-pages 5），`setup-node` 手动补至 v7.0.0

## [1.2.0] - 2026-09-24

### Added
- **正文 SSG 化**：`sync_fallbacks` 使字典成为全站兜底文本唯一权威源，手改正文即被 `build.py check` 拦截
- **GitHub Pages 上线**：deploy workflow + 在线演示（lxh113377.github.io/filialconnect）
- **移动端 Lighthouse 门禁**（412×846 仿真，perf≥0.85 / a11y≥0.95 error 级）
- **Service Worker 离线外壳**：页面与诈骗名单 network-first（过期名单绝不赢缓存）、图片 cache-first；SHELL 由 build.py 生成，新页自动入列
- **无障碍声明页**（第 14 页，双语，含已知局限清单）
- **per-page OG 分享卡** ×3（教程库/防骗/呼叫求助，sync_head 单源映射）
- **HowTo JSON-LD**（6 教程页，内容管线生成）
- **可疑链接自查工具**：destroylist 83,097 域名离线入库（MIT，档位披露见 SOURCES）
- **PWA**：manifest + 品牌图标（含 maskable）+ 长按 shortcuts
- lighthouserc / lighthouserc.mobile / sw.js 全部纳入 build.py 派生件（19 件零漂移门禁）

### Changed
- 无障碍声明口径 WCAG 2.1 → **2.2 AA**（补 2.4.11 focus-not-obscured：scroll-padding 实测落地）
- 字典实体规范化（&mdash; 等 889 行归一为纯文本）
- 内部工作文档迁出公开仓（_internal/）

## [1.1.0] - 2026-09-24

### Added
- **长者字号三档**（标准 / 大字 / 特大）：`html[data-fontscale]` 提根字号，全部 rem 令牌同步放大；
  `<head>` 前置内联脚本恢复档位避免首帧闪动；本机持久化。对应工信部《互联网网站适老化通用设计规范》
  "应提供网页的放大设置与大字屏幕服务"。
- **整页语音朗读**：浏览器内置 `speechSynthesis`，跟随当前语言，可随时中断，
  不支持的环境自动隐藏按钮。对应规范"至少要在正文页面中实现"语音阅读。
- **教程搜索**：与分类筛选共享一套状态，可组合使用；200ms 防抖；结果数与"无匹配"经
  `role=status aria-live` 播报。
- **求助闭环**：本机保存家人称呼/电话/邮箱 → 大按钮打开真实 `tel:` 拨号，
  求助表单生成真实 `sms:` / `mailto:` 草稿（本站仍无后端）。
- 可发现性：`404.html`、`sitemap.xml`、`robots.txt`，13 页 `canonical` + `og:url`。
- 开源门面：`SECURITY.md`（数据流与漏洞报告口径）、`SOURCES.md`（数据源方法论与覆盖边界）、
  `CODE_OF_CONDUCT.md`、issue 模板 ×2 与 PR 模板、`dependabot.yml`。
- 社交分享卡片 `assets/images/og-cover.png`（1200×630）+ 全站 `og:image` / `twitter:image` /
  `twitter:card=summary_large_image`，由 `<head>` 元数据单一来源注入（含生成页）。
- `CHANGELOG.md`、`CODE_OF_CONDUCT.md`（Contributor Covenant 2.1 本地化改写）。
- 门禁：`tools/test_build.py`（1,200+ 条管线/结构/双语/文案真实性/资源存在性断言，
  并已反向验证：抽掉 og 图后 13 页全部报错、还原后复绿）、`.htmlhintrc`（28 规则）、
  `refresh-fraud-feeds.yml`（每周一自动开 PR 刷新离线名单）。
- CI 按生产子路径 `/filialconnect/` 起服务并探测离线名单可达性。

### Changed
- 内容管线的教程清单与防骗键识别规则改为从 `content/*.json` **派生**
  （此前 `SLUGS` 与 `sign[1-4]/do[1-3]/[1-5]` 为硬编码，且已顶格：加一条即静默脱管）。
- 导航/页脚同步由无标记盲正则改为 `BEGIN/END` 标记区间；未标记页面直接使 `check` 失败。
- 字号令牌底线对账：`--text-xs` 12px → 16px、`--text-sm` 14px → 18px；
  文档口径从"全站最小 18px"改为"正文 ≥18px、辅助文字 ≥16px"（原文档与实现不符）。
- 教程步骤/指南卡/远程协助的标题层级去跳级（`h1→h4`、`h1→h3`、`h2→h4` 全部修正），视觉尺寸由 CSS 保持。
- `check-i18n.py` 复用 `build.all_pages()`（404 进入作用域），孤儿键判定收紧为
  仅认 `t('key')` 字面量（此前把 main.js 里任意单引号串都算"已使用"）。
- 离线名单改为页面空闲时预取（实测 gzip 传输 532 KB，非 1.5 MB），用户点"检查"时基本已就绪；
  尊重 `save-data` 与 2g。**按 TLD 分片方案经实测否决**：.com 仅占 43.4%、共 527 个 TLD，
  分片最多多省一半且仅在查询 .com 时生效，代价是数百个碎请求与新的失败面。

### Fixed
- 暗色模式下站点头部为半透明白底配提亮文字，导航对比度实测 **1.39:1**（12 页全部 WCAG 失败）；
  `.nav-cta` 前景 2.28:1。现分别 9.78:1 与 6.29:1（`getComputedStyle` 实测）。
- 16 处内联 SVG `stroke` 色值在暗色模式从未被映射（此前只映射 `fill`）。
- `data-i18n` 走 `textContent` 覆写，导致 12 个"回到顶部"按钮的箭头 SVG 被替换成文字、
  2 处 `<strong>`（"never"、"110 / 119 / 120"）被吞。
- 求助页虚假回执：提示"家人已收到通知"并承诺"附带您屏幕截图的通知"，而静态站无任何发送能力。
- 可疑链接自查未声明覆盖边界（名单为国际钓鱼域，0 条境内域、不覆盖电话诈骗）。
- 强制颜色模式（`forced-colors`）下焦点指示完全消失；隐藏态"回到顶部"仍可被 Tab 聚焦；
  JS 平滑滚动未响应 `prefers-reduced-motion`；教程筛选对读屏无结果播报。
- `fraud-feeds-meta.json` 的 `commit` 恒为空串（误以为 `/repos/{o}/{r}` 返回 head commit）。
- 部署产物曾包含 `__pycache__`/`.pyc` 风险（现 staging 显式清除）与内部工作文档（已移出公开仓）。

## [1.0.0] - 2026-09-24

### Added
- 内容管线 `tools/build.py`（教程与防骗案例唯一权威源为 `content/*.json`）、
  `tools/check-i18n.py` 双语对称门禁、暗色模式令牌层、GitHub Pages 部署、
  开源三件套（README / LICENSE / CONTRIBUTING）、离线诈骗域名名单与可疑链接自查工具。
- 修复 localStorage 隐私模式抛错中断整条 i18n 链、防骗手风琴 `aria-expanded` 恒 false、
  远程协助连接码写死与文案矛盾。

## [0.x] - 2026-06-17 … 2026-09-23

初版 6 页结构、设计令牌体系、中英双语 i18n、P0/P1/P2 三轮审计修复、
Lighthouse a11y 4 页 1.0 与 HTMLHint/linkinator CI 基线。
