## Context

当前 backend 复用 `CourtPoint2D` 表达两类语义不同的点：一类是手动或半自动标定中的标准球场控制点，必须位于 20 ft x 44 ft 球场内；另一类是视频分析中由 homography 得到的球员脚点投影观测，可能因为脚点估计、标定误差或边界抖动略微落在标准边界外。

`PlayerProjector` 和 `PlayerIdentityManager` 已经有容差边界概念，但 `ProjectedTrackPoint.court_point` 仍使用严格 `CourtPoint2D`。当身份轨迹导出 legacy feet 坐标时，类似 `y = 44.2195 ft` 的容差内观测会触发 Pydantic `le=44` 校验错误，使分析任务在“多目标跟踪”阶段失败。

## Goals / Non-Goals

**Goals:**

- 将标定控制点、原始投影观测点、指标消费点的 schema 语义分离。
- 允许 tracking artifact 和诊断数据保留真实投影观测值，包括容差内边界外坐标。
- 确保运动指标和标准球场可视化只使用标准球场内坐标，避免越界观测污染距离、速度、热力图、厨房区和双打间距结果。
- 保持现有 JSON 字段形状兼容：`court_point` 仍为 `{ "x": number, "y": number }`。

**Non-Goals:**

- 不改变 homography 算法、YOLO 检测、IOU 跟踪或脚点估计策略。
- 不在本变更中重新设计前端球场可视化坐标系。
- 不迁移现有历史分析结果文件。

## Decisions

### Decision 1: 为不同生命周期的球场点建立不同 schema

引入清晰命名的 schema 分层：

```text
CalibrationCourtPoint2D
  标定输入/标准角点
  x: 0..20 ft
  y: 0..44 ft

ProjectedCourtPoint2D
  原始投影观测
  x/y: finite float
  可表达容差内或边界外点

MetricCourtPoint2D 或等价边界门
  指标和标准球场可视化输入
  x: 0..20 ft
  y: 0..44 ft
```

现有 `CourtPoint2D` 可保留为严格标定点，也可在实现时重命名为 `CalibrationCourtPoint2D` 并提供兼容别名。关键是 `ProjectedTrackPoint.court_point` 不再使用严格标定点 schema。

替代方案：在导出前裁剪 `ProjectedTrackPoint`。该方案改动小，但会把真实投影误差静默改写为边界值，不利于后续排查标定质量和脚点抖动。

替代方案：在导出前过滤所有标准边界外点。该方案可以止血，但仍没有表达“原始观测”和“指标输入”的模型差异，后续新消费者容易再次复用错误 schema。

### Decision 2: 指标入口执行显式边界门

分析管线在调用距离、速度、厨房区、双打间距和热力图计算前，必须使用标准球场边界生成指标输入。标准边界外的 `ProjectedCourtPoint2D` 不参与指标计算；如果需要展示或调试，应通过 tracking artifact、player trajectory artifact 或 diagnostics 保留原始观测。

```text
raw projected observations
        │
        ├── tracking/identity artifacts: preserve observed x/y
        │
        └── metric boundary gate
              │
              ├── in-bounds points -> metrics
              └── out-of-bounds points -> excluded/diagnosed
```

替代方案：让每个 metrics 模块自行处理越界点。当前模块处理并不一致，例如 heatmap 已有边界过滤，而速度/距离更容易直接消费输入。统一入口边界门更容易测试，也减少未来遗漏。

### Decision 3: 保持 API 形状兼容，改变校验语义

对外 JSON 不新增必需字段，不改变 `court_point.x` 和 `court_point.y` 的结构。变更主要发生在 backend 内部 Pydantic 类型和 metrics 输入构造处。若需要明确单位或 validity，应优先复用已有 trajectory artifact metadata 和 diagnostics，而不是在 legacy `ProjectedTrackPoint` 上强加破坏性字段。

## Risks / Trade-offs

- [Risk] 放宽 `ProjectedTrackPoint.court_point` 后，新的下游消费者可能误把原始投影点当成标准球场内点。 → Mitigation: 增加命名明确的类型和 metrics 边界门测试，并在 spec 中规定指标消费必须先边界处理。
- [Risk] 过滤越界点会让边界附近轨迹在指标结果中出现短暂断点。 → Mitigation: 原始 artifact 保留完整观测，后续可在独立 change 中探索带诊断的裁剪或平滑策略。
- [Risk] 重命名严格 schema 可能影响现有 import。 → Mitigation: 实现时可保留 `CourtPoint2D` 兼容别名，逐步把 tracking 侧迁移到新投影点类型。

## Migration Plan

1. 在 schema 层添加投影观测点类型，并将 `ProjectedTrackPoint.court_point` 切换到该类型。
2. 保持 calibration 相关输入继续使用严格边界点类型。
3. 在 analysis pipeline 的 metrics 入口集中构造标准球场内点列表。
4. 增加回归测试，覆盖 `y = 44.2195 ft` 这类容差内越界观测不会导致 tracking 阶段失败，且不会参与标准指标计算。
5. 回滚时可恢复 `ProjectedTrackPoint.court_point` 的严格 schema，但会重新暴露原始分析失败问题。
