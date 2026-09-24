# Changelog

本项目所有值得注意的变更都记录在此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **DOM 级审计 `tools/verify-dom.mjs`（cheerio 只读不写）**：把每页当解析后的 DOM 重读一遍，
  与 `assets/locales/en.json` 对账 —— ① 每个 `[data-i18n]` 文本、`placeholder/aria-label/alt`
  属性等于字典值；② 每页 canonical / og:url / 分档 og:image / manifest / apple-touch-icon /
  twitter:card 符合规则；③ 用了字典里没有的键即报错。动机：head 与兜底文本由 `build.py`
  用正则**写**，而正则读者与正则作者会共享盲区。实测覆盖 **810 个 `[data-i18n]` 节点 / 14 页**；
  三类负样本（改兜底文本、改 canonical、塞入无字典键）全部指名"页面+键+期望/实际"转红，
  还原后 14 页全清。已同时挂进 `test_build.py`（1,376 → **1,377**）与 CI 步骤

## [Unreleased]

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
