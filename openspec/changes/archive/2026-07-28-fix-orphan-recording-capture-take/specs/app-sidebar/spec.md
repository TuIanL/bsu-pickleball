## MODIFIED Requirements

### Requirement: 侧边栏当前录制状态块

系统 MUST 在侧边栏底部显示当前活跃录制信息，并在活跃录制为孤儿（session 已不可控）时提供「强制终止」入口。

#### Scenario: 有活跃录制

- **WHEN** `GET /api/capture-takes/active` 返回录制数据
- **AND** 对应录制 session 可正常操作（非孤儿）
- **THEN** 侧边栏底部 SHALL 显示录制状态块
- **AND** 状态块 SHALL 包含：红色脉冲圆点、已录制时长（每秒更新）、会话名称、场地、录制模式、视频规格
- **AND** 点击状态块 SHALL 跳转到录制控制台（`/capture/{fieldSessionId}`）

#### Scenario: 活跃录制为孤儿

- **WHEN** `getActiveCaptureTake()` 返回活跃录制
- **AND** 前端检测到该录制的控制台无法正常操作（hydrate 返回 `NO_ACTIVE_SESSION` 或 `HYDRATE_FAILED`）
- **THEN** `ActiveRecordingBlock` SHALL 额外展示「强制终止」按钮
- **AND** 点击「强制终止」SHALL 调用 `cancelRecording(takeId)` 或 `cancelSyncRecording(takeId)` 清理 session 和 CaptureTake
- **AND** 终止成功后 SHALL 清除活跃录制状态
- **AND** 终止成功后 SHALL 允许用户开始新录制（409 解除）

#### Scenario: 无活跃录制

- **WHEN** `GET /api/capture-takes/active` 返回 null
- **THEN** 侧边栏底部 SHALL 隐藏录制状态块
