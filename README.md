# 孝心联 FilialConnect

> 面向老年人与其子女的跨代数字反哺教程站：手机挂号、火车票、微信、银行防骗，中英双语，适老化无障碍设计。

**🌐 在线演示：https://lxh113377.github.io/filialconnect/**

[![CI](https://github.com/lxh113377/filialconnect/actions/workflows/ci.yml/badge.svg)](https://github.com/lxh113377/filialconnect/actions/workflows/ci.yml)
[![Pages](https://github.com/lxh113377/filialconnect/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/lxh113377/filialconnect/actions/workflows/deploy-pages.yml)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=flat&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JS-vanilla-F7DF1E?style=flat&logo=javascript&logoColor=black)
![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![WCAG 2.2 AA](https://img.shields.io/badge/WCAG%202.2-AA%20%E2%9C%93-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**纯静态 · 零外部依赖 · 构建脚本只用 Python 标准库 · Lighthouse 无障碍 1.0（13 页 CI 门禁 ≥0.95）· 长者字号三档 + 整页朗读**

## 功能模块

| 模块 | 页面 | 说明 |
|------|------|------|
| 首页总入口 | `index.html` | 场景化导航（子女帮父母 / 老人自助） |
| 教程库 | `pages/tutorials.html` | 关键词搜索 + 分类筛选（两者可组合，结果数与"无匹配"均读屏播报） |
| 6 篇教程详情 | `pages/tutorial-*.html` | 医院 / 火车票 / 微信 / 医疗 / 银行 / 打车，各 6-7 大步骤（由 `content/tutorials.json` 生成） |
| 呼叫子女 | `pages/call-help.html` | 本机保存家人称呼/电话 → 大按钮打开**真实拨号界面**；求助表单生成**真实短信/邮件草稿** |
| 远程协助 | `pages/remote-assist.html` | 每次访问生成随机连接码（无 JS 时降级静态码） |
| 防骗数据库 | `pages/fraud-database.html` | 5 类典型骗局手风琴 + 可疑链接离线自查（覆盖边界如实标注） |
| 可打印指南 | `pages/printable-guides.html` | 大字号打印版（@media print 优化） |
| 阅读辅助（全站） | 导航条 | 标准/大字/特大三档字号 + 整页语音朗读（浏览器内置 `speechSynthesis`） |

## 设计与无障碍

- 适老化字号底线：正文与步骤 ≥18px、辅助文字 ≥16px（`--text-base`/`--text-sm`/`--text-xs` 令牌约束，clamp 流体缩放）；
  长者档位把根字号提到 118.75% / 137.5%，所有 rem 令牌一起放大，不会挤压布局
- 触控区 ≥44px（`min-height`，字号放大时同步增长）、全站对比度 ≥4.5:1（WCAG AA）
- 色彩令牌集中于 `:root`；支持 `prefers-reduced-motion`（CSS 与 JS 平滑滚动都响应）、
  `forced-colors`（焦点改用系统 outline）、`prefers-color-scheme: dark`（含导航栏与内联 SVG 描边）
- 键盘可达：skip-link、手风琴 Enter/Space、移动菜单 Esc 关闭 + Tab 焦点循环、
  隐藏态「回到顶部」不进入 Tab 顺序
- 渐进增强：动画/翻译均有无 JS 降级路径；打印按钮为内联 `onclick`（不依赖 JS）；
  朗读按钮在不支持 `speechSynthesis` 的环境自动隐藏

## i18n

- 机制：`data-i18n` / `data-i18n-placeholder` / `data-i18n-aria-label` 属性 + `assets/js/i18n.js` 双语字典（EN/ZH 键集严格对称）
- 语言判定：显式选择（localStorage，隐私模式自动降级）> 浏览器语言（`navigator.language`）> 英文
- 无外部请求：字体为系统栈（Noto Serif SC / PingFang SC 等），完全离线可用
- 数据流：语言、字号档位、家人联系方式都只写本机 `localStorage`，本站无后端、不上传任何内容（逐项见 [SECURITY.md](SECURITY.md)）

## 本地开发

```bash
# 任一静态服务器即可，无构建步骤
python -m http.server 8000
# 跑门禁（可选）：npm ci 只为装 htmlhint / linkinator / lighthouse-ci 三个检查工具，
# 站点本身不需要 npm install；lockfile 一并锁住它们的传递依赖，防上游发版把 CI 弄红
# 浏览器打开 http://localhost:8000
# 说明：直接双击 index.html（file://）也能浏览与切换语言，但浏览器禁止 file:// 下 fetch，
# 因此「可疑链接自查」会提示改用网页服务器 —— 这是浏览器安全策略，非站点缺陷

# 内容工作流（教程/防骗案例的唯一权威源是 content/*.json）：
python tools/build.py build    # 改完 JSON 后重新生成页面与 i18n 键
python tools/build.py check    # 校验派生件与内容源无漂移（CI 同款）
python tools/check-i18n.py     # EN/ZH 键对称 + HTML 覆盖 + 孤儿键
python tools/test_build.py     # 管线/结构/无障碍/文案真实性断言（1100+ 条）
python tools/fetch-fraud-feeds.py  # 手动刷新防骗域名离线名单（CI 每周一自动开 PR）
```

## 质量门禁（CI）

`.github/workflows/ci.yml` 在每次 push / PR 自动执行：

1. **HTMLHint** — 13 页（`.htmlhintrc` 收紧到 28 条规则：`button-type-required`、
   `label-has-associated-control`、`id-unique`、`attr-no-duplication` 等）
2. **Linkinator** — 站内递归 + fragment + 外部链接；Markdown 文档单独一轮
3. **i18n 对称门禁** — `tools/check-i18n.py`
4. **内容管线漂移门禁** — `python tools/build.py check`（含导航/页脚 marker 覆盖检查）
5. **管线自测** — `python tools/test_build.py`（1,200+ 条：幂等、单 h1、标题不跳级、本地链接可解析、
   子路径绝对路径防呆、双语对称、孤儿键、**文案真实性关键词**、`<head>` 引用的资源文件真实存在、
   og-cover.png 尺寸合规、名单与清单计数一致、sitemap 覆盖）
6. **子路径真实服务** — 按生产路径 `/filialconnect/` 起 http.server 并探测 1.5MB 离线名单可达
7. **Lighthouse CI** — 全部 13 页 × 2 次，Performance ≥0.9、Accessibility ≥0.95（error 级）

## 适老化与无障碍依据

对照工信部《互联网网站适老化通用设计规范》（专项行动方案附件）逐条自查：

| 规范要求 | 本站实现 |
|---|---|
| 提供网页放大设置与大字服务 | 标准 / 大字 / 特大三档，本机持久化，全站生效 |
| 组件聚焦时有明显状态提示 | `:focus-visible` 环 + `forced-colors` 下改用系统 outline |
| 全程键盘操作 | 跳至内容链接、手风琴/筛选/折叠均支持 Enter/Space、移动菜单 Esc + Tab 循环 |
| 严禁广告内容与插件、随机弹窗 | 零第三方脚本、零广告、零弹窗 |
| 非文本链接提供语音阅读 | 整页朗读（`speechSynthesis`）+ 全站 `aria-label`/`data-i18n-aria-label` 双语 |
| 背景高对比、色彩区分信息区 | 全站 ≥4.5:1（含暗色模式），风险等级另用形状 + 文字标注 |

WCAG 2.1 AA 之外的适老细节：`prefers-reduced-motion` 同时约束 CSS 与 JS 滚动；
隐藏元素退出 Tab 顺序；正文最小 18px。

## 已知边界（如实说明）

- **没有后端**。呼叫按钮和求助表单都只是把内容交给手机自带的拨号 / 短信 / 邮件 App，
  用户在自家 App 里点发送才真正发出；本站不会、也无法替用户发出任何通知。
  家人联系方式仅存于本机 `localStorage`。
- 远程协助的连接码是本机随机字符串，不对应任何真实远控会话。
- 可疑链接自查用的离线名单为**国际钓鱼域名**（83,097 条，gzip 后 532 KB），不含境内域名、
  不覆盖电话诈骗，「未命中」不等于安全（页面已按此措辞）。名单在页面空闲时预取，
  尊重 `save-data` 与 2g；已评估并按实测数据**否决**了按 TLD 分片方案（.com 仅占 43.4%、
  共 527 个 TLD，分片最多多省一半且仅在查 .com 时生效）。
- 分享卡片图 `assets/images/og-cover.png`（1200×630）由仓库外的 `_internal/make_og_image.py`
  用 Pillow 生成后入库 —— 站点运行时不请求任何外部资源，首页与教程页也不引用它（不产生图片请求）。
- 教程文案里的第三方 App 名称仅指认用途，无官方关联；界面为自绘内联 SVG，非真实软件截图。

## 目录结构

```
filialconnect/
├── index.html / 404.html     # 404 与 sitemap.xml 由 tools/build.py 生成
├── pages/            # 11 个子页面（教程详情页为全页生成）
├── content/          # 教程与防骗案例的唯一权威文案源（JSON）
├── assets/
│   ├── css/main.css  # 设计令牌 + 全部组件样式（单文件）
│   ├── js/i18n.js    # EN/ZH 双语字典（含生成块）
│   ├── js/main.js    # IIFE，14 个 init 模块
│   └── data/         # 离线诈骗域名名单 + 来源元数据
├── tools/            # 只用 Python 标准库的构建与门禁脚本（build/check-i18n/test_build/fetch-feeds）
├── .github/          # workflows + dependabot
├── lighthouserc.json
├── SECURITY.md       # 数据流与漏洞报告口径
└── SOURCES.md        # 数据源方法论与覆盖边界
```

## License

[MIT](LICENSE)。教程文案与图示 © FilialConnect 项目。
