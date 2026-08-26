## Context

比赛库卡片标题/日期的行内编辑由归档变更 `2026-08-24-library-card-metadata-editing` 实现，采用「方案 C 混合真源」：有 `fieldSessionId` 的 `recording` / `sync_recording` 把编辑写入 `FieldSession.title` / `FieldSession.started_at`，`upload` 写入 `video.display_title` / `display_date`。

`libraryAdapter` 当时已为各素材预留 `display_title` / `display_date` 字段（优先级链：`素材.display_*` → `FieldSession.{title,started_at}`），且后端 `PATCH /api/recordings/{id}`、`PATCH /api/sync-recordings/{id}` 在 D5 已就位，仅作为「无场次兜底」。本次把「兜底接口」提升为正路径，「场次共享」降级为「不再参与卡片显示」。

当前写路径缺陷位置：`src/pages/LibraryPage.tsx:165-185`（`handleUpdateTitle` / `handleUpdateDate`）；回退链缺陷位置：`src/services/libraryAdapter.ts:371/372/425/426/523/524/575/576`。

**后续发现（同 turn）**：修复卡片写路径后，用户反馈「卡片改了、详情/分析页没跟着变」。经排查，详情页（`LibraryItemWorkspace.tsx`）与任务页/技术详情页（`AnalysisDetailsPage`、`AnalysisJobPage`）分别读取 `item.title`（派生名）与 `job.metadata.matchTitle`，均未消费 `displayTitle`，导致「逐卡改名」无法跨页同步。本次一并统一三处显示源。

约束：
- 后端零改动（`display_title` / `display_date` 已存在于各素材 schema）。
- 不破坏 capture console / 分析工作台对 `FieldSession` 的真实引用（仅改 Library 用户层显示与写路径）。
- 不引入新字段、不做数据迁移（`FieldSession.{title,started_at}` 保留）。

## Goals / Non-Goals

**Goals:**
- 纠正语义：卡片上的标题/日期属于「本素材」，编辑任意一张卡不会联动同场次其他卡。
- 写路径统一为「按素材类型写各自 `display_*`」。
- 回退链收紧：删除 `FieldSession.{title,started_at}` 作为卡片显示回退源。
- 测试期望翻转并新增「同场次多卡互不影响」保证。

**Non-Goals:**
- 不新增「批量改名」「历史版本 / 审计」。
- 不改动 capture console / 分析工作台中 `FieldSession` 的工程引用。
- 不引入卡片级 override 与场次级标题的「双层语义」（`option C` 已被否决）。
- 不做字段迁移脚本（保留 `FieldSession` 字段）。

## Decisions

### D1：写路径改走素材自身 `display_*`
**决策**：`LibraryPage.handleUpdateTitle` / `handleUpdateDate` 按 `item.ref.kind` 分派：
- `upload` → `updateVideo(id, { display_title, display_date })`
- `recording` → `updateRecording(id, { display_title, display_date })`
- `sync_recording` → `updateSyncRecording(id, { display_title, display_date })`

不再存在「有 `fieldSessionId` → 写 `FieldSession`」分支；`updateFieldSession` 在此两回调中不再被调用（其他引用路径保留）。

**理由**：持久化层早已存在 per-asset 字段与接口，仅 UI 路径错接。改此处即消除「共享真源」的直接成因，与用户「逐卡编辑」心智一致。

**替代方案**：A — 保留写 `FieldSession` 但在 UI 加「重命名本场」提示（原 Mitigation）。否决：提示无法根除「改一张却影响一组」的实质行为，仍违背「逐卡」隐喻；且用户已明确表示要「逐卡独立」（option B）。

### D2：回退链删除 `FieldSession.{title,started_at}`
**决策**：`LibraryItemViewModel.displayTitle` / `displayDate` 计算收紧为：
- `upload`：`video.display_title || undefined`
- `recording` / `sync_recording`：`素材.display_title || undefined`（不再接 `fs?.title`）
- 日期：`素材.display_date || undefined`（不再接 `fs?.started_at`）

`semanticTitle()` 移除 `fieldSessionTitle` 形参与调用点（`libraryAdapter.ts:179 / 185 / 366 / 420 / 518 / 570`）。

**理由**：若保留场次回退，用户在 A 卡填了自定义名、B 卡留空时会看到「A 是自定名、B 是场次名」的不一致；且「B 表面看起来是场次名、本质仍可能被他人编辑同一场次波及」的隐性风险复现。彻底删除后，每张卡显示值仅取决于自身字段与纯派生（时间+形式 / source id）。

**替代方案**：保留 `fs?.title` 作为「全场未命名时的保底默认」。否决：与 D1 的「逐卡独立」语义不协调，且无法消除隐性连带。

### D3：测试期望翻转
**决策**：`src/services/libraryAdapter.test.ts:368-382` 的「recording/sync displayTitle/displayDate 映射（场次真 * 优先）」用例：
- 改为「素材自身 `display_*` 优先」，且当素材 `display_*` 为空时，`displayTitle` / `displayDate` 为 `undefined`（不再回退到 `fs?.title` / `fs?.started_at`）。
- 新增用例：同一 `FieldSession` 下 2 张卡，分别设不同 `display_title` → 各自显示，互不影响。
- `LibraryCard.test.tsx` / `LibraryItemWorkspace.test.tsx` 中涉及元数据写入断言者，断言调用 `updateRecording` / `updateSyncRecording` / `updateVideo` 而非 `updateFieldSession`。

**理由**：测试必须与新语义一致，否则 `npm test` 红。

### D4：`FieldSession.{title,started_at}` 保留为工程层字段
**决策**：本次仅剥离其在 Library 用户层的「显示回退来源」角色；capture / take 编排、工程层、capture console 中的真实引用路径不受影响。

**理由**：capture 流程仍依赖 `FieldSession` 作为「一场比赛」的编排实体，字段不宜删；删除显示回退来源即可，无需破坏 capture 耦合。

### D5：`reconcileItem` 局部刷新逻辑复用
**决策**：`LibraryPage.reconcileItem`（按 `LibraryItemRef` 定向重投影单素材）无需改动，保存成功后继续复用，避免全库重建闪烁。

**理由**：该机制与写路径解耦，只关心「按 ref 重拉单素材」。

### D6：详情 / 分析页标题同步（cross-surface 显示统一）
**决策**：三处标题渲染统一优先取 `displayTitle`：
- `LibraryItemWorkspace.tsx:189`：`title = item.displayTitle ?? item.title ?? 默认名`
- `AnalysisDetailsPage.tsx`：`useAnalysisResultReport` 通过 `resolveLibraryItemByRef`（按 `recording_session_id` / `videoId` 推断 kind）解析素材并取 `displayTitle`，`<h1>` 用 `displayTitle ?? job.metadata.matchTitle`
- `AnalysisJobPage.tsx:234`：`libraryItem?.displayTitle ?? job.metadata.matchTitle`

**理由**：避免「卡片改了、详情/分析中页没变」的割裂。AnalysisJobPage 在有 `libraryOrigin` 时已加载 `libraryItem`，可直接复用；AnalysisDetailsPage 额外通过 Job → asset 反查解析。

**替代方案**：仅改卡片。否决：用户明确需要三处一致。

## Risks / Trade-offs

- **[Risk] 存量数据显示不一致** → 库中已有若干 `FieldSession.title` / `FieldSession.started_at` 被当作卡片标题/日期显示。收紧后，这些卡片若无 per-asset `display_*`，将回退到「时间+形式」派生名（如「8月20日 双打」），而非原场次名。**Mitigation**：这是预期行为变更（语义澄清）；若需保留存量场次名，需在迁移脚本中为每张卡写入对应 `display_*`（本期不做，列为 Open Question）。
- **[Risk] 删除回退后部分卡片显示值「降级」** → 原本显示「场次名」的卡，收紧后可能显示「时间+形式」或 source id。**Mitigation**：属预期；用户可在卡片上重新命名。不改既有数据。
- **[Risk] `libraryAdapter.test.ts` 之外仍有断言 `updateFieldSession` 用于卡片编辑** → **Mitigation**：实施前用 grep 全量核查 `updateFieldSession` 引用点，确认 Library 路径已移除。
- **[Risk] 误伤 capture console 的 `FieldSession` 真实引用** → **Mitigation**：D4 明确边界；grep `FieldSession`/`updateFieldSession` 全量调用点，逐一确认是否属于 Library 卡片显示/编辑路径。

## Migration Plan

- 纯前端增量：删除回退链分支、改写路径、翻测试。
- 后端接口零改动；`display_*` 字段已存在（缺省回退旧值）。
- 前后端可独立部署；回滚：前端回退到本 change 之前的 `LibraryPage` / `libraryAdapter` 即可恢复「场次共享」行为；后端字段保留不影响。
- 不写数据迁移脚本（存量卡片显示回退到派生名）。

## Open Questions

- 存量「被当作卡片标题显示的 `FieldSession.title`」是否需要一次性迁移为各卡 `display_title`？**本期不做**（仅语义澄清，不迁移）；若答辩/展示前希望保留存量场次名，可后续补迁移脚本。
- 是否需要在 UI 上明确标注「本素材」而非「本场」？本次仅纠正语义，不新增额外提示文案；如有需要可作为独立小变更追加。
