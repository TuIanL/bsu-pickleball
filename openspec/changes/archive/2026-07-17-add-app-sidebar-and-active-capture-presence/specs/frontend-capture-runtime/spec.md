## ADDED Requirements

### Requirement: 活跃录制查询 API

系统 MUST 提供 `GET /api/capture-takes/active` 接口供侧边栏等独立组件查询当前活跃录制。

#### Scenario: 有活跃录制

- **WHEN** 当前存在 status 为 `recording` 的 CaptureTake
- **THEN** 接口 SHALL 返回 HTTP 200
- **AND** 响应体 SHALL 包含：
  - `takeId`: string
  - `fieldSessionId`: string
  - `captureTakeId`: string
  - `startedAt`: ISO 8601
  - `serverNow`: ISO 8601（服务器当前时间，用于客户端时钟校准）
  - `status`: ActiveCaptureStatus
  - `title`: string | null（会话名称）
  - `courtName`: string | null
  - `captureMode`: "single" | "dual"
  - `videoSpec`: `{ width?: number; height?: number; fps?: number }`（前端自行格式化显示）

ActiveCaptureStatus 定义为 `"starting" | "recording" | "stopping" | "recovering" | "finalizing"`。

#### Scenario: 无活跃录制

- **WHEN** 当前不存在 status 为 `recording` 的 CaptureTake
- **THEN** 接口 SHALL 返回 HTTP 200
- **AND** 响应体 SHALL 为 JSON `null`
- **AND** 系统 SHALL NOT 使用 204 No Content

#### Scenario: 唯一性约束

- **WHEN** 系统尝试启动第二个 CaptureTake（已有活跃录制）
- **THEN** 后端 SHALL 拒绝并返回错误
- **AND** 检查和创建 SHALL 在同一原子操作中（SQLite 事务或应用层锁）
- **AND** `active` 查询接口 SHALL 始终最多返回一个活跃录制

#### Scenario: 活跃状态定义

- **WHEN** CaptureTake 的 status 为 `starting` / `recording` / `stopping` / `recovering` / `finalizing`
- **THEN** 该 Take SHALL 被视为活跃
- **WHEN** CaptureTake 的 status 为 `completed` / `partial` / `failed` / `canceled`
- **THEN** 该 Take SHALL 被视为不活跃

#### Scenario: 用户作用域

- **WHEN** 系统为单机部署（无用户认证）
- **THEN** 唯一性约束范围为全局——整个系统最多一个活跃 Take

### Requirement: 前端 useActiveCaptureTake Hook

系统 MUST 提供前端 hook 封装活跃录制查询。

#### Scenario: Hook 行为

- **WHEN** `useActiveCaptureTake` 挂载
- **THEN** 系统 SHALL 立即发起一次查询
- **AND** 系统 SHALL 每 5 秒自动轮询
- **AND** 系统 SHALL 使用 request sequence id 或 AbortController 防止过期请求覆盖新状态
- **AND** 页面恢复可见时 SHALL abort 进行中的请求并立即发起新请求
- **AND** 系统 SHALL 监听 `document.visibilitychange`，页面隐藏时暂停轮询
- **AND** 组件卸载时 SHALL 清理 polling interval、clock interval 和 abort 控制器
- **AND** 系统 SHALL 返回 `{ activeTake: ActiveCaptureTakeSummary | null, isLoading: boolean }`
- **AND** 系统 SHALL NOT 返回 204 的 null（统一为 200 null）
