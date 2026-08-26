## ADDED Requirements

### Requirement: MultiView 显式引用场景标定 revision

双摄 Parent、`jointViewInputs` 和运行时 input bundle SHALL 显式保存适用的 `scene_calibration_revision`、`capture_take_id`、view ids 和 scene calibration status。场景标定 SHALL 与既有 sync authority、court orientation、Canonical Timeline 和 canonical frame 一起参与输入追溯。

#### Scenario: metric 模式输入完整
- **WHEN** 用户以 metric 3D 模式创建双摄分析
- **THEN** preflight SHALL 验证引用的 scene calibration revision 属于当前 `capture_take_id`、覆盖两个 view 且状态为 `ready`
- **AND** Parent 与 JointRun SHALL 持久化相同的 scene reference

#### Scenario: 显式 approximate fallback
- **WHEN** 当前采集任务缺少 ready scene revision但用户选择兼容 approximate 模式
- **THEN** preflight SHALL 允许任务按已有近似 virtual camera 路径运行
- **AND** SHALL 将 fallback mode、缺失原因和 scene status 写入 job config 与 diagnostics

#### Scenario: 不同固定机位禁止静默复用
- **WHEN** scene revision 的 camera/video/image-size provenance 与当前 input bundle 不匹配
- **THEN** preflight SHALL 返回结构化 scene calibration mismatch
- **AND** SHALL NOT 自动使用另一采集任务或另一 revision 的相机模型
