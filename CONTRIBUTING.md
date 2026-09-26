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
   列表卡片要显示的两样也写在这里（第三十四轮起是**必填**，缺了构建会点名拒绝）：
   `card_p`（一句简介 `{en, zh}`）与 `card_tags`（1–2 个标签 `{en, zh}`）；卡片标题不再单独写，
   它就是本页已翻译的 `<h1>`（实测六篇全等）。
2. `python tools/build.py build`：教程页 **和** 两侧字典键都由这一步生成
   （键数不在此处写死，以 `python tools/check-i18n.py` 的打印为准），
   不要手抄文案，也不要改 `assets/js/i18n.js`。
3. `python tools/last-updated.py --write` 更新「最近更新」账本（`reports/last-updated.json`），
   然后再跑一次 `python tools/build.py build` 把日期渲染进页面。**这一步必须在本地做**：
   CI 的 `actions/checkout` 是浅克隆（实测：一个有 12 次提交历史的页面上只剩 1 条、日期=构建当天），
   在 CI 现算 git 日期会让全站都声称"今天刚更新"。账本按每篇内容自己的哈希决定要不要换日期，
   改一篇不会把另五篇的"最近更新"一起刷新（实测：改 hospital 只有它 refreshed，其余 unchanged）。
4. 卡片自第三十三轮起**也是生成产物**：往 `content/tutorial-cards.json` 追加一条
   `{"slug": "…", "label": "…"}`（顺序即展示顺序，`label` 只用于源码注释），
   并把那张手绘图放成 `content/card-art/<slug>.svg`。**不要再改 `pages/tutorials.html`**——
   卡片区在 `BEGIN/END:TUTORIAL-CARDS` 标记之间，构建会整段重写，手改会被判据点名。
   缺图时构建直接拒绝并点名（不给静默产出无图卡片的机会）；每篇画仍由人绘制，这是内容决策，不是工具决策。
   卡片文案不在这里写，在第 1 步的 `card_p` / `card_tags`（第三十四轮起是派生的，改内容即改卡片）。
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
python tools/test_build.py     # 管线/结构/无障碍/文案真实性断言（条数以实跑输出为准，本文不写死）
python tools/stage-site.py check   # 「哪些文件离得开这个仓」与已提交台账对账（部署集 = 页面引用集）
python tools/stage-site.py explain <path>   # 这个文件凭什么被部署（无原因＝它是漏进来的散件）
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
3. 提 PR，等待 CI 全绿：HTMLHint（14 页）→ i18n → 管线漂移 → 部署集台账 → 管线自测 →
   链接检查（HTML + Markdown）→ 子路径起服务 → Lighthouse CI（14 页，
   Performance ≥0.9、Accessibility ≥0.95 为 error 级）。
4. 附修改前后截图（桌面 + 手机两个断点；改到颜色时补暗色模式各一张）。

## 发版前清单（`python tools/release.py` 只替你做其中一部分）

```bash
node tools/perf-probe.mjs --runs=3          # 3 次/URL；runs=1 会把双峰压成一个漂亮值，判据会拒绝它
python tools/build.py check && node tools/build.mjs check
python tools/stage-site.py check --write    # 动了引用才需要重算台账，随后把台账一起提交
python tools/test_build.py                  # 全绿
python tools/release.py                     # 干跑：版本三处一致 + CI 结论 + 会发什么资产
python tools/release.py --apply             # 打 tag、推 tag、建 Release、挂离线 ZIP 资产
```

`--apply` 在 CI 为 red/unknown 时**拒绝**发版，这是正确结果不是障碍（发版必须落在绿提交上）。
发完后 `deploy-pages.yml` 的 `verify-live` 作业会把线上逐文件取回来与本次提交比 sha256，
并核对仓外元数据；`gh run watch <id> --exit-status` 已在链路里，不必另装 git hook。

## 数据源

防骗名单等外部数据的来源、许可与覆盖边界见 [SOURCES.md](SOURCES.md)。
新增数据源必须同时写清「它不能覆盖什么」。
