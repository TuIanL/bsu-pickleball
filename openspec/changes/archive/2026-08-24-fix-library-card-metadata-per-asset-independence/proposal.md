## Why

比赛库（`LibraryPage` + `LibraryCard`）标题/日期行内编辑上线后，用户反馈：在「同一场次」分组下的任意一张卡片上修改标题或比赛日期，会导致**该场次下所有卡片同步变化**。根因是写路径把用户编辑写入了共享真源 `FieldSession.title` / `FieldSession.started_at`，而卡片 UI 呈现的是「逐卡可编辑」隐喻，二者直接冲突。

该行为是归档变更 `2026-08-24-library-card-metadata-editing` 在 design.md Risk #1 中**已预见的已知风险**，其 Mitigation（「UI 提示『重命名本场』」）从未落地，导致用户误以为只改了一张。本次变更纠正语义：**卡片上的标题/日期属于「本素材」，而非「本场次」**，消除「看似改本卡、实则改场次」的隐性连带。

## What Changes

- **写路径纠正**：`LibraryPage.handleUpdateTitle` / `handleUpdateDate` 不再把有 `fieldSessionId` 的 `recording` / `sync_recording` 写到 `FieldSession`，改为写到素材自身（`PATCH /api/recordings/{id}`、`PATCH /api/sync-recordings/{id}` 的 `display_title` / `display_date`）。`upload` 仍写到 `PATCH /api/videos/{id}`，逻辑不变。
- **回退链收紧**：`LibraryItemViewModel.displayTitle` / `displayDate` 不再把 `FieldSession.title` / `FieldSession.started_at` 作为回退项；仅保留 `素材自身 display_*` → 派生（时间+形式 / source id）的优先级链。`semanticTitle()` 移除 `fieldSessionTitle` 形参。
- **语义澄清**：`FieldSession.title` / `FieldSession.started_at` 仅保留 capture / take 编排、工程层引用；不再驱动 LibraryCard 用户层显示。
- **测试期望翻转**：`libraryAdapter.test.ts` 中「场次真源优先」用例改为「素材自身真源优先，场次不参与单卡显示回退」。
- **BREAKING（用户层语义）**：同一场次下多张卡片的标题/日期从「共享」变为「独立」。已在库中的历史 `FieldSession.title` / `FieldSession.started_at` 不再作为卡片显示值回退源，但字段保留、不破坏 capture 流程。

## Capabilities

### New Capabilities
<!-- 本次无新增 capability -->

### Modified Capabilities
- `library-card-metadata-editing`：将「方案 C 混合真源写入」替换为「每素材独立真源写入」——去除了「有 fieldSessionId 的 recording/sync 写 FieldSession」行为，新增「recording/sync/upload 分别写各自 `display_*`」行为；明确「同场次多卡各自编辑互不影响」。
- `library-semantic-metadata`：标题/日期派生链移除「回退到 FieldSession 标题 / started_at」分支；明确「覆盖值仅源自本素材」。

## Impact

- **前端代码**：`src/pages/LibraryPage.tsx`（`handleUpdateTitle` / `handleUpdateDate`）、`src/services/libraryAdapter.ts`（`buildLibraryItems` / `resolveLibraryItemByRef` 的 `displayTitle` / `displayDate` 计算、`semanticTitle`）、`src/services/analysisClient.ts`（注释由「兜底」更正为「per-asset 主路径」）。
- **测试**：`src/services/libraryAdapter.test.ts`（`recording/sync displayTitle/displayDate 映射` 用例）、`src/components/library/LibraryCard.test.tsx` / `LibraryItemWorkspace.test.tsx` 中涉及元数据写入断言者。
- **后端**：无需改动。`/api/recordings/{id}`、`/api/sync-recordings/{id}` 的 `display_title` / `display_date` PATCH 接口在归档变更 D5 阶段已就绪。
- **数据**：不涉及迁移脚本。`FieldSession.{title,started_at}` 字段保留不删；只是不再作为卡片显示回退源。
- **引用面**：capture console / 分析工作台中 `FieldSession` 的真实引用路径不受影响（本次只改 Library 用户层显示与写路径）。
