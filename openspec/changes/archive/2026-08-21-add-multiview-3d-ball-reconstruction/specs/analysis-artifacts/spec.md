## ADDED Requirements

### Requirement: 球立体证据产物契约
系统 SHALL 为 `multiview_ball_stereo_evidence` 提供稳定的 artifact url / path / status 契约，供前端按需获取。

#### Scenario: 固定存储与访问路径
- **WHEN** 系统写入球立体证据
- **THEN** 文件 SHALL 存入固定路径 `multiview_ball_stereo_evidence.json`
- **AND** 该 slug 可通过既有 artifact 访问机制按需请求，无需后端主动加载重产物

#### Scenario: 状态机一致
- **WHEN** 前端请求球立体证据
- **THEN** 该 artifact SHALL 沿用与现有产物一致的 `available / unavailable / skipped / failed` 状态语义
- **AND** 缺失或不可用时不得返回 422 破坏分析展示