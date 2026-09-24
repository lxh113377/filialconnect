# Changelog

本项目所有值得注意的变更都记录在此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed
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
