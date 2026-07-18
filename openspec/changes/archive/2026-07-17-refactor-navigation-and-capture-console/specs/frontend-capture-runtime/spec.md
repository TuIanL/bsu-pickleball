## ADDED Requirements

### Requirement: 活跃录制查询 API

系统 MUST 提供 `GET /api/capture-takes/active` 接口供侧边栏等独立组件查询当前活跃录制状态。

#### Scenario: 有活跃录制

- **WHEN** 当前存在 status 为 `recording` 的 CaptureTake
- **THEN** 接口 SHALL 返回 200
- **AND** 响应体 SHALL 包含：`take_id`、`started_at`、`elapsed_ms`、`status`、`session_name`、`court_name`、`capture_mode`、`video_spec`（分辨率 + fps）
- **AND** `elapsed_ms` SHALL 由服务器计算（`now - started_at`）

#### Scenario: 无活跃录制

- **WHEN** 当前不存在 status 为 `recording` 的 CaptureTake
- **THEN** 接口 SHALL 返回 204 No Content

#### Scenario: 多个活跃录制

- **WHEN** 存在多个 status 为 `recording` 的 CaptureTake（边缘情况）
- **THEN** 接口 SHALL 返回最近创建的一个

### Requirement: 前端 `useActiveCaptureTake` Hook

系统 MUST 提供前端 hook 封装活跃录制查询与状态管理。

#### Scenario: Hook 行为

- **WHEN** `useActiveCaptureTake` 挂载
- **THEN** 系统 SHALL 立即发起一次查询
- **AND** 系统 SHALL 每 5 秒自动轮询
- **AND** 系统 SHALL 监听 `document.visibilitychange`，页面隐藏时暂停轮询
- **AND** 系统 SHALL 返回 `{ activeTake, isLoading }`
- **WHEN** 收到 204
- **THEN** `activeTake` SHALL 为 null
