# multiview-analysis-input-contract Delta

## ADDED Requirements

### Requirement: jointViewInputs 持久化输入

`joint_tracking_v2` Parent SHALL 持久化 `jointViewInputs: [JointViewInput { cameraSlot, captureTrackId, cameraId, videoId, calibrationId, courtOrientation }]`,`sourceJobs = []`。该输入 MUST 进入 `AnalysisJobSummary` 持久化,使后端重启后可重建 `MultiViewJointRun`。`cameraId` SHALL 保留(sync calibration 可能以真实 camera id 为 mapping key,不依赖 `_resolve_secondary_sync_key()` 猜测)。

#### Scenario: 重启可重建 JointRun

- **WHEN** 后端重启后读取 `executionMode=joint_tracking_v2` 的 Parent
- **THEN** 系统 SHALL 从持久化 `jointViewInputs` 重建两路输入
- **AND** SHALL NOT 依赖 AnalysisJob children 或内存临时对象

#### Scenario: cameraId 保留

- **WHEN** joint 模式解析 sync mapping key
- **THEN** 系统 SHALL 使用 `JointViewInput.cameraId` 作为 sync key 候选
- **AND** 不依赖 P0 的 secondary-key 猜测逻辑

### Requirement: executionMode 输入签名

`multiviewExecutionMode` SHALL 进入 Parent 的 `inputSignature` / `configSignature`。同一 CaptureTake 的 late_fusion_v1 与 joint_tracking_v2 任务 SHALL 视为不同分析任务,不被幂等/去重合并。

#### Scenario: 输入签名区分

- **WHEN** 同一 CaptureTake 创建两种 executionMode 的 Parent
- **THEN** 两者的 inputSignature SHALL 不同
- **AND** 去重逻辑 SHALL NOT 丢弃其一

### Requirement: P0 契约语义不变

P0 冻结契约(sync authority / orientation / Canonical Timeline / pairing tolerance)SHALL 保持语义不变。joint 模式消费这些契约的语义与 late_fusion_v1 一致,仅执行边界改变。

#### Scenario: 契约语义不变

- **WHEN** joint 模式消费 sync / orientation / Canonical Timeline
- **THEN** 其语义 SHALL 与 P0 冻结版本一致
- **AND** 本 Change SHALL NOT 重定义任何已冻结契约
