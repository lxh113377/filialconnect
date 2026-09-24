# 孝心联 FilialConnect

> 面向老年人与其子女的跨代数字反哺教程站：手机挂号、火车票、微信、银行防骗，中英双语，适老化无障碍设计。

![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=flat&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JS-vanilla-F7DF1E?style=flat&logo=javascript&logoColor=black)
![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![WCAG AA](https://img.shields.io/badge/WCAG-AA%20%E2%9C%93-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**纯静态 · 零外部依赖 · 零构建 · Lighthouse 无障碍 1.0（CI 门禁 ≥0.95）**

## 功能模块

| 模块 | 页面 | 说明 |
|------|------|------|
| 首页总入口 | `index.html` | 场景化导航（子女帮父母 / 老人自助） |
| 教程库 | `pages/tutorials.html` | 分类筛选（button + aria-pressed） |
| 6 篇教程详情 | `pages/tutorial-*.html` | 医院 / 火车票 / 微信 / 医疗 / 银行 / 打车，各 6-7 大步骤 |
| 呼叫子女 | `pages/call-help.html` | 一键求助演示 + 求助表单（toast 反馈） |
| 远程协助 | `pages/remote-assist.html` | 每次访问生成随机连接码（无 JS 时降级静态码） |
| 防骗数据库 | `pages/fraud-database.html` | 5 类典型骗局手风琴（aria-expanded 同步） |
| 可打印指南 | `pages/printable-guides.html` | 大字号打印版（@media print 优化） |

## 设计与无障碍

- 适老化基线：最小字号 18px（clamp 流体缩放）、触控区 ≥48px、全站对比度 ≥4.5:1（WCAG AA）
- 色彩令牌 61 项集中于 `:root`；支持 `prefers-reduced-motion`、`forced-colors`、`prefers-color-scheme: dark`
- 键盘可达：skip-link、手风琴 Enter/Space、移动菜单 Esc 关闭 + Tab 焦点循环
- 渐进增强：动画/翻译均有无 JS 降级路径；打印按钮为内联 `onclick`（不依赖 JS）

## i18n

- 机制：`data-i18n` / `data-i18n-placeholder` / `data-i18n-aria-label` 属性 + `assets/js/i18n.js` 双语字典（EN/ZH 键集严格对称）
- 语言判定：显式选择（localStorage，隐私模式自动降级）> 浏览器语言（`navigator.language`）> 英文
- 无外部请求：字体为系统栈（Noto Serif SC / PingFang SC 等），完全离线可用

## 本地开发

```bash
# 任一静态服务器即可，无构建步骤
python -m http.server 8000
# 浏览器打开 http://localhost:8000

# 内容工作流（教程/防骗案例的唯一权威源是 content/*.json）：
python tools/build.py build    # 改完 JSON 后重新生成页面与 i18n 键
python tools/build.py check    # 校验派生件与内容源无漂移（CI 同款）
python tools/check-i18n.py     # EN/ZH 键对称 + HTML 覆盖 + 孤儿键
python tools/fetch-fraud-feeds.py  # 刷新防骗域名离线名单（建议每周）
```

## 质量门禁（CI）

`.github/workflows/ci.yml` 在每次 push / PR 自动执行：

1. **HTMLHint** — 12 页 HTML 校验（零错误）
2. **Linkinator** — 递归链接检查（fragments + external，零断链）
3. **i18n 对称门禁** — `tools/check-i18n.py`
4. **内容管线漂移门禁** — `python tools/build.py check`
5. **Lighthouse CI**（`lighthouserc.json`）— Performance ≥0.9、Accessibility ≥0.95（error 级）；Best Practices / SEO ≥0.9（warn 级）

## 已知演示边界

本项目为竞赛/展示用静态站：`call-help` 表单与一键呼叫为前端演示（不发送真实数据）；远程协助连接码为本地随机生成，无后端会话系统。生产化需接入短信/推送与真实远控通道。

## 目录结构

```
filialconnect/
├── index.html
├── pages/            # 11 个子页面
├── assets/
│   ├── css/main.css  # 设计令牌 + 全部组件样式（单文件）
│   ├── js/i18n.js    # EN/ZH 双语字典
│   └── js/main.js    # IIFE，11 个 init 模块
├── .github/workflows/ci.yml
├── lighthouserc.json
└── reports/          # 对标分析与审计报告
```

## License

[MIT](LICENSE)。教程文案与图示 © FilialConnect 项目。
