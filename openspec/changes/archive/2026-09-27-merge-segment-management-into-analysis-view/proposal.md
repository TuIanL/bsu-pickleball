# Proposal: merge-segment-management-into-analysis-view

## Why

片段管理页（SegmentManagerPage）与数据分析页（VisionPage）是同一素材的两套独立回放入口：前者独占回合切分浏览与 auto-skip 回合跳转播放，后者独占人物框/骨架/球叠加与小地图。用户看一份数据要在两个页面之间切换，而数据分析页右侧的信息栏（任务状态、视觉层状态、下级报告入口）在完成态下信息价值低。把片段能力并入数据分析页，可以让「带视觉叠加的回合连播」成为单一主路径，同时删除一个整页入口及其 QA 复核流程，收窄前端维护面。

## What Changes

- **BREAKING** 删除片段管理页：`SegmentManagerPage`、其独立路由 `/capture/:fieldSessionId/takes/:takeId/segments`、Library 工作区的「片段」Tab、`EditableSegmentTimeline`、`SegmentVideoPlayer` 及其全部前端消费者。
- **BREAKING** 删除 boundary-review QA 复核前端：模型候选复核、人工边界复核、分序号调整、新增漏记回合等 UI 与 `?mode=boundary-review` 入口全部移除；切分结果在前端变为完全只读。后端 API 保留不动（前端清理与后端清理解耦，后者留独立 change）。
- 数据分析页右栏（AnalysisStatusRail 的位置，380px）替换为片段面板：片段筛选（全部/盘/局/分）、自动回合切分摘要、模型回合列表、人工标记列表，点击回合可在主画面定位/播放。
- AnalysisStatusRail 的任务状态、视觉层状态收进 info 图标弹层（按需暴露，不占右栏）；下级报告入口保留并重新安置。
- auto-skip 回合自动跳转（开关、非比赛时间推导、回合窗口续播、中央回合提示、进度条回合色带）迁移到数据分析页的 VideoAnalysisCard 播放器，状态机从页面私有逻辑抽取为共享 hook。
- 回合毫秒轴与播放器 canonical 时间轴的映射成为显式契约：回合窗口定义在 take 轴上，VideoAnalysisCard 播放走 canonical 轴（含双摄 displayTimeMapping 与分析窗口裁剪），必须显式换算。
- 降级路径：无 take 关联（上传视频 job）或无正式切分结果时，auto-skip 开关禁用并给出原因，其余分析能力不受影响。

## Capabilities

### New Capabilities

- `analysis-view-segment-panel`: 数据分析页右侧片段面板——take 反查与数据加载、片段列表/切分摘要展示、回合点击定位到主画面播放、无片段数据时的降级提示。

### Modified Capabilities

- `auto-skip-non-play-playback`: 播放入口从片段页迁移到数据分析页的 VideoAnalysisCard；删除「隔离复核模式不启用」场景（QA 模式已删）；新增回合毫秒轴到 canonical 时间轴的映射口径。
- `auto-rally-playback-cues`: 中央回合提示与进度条回合色带从 SegmentVideoPlayer 迁移到 VideoAnalysisCard，提示状态机行为保持；随 QA 删除移除「隔离复核模式不启用」场景。
- `visual-analysis-workspace`: Right-side analysis status rail 从常驻右栏改为折叠 info 弹层；右栏让位给片段面板。
- `segment-manager`: 页面删除——视频回放源解析、播放头列表高亮同步等仍被新面板复用的行为迁入 `analysis-view-segment-panel`，其余页面专属 requirement 全部移除。
- `segment-playback-editing-sync`: 回放联动部分（统一回放状态、点击片段播放、播完自动暂停）由新面板与增强播放器承接；时间线/事件标记联动与边界拖拽草稿随 QA 删除移除。
- `segment-player-view-controls`: SegmentVideoPlayer 删除，其全屏/静音/快捷键 requirement 移除（VideoAnalysisCard 既有控件不受影响）。

不动：`library-item-workspace`（其主规格从未枚举「片段」view，「片段」Tab 删除属实现层收敛，无 spec 级行为变化——刻意留空，非遗漏）、`segment-editing`（后端编辑契约保留，仅失去前端消费者）、`session-timeline-events`、`formal-match-state-segmentation`（后端行为不变）。

## Impact

- **前端删除**：`src/pages/SegmentManagerPage.tsx`（1801 行）+ 测试、`src/components/SegmentVideoPlayer.tsx`（603 行）+ 测试、`src/components/EditableSegmentTimeline.tsx`（278 行）+ 测试、`src/app/router.ts` 与 `navigationTypes.ts` 的 segmentManager 路由、`viewCapabilities.ts` 的 `segments` view、`LibraryItemWorkspace` 的 segments tab 与 lazy import。
- **前端改造**：`VisionPage.tsx`（右栏替换）、`VideoAnalysisCard.tsx`（接入 auto-skip 状态机、回合色带、中央提示）、`AnalysisStatusRail` 重构为折叠弹层、auto-skip 逻辑抽取为共享 hook（含 `resolveAutoRallyWindow` 左闭右开、终点缺省 `max(durationMs, startMs+500)` 等既有不变量）。
- **前端 service 清理**：`getBoundaryReview` / `getMatchStateCandidates` / `decideMatchStateCandidate` / `reviewSegmentBoundary` / `renumberRallyOrdinals` 等仅被 QA 模式消费的 client 函数删除；`listSegments` / `getFormalSegmentationSummary` / `getCaptureTake` 转由新面板消费。
- **后端**：无行为变更；boundary-review 相关 API 端点保留但失去前端消费者（清理留独立 change）。
- **测试**：`SegmentManagerPage.test.tsx`、`SegmentVideoPlayer.test.tsx`、`EditableSegmentTimeline.test.tsx`、`router.test.ts`、`VisionPage.test.tsx`、`LibraryItemWorkspace.test.tsx`、`viewCapabilities.test.ts` 受影响。
- **既有基线**：`SegmentManagerPage.tsx` 现存 14 条 `no-unused-vars` lint error，随文件删除一并消失，无需先修。
