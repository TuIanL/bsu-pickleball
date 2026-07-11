# capture-workflow Specification

## Purpose
TBD - created by syncing change redesign-product-entry-and-capture-console.

## Requirements
### Requirement: 采集任务首页

系统 SHALL 在 `/capture` 路径提供现场采集首页，展示最近采集任务列表和新建任务入口。

#### Scenario: 用户进入现场采集首页
- **WHEN** 用户导航到 `/capture`
- **THEN** 系统展示「现场采集」标题
- **AND** 系统展示「新建采集任务」主按钮
- **AND** 系统展示最近采集任务列表（按创建时间倒序），每项包含标题、场地名、采集模式、比赛形式、状态和时间

#### Scenario: 用户点击新建采集任务
- **WHEN** 用户点击「新建采集任务」按钮
- **THEN** 系统导航到 `/capture/new` 进入三步创建向导

#### Scenario: 用户点击已有采集任务
- **WHEN** 用户点击列表中某个采集任务
- **THEN** 系统导航到 `/capture/:id` 进入采集控制台

#### Scenario: 采集任务列表为空
- **WHEN** 系统中没有已创建的采集任务
- **THEN** 系统在列表区域展示空状态提示，引导用户创建第一次采集

### Requirement: 三步创建向导

系统 SHALL 在 `/capture/new` 路径提供三步向导创建 Field Session：采集场景 → 摄像头方案 → 分析设置。

#### Scenario: 向导第一步 - 采集场景
- **WHEN** 用户进入向导第一步
- **THEN** 系统展示表单字段：场地名称（court_name）、采集类型（capture_mode: 自由练习 / 记分比赛 / 工程测试）、人数模式（match_format: 单打 / 双打）、备注（notes）
- **AND** 系统展示「下一步」按钮
- **AND** 用户可跳过可选字段直接进入下一步

#### Scenario: 向导第二步 - 摄像头方案
- **WHEN** 用户进入向导第二步
- **THEN** 系统展示摄像头方案选择：单摄模式（底线高机位）/ 双摄模式 / 工程调试
- **AND** 每项包含简要说明
- **AND** 用户可在单摄和双摄模式下选择/确认具体摄像头（如果已注册）
- **AND** 系统展示「上一步」和「下一步」按钮

#### Scenario: 向导第三步 - 分析设置
- **WHEN** 用户进入向导第三步
- **THEN** 系统展示分析设置选项：自动创建分析任务 / 录制完成后再决定 / 仅保存视频
- **AND** 系统展示「上一步」和「创建采集任务」按钮
- **AND** 各选项含义清晰说明

#### Scenario: 向导完成创建
- **WHEN** 用户在三步向导中点击「创建采集任务」
- **THEN** 系统调用 `createFieldSession` API 提交表单数据
- **AND** 系统将 `analysisIntent` 保存为前端状态（不写入 Field Session）
- **AND** 创建成功后导航到 `/capture/:id` 采集控制台
- **AND** Field Session 状态保持 `planned`，在用户点击「开始录制」时才调用 `startFieldSession` 将状态置为 `live`

#### Scenario: 向导中返回上一步
- **WHEN** 用户在任一步骤点击「上一步」
- **THEN** 系统保留用户已填写的表单数据，回到上一步视图

### Requirement: 采集控制台布局

系统 SHALL 在 `/capture/:id` 路径提供采集控制台，布局为左预览、右控制、下事件标记和时间线。

#### Scenario: 进入采集控制台
- **WHEN** 用户导航到 `/capture/:id`
- **THEN** 系统加载 Field Session 详情并展示控制台
- **AND** 左侧为主预览区，显示实时摄像头画面
- **AND** 右侧上方为设备状态区（显示当前采集方案中使用的摄像头状态）
- **AND** 右侧下方为录制控制区（开始录制 / 停止录制按钮）
- **AND** 底部为场边事件标记条和时间线

#### Scenario: 控制台实时预览
- **WHEN** 用户在控制台中选择摄像头并确认
- **THEN** 系统通过 `getCameraPreviewUrl` 加载实时画面
- **AND** 预览区占据页面左侧主要空间
- **AND** 画面加载失败时展示重试按钮和错误提示

#### Scenario: 控制台设备状态
- **WHEN** 用户查看控制台设备状态区
- **THEN** 系统显示当前采集方案中使用的摄像头名称、在线状态（探测后）、连接地址
- **AND** 系统提供「重新探测」和「更换摄像头」操作按钮
- **AND** 不显示所有已注册摄像头的完整列表

#### Scenario: 用户点击更换摄像头
- **WHEN** 用户点击控制台中的「更换摄像头」按钮
- **THEN** 系统打开设备抽屉（右侧滑出），展示所有已注册摄像头的列表、注册、探测和删除操作

### Requirement: 录制中事件标记

系统 SHALL 在录制中提供场边事件快捷标记按钮和实时时间线。

#### Scenario: 录制中展示事件标记
- **WHEN** 录制状态为 recording
- **THEN** 系统在控制台底部展示场边事件标记按钮栏
- **AND** 按钮按采集模式（capture_mode）分类展示对应的快捷事件类型
- **AND** 用户点击事件按钮后，系统调用 `createTimelineEvent` API 记录事件

#### Scenario: 录制中展示时间线
- **WHEN** 录制状态为 recording
- **THEN** 系统在事件标记下方展示时间线
- **AND** 时间线实时展示已标记的事件，包含时间戳和事件标签
- **AND** 新事件实时追加到时间线末尾
- **AND** 时间线 SHALL 与视频预览底部对齐，位于预览画面正下方
- **AND** 时间线 SHALL 使用三轨道色条（盘、局、分）展示 CaptureSegment
- **AND** 色条 SHALL 在录制中随 elapsedMs 实时增长
- **AND** 时间线不 SHALL 使用倒三角事件标记

### Requirement: 录制完成面板

系统 SHALL 在停止录制后展示录制完成面板，根据向导中的分析设置展示对应操作选项。

#### Scenario: 自动分析模式 - 录制完成
- **WHEN** 用户在向导中选择了「自动创建分析任务」并停止录制
- **THEN** 系统显示「分析任务已自动创建」面板
- **AND** 面板包含分析任务 ID 或状态信息
- **AND** 面板提供「查看分析进度」和「播放回看」按钮

#### Scenario: 录制后再决定模式 - 录制完成
- **WHEN** 用户在向导中选择了「录制完成后再决定」并停止录制
- **THEN** 系统显示「录制已完成」面板
- **AND** 面板提供「立即创建分析任务」「仅保存视频」「播放回看」三个按钮

#### Scenario: 仅保存模式 - 录制完成
- **WHEN** 用户在向导中选择了「仅保存视频」并停止录制
- **THEN** 系统显示「录制已保存」面板
- **AND** 面板提供「创建分析任务」「播放回看」「返回采集任务」三个按钮

#### Scenario: 录制完成后面板可关闭
- **WHEN** 录制完成面板展示
- **THEN** 用户可关闭面板，回到控制台预览状态
- **AND** 系统保留已完成录制的信息在控制台上下文中

### Requirement: 采集控制台内录制状态机

系统 SHALL 在采集控制台内部使用统一的 `CaptureRuntimeState` 判别联合驱动 UI（含 `canceled` 和 `recovering`），替代原有的 `preview → recording → stopped`（单摄）和 `setup → testing → recording → stopped`（双摄）两套并行状态机。

#### Scenario: 录制状态统一

- **WHEN** runtime.phase 为 recording
- **THEN** 统一的录制中指示器（不区分单摄/双摄）
- **AND** 统一的停止按钮（不区分 handleStopRecording / handleDualStopRecording）
- **AND** 统一的 Live Coding 面板
- **AND** 统一的 elapsedMs 计时器

#### Scenario: 完成面板统一且保留上下文

- **WHEN** runtime.phase 为 completed 或 partial
- **THEN** 统一的完成面板，从 runtime.result + runtime.session 读取
- **AND** 可访问 fps、auto_analysis_job_id、摄像机名称（不仅仅是 tracks）
- **AND** 不再需要 isDualMode 分支

### Requirement: 采集任务与录制的关系

系统 SHALL 将 Field Session 作为顶层容器，Recording 是其下的视频采集活动。停止录制后返回统一的 `CaptureStopResult`，前端通过此结构判断分析可用性。

#### Scenario: 创建录制关联采集任务

- **WHEN** 用户在采集控制台中开始录制
- **THEN** 系统调用 `startRecording` 或 `startSyncRecording` API 并传入当前 `field_session_id`
- **AND** Recording 的 `auto_analyze_after_stop` 根据向导中的 `analysisIntent` 设置

#### Scenario: 停止录制返回统一结果

- **WHEN** 用户在采集控制台中停止录制
- **THEN** 系统调用 `stopRecording` 或 `stopSyncRecording` API
- **AND** 两者均返回 `CaptureStopResult`（统一 schema）
- **AND** 前端从 `CaptureStopResult` 读取 tracks、analysis_available、warnings
- **AND** 前端不再需要 `isDualMode ? dualStopResponse : completedRecording` 分支

### Requirement: 双摄采集控制台

系统 SHALL 在 Field Session 的 `camera_setup` 为 `dual` 时展示双摄像头选择界面。预览区通过 `previewTracks[]` 统一渲染。

#### Scenario: 预览区根据轨道数自适应

- **WHEN** tracks.length 为 1 → grid-cols-1
- **WHEN** tracks.length 为 2 → grid-cols-2
- **AND** 不区分单摄和双摄的独立 JSX 分支

### Requirement: 双摄录制完成面板

系统 SHALL 在双摄同步录制停止后展示双摄录制完成面板，使用统一的 `CaptureStopResult` 数据结构。

#### Scenario: 双摄录制正常完成

- **WHEN** 用户停止双摄同步录制且会话状态为 completed
- **THEN** 系统从 `CaptureStopResult.tracks` 展示两路摄像头的保存摘要
- **AND** 系统展示录制时长、分段数量和输出状态
- **AND** 若 tracks 中存在 status=completed 的 track，系统提供创建分析任务入口
- **AND** 系统通过 `analysis_available` 和 `analysis_blocked_reason` 判断分析入口状态
- **AND** 系统提供继续采集入口

#### Scenario: 双摄录制完成但分析入口不可用

- **WHEN** 双摄录制完成但 `analysis_available` 为 false
- **THEN** 系统展示录制已保存
- **AND** 系统展示 `analysis_blocked_reason` 说明不可用原因
- **AND** 系统不得跳转到失效的分析创建流程

### Requirement: 双摄录制前测试

系统 SHALL 在双摄采集控制台提供正式录制前的同步短录测试入口。

#### Scenario: 用户运行短录测试
- **WHEN** 用户在两个机位都已选择摄像头后点击短录测试
- **THEN** 系统调用双摄短录测试 API
- **AND** 系统展示每路摄像头的测试状态、首帧、尾帧和错误信息

#### Scenario: 短录测试未通过
- **WHEN** 短录测试返回失败
- **THEN** 系统突出显示失败机位
- **AND** 系统保留同步开始录制按钮禁用或显示风险确认状态

### Requirement: Outbox 同步与媒体完成正交

系统 SHALL 将录制停止后的 capturePhase 和 outboxHealth 作为两个独立的正交状态维度，允许在媒体已完成但事件未同步时正常展示完成面板。

#### Scenario: 媒体完成 + Outbox 未同步

- **WHEN** 录制停止完成但 Outbox 有未同步事件
- **THEN** capturePhase MUST 为 `completed`
- **AND** outboxHealth MUST 为 `pending`（显示待同步事件数量）
- **AND** 完成面板 MUST 正常展示（不被 Outbox 阻塞）
- **AND** 面板 MUST 提示「有 N 条现场标记待同步」

#### Scenario: 媒体完成 + Outbox 已同步

- **WHEN** 录制停止完成且 Outbox drain 全部成功
- **THEN** capturePhase MUST 为 `completed`
- **AND** outboxHealth MUST 为 `synced`
- **AND** 面板 MUST 不显示同步相关提示

### Requirement: useCaptureRuntime 替代分散的录制 handler

系统 MUST 提供 `useCaptureRuntime` Hook 作为录制生命周期唯一入口。页面使用协调层（freeze → stop → flushWithDeadline）。

#### Scenario: 停止流程由页面协调

- **WHEN** 页面需要停止录制
- **THEN** 页面协调层 MUST 先 liveCoding.freeze()
- **AND** MUST 立即 runtime.stop()（媒体优先）
- **AND** 同时 flushWithDeadline(3000)（best-effort）
- **AND** MUST NOT 存在 handleStopRecording / handleDualStopRecording

#### Scenario: 使用 session-specific polling

- **WHEN** 录制中轮询状态
- **THEN** 系统 MUST 使用 `getRecording(sourceSessionId)` 或 `getSyncRecording(sourceSessionId)`
- **AND** MUST NOT 使用 `/api/sync-recordings/active`
