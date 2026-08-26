## 1. 写路径纠正（LibraryPage）

- [ ] 1.1 修改 `src/pages/LibraryPage.tsx` 的 `handleUpdateTitle`：按 `item.ref.kind` 分派 — `upload`→`updateVideo`、`recording`→`updateRecording`、`sync_recording`→`updateSyncRecording`；删除 `fieldSessionId`→`updateFieldSession` 分支
- [ ] 1.2 修改 `handleUpdateDate`：同上分派，删除 `fieldSessionId`→`updateFieldSession` 分支
- [ ] 1.3 移除 `LibraryPage.tsx` 顶部 `updateFieldSession` 的 import（确认其他引用点不再需要）

## 2. 回退链收紧（libraryAdapter）

- [ ] 2.1 `buildLibraryItems` 中 sync_recording（:371/372）、recording（:425/426）的 `displayTitle` / `displayDate` 计算：删除 `fs?.title` / `fs?.started_at` 回退，仅保留 `素材.display_* || undefined`
- [ ] 2.2 `resolveLibraryItemByRef` 中 sync_recording（:523/524）、recording（:575/576）同步收紧
- [ ] 2.3 `semanticTitle()`（:177-196）移除 `fieldSessionTitle` 形参；同步删除调用点（:366 / :420 / :518 / :570）

## 3. 客户端注释与引用校准

- [ ] 3.1 更新 `src/services/analysisClient.ts` 中 `updateRecording` / `updateSyncRecording` 的注释：从「兜底 / 无场次」更正为「per-asset 标题主路径」（D1 正路径）
- [ ] 3.2 grep 全量 `updateFieldSession` 引用点，确认除 LibraryPage 卡片编辑路径外，capture / 工作台等真实引用未受影响

## 4. 测试翻转与补充

- [ ] 4.1 `src/services/libraryAdapter.test.ts` 第 368-382（`recording/sync displayTitle/displayDate 映射（场次真源优先）`）用例：改为「素材自身 `display_*` 优先；为空时 `displayTitle`/`displayDate` 为 `undefined`（不再回退 `fs?.title`/`fs?.started_at`）」
- [ ] 4.2 新增用例：同一 `FieldSession` 下 2 张卡各自设不同 `display_title` → 各自显示、互不影响
- [ ] 4.3 `src/components/library/LibraryCard.test.tsx` / `LibraryItemWorkspace.test.tsx` 中涉及元数据写入断言者：断言调用 `updateRecording` / `updateSyncRecording` / `updateVideo` 而非 `updateFieldSession`

## 5. 详情/分析页标题同步（cross-surface 统一）

- [ ] 5.1 `src/components/library/LibraryItemWorkspace.tsx:189` 标题改为 `item.displayTitle ?? item.title ?? 默认名`
- [ ] 5.2 `src/pages/AnalysisDetailsPage.tsx`：`useAnalysisResultReport` 解析 asset displayTitle 并透传；`<h1>` 用 `displayTitle ?? job.metadata.matchTitle`
- [ ] 5.3 `src/pages/AnalysisJobPage.tsx:234` 头部描述用 `libraryItem?.displayTitle ?? job.metadata.matchTitle`

## 6. 验证

- [ ] 6.1 运行 `npm test`（或 `npx vitest run`）确认全部测试全绿
- [ ] 6.2 浏览器端手动验证：同场次 N 卡分组，改 A 标题/日期 → 仅 A 变；B、C… 仍是原值 / 派生值
- [ ] 6.3 浏览器端验证：从卡片进入详情（LibraryItemWorkspace）/ 技术详情（AnalysisDetailsPage）/ 任务页（AnalysisJobPage）标题均显示自定义名
- [ ] 6.4 确认 capture console / 分析工作台中 `FieldSession` 引用路径未被误伤

## 7. Spec 同步

- [ ] 7.1 落盘本 change 的 delta spec（`library-card-metadata-editing` / `library-semantic-metadata`）已与代码改动一致
- [ ] 7.2 归档前复核：本次语义变更是否需要在 OpenSpec 当前 specs 目录同步更新（在 archive 阶段一并校验）
