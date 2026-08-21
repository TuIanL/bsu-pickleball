## Why

Library-first 前端信息架构重构（commit `9c818a7`）把一级导航收敛为「比赛库 / 现场采集 / 设备管理」，并将任务管理页降级为工程控制台（工程模式才进入）。但"开始分析 / 再次分析 / 对一个录制建立多次分析"的入口没有同步迁移到 Library 这一层：未分析素材点「进入分析」只跳到 `?view=analysis` 的空态，而非真正的分析创建页；已分析素材在 Library 也没有任何"再建一次分析"的入口。页面、路由、后端能力都在，缺的是 Library 层接线。

现在需要补齐这两条用户路径，保持 Library-first 定位、不动工程控制台。

## What Changes

- 未分析素材的「开始分析」按素材类型分派到真实分析创建页：
  - `sync_recording`（双摄）→ `MultiViewAnalysisSetupPage`（`/capture/takes/:takeId/analyze`）
  - 单摄 `recording` / `upload` → 复用对应已有分析入口（单摄录制沿用录制派生分析页 / 上传沿用预填 videoId 的上传分析页）
- 已分析素材的「再次分析」入口：在 Library 卡片与素材工作区提供「再建一次分析」操作，复用既有 `RecordingAnalyzePage` / `MultiViewAnalysisSetupPage`，一次录制可建立多个分析任务（含 A/B 单摄与双摄）。
- 修正 [LibraryCard.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/../components/library/LibraryCard.tsx) 中"重新分析/分析"菜单项仅对 `upload` 开放的限制，放开录制/双摄。
- 修正 [LibraryPage.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/LibraryPage.tsx) 的 `handleReanalyze` 分支（当前录制/双摄错误跳转到 `/analysis/new` 上传页）。
- 修正 [LibraryItemWorkspace.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/components/library/LibraryItemWorkspace.tsx) 的 `OverviewView`「进入分析」按钮，从 `?view=analysis` 空态改为跳转分析创建页。
- 为 `LibraryItemViewModel` 暴露分派所需路由元数据（`captureTakeId`、双摄标记、单摄 videoId 等已部分存在，补齐缺口）。

## Capabilities

### New Capabilities

- `library-analysis-start`: 未分析 LibraryItem 从比赛库卡片 / 素材工作区进入分析创建页的路径，按素材类型分派到正确的创建入口；不落入结果空态。
- `library-analysis-recreate`: 已分析 LibraryItem 提供「再次分析 / 再建一次分析」入口，对一个录制建立多个分析任务（多类型：双摄协同、A/B 机位单摄），并正确回跳工作区/比赛库。

### Modified Capabilities

<!-- 本轮不改变现有 capability 的需求语义：library-item-workspace / match-library / analysis-task-management 的既有需求保持不变，
     仅新增上述两条用户路径作为独立 capability 消费它们。如需明确某个既有 requirement 变更，在此补列 delta。 -->

## Impact

- 受影响的代码（前端为主）：
  - `src/components/library/LibraryCard.tsx`、`src/pages/LibraryPage.tsx`、`src/components/library/LibraryItemWorkspace.tsx`
  - `src/services/libraryAdapter.ts`（如需补 `LibraryItemViewModel` 分派元数据）
  - `src/app/AppRouter.tsx` / `src/app/navigationTypes.ts`（如需新增路由于 type，优先复用既有 `recording-analyze` / `multiview-setup`）
- 复用而不改动：`RecordingAnalyzePage`、`MultiViewAnalysisSetupPage`、工程控制台 `/analysis/tasks`。
- 后端：预期无改动；如需支撑单摄录制创建分析的分派，可能复用既有 `recording_session_id`/`video_id` 契约。
- 测试：前端路由/组件行为测试，覆盖三类素材的分派与再分析回跳。