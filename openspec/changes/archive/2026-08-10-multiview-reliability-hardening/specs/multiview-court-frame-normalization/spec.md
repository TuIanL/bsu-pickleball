## ADDED Requirements

### Requirement: canonical frame 跨运行复用

同一 CaptureTake 的 `CanonicalCourtFrameDefinition` SHALL 在 Parent、`MultiViewFusionRun` 和 `MultiViewJointRun` 之间复用。新任务不得因重新选择端点而创建第二个 canonical frame。

#### Scenario: 首次创建并持久化

- **WHEN** take 首次创建多视角分析且不存在 canonical frame
- **THEN** 系统 SHALL 根据显式端点定义持久化一个 `CanonicalCourtFrameDefinition`
- **AND** Parent SHALL 保存该 frame id

#### Scenario: 已有 frame 只读复用

- **WHEN** 同一 take 再次创建多视角分析
- **THEN** 系统 SHALL 复用既有 frame id
- **AND** 不得因新的默认 orientation 自动整体翻转 canonical 坐标

#### Scenario: 定义冲突显式失败

- **WHEN** 新请求的 orientation/端点定义与既有 canonical frame 冲突
- **THEN** preflight SHALL 返回冲突原因
- **AND** 系统 SHALL NOT 静默创建新的 canonical world
