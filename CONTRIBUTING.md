# Contributing to FilialConnect 孝心联

感谢参与！本项目是零依赖纯静态站，贡献门槛很低。

## 可以贡献什么

1. **教程内容**：新增 `pages/tutorial-*.html`（复用现有步骤卡结构），并在 `assets/js/i18n.js` 的 EN/ZH 两个字典中补齐键
2. **翻译改进**：老年适切用语优先（如"呼叫求助"而非"一键SOS"）
3. **防骗案例**：`pages/fraud-database.html` 手风琴条目
4. **无障碍问题**：对比度、键盘操作、读屏语义缺陷

## 硬性约束（CI 会拦截）

- 保持**零外部依赖**：不引入 CDN、npm 包、Web Font 请求
- 新增文案必须 **EN/ZH 成对**，字典键集保持对称
- 新页面 `<head>` 结构对齐现有 12 页（charset/viewport/theme-color/description/OG/favicon/`js` class 探针）
- 颜色只用 `:root` 令牌，不在 HTML/组件里硬编码色值（内联 SVG 现状为遗留，勿新增）
- 最小字号 ≥18px、触控目标 ≥48×48px、对比度 ≥4.5:1
- 本地验证：`python -m http.server` + Chrome DevTools；CI 跑 HTMLHint / Linkinator / Lighthouse CI

## 流程

1. 从 `main` 开分支 → 修改 → 本地过上述检查
2. Commit 遵循 [Conventional Commits](https://www.conventionalcommits.org/)（`feat(tutorial): ...` / `fix(a11y): ...`）
3. 提 PR，等待 CI 三项全绿
4. 截图对比修改前后（桌面 + 手机两个断点）
