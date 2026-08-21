## 1. 全局 Token 层

- [x] 1.1 在 `src/index.css` 的 `:root` 对旧 `--capture-*` 定义**原位改值**（surface-page `#F1F5F3`、border-default `#D9E3DD`、brand-primary `#23985B`、brand-soft `#DDF1E5`、text-primary `#182B24` 等），保证每个 Token 只保留一份权威定义，不出现同名重复定义
- [x] 1.2 追加缺失 Token：surface-soft/surface-video `#24302B`/border-strong/brand-strong `#197947`/brand-primary-hover `#14683D`/accent/lime/sidebar 系列/status 系列（含 soft 浅底）
- [x] 1.3 状态前景色使用加深值（pending `#475569`、processing `#8A570E`、success `#176B3C`、merge `#9A5300`、failed `#B42318`、ai `#2F6F7B`），soft 浅底保留，Badge 小字号对比度 ≥ ~4.5:1
- [x] 1.4 保留 timeline/recording 功能语义色原值，不参与品牌换色

## 2. 报告页荧光绿迁移

- [x] 2.1 将 `.pb-vision-theme` 的 `--pb-primary`/`--pb-primary-dark`/`--pb-primary-soft`/`--pb-page-bg`/`--pb-card-border`/`--pb-text-*` 改为引用全局 Token（primary→brand-primary、primary-dark→brand-strong、primary-soft→brand-soft）；**保留 `--pb-*` aliases**
- [x] 2.2 `--pb-heat-mid` 改独立可视化绿 `#3AAF6B`（黄→绿→粉语义保留，不与品牌绿绑定）；`--pb-success` 改 `--capture-status-success`
- [x] 2.3 确认 6 维度色/浅底、`--pb-coach-*`、热力黄/粉原值保留

## 3. 库/工作台/侧边栏去硬编码

- [x] 3.1 `AppSidebar.tsx`：底 `bg-white` → `var(--capture-sidebar-bg)`、边框 → `var(--capture-sidebar-border)`；选中导航改为「左侧 3px 强调条 `var(--capture-brand-primary)` + 浅绿底 `var(--capture-nav-active-bg)` + 深绿字 `var(--capture-nav-active-text)`」；灰阶改 `var(--capture-text-*)`
- [x] 3.2 `LibraryItemWorkspace.tsx`：外层 `bg-white` → surface-soft，顶栏/卡片 → surface-card，边框/文字改 Token
- [x] 3.3 `LibraryCard.tsx`：卡片边框/阴影改 Token；占位缩略图改中性灰渐变（`#E7EEEB → #DCE7E2`）+ 轻球场线纹理；`stateBadge`/`toneClass` 类型由颜色名升格为业务语义 `StatusTone = "pending" | "processing" | "success" | "merge" | "failed" | "ai"`，映射对应 `--capture-status-<tone>` / `-soft`
- [x] 3.4 比赛库页背景加分层氛围（`linear-gradient(180deg,#F4F8F6,#EEF3F1)` + 顶部弱径向渐变 `rgba(87,181,142,0.10)`）；搜索框 `#FAFCFB`、筛选器外背景 `surface-soft`、选中项 `#E4F2E9`，颜色透明度不超过 10%

## 4. 清理死代码

- [x] 4.1 删除 `:root` 中 0 使用的通用色（`--surface-0..4`、`--text-strong`、`--text-soft`、`--line-dark`、`--action-green`、`--glow-green`、`--pickle-lime`、`--court-blue`、`--warning-orange`、`--error-red`）
- [x] 4.2 删除荧光绿 literal 与旧注释（`#00ff41 / #00cc33 / #e6ffe9` 等）；**保留 `--pb-*` compatibility aliases 引用全局 Token**，确保 101 处 `var(--pb-*)` 不断
- [x] 4.3 grep 复查全站硬编码 hex（capture 控制台、pb-vizion、库/工作台/侧边栏），残余颜色统一收敛到全局 Token；`src/styles/app.css` 不纳入

## 5. 色彩纪律与视觉层级

- [x] 5.1 确认 `--capture-accent` 仅用于 AI/双摄/技术提示与辅助 icon，不做 Primary CTA
- [x] 5.2 确认 `--capture-lime` 仅作数据高亮/运动感微点缀，全屏占比 < 5%，不做大面积背景/正文/主按钮
- [x] 5.3 主绿分级落地：`brand-primary` 用于标识/图标/Tab underline/大色块，`brand-strong` 用于白字主按钮，`brand-primary-hover` 用于 hover/pressed

## 6. 验证与回归

- [x] 6.1 运行 `npm run build` 与现有测试，确认无类型/样式错误
- [x] 6.2 人工回归新版报告页（主按钮/进度/热力图/6 维度卡）不再出现荧光绿；热力图黄→绿→粉对比度正常
- [x] 6.3 人工回归旧版报告（`?legacy=1`）与新版同属深绿家族
- [x] 6.4 人工回归比赛库（卡片占位、状态 Badge 小字号可读性、筛选栏、背景分层）与素材工作台（播放器外框、Vidat 工具条、时间线）
- [x] 6.5 人工回归 capture 控制台与时间线，确认功能语义色未受影响
