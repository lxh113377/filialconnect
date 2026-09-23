# 孝心联 (FilialConnect) — 项目记忆

## 基本信息
- 项目名称：孝心联 (FilialConnect)
- 创建日期：2026-06-17
- 技术栈：纯原生 HTML + CSS + JS（零外部依赖）
- 比赛：NCDA 1-C1 交互网页设计

## 设计系统
- 主色：温暖蓝 `#2B5797`
- 强调色：暖橙 `#E8833A`
- 背景：米白 `#FAF8F5`
- 最小字号：18px（CSS clamp 流体缩放）
- 对比度：全站 ≥4.5:1（WCAG AA）
- 按钮最小触控区：48×48px

## 页面结构（6 个文件，超额满足 3 层要求）
1. `index.html` — 首页（总入口）
2. `pages/tutorials.html` — 教程库
3. `pages/call-help.html` — 呼叫子女
4. `pages/remote-assist.html` — 远程协助
5. `pages/fraud-database.html` — 防骗数据库
6. `pages/printable-guides.html` — 可打印指南

## 响应式断点
- 桌面：>1024px
- 平板：768–1023px
- 手机：<768px
- 小屏手机：<480px

## 合规检查（已完成）
- [x] 所有资源本地存放
- [x] 无外部 CDN 依赖
- [x] 无个人信息（姓名/学校/班级/老师）
- [x] 所有链接双向导通（检查导航）
- [x] 无中文引号出现在代码文件
- [x] 英文文件命名
- [x] 响应式三端适配

## i18n 国际化（已完成）
- 方案：`data-i18n` 属性 + JS 字典对象（零外部依赖）
- 字典文件：`assets/js/i18n.js`（~251 键/语言，EN/ZH）
- 切换逻辑：`assets/js/main.js` → `initI18n()` + `applyTranslations()`
- 持久化：`localStorage` key `filialconnect-lang`，默认英文
- 切换按钮：导航栏胶囊按钮 `ZH` / `EN`
- 覆盖：全部 6 个页面（含导航、面包屑、正文、页脚、表单占位符）
- 中文翻译：适老化用语（呼叫求助、防骗提醒、冒充公检法等）

## 工程化（2026-09-23 新增）
- Git 仓库：已初始化，分支 main，Conventional Commits 规范
- CI：`.github/workflows/ci.yml` — HTMLHint（12 页零错误）+ linkinator（目录模式递归 16 链接零断链）+ Lighthouse CI（`lighthouserc.json`：性能≥0.9、无障碍≥0.95）
- 换行：`.gitattributes` 统一 LF
- 本机跑 npx 注意：全局 npmrc 配了 7897 代理，离线时用临时 userconfig 覆盖（registry=npmmirror，无 proxy）

## P0 审计（2026-07-28）→ 全部闭环（2026-09-23 实测修复）
- 详见 `项目优化建议.md` P0 表，5 条全部 [x]

## 待完善（用户后续可提）
- [ ] 教程详情页内容（当前为卡片入口+占位）
- [ ] 「未来设计师」Logo 文件（`assets/images/logo-future-designer.png`）
- [ ] 思源黑体 woff2 文件（`assets/fonts/`，可选）
- [ ] 实际截图图片（替换 SVG 占位图）

## 提交前最后检查清单
- [ ] 用浏览器打开每个 HTML 文件，检查导航链接
- [ ] 用 Chrome DevTools 检查手机/平板视图
- [ ] 用 WAVE 或 axe 检查无障碍
- [ ] 确认 `assets/images/` 无漏文件
- [ ] 整个文件夹压缩为 ZIP（仅英文命名）
