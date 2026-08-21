## Context

当前前端颜色代码分散在四层（见 proposal.md「Impact」）：

1. `:root --capture-*`（204 处使用）：capture 控制台 + 时间线。其中**化妆层**（surface/border/text/brand）应并入全局 Token；**功能层**（timeline 盘/局/分/playhead、recording 红）是语义色，原值保留。
2. `:root` 通用色（`--surface-0..4`、`--action-green`、`--glow-green`、`--pickle-lime`、`--court-blue` 等）：已验证 0 使用，纯死代码。
3. `.pb-vision-theme`（101 处使用）：报告页荧光绿 `#00ff41` 专属，作用域限于 `.pb-vision-theme` 子树。
4. 硬编码 hex：比赛库、Workspace、Sidebar、LibraryCard（深绿 `#19B84C`/`#168A34`、灰阶 `#182230`/`#667085`/`#98A2B3`、边框 `#E4E7EC`）。
5. `src/styles/app.css` 旧落地页风格（30 个文件在用，含旧版报告）——**本次不改、不删**。

约束（来自用户决策）：
- 全局 Token 沿用 `--capture-*` 命名惯例升级为全局；不引入新命名体系。
- capture 功能语义色（timeline/recording 等）原值保留，不校准。
- 报告页荧光绿 `#00ff41` 迁移到深绿 `#23985B`。
- 统一后删除所有无用颜色方案代码。
- 所有可见文案保持中文。

## Goals / Non-Goals

**Goals:**
- 建立 `:root` 全局 Token 层，作为全平台唯一颜色来源。
- 迁移三处旧体系（capture 化妆层、报告页荧光绿、库/工作台/侧边栏硬编码）到全局 Token。
- 引入 canvas → surface-soft → surface 三层底色层级。
- 统一状态色板（沿用 LibraryCard tone 语义 + 校准到新色板）。
- 删除死代码与迁移后的旧定义。
- 报告页迁移后新旧两版报告自然收敛到同一深绿家族。

**Non-Goals:**
- 不改 `src/styles/app.css` 老落地页风格及其 30 个使用文件（单独后续处理）。
- 不校准 capture 时间线/录制红等功能语义色（保持原值）。
- 不改任何 API、后端、数据模型。

**Goals 补充（来自设计评审的显式要求，均纳入本次范围）：**
- 侧边栏选中态采用"左侧强调条 + 浅绿底 + 深绿字"而非整块浅绿按钮。
- 状态色板同时提供前景色与 Badge 浅底色（soft tint）两组 Token。

## Decisions

### D1：全局 Token 定义与命名

在 `:root` **原位升级**为升级版 `--capture-*` 全局 Token（沿用 capture 命名惯例）。**关键约束：整个 `:root` 对每个 Token 只保留一份权威定义**——不先新增同名变量再保留旧定义，避免 CSS custom property 同名多定义按声明顺序覆盖导致的"改了 Token 页面还是旧色"问题。迁移方式 = 旧定义直接原位改值 + 补充缺失 Token。

```css
:root {
  /* Global product tokens.
     --capture-* prefix retained for backward compatibility. */

  /* 底色层级 */
  --capture-surface-page: #F1F5F3;   /* canvas 最外层（由 #f7f8fa 校准） */
  --capture-surface-soft: #F7FAF8;   /* Workspace/筛选栏/页面区域（新增） */
  --capture-surface-card: #FFFFFF;   /* 卡片 surface */
  --capture-surface-elevated: #FFFFFF;/* 浮层/弹层 */
  --capture-surface-video: #24302B;  /* 播放器外框（由 #101828 校准，替代纯黑） */

  /* 边框 */
  --capture-border-default: #D9E3DD; /* 普通边框（由 #e4e7ec 校准） */
  --capture-border-strong: #C7D5CD;  /* 卡片/模块主要边界（新增） */

  /* 品牌绿（按用途分级，保证白字可读性与 hover 层级） */
  --capture-brand-primary: #23985B;        /* 品牌标识/图标/Tab underline/大色块 */
  --capture-brand-strong: #197947;         /* 白字 Primary Button/较小绿色文字（白字对比 ~4.8:1） */
  --capture-brand-primary-hover: #14683D;  /* hover/pressed */
  --capture-brand-soft: #DDF1E5;           /* 绿色浅底 */

  /* 文字三级 */
  --capture-text-primary: #182B24;
  --capture-text-secondary: #64736C;
  --capture-text-muted: #8F9D96;

  /* 辅助色（使用约束见 D5） */
  --capture-accent: #72B8C4;          /* AI/双摄/技术提示、辅助 icon；不做 Primary CTA */
  --capture-lime: #B8DE64;            /* 数据高亮/运动感微点缀；全屏占比 < 5% */

  /* 侧边栏（新增，来自设计评审） */
  --capture-sidebar-bg: #FAFCFB;       /* 侧边栏底 */
  --capture-sidebar-border: #DCE5E0;   /* 右侧分隔边框 */
  --capture-nav-active-bg: #E6F3EA;    /* 选中导航浅绿底 */
  --capture-nav-active-text: #1B824C;  /* 选中导航深绿字 */

  /* 状态色板（按业务语义命名；前景色加深以满足 10~12px Badge 对比度 ≥ ~4.5:1） */
  --capture-status-pending: #475569;       /* 待处理（≈4.7:1） */
  --capture-status-pending-soft: #EEF2F6;
  --capture-status-processing: #8A570E;    /* 正在分析（≈4.8:1） */
  --capture-status-processing-soft: #FFF3DC;
  --capture-status-success: #176B3C;       /* 分析完成（≈4.6:1） */
  --capture-status-success-soft: #E5F4EA;
  --capture-status-merge: #9A5300;         /* 待合并（≈4.6:1） */
  --capture-status-merge-soft: #FFF0DA;
  --capture-status-failed: #B42318;        /* 失败（≈4.7:1） */
  --capture-status-failed-soft: #FDE8E7;
  --capture-status-ai: #2F6F7B;            /* 技术/AI（≈4.5:1） */
  --capture-status-ai-soft: #E8F4F6;

  /* 功能语义色：原值保留（不校准） */
  --capture-status-recording: #e5484d;
  --capture-timeline-set: #f08a3c;
  --capture-timeline-game: #4f7df3;
  --capture-timeline-rally: #3baa62;
  --capture-timeline-highlight: #8b5cf6;
  --capture-timeline-playhead: #e5484d;
  --capture-timeline-side-change: #ec6d9e;
}
```

**备选**：采用设计评审的 `--bg-canvas/--green-500` 命名。否决原因：会同时重命名 capture 204 处与报告页 101 处引用，迁移面过大；沿用 `--capture-*` 只需改定义值，引用侧多数不变。

### D2：报告页荧光绿迁移

`.pb-vision-theme` 块保留（维度色、热力色仍需作用域隔离），但颜色值改为引用全局 Token 或直接取新色值：

- `--pb-primary: #00ff41` → `var(--capture-brand-primary)`（#23985B）
- `--pb-primary-dark: #00cc33` → `var(--capture-brand-strong)`（#197947）
- `--pb-primary-soft: #e6ffe9` → `var(--capture-brand-soft)`（#DDF1E5）
- `--pb-page-bg: #f0f4f2` → `var(--capture-surface-page)`（#F1F5F3）
- `--pb-card-border: #e5e7eb` → `var(--capture-border-default)`（#D9E3DD）
- `--pb-text-*` → 对应 `--capture-text-*`
- `--pb-heat-mid: #00ff41` → **独立可视化绿 `#3AAF6B`**（数据可视化色不与品牌装饰色绑定；收掉荧光但不用深品牌绿，避免热力图发闷；黄→可视化绿→粉语义保留）
- 6 维度色/浅底、`--pb-coach-*`：**原值保留**
- `--pb-success/#00ff41` → `var(--capture-status-success)`

`.pb-vision-theme` 子树内的组件引用方式不变（仍用 `var(--pb-*)`），只改定义，避免改动 12 个 pb-vizion 文件内联引用。

### D3：库/工作台/侧边栏去硬编码

- `AppSidebar.tsx`：侧边栏底 `bg-white` → `var(--capture-sidebar-bg)`（`#FAFCFB`）；右侧边框 `#E4E7EC` → `var(--capture-sidebar-border)`（`#DCE5E0`）；**选中导航由"整块浅绿"改为"左侧 3px 强调条 `var(--capture-brand-primary)`（#23985B）+ 浅绿底 `var(--capture-nav-active-bg)`（#E6F3EA）+ 深绿字 `var(--capture-nav-active-text)`（#1B824C）"**；图标 `#23985B`；灰阶 → `var(--capture-text-*)`。
- `LibraryItemWorkspace.tsx`：外层 `bg-white` → `var(--capture-surface-soft)`（Workspace canvas 层级），顶栏/卡片 `bg-white` → `var(--capture-surface-card)`。
- `LibraryCard.tsx`：卡片边框/阴影改 Token；缩略图占位由绿渐变（`from-[#EAF7EE] to-[#D1FADF]` + 绿色图标）改为中性灰渐变（`#E7EEEB → #DCE7E2`）+ 轻球场线纹理，品牌绿只保留在状态 Badge。
- **LibraryCard 状态 tone 升格为业务语义**（不再用颜色名）：`stateBadge` 返回类型由 `"green" | "blue" | "amber" | "gray" | "red"` 改为：
  ```ts
  type StatusTone = "pending" | "processing" | "success" | "merge" | "failed" | "ai";
  ```
  映射直接对应 `--capture-status-<tone>` / `-soft`（前景 + 浅底）：
  - 待分析/待处理 → `pending`
  - 正在分析 → `processing`
  - 队列中/视频处理中 → `ai`（技术类）
  - 待合并 → `merge`
  - 分析完成 → `success`
  - 失败 → `failed`
- 底部渐变氛围（设计评审明确给出）：库页背景用 `linear-gradient(180deg,#F4F8F6,#EEF3F1)` + 顶部 `radial-gradient(circle at 85% 0%, rgba(87,181,142,0.10), transparent 30%)`；搜索框 `#FAFCFB`、筛选器外背景 `var(--capture-surface-soft)`、选中项 `#E4F2E9`。

### D4：删除清单

迁移完成后一次性删除：

- `:root` 通用色 9 个（0 使用）：`--surface-0..4`、`--text-strong`、`--text-soft`、`--line-dark`、`--action-green`、`--glow-green`、`--pickle-lime`、`--court-blue`、`--warning-orange`、`--error-red`。
- `.pb-vision-theme` 中荧光绿 **literal** 与旧注释：`#00ff41 / #00cc33 / #e6ffe9` 等。
- 若 `--capture-*` 化妆层存在同名重复定义，只保留 `:root` 唯一权威定义。

**保留 `--pb-*` compatibility aliases（不删）**：`.pb-vision-theme` 继续保留并引用全局 Token，否则现有 101 处 `var(--pb-*)` 会断：

```css
.pb-vision-theme {
  --pb-primary: var(--capture-brand-primary);
  --pb-primary-dark: var(--capture-brand-strong);
  --pb-primary-soft: var(--capture-brand-soft);
  /* ...其余 --pb-* 同理引用全局 Token */
}
```

**不删**：`src/styles/app.css`、capture 功能语义色、报告页 6 维度色与热力色、`--pb-*` aliases。

### D5：视觉层级与色彩纪律（新增）

状态色按业务语义命名后，UI 不再关心"什么颜色"而只关心"什么状态"。为保证长期不再次花掉，固定全局视觉占比与辅助色使用边界：

```text
70%  雾灰绿 / 云白（canvas / surface-soft / surface）
20%  深文字 / 中性边框（--capture-text-* / --capture-border-*）
 7%  青瓷主绿（--capture-brand-*）
 2%  状态色（--capture-status-*，用于 Badge/小字号信息，前景满足 ≥ ~4.5:1）
 1%  Cyan / Lime 点缀（--capture-accent / --capture-lime）
```

- `--capture-accent`（#72B8C4）：AI / 双摄 / 技术提示、辅助 icon；**不做 Primary CTA**。
- `--capture-lime`（#B8DE64）：数据高亮、运动感微点缀；全屏占比 `< 5%`；**不做大面积背景、正文文字、主按钮**。
- 主绿分级：`--capture-brand-primary`（#23985B）用于品牌标识/图标/Tab underline/大色块；`--capture-brand-strong`（#197947）用于白字 Primary Button/较小绿色文字；`--capture-brand-primary-hover`（#14683D）用于 hover/pressed。
- 状态前景色对比度 ≥ ~4.5:1（10~12px Badge 小字号），浅底保留。

## Risks / Trade-offs

- **[荧光绿迁移后报告页视觉变暗]** → 报告页关键数字/进度原为荧光绿，迁移后整体观感更沉稳；热力三段改独立可视化绿 `#3AAF6B`（黄→绿→粉）保留对比度，需视觉回归确认。
- **[`--pb-*` 定义改成引用全局 Token 可能踩到作用域问题]** → `.pb-vision-theme` 在 `:root` 之内，`var(--capture-*)` 可正常解析；需确保无循环引用。
- **[204 处 capture 引用侧有个别硬编码未走 Token]** → 迁移后 grep `#([0-9a-fA-F]{6})` 复查 capture 控制台与库/工作台，残余硬编码一并收敛。
- **[两个 in-progress 变更（pb-vision-style-report-page / library-cover-cache-and-navigation-fixes）回归风险]** → 本变更落地后跑完整构建 + 现有测试，人工回归报告页新旧两版与比赛库打开视频/双摄。
- **[`--capture-surface-video` 从 #101828 校准到 #24302B 影响时间线对比]** → 仅播放器外框变色，时间线/视频内容不变；回归确认录制/回放观感。

## Migration Plan

1. **单一权威 Token 源**：直接在 `:root` 对旧 `--capture-*` 定义**原位改值**（surface-page/border-default/brand-primary/brand-soft/text 等），并**追加**缺失 Token（surface-soft/border-strong/brand-strong/brand-primary-hover/accent/lime/sidebar/status 系列含 soft）。全程每个 Token 只保留一份定义，不先新增同名再覆盖。
2. **capture 化妆层校准**：上一步即完成；改名项（如 text-secondary/muted）同步更新 11 个 capture 文件的引用。功能语义色不动。
3. **报告页迁移**：`.pb-vision-theme` 定义改为引用全局 Token / 新色值（含热力可视化绿 `#3AAF6B`），`--pb-*` aliases 保留。
4. **库/工作台/侧边栏去硬编码**：替换 hex 为 `var(--capture-*)`；LibraryCard `stateBadge` 类型升格为业务语义 tone。
5. **死代码清理**：删除零使用通用色与荧光绿 literal；保留 `--pb-*` aliases。
6. **回归验证**：`npm run build` + 测试 + 人工回归（报告页新/旧、比赛库卡片占位与状态 Badge、capture 控制台、Workspace 播放器）。

回滚：本变更纯前端样式，改动集中在 `src/index.css` 与少量组件 className；异常时通过 git 回退即可，无数据迁移。
