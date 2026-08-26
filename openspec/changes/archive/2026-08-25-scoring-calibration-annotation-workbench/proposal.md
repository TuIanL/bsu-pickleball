## Why

当前系统已经有比赛视频、回合片段、逐帧播放和算法事件的基础能力，但还没有一个可以对逐球事实进行人工确认、复核和版本化保存的入口。因此，发球入界率、接发入界率和落点深度等指标缺少可审计的人工真值，暂时不能可靠地进入评分模型。

现在需要先建立一个独立的评分校准标注工作台，用用户自己的比赛视频形成第一批 Gold Set，再用它评估算法和校准单指标评分。这个阶段不要求继续依赖 PB Vision 的导出，也不要求立即训练机器学习模型。

## What Changes

- 新增评分校准标注工作台，复用现有 CaptureTake 视频、回合片段、视频播放和逐帧控制能力。
- 支持以逐球/击球机会为单位创建、确认、修正和跳过人工标注。
- 第一版覆盖发球、接发及其入界结果，并支持可观察时的落点区域标注；明确区分“不可观察”和“失败”。
- 展示算法候选事件，但将候选结果与人工决定分开保存，算法候选不得自动成为 Gold Set。
- 支持标注证据时间窗、所属回合、击球人、击球阶段、结果、落点、置信度和备注。
- 新增版本化的 `scoring-calibration-annotation.v1` 标注包，支持草稿、审核和锁定状态，并保留修订来源和数据血缘。
- 为后续指标校验提供结构化 Gold Set 输出和覆盖率、未知率、冲突等质量摘要。
- 第一版不新增六维技能分数、Overall 分数、PB Vision 专有 quality 分数、厨房区评分或机器学习训练流程。

## Capabilities

### New Capabilities

- `scoring-calibration-annotation-workbench`: 提供基于比赛视频的逐球人工标注、算法候选复核、标注包版本管理和 Gold Set 导出能力。

### Modified Capabilities

无。

## Impact

- 前端新增评分校准工作台页面和标注交互，复用 `SegmentVideoPlayer`、CaptureTake 视频源及现有时间轴能力。
- 后端新增标注包、标注条目、修订状态和查询/保存 API；不覆盖现有 `CaptureSegment`、`SessionTimelineEvent` 或算法生成的 `shot_rally_events`。
- 标注包需要关联 CaptureTake、视频版本、回合片段版本及算法候选产物，保证后续比较结果可追溯。
- 后续指标计算和 `performance-score.v1` 可以消费锁定的 Gold Set，但本 change 不实现正式总分模型。
- 现有 Vidat 导入、实时编码和片段编辑流程保持兼容；PB Vision 的 JSON/Excel 仅作为可选外部对照输入。
