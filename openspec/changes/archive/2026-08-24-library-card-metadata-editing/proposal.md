## Why

比赛库卡片的标题与日期当前是只读派生值（标题来自源文件名 / 场次标题 / 分析任务 matchTitle，日期来自录制开始时间 / 上传时间），用户无法在卡片上直接命名或修正比赛，导致后续「按自定义名称搜索比赛视频」的诉求无法满足。同时产品对外品牌已从「拍动视析」统一为「瞬境」，Web 端 logo、页面标题与文案需同步改名。本变更让用户在卡片上就近重命名标题、修改比赛日期（仅到日），并统一品牌命名。

## What Changes

- **卡片内联标题编辑**：标题右侧 hover 显示浅铅笔图标与高亮，点击进入行内编辑（input），回车保存、Esc 取消；保存后标题持久化并对搜索生效。
- **卡片内联日期编辑**：日期行 hover 显示浅铅笔图标与高亮，点击进入原生日期选择（仅到日，不含时间），保存后持久化。
- **编辑态与导航态视觉区分**：整卡外层仍是「点击封面进详情」的导航 button；标题/日期编辑区重构为导航 button 之外的兄弟节点，编辑态以品牌色 ring + 浅底呈现，与整卡的 `hover:shadow-md` 明显不同，避免「在改东西」与「在翻页」混淆。
- **方案 C 持久化（混合真源）**：
  - 有 `fieldSessionId` 的 recording / sync_recording 素材：编辑标题/日期时 **PATCH `/api/field-sessions/{id}`**（标题改 `title`、日期改 `started_at`）。同场次下多张卡共享此标题/日期。
  - 无 `fieldSessionId` 的 upload 素材：编辑标题/日期时 **PATCH `/api/videos/{id}`**，写入素材自身的 `display_title` / `display_date`。
- **品牌改名**：`拍动视析` → `瞬境`，覆盖 `index.html`（title + meta description）、`src/data/productCopy.ts`（`brand` 及硬件叙事 tagline）、`src/components/platform/AppSidebar.tsx`、`src/components/platform/AppShell.tsx`（顶部 logo 与 footer）。
- 搜索逻辑不变（已按 `title` 匹配），持久化标题后自定义名称自动可被搜索到。

## Capabilities

### New Capabilities
- `library-card-metadata-editing`：比赛库卡片标题/日期的可视化内联编辑与持久化能力，包括 hover 铅笔提示、行内编辑交互、方案 C 混合真源写入，以及编辑态与导航态的视觉区分。

### Modified Capabilities
- `library-semantic-metadata`：在既有「语义化标题解析」「工程 ID 去暴露」之上，新增「用户可编辑元数据优先」要求——`displayTitle` / `displayDate` 若存在则最高优先级展示，缺失时回退既有派生链（matchTitle → FieldSession 标题 → 时间+形式 → source id）；并明确卡片信息区由只读派生改为可编辑优先。
- `field-sessions`：在既有更新能力之上，允许 PATCH 修改 `started_at`（比赛日期），供卡片日期编辑写入场次真源。

## Impact

- **后端**：
  - `FieldSessionUpdate`（schema）增加 `started_at` 字段，供 PATCH `/api/field-sessions/{id}` 修改场次日期。
  - 新增 `PATCH /api/recordings/{id}`、`PATCH /api/sync-recordings/{id}`（若尚不存在）支持 `display_title`/`display_date`（方案 C 中 recording/sync 优先走 FieldSession，此接口为兜底/未来扩展保留）。
  - 新增 `PATCH /api/videos/{id}` 支持 `display_title` / `display_date`（upload 素材的真源）。
  - 对应 service / schema 字段与数据持久化（upload 需新增 `display_title`/`display_date` 字段）。
- **前端**：
  - `src/services/libraryAdapter.ts`：`LibraryItemViewModel` 增加 `displayTitle?` / `displayDate?`，三处组装（sync_recording / recording / upload）优先取真源值。
  - `src/components/library/LibraryCard.tsx`：重构信息区（封面导航 button + 可编辑标题/日期兄弟节点），新增内联编辑子组件；编辑态视觉与导航态区分。
  - `src/pages/LibraryPage.tsx`：新增 `onUpdateTitle(item, title)` / `onUpdateDate(item, date)`，保存后局部刷新该项（调用 `reconcileItem` 或 `buildLibraryItems`）。
  - `src/services/analysisClient.ts`：新增 `updateFieldSession`、`updateVideo` 等 API 封装（含 upload 的 PATCH）。
- **品牌文案**：4 处「拍动视析」→「瞬境」及配套 tagline 调整；不涉及代码逻辑变更。
- **依赖/风险**：
  - 同场次多素材共享 FieldSession 标题/日期，改一次会同步影响同场次所有卡（UI 上需让用户可预期）。
  - upload 改 `display_date` 不应覆盖 `uploaded_at`（上传时间保留为系统字段）。
  - 实施顺序建议与进行中的 `library-cover-poster` 错开 apply（两者改 LibraryCard 不同区域、adapter 不同字段，冲突极低）。
