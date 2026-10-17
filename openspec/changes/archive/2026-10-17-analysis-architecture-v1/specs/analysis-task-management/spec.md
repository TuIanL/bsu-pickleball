## MODIFIED Requirements

### Requirement: Task status actions

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

系统 SHALL 按任务当前状态提供操作：活动任务可取消，中断任务可恢复，满足条件的历史任务可删除。

#### Scenario: Completed task is visible

- **WHEN** 任务状态为 succeeded 或兼容的完成状态
- **THEN** 任务行或卡片 SHALL 提供查看视频分析结果的主操作、分析详情入口及删除操作

#### Scenario: Processing task is visible

- **WHEN** 任务为 queued、uploaded、running 或兼容处理中状态，且 Worker liveness 新鲜
- **THEN** 任务行或卡片 SHALL 显示进度和状态详情入口，在后端允许时提供取消，不启用完成结果或删除操作

#### Scenario: Interrupted task is visible

- **WHEN** 任务为 interrupted，或 Worker liveness 已被持久标记失联
- **THEN** the task row or card shows the user-facing label “任务失联” and the last known stage/progress
- **AND** SHALL 停止将该任务视为仍在活动执行
- **AND** SHALL 提供任务详情、显式重新分析/重试和删除，不提供普通取消

#### Scenario: Failed task is visible

- **WHEN** 任务状态为 failed
- **THEN** 任务行或卡片 SHALL 显示已有失败上下文，提供详情、新上传、可用时重试及删除失败任务操作

#### Scenario: Canceled task is visible

- **WHEN** 任务状态为 canceled
- **THEN** 任务行或卡片 SHALL 显示取消上下文，提供详情、新上传及删除已取消任务操作

#### Scenario: 模块任务结果入口
- **WHEN** 任务列表显示 modular_v1 的终态 Job
- **THEN** 主操作 SHALL 打开模块运行清单和已保留结果
- **AND** partial SHALL 明确显示未完成目标，不要求 reportId 或跳入完整报告页

### Requirement: Analysis task inference toggles display
系统 SHALL 在任务摘要暴露所用推理开关状态，并在任务管理和详情页显示。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: Job summary exposes toggle states
- **WHEN** 前端读取分析任务摘要
- **THEN** 摘要 SHALL 包含 enableModelInference 与 enablePoseInference，反映创建任务时的值

#### Scenario: Legacy jobs have fallback values
- **WHEN** 历史任务创建于开关字段引入前且缺少这些字段
- **THEN** 摘要 SHALL 使用后端全局配置的兼容缺省值，不因缺字段无法渲染

#### Scenario: Task management page shows toggle states
- **WHEN** 任务管理页列出分析任务
- **THEN** 每个任务卡片 SHALL 显示推理开关，例如“检测开 / 姿态关”

#### Scenario: Job detail page shows toggle states
- **WHEN** 用户打开任务详情页
- **THEN** 任务信息区 SHALL 与其他元数据一起显示人检测及姿态开关

#### Scenario: 模块任务显示有效实现
- **WHEN** 任务列表或详情显示 modular_v1 Job
- **THEN** 系统 SHALL 显示冻结计划中的目标、实现及实际模型/参数摘要
- **AND** SHALL 不用未消费的 legacy 全局开关推断节点是否执行

### Requirement: 级联删除语义

`AnalysisDeleteResult` / 批量删除路径 MUST 支持 multiview Parent 的级联删除（Parent + owned child 分析产物 + fusion run 产物 + parent artifacts/report），且 MUST NOT 删除 CaptureTake、源视频或 CaptureTrack。child 的删除仅能由 Parent cascade 触发。

级联删除 MUST 只删除任务拥有且不被共享引用的文件。模块 Job 或跨 Job 共享引用 SHALL 先解绑，仍被直接引用、血缘或来源 pin 使用的证据 MUST 保留。

#### Scenario: 删除 Parent 级联

- **WHEN** 用户删除 terminal 的 multiview Parent
- **THEN** 删除结果 SHALL 覆盖 Parent 及其 owned child 的分析产物与 fusion run 产物
- **AND** 录制资产（CaptureTake / 源视频 / CaptureTrack）SHALL 保留

#### Scenario: 删除 child 被阻断

- **WHEN** 外部 API 尝试直接删除 internal child
- **THEN** 系统 SHALL 返回 `blocked`
- **AND** 删除 SHALL 仅经 Parent cascade 发生

#### Scenario: 级联包含共享引用
- **WHEN** 被删除 Parent 或其子任务曾生产被其他 Job/产物引用的证据
- **THEN** 系统 SHALL 保留受引用证据并只解除本次任务使用绑定
- **AND** SHALL 不因 Parent cascade 删除共享物理内容

### Requirement: 双摄录制卡片删除分析任务

「双摄录制」Tab 的录制卡片 SHALL 在存在分析任务时提供「删除分析任务」入口，用于清除该录制派生的所有分析任务及其本地产物，同时保留录制本身。

该入口对共享产物 SHALL 清除本组任务绑定并按引用生命周期保留存活证据，不保证物理删除仍被其他对象使用的内容。

#### Scenario: 卡片显示删除分析任务按钮

- **WHEN** 录制卡片存在任一分析任务（multiview Parent、A 机位或 B 机位单摄任务）
- **THEN** 卡片 SHALL 提供「删除分析任务」操作
- **AND** 该操作 SHALL 区别于「删除」（整条录制）按钮

#### Scenario: 卡片无分析任务时不显示

- **WHEN** 录制卡片不存在任何分析任务
- **THEN** 卡片 SHALL 不显示「删除分析任务」操作

#### Scenario: 用户确认后删除分析任务

- **WHEN** 用户确认删除该录制的分析任务
- **THEN** 前端 SHALL 调用后端录制级删除接口
- **AND** 删除完成后 SHALL 刷新任务列表
- **AND** 录制卡片 SHALL 保留在「双摄录制」Tab

#### Scenario: 有活跃分析任务被阻断

- **WHEN** 删除结果中包含 `blocked`（处理中任务）或 `failed` 项
- **THEN** 前端 SHALL 报告哪些任务已删除、哪些需要用户处理
- **AND** SHALL NOT 将阻塞项当作删除成功移除

#### Scenario: 录制级删除后外部消费者仍可读
- **WHEN** 其他 Job 或存活派生产物引用本录制分析证据
- **THEN** 删除本录制的分析任务 SHALL 不使该证据失效
- **AND** 源录制及必要快照 SHALL 继续保留

### Requirement: 分析任务删除清理完整产物目录

删除分析任务 SHALL 清除该任务拥有且可安全删除的完整私有产物目录，而不只是部分已知文件；录制资产、共享 Artifact 及仍被 pin 的媒体/快照 MUST NOT 被误删。共享产物 SHALL 存于受控共享根，不随私有目录递归删除；若历史私有目录中仍含被引用内容，系统 MUST 先安全迁移并保留身份/更新 locator，或明确阻断删除，不能使引用悬空。

#### Scenario: capture job 产物目录整体删除

- **WHEN** 用户删除一个产物位于 take_dir/analysis/<job_id>/ 的 capture 分析任务，且目录内不存在仍被引用或 pin 的内容
- **THEN** 后端 SHALL 删除该 `<job_id>` 目录及其全部内容，包括 `analysis_overlay.mp4`、`position_visualizations/`、`fused_*.json`、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`、`player_render_trajectory.json`、`players_trajectory.*`、`detections.jsonl` 等
- **AND** `take_dir` 下的录制视频、分段与 `sync_calibration.json` SHALL 保留

#### Scenario: 删除路径安全校验

- **WHEN** 后端准备整体删除分析任务产物目录
- **THEN** 目标路径 SHALL 严格匹配 `<take_dir>/analysis/<job_id>` 或 `<outputs_dir>/<job_id>` 格式
- **AND** `job_id` SHALL 以 `job-` 前缀开头并仅含 URL 安全字符（`^job-[A-Za-z0-9_-]+$`），避免误删录制目录

#### Scenario: 非 capture job 行为不变

- **WHEN** 用户删除产物位于 <outputs_dir>/<job_id> 的非 capture 分析任务，且目录内不存在仍被引用或 pin 的内容
- **THEN** 后端 SHALL 删除该 job 的输出目录
- **AND** 既有删除行为 SHALL 保持一致

#### Scenario: 私有目录内存在被 pin 的历史源
- **WHEN** 删除准备发现私有目录内的源文件仍被存活计划/产物使用
- **THEN** 系统 SHALL 安全保留该文件或返回 blocked 与明确原因
- **AND** SHALL 不先删除目录再修复引用

## ADDED Requirements

### Requirement: 模块任务删除遵循引用生命周期
模块任务删除 SHALL 解除 Job/计划拥有的直接使用关系，并保留其他 Job、固定输入、活动运行及产物血缘仍需的证据。v1 SHALL 默认保守保留共享产物；删除响应 MUST 区分任务已移除、物理证据被保留和阻断原因。

#### Scenario: 删除生产 Job 后消费者可用
- **WHEN** Job A 被删除而 Job B 仍引用 A 生产的模块姿态
- **THEN** A 的私有清单/trace SHALL 可清理，姿态 Artifact SHALL 保留供 B 使用
- **AND** SHALL 不覆盖原 artifact_id 或生产 provenance
