## Context

当前真实视频分析链路已经能够生成 tracking overlay、pose overlay、player trajectory 和 `serve_events.json`。在本地已有输出中，视频时长约 362 秒，tracking 与 pose overlay 覆盖到 360 秒以后，但 player trajectory 最长只到约 93 秒，serve score series 最晚只到约 44 秒，最终发球候选也只出现在前 42 秒。这说明问题不在前端 marker 映射，而在发球检测依赖的稳定 player trajectory 或上下文评分输入没有覆盖后半段。

前端目前把所有发球候选渲染为播放器进度条上的圆点。这个方案在候选少时有效，但候选多时会拥挤、难点、tooltip 重叠，也让播放控制和回合浏览混在一起。

## Goals / Non-Goals

**Goals:**

- 让发球检测输出能够解释“后半段为什么没有候选”，特别是 trajectory 覆盖不足、身份失联、目标球场过滤过严和评分时域提前结束。
- 在 player trajectory 提前中断但 tracking/pose 仍可用时，保守降级到 tracking、pose 或 ROI 信号，输出 `partial` 候选或明确的降级失败原因。
- 将发球候选浏览从播放器进度条迁移到播放器下方的横向回合导航条，宽度与播放器一致，候选卡片可横向滚动并可点击跳转。
- 保持现有 `serve_events.json` 基础字段、artifact URL、播放器播放控制和 overlay 加载行为兼容。

**Non-Goals:**

- 不实现完整 rally segmentation、回合结束检测、比分识别或发球得分归因。
- 不引入新的视觉模型或外部服务依赖。
- 不把降级候选包装成高置信完整检测；缺少底线坐标或 pose 时必须如实标记。

## Decisions

### 1. 先补覆盖诊断，再调阈值

发球检测应先输出覆盖诊断，而不是直接放宽阈值。诊断字段建议包括：

- `coverage.source_duration_seconds`
- `coverage.tracking_last_timestamp_seconds`
- `coverage.pose_last_timestamp_seconds`
- `coverage.trajectory_last_timestamp_seconds`
- `coverage.score_series_first_timestamp_seconds`
- `coverage.score_series_last_timestamp_seconds`
- `coverage.score_series_count`
- `coverage.candidate_first_timestamp_seconds`
- `coverage.candidate_last_timestamp_seconds`
- `coverage.coverage_ratio`
- `coverage.gaps` 或 `coverage.warnings`

这样可以先判断是“算法阈值太严格”还是“输入链路没有继续给样本”。备选方案是只增加日志，但日志不适合前端状态和历史 artifact 复盘。

### 2. 调试 artifact 用分桶统计替代只截前 N 条 rejected

当前 rejected 明细有数量限制，容易只保留视频前段样本。保留上限仍然必要，但必须增加时间分桶统计，例如每 30 秒或按视频百分比分桶，记录拒绝原因计数和可用输入状态。这样 artifact 体积可控，同时后半段仍可复盘。

备选方案是写出所有 rejected 明细；长视频会产生大 JSON，加载和存储成本都更差。

### 3. 降级检测不伪造上下文信号

当 player trajectory 缺失时，检测器可以使用 tracking frame 的 bbox 稳定后突增、pose 手臂峰值或 ROI 运动产生 `partial` 候选，但候选必须明确：

- `detection_mode` 为 `tracking`、`pose` 或 `roi`
- `source_signals` 只列出真实可用信号
- 缺少底线坐标时不填或不使用 `baseline_position_score`
- `reason` 说明因为 trajectory 覆盖不足进入降级

这能提升后半段可用性，同时避免把弱信号候选误认成完整上下文发球检测。

### 4. Player trajectory 输出承担覆盖诊断责任

发球检测是下游能力，无法独自判断 identity layer 为什么不再输出样本。player trajectory artifact 或 identity diagnostics 应记录每个 player 的时间覆盖、状态变化、未匹配 track、target-court 过滤和 primary-player selection 结果摘要。发球检测只消费这些信息并在自己的 artifact 中转述关键影响。

### 5. 前端新增独立 `ServeRallyStrip` 组件

`VideoAnalysisCard` 应保留现有视频播放器、控制条和进度 range。发球候选展示迁移到播放器容器下方或卡片内部视频区域之后的独立组件：

```text
video player
playback controls
serve rally strip: [#01 00:04 92%] [#02 00:14 76%] ...
```

组件输入使用现有 `resolveServeMarkers` 结果和 load state。容器宽度与播放器视觉宽度一致，使用横向 `overflow-x-auto`，卡片固定宽度，当前播放命中候选高亮。进度条上可以移除密集发球圆点，或只保留非常轻量的非主要提示；主要入口必须是导航条。

### 6. 状态表达沿用“候选”语义

UI 文案继续使用“发球候选”“发球时刻候选”或“回合起点候选”，不称为完整回合。`partial`、`no_candidates`、`unavailable` 和请求失败状态显示在导航条区域，不影响视频播放、暂停、拖动、tracking overlay 或 pose overlay。

## Risks / Trade-offs

- [Risk] 降级候选误报增加 → Mitigation: 以 `partial` 状态和降级模式展示，置信度上限保守，并在 reason 中说明缺失信号。
- [Risk] debug artifact 变大 → Mitigation: 明细保留上限，新增时间分桶和原因聚合，避免写出所有 rejected 样本。
- [Risk] 前端导航条占用竖向空间 → Mitigation: 使用紧凑卡片、固定高度和横向滚动，保持视频为第一视觉层级。
- [Risk] 新诊断字段与旧 artifact 不一致 → Mitigation: 字段全部可选，前端对缺失诊断显示未知，不破坏旧事件。

## Migration Plan

1. 后端先添加可选诊断字段和 debug 分桶统计，保持现有事件字段兼容。
2. 增加发球检测对 trajectory 覆盖不足的识别和降级分支。
3. 扩展 player trajectory identity diagnostics，供发球检测和调试 artifact 引用。
4. 前端新增 `ServeRallyStrip`，将真实视频发球候选主浏览入口迁移到播放器下方。
5. 保留旧 artifact 的读取兼容；已有分析结果仍能显示候选，只是覆盖诊断显示为未知。

## Open Questions

- 时间分桶默认粒度使用固定 30 秒，还是按视频时长自适应为 10 到 20 个 bucket？
- 进度条上的旧圆点是完全移除，还是保留为轻量时间位置提示但不再显示复杂 tooltip？
- 降级检测是否需要单独配置开关，还是默认启用并通过 `partial` 状态表达风险？
