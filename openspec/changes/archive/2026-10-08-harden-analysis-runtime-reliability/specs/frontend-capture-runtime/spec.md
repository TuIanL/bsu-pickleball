## MODIFIED Requirements

### Requirement: 判别联合状态替代双状态机

系统 MUST 使用 `CaptureRuntimeState` 判别联合替代 `consoleState` 和 `dualState` 两个独立状态。状态机包含 `canceled` 和 `recovering` phase。状态机 MUST 为「取消请求已发出但后端尚未确认」表达独立可观察状态，MUST NOT 让该 action 成为无状态变化的动作。

#### Scenario: 恢复网络不确定性

**变更**：进入 `recovering` 后增加自动恢复机制，无需用户手动点击；恢复结果保留完整媒体和分析入口。

**修改前**：`recovering` 仅显示"重试恢复"按钮等待用户手动操作。`recover()` 恢复时构造的结果固定为空 `tracks`、`analysisAvailable: false`，丢失视频与分析入口。

**修改后**：
- **WHEN** 用户点击停止且 stop API 返回前网络断开
- **THEN** runtime phase MUST 进入 `recovering`（不是 `failed`）
- **AND** 系统 MUST 按 sourceSessionId 查询服务器确认最终状态
- **AND** 系统 SHALL 在进入 recovering 后 500ms 启动第一次查询
- **AND** 系统 SHALL 使用 `recoveryRef` 控制查询状态（查询次数、飞行中标志、定时器引用）
- **AND** 查询成功且终态为 `completed/partial/failed` 时 SHALL 自动进入对应终态
- **AND** 查询结果为 `recording` 时 SHALL 保持 recovering，每 3 秒继续查询
- **AND** 查询发生网络错误时 SHALL 保持 recovering，更新 `operationError`，不进入 `failed`
- **AND** 超过 30 秒后 SHALL 停止自动高频轮询，仍保持 recovering，显示"再次停止"和"取消录制"

#### Scenario: 恢复超时判定按本次进入 recovering 的起点计算

- **WHEN** runtime 从非 `recovering` phase 进入 `recovering`
- **THEN** 系统 SHALL 以本次进入 `recovering` 的时刻作为本次恢复超时的计时起点
- **AND** 离开 `recovering` 时 MUST 重置该计时起点与尝试计数
- **AND** 同一挂载周期内第二次进入 `recovering` 时 SHALL 重新获得完整超时窗口
- **AND** MUST NOT 因沿用上一次恢复遗留的计时起点而在进入 `recovering` 的首次判定时就直接置为恢复超时

#### Scenario: 恢复超时后再次进入恢复仍可成功

- **WHEN** 某次恢复因超过超时窗口而停止自动查询且仍处于 `recovering`
- **AND** 用户随后再次触发停止或恢复使系统重新进入 `recovering`
- **THEN** 系统 SHALL 重新排程恢复查询
- **AND** SHALL 在本次进入后的超时窗口内持续查询直到得到终态
- **AND** MUST NOT 在排程下一次查询之前提前返回，导致后端已就绪的结果被丢弃

#### Scenario: 用户主动取消进入 canceled

- **WHEN** 用户点击取消录制
- **THEN** runtime phase MUST 进入 `canceled`
- **AND** MUST NOT 进入 `failed`（用户取消不是录制失败）

#### Scenario: 取消请求在飞行中产生可观察状态

- **WHEN** 用户在 `recording`、`stopping` 或 `recovering` phase 触发取消
- **THEN** 系统 SHALL 在发出取消请求后立即进入可观察的「正在取消」状态
- **AND** 该状态 MUST NOT 与「尚未发出取消请求」在状态机上不可区分
- **AND** UI SHALL 显示取消进行中的反馈
- **AND** 该状态下 MUST NOT 重复派发取消请求

#### Scenario: 取消请求失败后回到可重试状态

- **WHEN** 取消请求无法送达后端
- **THEN** 系统 SHALL 暴露可恢复的错误状态
- **AND** MUST NOT 把该次取消呈现为已取消
- **AND** 用户 SHALL 能够再次触发取消

#### Scenario: STOP_REQUESTED 不等 API 返回

- **WHEN** runtime.stop() 被调用
- **THEN** dispatch STOP_REQUESTED MUST 在 API 请求之前执行
- **AND** UI MUST 立即进入 stopping（不等网络响应）

#### Scenario: completed 状态保留 session 上下文

- **WHEN** phase 为 completed 或 partial
- **THEN** state.session MUST 保留 UnifiedCaptureSession（不仅仅 result）
- **AND** 完成面板 MUST 可访问 fps、auto_analysis_job_id、摄像机名称

### Requirement: 统一 elapsedMs 从服务器时间派生

系统 MUST 使用 `Date.parse(session.startedAt)` 派生 `elapsedMs`，停止后从结果的 track duration 读取。终态缺少可用轨道时长时，`elapsedMs` MUST NOT 回退为 0。

#### Scenario: 录制中 250ms 刷新

- **WHEN** capturePhase 为 recording
- **THEN** 系统 MUST 每 250ms 刷新 clockNow
- **AND** elapsedMs MUST = clockNow - Date.parse(session.startedAt)

#### Scenario: 停止后从 track duration 读取时长

- **WHEN** phase 为 completed 或 partial
- **THEN** elapsedMs MUST 从 result.tracks[0]?.durationMs 读取
- **AND** MUST NOT 使用时钟计算
- **AND** MUST NOT 在缺少可用轨道时长时把 elapsedMs 置为 0

#### Scenario: 终态缺失轨道时长时保留已知时长

- **WHEN** phase 进入 completed 或 partial
- **AND** 停止结果中的轨道集合为空或不含可用 durationMs
- **THEN** elapsedMs MUST 保留进入终态前已知的最后时长
- **AND** MUST NOT 跳变为 `00:00`
- **AND** 界面 MUST NOT 让操作员误判录制未成功而诱发重复录制
- **AND** 系统 SHALL 以可区分「时长未知」的方式表达该缺失，MUST NOT 以 0 冒充已知时长

#### Scenario: RECOVERED 后从 track duration 读取

- **WHEN** phase 为 recovered
- **THEN** 系统 SHALL 更新 elapsedMs 为 result.tracks[0]?.durationMs ?? 0
- **AND** 缺少可用轨道时长时 MUST 保留此前已知时长，MUST NOT 回退为 0

### Requirement: session-specific polling 替代全局 active

录制中 MUST 使用按 sourceSessionId 的 session-specific 查询（`getRecording` / `getSyncRecording`），不再使用 `/api/sync-recordings/active`。轮询 SHALL 具备在途请求守卫、SHALL NOT 依赖过期的会话快照，且 SHALL 在页面隐藏时暂停。

#### Scenario: 单摄录制中轮询

- **WHEN** mode 为 single 且 phase 为 recording
- **THEN** 系统 MUST 调用 `getRecording(sourceSessionId)` 轮询状态

#### Scenario: 双摄录制中轮询

- **WHEN** mode 为 dual 且 phase 为 recording
- **THEN** 系统 MUST 调用 `getSyncRecording(sourceSessionId)` 轮询状态

#### Scenario: 单次轮询请求慢于轮询间隔

- **WHEN** 某次轮询请求耗时超过轮询间隔
- **THEN** 系统 MUST NOT 叠加并发轮询请求
- **AND** SHALL 在前一请求完成后继续按间隔轮询

#### Scenario: 轮询写入使用最新会话而非过期快照

- **WHEN** 同一 sourceSessionId 的会话对象在轮询期间被替换
- **THEN** 轮询结果 SHALL 使用最新会话对象写入状态
- **AND** MUST NOT 把过期会话对象写入 reducer 状态

#### Scenario: 页面隐藏时暂停轮询

- **WHEN** `document.hidden` 为 true
- **THEN** session-specific 轮询 SHALL 暂停
- **AND** 页面恢复可见时 SHALL 补一次对账查询

## ADDED Requirements

### Requirement: 运行状态轮询的生命周期状态必须可观察且与实际一致

运行状态轮询 hook SHALL 以可触发渲染的状态表达「当前是否在轮询」，MUST NOT 在渲染期直接读取定时器引用等非渲染状态。轮询存活状态 SHALL 在定时器建立与清除后立即反映到返回值。

#### Scenario: 定时器清除后不再报告轮询中

- **WHEN** 轮询因页面隐藏或 phase 变化被清除
- **THEN** hook 返回的「正在轮询」标志 SHALL 为 false
- **AND** 该标志变化 SHALL 触发一次渲染

#### Scenario: 页面隐藏后标志不残留为轮询中

- **WHEN** 页面进入隐藏状态并清除轮询定时器
- **THEN** hook 返回的「正在轮询」标志 MUST NOT 仍为 true
- **AND** 页面恢复可见并重启轮询后该标志 SHALL 为 true

#### Scenario: 请求失败仍保留上一次快照

- **WHEN** 运行状态请求失败
- **THEN** hook SHALL 保留上一次成功快照
- **AND** SHALL 单独暴露该次请求的错误状态

### Requirement: 采集运行时轮询 SHALL 在页面隐藏时暂停

采集运行时的 session 轮询与恢复查询 SHALL 在 `document.hidden` 为 true 时停止发起新请求，并在页面恢复可见时补一次对账，避免后台标签页持续占用连接与后端资源。

#### Scenario: 录制中页面隐藏

- **WHEN** phase 为 recording 且页面被隐藏
- **THEN** 系统 MUST NOT 继续发起 session 轮询请求

#### Scenario: 恢复中页面隐藏

- **WHEN** phase 为 recovering 且页面被隐藏
- **THEN** 系统 MUST NOT 继续发起恢复查询

#### Scenario: 页面恢复可见后补一次对账

- **WHEN** 页面从隐藏恢复可见且运行时仍处于 recording 或 recovering
- **THEN** 系统 SHALL 立即发起一次对账查询
- **AND** MUST NOT 把恢复超时判定建立在页面隐藏期间未推进的计时之上