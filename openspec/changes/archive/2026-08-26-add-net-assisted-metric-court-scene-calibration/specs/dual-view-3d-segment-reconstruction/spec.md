## ADDED Requirements

### Requirement: 场景标定质量决定双摄高度资格

系统 SHALL 区分由 scene-calibrated 双摄约束得到的 metric/近似高度和仅用于可视化的先验弧线。双摄合格段的 `estimated_z(t)` SHALL 由两个视角回投约束；其 metric 资格还 SHALL 依赖所引用 scene calibration revision 的状态和质量。双摄不合格段可以输出显式标记的 approximate 或 2.5D 高度，但 MUST NOT 冒充 metric 三维测量。

#### Scenario: ready scene 的双摄段
- **WHEN** 段级重建使用 `ready` scene revision、双视角回投约束和合格 stereo coverage
- **THEN** `z(t)` SHALL 来自两视角回投约束
- **AND** SHALL 标记 `metric_validity = metric_multiview` 或明确的近似 metric 状态
- **AND** sample SHALL 保存 scene revision 与 height uncertainty

#### Scenario: approximate scene 的双摄段
- **WHEN** 段具有双摄观测但只使用 `homography_constrained_virtual` 相机
- **THEN** 系统 SHALL 允许输出 approximate multiview height
- **AND** SHALL 标记 `metric_validity = approximate_multiview`
- **AND** SHALL 禁止将 peak height、speed 或其他高度指标表达为精确 metric 结果

#### Scenario: 双摄不合格但单摄段可显示
- **WHEN** 段具有连续单摄证据与事件端点但不足以重建可靠 3D
- **THEN** 系统 SHALL 允许使用事件边界感知的二次弧生成估算高度
- **AND** SHALL 标记 `metric_validity = visualization_only` 与具体 reconstruction mode
- **AND** MUST NOT 输出真实最高点或三维球速

### Requirement: 场景标定失败时分层降级

系统 SHALL 将 scene calibration unavailable、degraded、invalidated 与动态 stereo 质量失败分别记录，不得因为单个失败原因覆盖其他诊断。场景标定失败时 SHALL 优先保留球场 XY、落点和可解释的 2.5D 展示结果。

#### Scenario: 场景 revision 被 invalidated
- **WHEN** 当前任务引用的 scene revision 与输入 video/image-size provenance 不匹配
- **THEN** 该任务 SHALL NOT 发布 metric 3D height
- **AND** SHALL 记录 mismatch reason
- **AND** 在满足现有质量门时允许显式 approximate fallback
