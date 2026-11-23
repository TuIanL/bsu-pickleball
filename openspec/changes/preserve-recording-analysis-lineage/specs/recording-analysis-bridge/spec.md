## ADDED Requirements

### Requirement: 录制来源的服务端归属核验

系统 SHALL 在创建分析任务时由服务端核验请求声明的录制来源，而不是信任客户端声明。核验 MUST 覆盖 Session、登记 Video 与可核实的 CaptureTake，并产出唯一的规范化来源快照。核验 MUST 只读：系统 MUST NOT 修改历史 Job、补齐历史快照或修正旧 metadata。
服务端 MUST 先一致性检查顶层请求字段与 `metadata` 中重复声明的 Session/slot；冲突时 MUST 拒绝请求，不得任选一个字段。只在一处声明来源时，系统 SHALL 按该契约入口归一化后再执行同一套服务端核验。

#### Scenario: 旧录制零 Take 允许 session-only

- **WHEN** 请求声明的 Session 与 Video 关系可核实，且该 Session 名下查询成功但没有任何 CaptureTake
- **THEN** 系统 SHALL 创建任务，`captureTakeId` 为空，来源快照标记为已核实声明来源
- **AND** MUST NOT 因缺少 Take 而拒绝该请求

#### Scenario: 唯一 Take 被补齐

- **WHEN** 该 Session 名下恰好有一条 CaptureTake，且其 `source_session_id` 与请求 Session 相等
- **THEN** 系统 SHALL 在来源快照中补齐该 Take 的 ID
- **AND** SHALL 继续核对 Track 与 Video 的一致性

#### Scenario: Track 的空 Video 不构成冲突

- **WHEN** 该 Take 下某条 CaptureTrack 的 `video_id` 为空
- **THEN** 系统 MUST NOT 将其判定为 Video 冲突
- **AND** 仅当 `video_id` 非空且与请求视频不同时，才判定为冲突

#### Scenario: Take 与 Session 不匹配

- **WHEN** 声明的 Take 存在，但其 `source_session_id` 与请求 Session 不相等
- **THEN** 系统 MUST 返回来源归属冲突（HTTP 409）

#### Scenario: Video 不属于该 Session

- **WHEN** 请求的 `videoId` 不在该 Session 的登记视频集合内
- **THEN** 系统 MUST 返回来源归属冲突（HTTP 409）

#### Scenario: 顶层与 metadata 来源声明冲突

- **WHEN** 请求顶层 `recording_session_id` 与 `metadata.recording_session_id` 同时存在但值不同
- **THEN** 系统 MUST 返回 HTTP 409 `source_ownership_mismatch`
- **AND** MUST NOT 任选其中一处继续创建任务

#### Scenario: 单一允许入口的来源声明

- **WHEN** Session 来源只在契约允许的一个字段入口声明，且服务端能核验 Session、Video 与可用 Take
- **THEN** 系统 SHALL 将该来源归一化为一致的服务端快照
- **AND** MUST NOT 要求客户端重复提交同一来源字段

### Requirement: Take 解析的四态语义

系统 SHALL 把 Take 解析结果区分为四种互斥状态：查询成功且零条、恰好一条、多于一条、查询异常或存储不可访问。

仅当结果为「零条」且 Session 与 Video 关系已核实时，请求 SHALL 允许 `session-only`。「多于一条」MUST 视为来源不唯一而拒绝；「查询异常」MUST 视为暂不可用而拒绝。系统 MUST NOT 把异常、超时、存储离线或多候选无法判定当作「没有 Take」。

唯一性 MUST 由有界读取（最多读取两条即可判定）的结果数量确定，MUST NOT 依赖数据库唯一约束，因为历史数据库可能不携带该约束。

#### Scenario: 多个候选 Take 拒绝

- **WHEN** 同一 `(source_session_type, source_session_id)` 命中两条或更多 CaptureTake
- **THEN** 系统 MUST 拒绝创建并返回 HTTP 409
- **AND** MUST NOT 自动选择其中任意一条，也 MUST NOT 降级为 `session-only`

#### Scenario: 查询异常不降级

- **WHEN** Take 查询抛出异常、连接失败、超时或存储根不可访问
- **THEN** 系统 MUST 返回 HTTP 503
- **AND** MUST NOT 当作零 Take 放行

#### Scenario: 有界读取

- **WHEN** 某 Session 名下存在大量 Take 记录
- **THEN** 判定 MUST 只读取有限条记录即可得出结论
- **AND** MUST NOT 通过无界读取或全表扫描得出唯一性结论

### Requirement: 来源错误的对外契约

系统 SHALL 以既有 `{code, message, details}` 结构返回来源错误，且业务含义 MUST 由 machine code 决定，MUST NOT 由 HTTP 状态码单独决定。

新请求的来源归属冲突 MUST 返回 HTTP 409。后端 MUST NOT 为兼容旧客户端同时返回 400；兼容旧 Modular 客户端历史 400 响应 SHALL 由客户端按同一 machine code 完成。

`details` MUST 脱敏，MUST NOT 包含绝对文件路径、`session_dir`、异常栈或内部标识。`message` MUST 是面向用户、可据以采取行动的中文说明。

#### Scenario: 声明了来源但无法解析

- **WHEN** 请求提供了 `capture_take_id`，但没有 `recording_session_id` 与 `videoId`，且无法从该 Take 推出所属 Session 与视频
- **THEN** 系统 SHALL 返回 HTTP 400 且 `code = recording_source_required`

#### Scenario: 登记对象不存在

- **WHEN** 声明的 Session、Video 或 Take 在登记中不存在
- **THEN** 系统 SHALL 返回 HTTP 404 且 `code = recording_source_not_found`

#### Scenario: 显式 Take 不存在

- **WHEN** 请求显式提供 `capture_take_id`，但该 Take ID 不存在
- **THEN** 系统 MUST 返回 HTTP 404 且 `code = recording_source_not_found`
- **AND** MUST NOT 因该 Session 查询到零个 Take 而降级为 `session-only`

#### Scenario: 来源归属冲突

- **WHEN** Session、Video、Take 与机位之间存在不一致，或 Take 候选不唯一
- **THEN** 系统 SHALL 返回 HTTP 409 且 `code = source_ownership_mismatch`

#### Scenario: 来源登记暂不可用

- **WHEN** 来源登记查询异常或存储不可访问
- **THEN** 系统 SHALL 返回 HTTP 503 且 `code = recording_source_unavailable`
- **AND** 响应 SHALL 可重试
- **AND** MUST NOT 将数据库异常、超时或离线存储映射成普通 400、500 或零 Take

#### Scenario: 不泄漏内部路径

- **WHEN** 任一来源错误被返回
- **THEN** 响应体 MUST NOT 出现绝对路径、`session_dir` 或异常原文

### Requirement: 内部自动分析的可信来源上下文

系统 SHALL 允许录制停止流程在进程内构造可信来源上下文，用于「视频已登记、最终 Session 快照尚未写盘」这一时刻的自动分析创建。

该上下文 MUST 仅由录制停止服务构造，MUST 与本次正在停止的 Session 绑定，MUST 使用本次成功登记的 Video ID。该上下文 MUST 进入与普通请求一致的来源归一化与候选复用流程。

该上下文 MUST NOT 出现在任何公开 HTTP Schema 中。系统 MUST NOT 通过 `metadata`、URL 参数、请求头或 `session_dir` 授予内部信任，也 MUST NOT 引入可被外部请求设置的布尔信任标记。

自动分析创建失败 MUST NOT 破坏录制停止、视频登记、最终 Session 落盘与采集元数据写入。

#### Scenario: 最终快照未落盘仍能创建

- **WHEN** 视频登记成功、最终 Session 快照尚未写盘时触发自动分析
- **THEN** 系统 SHALL 使用进程内可信来源完成创建
- **AND** 任务来源快照 SHALL 标注为内部构造来源并绑定该 Session 与 Video

#### Scenario: 自动分析失败仍完成停录

- **WHEN** 自动分析创建过程抛出异常
- **THEN** 录制 SHALL 仍置为 completed，`auto_analysis_job_id` SHALL 为空
- **AND** 最终 Session 快照与采集元数据 SHALL 正常写入
- **AND** 异常 MUST 只记入内部日志，不影响接口成功返回

#### Scenario: 停录顺序与门控不变

- **WHEN** 录制停止被触发
- **THEN** 停录、视频登记、自动分析门控、会话置为 completed、快照落盘的既有顺序 SHALL 保持不变
- **AND** 回合上下文门控开启时 SHALL 仍不自动创建任务

#### Scenario: 伪造内部来源参数无效

- **WHEN** 普通 HTTP 请求在 `metadata` 中加入自造的信任字段或伪造 `session_dir`
- **THEN** 系统 MUST NOT 授予内部信任
- **AND** 该请求 SHALL 继续走常规来源核验

#### Scenario: Take 冲突时不创建

- **WHEN** 内部自动分析时刻的 Take 与 Track/Video 存在冲突
- **THEN** 系统 MUST NOT 创建任务
- **AND** 录制停止与落盘流程 SHALL 不受影响

## MODIFIED Requirements

### Requirement: 分析任务归属录制

系统 MUST 在分析任务创建时记录所属的录制 session ID 与机位 slot，并在前后端任务摘要中同时提供可兼容读取的字段。

`recording_session_id` 与 `camera_slot` MUST 作为**可空字段**存在于 `AnalysisJobCreate`：字段存在性不等于必填。请求仅在声明录制来源时提供 `recording_session_id`；`camera_slot` MUST NOT 被改为必填，也 MUST NOT 单独作为来源申报。服务端 MUST NOT 用 `metadata.session_dir` 判断归属。

#### Scenario: 创建分析任务携带归属

- **WHEN** 分析任务通过录制→分析迷你面板创建
- **THEN** `AnalysisJobCreate` MUST 提供 `recording_session_id` 与 `camera_slot` 两个**可空**字段
- **AND** 后端 MUST 将**核验后**的来源同时写入任务顶层 `recordingSessionId`、`cameraSlot` 与 `metadata`，且两处 MUST 一致
- **AND** 前端 `AnalysisJobSummary` SHALL 能读取 `recordingSessionId`、`cameraSlot` 以及旧任务缺失字段的 `undefined` 状态

#### Scenario: 单摄省略机位仍然合法

- **WHEN** 单摄录制分析请求只提供 `recording_session_id`，不提供 `camera_slot`
- **THEN** 系统 SHALL 正常创建任务，`cameraSlot` 为空
- **AND** MUST NOT 因缺少 `camera_slot` 而拒绝

#### Scenario: 按录制 session 过滤分析任务

- **WHEN** 前端请求 `GET /api/analysis/jobs?recording_session_id=<sid>`
- **THEN** 后端 SHALL 返回所有 `metadata.recording_session_id` 匹配的分析任务摘要

#### Scenario: 录制卡片展示关联分析任务

- **WHEN** 录制任务卡片渲染且存在派生分析任务
- **THEN** 卡片 SHALL 列出关联分析任务的状态与链接
- **AND** 卡片 SHALL 不阻塞于无关联任务的录制

#### Scenario: 历史任务字段缺失仍可展示

- **WHEN** 前端读取不包含录制归属字段的历史分析任务
- **THEN** 任务列表 SHALL 正常渲染文件、状态和时间信息
- **AND** SHALL 隐藏录制来源专属控件而不是抛出运行时异常
