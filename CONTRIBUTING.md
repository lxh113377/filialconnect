# Contributing to FilialConnect 孝心联

感谢参与！本项目是纯静态站：浏览器只从本站自身取资源（第三方库一律入库，不远程拉取），本地预览不需要装环境；构建与 CI 工具清单见 `package.json`。

## 文案改在哪里（重要）

导航、页脚、教程步骤、防骗条目都是**生成产物**，直接改 HTML 会被 CI 的
`build.py check` 判为漂移并失败。

| 想改什么 | 改这个 | 然后跑 |
|---|---|---|
| 教程标题/步骤/相关教程 | `content/tutorials.json` | `python tools/build.py build` |
| 防骗案例 | `content/fraud-cases.json` | 同上 |
| 导航 / 页脚（全站 14 页） | `tools/build.py` 里的 `NAV_TMPL` / `FOOTER_TMPL` | 同上 |
| 404 页 / `sitemap.xml` | `tools/build.py` 的 `PAGE_404_TMPL` / `render_sitemap()` | 同上 |
| 界面文字（非生成部分） | `assets/locales/en.json` 与 `zh.json` **成对**加；不要改 `assets/js/i18n.js`（Node 生成物，改了会被覆盖） | `node tools/build.mjs build` 后跑 `python tools/check-i18n.py` |
| 样式与无障碍 | `assets/css/main.css`（只用 `:root` 令牌） | 见下方本地验证 |

新增第 7 篇教程（第十四轮按真实动作量过的流程；在此之前本节写的是「追加一条 + 跑一次 build 即可」，
而实测那次 build 什么文件都没生成、也没报错，所以这里逐步写明）：

1. 往 `content/tutorials.json` 追加一条，含 `slug`、`file`、`category`（必须是教程页筛选 chips 里的
   一个：`health` / `transport` / `banking` / `daily`），每段文案带 `{en, zh}`。
2. `python tools/build.py build`：教程页 **和** 两侧字典键都由这一步生成（实测一篇 = 18 键 × 2 语言），
   不要手抄文案，也不要改 `assets/js/i18n.js`。
3. `python tools/last-updated.py --write` 更新「最近更新」账本（`reports/last-updated.json`），
   然后再跑一次 `python tools/build.py build` 把日期渲染进页面。**这一步必须在本地做**：
   CI 的 `actions/checkout` 是浅克隆（实测：一个有 12 次提交历史的页面上只剩 1 条、日期=构建当天），
   在 CI 现算 git 日期会让全站都声称"今天刚更新"。账本按每篇内容自己的哈希决定要不要换日期，
   改一篇不会把另五篇的"最近更新"一起刷新（实测：改 hospital 只有它 refreshed，其余 unchanged）。
4. 在 `pages/tutorials.html` 手写一张卡片：`<div class="tutorial-card" data-category="…">` + 该篇的
   内联 SVG 插画。卡片是刻意保留的手绘件（每篇有自己的画）；忘了它门禁会直接点名，不会再静默。
5. `node tools/build.mjs build` 更新 `sitemap.xml` / `sw.js` precache / Lighthouse URL 矩阵，
   然后三条检查全绿再提：`python tools/build.py check`、`node tools/build.mjs check`、
   `python tools/test_build.py`。

## 硬性约束（CI 会拦截）

- 页面运行时不请求 CDN 与网络字体；确需第三方库时**入库并锁版本**（`package.json` +
  lockfile），不做远程拉取。依赖取舍走 PR 讨论，不预设"必须自己写"。
- 新增文案必须 **EN/ZH 成对**，字典键集保持对称，且不允许出现孤儿键。
- **文字承诺不得超过代码能力**。这是本项目历史上返工最多的一类缺陷：连接码曾写死却宣称
  "每次会话生成"、文案承诺"大截图"而全站零图片、求助页曾提示"家人已收到通知"而实际什么都没发。
  新文案请自问：这句话对应的代码在哪一行？答不出来就改成如实的表述。
- 带 `data-i18n` 的元素**内部不得再嵌标签**：翻译走 `textContent` 覆写，会把子节点
  （图标、`<strong>`）整颗删掉。需要强调就换措辞，或把 `data-i18n` 放到内层 `<span>`。
- 颜色只用 `:root` 令牌；内联 SVG 的硬编码色值需同步补进暗色模式的属性选择器映射。
- 字号分级底线：正文/步骤 ≥18px，辅助文字 ≥16px；触控目标 ≥44×44px；对比度 ≥4.5:1。
  长者字号档位（`html[data-fontscale]`）下所有 rem 令牌一起放大，勿新增 px 硬编码字号。
- 标题层级不得跳级（`h1 → h3` 会被 axe 判失败）。

## 本地验证

```bash
python tools/build.py build      # 重新生成派生产物
python tools/build.py check      # 漂移门禁（CI 同款）
python tools/check-i18n.py       # 双语对称 + HTML 覆盖 + 孤儿键
python tools/test_build.py       # 1100+ 条管线/结构/无障碍/文案真实性断言
npx --yes htmlhint "index.html" "404.html" "pages/*.html"
npx --yes linkinator . --recurse --check-fragments \
    --skip "https://lxh113377.github.io/filialconnect.*"
python -m http.server 8765       # 再用 Chrome DevTools 看四个断点与暗色模式
```

离线环境的 npm 代理问题：用临时 userconfig 覆盖
（`npx --userconfig <file>`，文件内写 `registry=https://registry.npmmirror.com` 与 `proxy=null`）。

## 流程

1. 从 `main` 开分支 → 修改 → 本地过上述检查。
2. Commit 遵循 [Conventional Commits](https://www.conventionalcommits.org/)（`feat(tutorial): ...` / `fix(a11y): ...`）。
3. 提 PR，等待 CI 全绿：HTMLHint（14 页）→ i18n → 管线漂移 → 管线自测 →
   链接检查（HTML + Markdown）→ 子路径起服务 → Lighthouse CI（14 页，
   Performance ≥0.9、Accessibility ≥0.95 为 error 级）。
4. 附修改前后截图（桌面 + 手机两个断点；改到颜色时补暗色模式各一张）。

## 数据源

防骗名单等外部数据的来源、许可与覆盖边界见 [SOURCES.md](SOURCES.md)。
新增数据源必须同时写清「它不能覆盖什么」。
