## ADDED Requirements

### Requirement: 球跟踪和弹跳检测依据 effective FPS
球跟踪、静止候选过滤和弹跳检测 SHALL 使用后端统一的 `effective_fps` 计算速度、静止时长、缺失窗口和事件间隔。

#### Scenario: 静止球黑名单按秒换算
- **WHEN** 静止候选黑名单阈值配置为 2 秒，且 `effective_fps` 为 60fps
- **THEN** BallTracker MUST 在约 120 帧静止累计后触发黑名单逻辑
- **AND** 该逻辑 MUST NOT 固定使用 60 帧

#### Scenario: 弹跳事件间隔按 FPS 换算
- **WHEN** BounceDetector 的最小事件间隔配置为 0.25 秒，且 `effective_fps` 为 120fps
- **THEN** BounceDetector MUST 使用约 30 帧作为事件去重间隔
- **AND** 在 30fps 下 MUST 使用约 8 帧

#### Scenario: 球速度使用真实 FPS
- **WHEN** 相邻帧球坐标位移为 10 像素且 `effective_fps` 为 90fps
- **THEN** 球速度计算 MUST 使用 900 像素/秒作为该位移对应速度
- **AND** 后端 MUST NOT 使用 30fps fallback 计算为 300 像素/秒
