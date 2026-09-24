# Changelog

本项目所有值得注意的变更都记录在此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
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
