## Why

当前前端存在三套并行的颜色体系：capture 控制台的 `--capture-*` Token（深绿 `#3baa62`）、报告页专属 `.pb-vision-theme` 荧光绿（`#00ff41`）、以及比赛库/工作台/侧边栏的硬编码 hex（深绿 `#19B84C`/`#168A34`）。三者混用导致页面"组件拼在白纸上"，没有 canvas→surface-soft→surface 的底色层级，且荧光绿与深绿并存缺乏统一品牌认知。设计评审建议收敛为一套「青瓷绿 × 雾蓝灰 × 云白」体系：以分层底色解决空间感、以深绿 `#23985B` 统一品牌主色、以状态色板统一信息编码。

## What Changes

- **全局设计 Token 层（单一权威源）**：在 `:root` 对旧 `--capture-*` 定义原位升级 + 追加缺失 Token，每个 Token 只保留一份定义，不出现同名重复定义；涵盖 canvas/surface-soft/surface/border/border-strong/brand（primary/strong/hover/soft）/text-*/status-*（含 soft 浅底）/sidebar/accent/lime。
- **报告页荧光绿迁移**：`.pb-vision-theme` 主色由 `#00ff41` 收敛到深绿家系；`--pb-*` 保留为 compatibility aliases 引用全局 Token；6 维度色与热力三段渐变（黄→绿→粉）语义保留，热力绿改用独立可视化绿 `#3AAF6B`（不绑定品牌色）。
- **状态色按业务语义命名**：LibraryCard 状态 tone 由颜色名升格为 `pending/processing/success/merge/failed/ai`；前景色加深使 10~12px Badge 对比度 ≥ ~4.5:1，soft 浅底保留。
- **比赛库/工作台/侧边栏去硬编码**：库、Workspace、Sidebar、LibraryCard 的硬编码 hex 全部改为引用全局 Token；Sidebar 选中导航加左侧强调条。
- **新增底色层级**：主产品壳层引入 canvas（最外层）/ surface-soft（Workspace、筛选栏）/ surface（卡片）三层背景，替代当前"白→白→白"；播放器外框改 `#24302B`。
- **辅助色纪律**：固定视觉占比（70/20/7/2/1%），`--capture-accent` 仅用于 AI/技术提示（不做 Primary CTA），`--capture-lime` 仅作点缀（占比 < 5%）。
- **删除死代码**：移除 `:root` 中 0 使用的通用色（`--surface-0..4`、`--action-green`、`--glow-green`、`--pickle-lime`、`--court-blue`、`--warning-orange`、`--error-red` 等）与荧光绿 literal/旧注释；**保留 `--pb-*` aliases 与 capture 功能语义色**。
- **保留不动（兼容样式域）**：capture 时间线/录制红等功能语义色原值保留；`src/styles/app.css` 旧 Landing/legacy 风格（30 个文件在用）作为兼容样式域保留，不属于本 Change 的"唯一颜色来源"范围。

## Capabilities

### New Capabilities
- `global-design-token-system`: 当前主产品壳层（Library / Workspace / Capture / Sidebar / PB Vision Report）统一 CSS 设计 Token 层（底色层级、主色、文字色、状态色板、视觉纪律），作为这些页面的唯一颜色来源与后续换肤入口；旧 Landing/legacy `app.css` 作为兼容样式域保留。

### Modified Capabilities
- `app-sidebar`: 活跃导航高亮由整块浅绿改为「左侧强调条 + 浅绿底 + 深绿字」（引用 `--capture-nav-active-*` 与 `--capture-brand-primary`），右侧分隔边框改用全局 Token。
- `localized-bright-ui`: 「Bright primary visual theme」需求从"亮色为主"升级为"分层底色 + 统一深绿主色"的具体实现；绿/蓝/橙/红等强调色关系保留，报告页主色由荧光绿收敛到深绿。

## Impact

- **样式**：`src/index.css`（新增全局 Token、删除死代码与荧光绿）、`src/styles/app.css`（不改）。
- **组件**：`src/components/pb-vizion/*`（101 处 `--pb-*` 引用）、capture 控制台 11 个文件（204 处 `--capture-*` 引用）、`src/components/platform/AppSidebar.tsx`、`src/components/library/LibraryCard.tsx`、`src/components/library/LibraryItemWorkspace.tsx`。
- **现有 OpenSpec 变更**：`pb-vision-style-report-page`（in-progress）与 `library-cover-cache-and-navigation-fixes`（in-progress）可能受影响，需在本变更落地后回归。
- **无 API/后端影响**，纯前端样式与 Token 重构。
