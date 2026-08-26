## Why

当前评分校准工作台要求用户面对完整比赛视频，逐球填写大量字段；而且已有分析产物没有进入候选队列，导致人工标注成本无法接受。现在需要把工作台改成以回合抽样、算法候选和快捷决定为中心的小样本校准流程，先用有限人工成本获得第一批可用于评分校准的 Gold Set。

## What Changes

- 增加按回合抽样的校准队列，不要求用户从头播放并标注整场比赛。
- 优先读取 CaptureTake 已保存的分析候选，并显示候选缺失的明确原因。
- 将回合、机位、证据时间窗和基础字段自动填充，减少重复录入。
- 增加“发球入界、发球失败、接发入界、接发不可观察、跳过”等快捷决定，并支持保存后自动进入下一回合。
- 将击球人、落点、置信度和备注收纳为可选的高级信息；第一批校准只要求评分所需的最小事实。
- 展示抽样进度、已完成回合数和待处理回合数，并保留现有 Gold Set 生命周期与详细编辑能力。
- 不改变 `scoring-calibration-annotation.v1` 的数据语义，不生成正式六维评分或 Overall 分数。

## Capabilities

### New Capabilities

- `scoring-calibration-quick-sampling`: 提供以回合抽样、候选优先和快捷决定为核心的高效评分校准工作流。

### Modified Capabilities

无

## Impact

- 修改 `ScoringCalibrationWorkbenchPage`、时间轴和候选适配逻辑。
- 需要从 CaptureTake 关联的本地分析目录读取已保存的候选事件，并保留原始 job/artifact provenance。
- 可能新增轻量的抽样队列 API 或在现有标注包 API 上增加队列字段，但不修改已有 Gold Set schema。
- 复用现有 `CaptureSegment` 回合片段、`SegmentVideoPlayer` 和评分校准标注 API。
