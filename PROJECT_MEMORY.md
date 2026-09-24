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
- 持久化：`localStorage` key `filialconnect-lang`；无记录时按浏览器语言自动检测（navigator.language zh* → 中文，否则英文；2026-09-24 用户决策选项 C）
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

## A11y 修复（2026-09-24，CI 抓出）
- Lighthouse a11y 4 页 0.94-0.95 → 1.0，CI 已转绿
- 对比度方案：橙底按钮用深色文字（#1A1A2E on #E8833A = 6.29:1），保住品牌橙不改色相；muted 文字 #6E6E82；accent-dark #A85212；footer-bottom alpha 0.65
- 标题层级：trust/step h4→h3、fraud 详情 h4→h2、教程卡 h3→h2、call-status h3→h2，CSS 保持原视觉尺寸
- 可访问名：lang-toggle aria-label 含可见文字（"ZH - Switch to Chinese"），call-button 改 data-i18n-aria-label + 双语字典键 call.button.aria
- 注意：改 HTML 标题时开闭标签必须同步（首轮脚本只改开标签，靠 HTMLHint 抓出修复）

## P1 审计清理（2026-09-24）
- P1-1 已修：main.js 全站零 innerHTML（hero `<br>` 走 split+createTextNode；toast 走 textContent）
- P1-2/P1-3 核验发现此前已修好（role 已移除、筛选已是 button+aria-pressed），无需动
- P1-4 已修：call-help 表单去内联 alert，新增 initHelpForm() 走 toast + toast.help-sent 双语键
- P1-5 已修（用户选 C）：detectBrowserLang() 按 navigator.language 自动选中/英文，localStorage 显式选择优先；实测 zh-CN 显示中文、en-US 显示英文
- 复测：Lighthouse a11y 4 页保持 1.0，HTMLHint/linkinator 零错误

## P2 审计清理（2026-09-24）
- P2-1 已修：initScrollAnimations 改 IntersectionObserver（rootMargin -15% 复现原 85% 触发点，触发后 unobserve；无 IO 环境直接显示兜底）
- P2-2/P2-3 核验发现此前已修好（t() 读 I18N / 5 处全 auto-fit）
- P2-4 已修：12 页注入 `<meta name="theme-color" content="#2B5797">`
- P2-5 已修：fraud/printable/remote 3 页 page-header 补 aria-labelledby（审计只列了 1 页，实测 3 页）
- P2-6 维持审计决策：SVG symbol+use 低优暂不动
- 复测：Lighthouse a11y 4 页 1.0，截图验证 IO 动画正常触发

## GitHub 对标 + 按优先级直接执行（2026-09-24）
- 报告：`reports/2026-09-24_GitHub开源项目对标分析报告.md`（无同类高质量项目 → 5 近邻标杆：a11yproject/web.dev/BaldPhone/destroylist/Scam-Blocklist）
- 高优已修：localStorage try/catch 降级（隐私模式防整站 i18n 断链）；防骗手风琴 aria-expanded 同步；remote-assist 连接码改每访随机（消文案矛盾，排除 I/O/0/1）；执行前基线兜底提交 fcd2f05
- 门面补齐：README.md（徽章+模块表+演示边界诚实披露）、LICENSE (MIT)、CONTRIBUTING.md
- 元数据：12 页 OG/Twitter meta + index WebSite JSON-LD（脚本注入，实测 12/12）
- 暗色模式：`@media screen and (prefers-color-scheme: dark)` 令牌层 + 主色拆出 text 令牌（--color-primary-text/-text-deep/--color-accent-text，浅色态值不变零视觉回归）+ 内联 SVG 硬编码色用属性选择器映射；对比度手算 ≥4.5:1，**浏览器像素级目检待做**
- 一致性清理：12 页手写 class="active" 全删（initActiveNav 接管，教程详情页加 isTutorialDetail 规则）；孤儿键 tut-detail.back 双语删除；打印按钮 JS 双绑定移除（保留内联 onclick 走渐进增强）；移动菜单 Tab 焦点循环
- 文案对齐资产："large screenshots" → "large-print steps and simple diagrams"（全站 0 图片，兑现不了就别承诺）
- 新门禁：`tools/check-i18n.py`（EN/ZH 对称 + HTML 覆盖 + 孤儿键，本机实测 PASS 365 键）已挂 ci.yml 第 3 步
- 验证：HTMLHint 12 页零错误（npx+npmmirror 临时 userconfig 跑通）；内部链接 0 断链；标签配平 12/12
- 遗留（报告 §6.2）：内容数据驱动（推荐零依赖 build.py 方案 A）、防骗库消费外部 feeds、GitHub Pages 部署（推公开仓需用户决策）、求助表单真实闭环、暗色像素级复测

## D1/D2/D3/D4 裁决执行（2026-09-24 用户裁决：D1-A / D2-B / D3-B）
- **双仓结构警示**：外层 `项目/` 归档仓（remote=proj-22336e6b-private-archive）+ 内层 `filialconnect/.git`（remote=github.com/lxh113377/filialconnect）。项目权威 = 内层仓；外层仅作工作区快照。提交前必 `git rev-parse --show-toplevel` 确认在哪个仓。
- D1 内容管线：`content/tutorials.json`(6 教程 40 步) + `content/fraud-cases.json`(5 案例) 为唯一文案权威源；`tools/build.py` extract/build/check 三命令；教程页全页生成、导航/页脚 partial 同步 12 页、防骗条目标记区注入、i18n 生成块（BEGIN/END 标记）；build check 幂等实测通过；对等验证：730 双语键逐键 diff=0
- D1 副产物（治病）：防骗页 HTML 兜底文案与字典漂移 112 行 → 统一为字典权威值；footer.brand.p 三页漂移 → partial 统一
- D2：`tools/fetch-fraud-feeds.py` 拉 destroylist（MIT）rootlist → `assets/data/destroylist-domains.txt` 83,097 域名离线入库 + meta JSON；防骗页新增「可疑链接自查」工具（三分支实测：命中/未命中/不可解析全对，懒加载 Set）
- **D4 揪出 P0 级 CSS 级联 bug**：`html.js .animate-in`(0-2-1) 压过 `.animate-in.visible`(0-2-0) → 开 JS 用户所有动画区永久 opacity:0（2026-09-23 P0-3 渐进增强改造引入，前次"截图验证"漏检）。修复：transition 常匹配 + `:not(.visible)` 只管隐藏态；main.js 加视口内直显兜底。CDP `Emulation.setEmulatedMedia` 真暗色像素验收：index/fraud/tutorial 三页 + 浅色回归全过，控制台零输出
- 教训（反哺已入 lessons）：验证"动画正常触发"必须查**内容可见性终态**（computed opacity），不能只看类名/截图首屏
- D3：见下节（公开仓 + Pages）

## 待完善（2026-09-24 实测核验后更新）
- [x] 教程详情页内容 —— 实测 6 页全部有真实完整步骤（hospital/train/wechat/medical/banking/ride 各 6-7 步，EN+ZH 双语键全覆盖，362 键零缺失），旧记录"占位"已过时
- [ ] 「未来设计师」Logo 文件（`assets/images/logo-future-designer.png`）—— 需要外部素材，代码零图片引用（全站内联 SVG），无断链
- [ ] 思源黑体 woff2 文件（`assets/fonts/`，可选）—— 目录不存在，当前系统字体栈工作正常
- [ ] 实际截图图片（替换 SVG 占位图）—— 需要外部素材，非代码任务

## 提交前最后检查清单（2026-09-24 状态）
- [x] 导航链接双向导通 —— linkinator 16 链接零断链（CI 每次 push 自动跑）
- [x] Chrome DevTools 手机/平板视图 —— 四断点响应式已验证，Edge headless 截图抽查通过
- [x] WAVE/axe 无障碍检查 —— Lighthouse a11y 4 页 1.0（CI 门禁 ≥0.95）
- [x] `assets/images/` 无漏文件 —— 全站零图片引用（内联 SVG），无缺失
- [ ] 整个文件夹压缩为 ZIP（仅英文命名）—— 提交前最后一步执行
