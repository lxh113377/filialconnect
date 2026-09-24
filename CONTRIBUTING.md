# Contributing to FilialConnect 孝心联

感谢参与！本项目是纯静态站：浏览器不请求任何第三方资源，改文案也不需要装环境（CI 检查工具另有 `package.json` 清单，与站点本身无关）。

## 文案改在哪里（重要）

导航、页脚、教程步骤、防骗条目都是**生成产物**，直接改 HTML 会被 CI 的
`build.py check` 判为漂移并失败。

| 想改什么 | 改这个 | 然后跑 |
|---|---|---|
| 教程标题/步骤/相关教程 | `content/tutorials.json` | `python tools/build.py build` |
| 防骗案例 | `content/fraud-cases.json` | 同上 |
| 导航 / 页脚（全站 13 页） | `tools/build.py` 里的 `NAV_TMPL` / `FOOTER_TMPL` | 同上 |
| 404 页 / `sitemap.xml` | `tools/build.py` 的 `PAGE_404_TMPL` / `render_sitemap()` | 同上 |
| 界面文字（非生成部分） | `assets/js/i18n.js` 手写区，EN 与 ZH 同时加 | `python tools/check-i18n.py` |
| 样式与无障碍 | `assets/css/main.css`（只用 `:root` 令牌） | 见下方本地验证 |

新增第 7 篇教程：往 `content/tutorials.json` 追加一条（含 `slug`/`file`），
跑一次 `build` 即可 —— 页面清单与字典键的识别规则都从 JSON 派生，不需要改脚本常量。

## 硬性约束（CI 会拦截）

- 保持**零外部依赖**：不引入 CDN、npm 包、Web Font 请求。
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
3. 提 PR，等待 CI 全绿：HTMLHint（13 页）→ i18n → 管线漂移 → 管线自测 →
   链接检查（HTML + Markdown）→ 子路径起服务 → Lighthouse CI（13 页，
   Performance ≥0.9、Accessibility ≥0.95 为 error 级）。
4. 附修改前后截图（桌面 + 手机两个断点；改到颜色时补暗色模式各一张）。

## 数据源

防骗名单等外部数据的来源、许可与覆盖边界见 [SOURCES.md](SOURCES.md)。
新增数据源必须同时写清「它不能覆盖什么」。
