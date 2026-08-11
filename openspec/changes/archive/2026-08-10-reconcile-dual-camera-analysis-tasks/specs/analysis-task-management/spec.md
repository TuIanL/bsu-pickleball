## ADDED Requirements

### Requirement: 双摄录制派生任务归属一致性

前端 SHALL 使用与后端录制级删除一致的归属规则识别双摄录制派生的公开分析任务：任务的 `recordingSessionId` 或 `metadata.recording_session_id` 命中 session id，或任务的 `metadata.capture_take_id` 命中该双摄会话的 `capture_take_id`。

#### Scenario: 任务通过 recording session 归属

- **WHEN** 公开分析任务的 `recordingSessionId` 或 `metadata.recording_session_id` 等于双摄会话的 `session_id`
- **THEN** 前端 SHALL 将任务展示在该双摄录制卡片的分析任务区域
- **AND** 前端 SHALL 将任务从上传任务 Tab 中排除

#### Scenario: 任务通过 capture take 归属

- **WHEN** 公开分析任务缺少 session id，但 `metadata.capture_take_id` 等于双摄会话的 `capture_take_id`
- **THEN** 前端 SHALL 将任务展示在该双摄录制卡片的分析任务区域
- **AND** 前端 SHALL 将任务从上传任务 Tab 中排除

#### Scenario: 任务不属于任何双摄会话

- **WHEN** 公开分析任务的 session id 和 capture take id 均未命中任何双摄会话
- **THEN** 前端 SHALL 将任务保留在上传任务 Tab 或未归属诊断范围
- **AND** SHALL NOT 将任务错误挂载到任一双摄录制卡片

### Requirement: 双摄任务按类型分组并保留历史

双摄录制卡片 SHALL 将归属该会话的公开分析任务分为双摄协同 Parent、A 机位单摄任务和 B 机位单摄任务。每组 SHALL 默认展示按最近更新时间排序的最新任务；同组其他任务 SHALL 作为历史任务保留并可展开查看。

#### Scenario: 双摄 Parent 作为主任务

- **WHEN** 双摄录制会话存在一个或多个公开 `analysisKind=multiview` 任务
- **THEN** 卡片 SHALL 将最新 Parent 作为双摄协同主任务展示
- **AND** internal child SHALL NOT 作为独立任务展示

#### Scenario: 同一机位存在多个任务

- **WHEN** A 或 B 机位存在多个公开单摄分析任务
- **THEN** 卡片 SHALL 展示该机位最新任务的状态和操作
- **AND** SHALL 提供历史任务数量与展开入口
- **AND** 历史任务 SHALL 保留各自的 job id 和状态

#### Scenario: 任务更新时间缺失

- **WHEN** 某任务没有 `updatedAt`
- **THEN** 前端 SHALL 使用 `createdAt` 参与当前任务和历史任务排序
- **AND** SHALL 使用 job id 作为相同时间下的稳定排序依据

### Requirement: 双摄任务操作绑定具体任务

双摄卡片上的查看报告、查看进度、重试、取消和任务级删除操作 SHALL 绑定用户当前看到的具体任务 ID，不得通过任务类型再次隐式选择第一条任务。

#### Scenario: 最新任务操作

- **WHEN** 用户在双摄卡片点击最新 Parent 或 A/B 任务的操作
- **THEN** 前端 SHALL 使用该任务行对应的 `job.id` 导航或调用操作接口

#### Scenario: 历史任务操作

- **WHEN** 用户展开历史任务并点击某一历史任务的详情或删除操作
- **THEN** 前端 SHALL 只作用于该历史任务的 `job.id`
- **AND** SHALL NOT 修改同组当前任务

## MODIFIED Requirements

### Requirement: Analysis task management page

任务管理页 MUST 对每个双摄分析只展示一张 Parent 卡片，卡片标注「双摄协同分析」与 A/B/融合子状态，不再出现两张无关联的机位任务卡片。双摄任务卡片 SHALL 在 Parent、A 机位和 B 机位之间建立明确的任务分组；每组默认展示最新公开任务，并提供历史任务入口。双摄任务卡片的 CTA 按当前 Parent 状态区分：完成 → 查看报告；失败/取消 → 提供「重新双摄分析」入口；运行中 → 展示进度。

#### Scenario: 双摄任务单卡片

- **WHEN** 任务列表包含一个或多个属于同一双摄录制的 multiview Parent
- **THEN** 该录制 SHALL 以一张卡片展示最新 Parent
- **AND** 卡片 SHALL 含「双摄协同分析」标题、A 机位/B 机位/多视角融合子状态与数据来源
- **AND** 其 internal child SHALL 不单独出现在列表中

#### Scenario: 多个 Parent 保留历史

- **WHEN** 同一双摄录制存在多个公开 multiview Parent
- **THEN** 卡片 SHALL 默认展示最近更新的 Parent
- **AND** SHALL 提供展开入口查看其他 Parent 任务

#### Scenario: 失败/取消的 Parent 可重新分析

- **WHEN** 当前 multiview Parent 状态为 `failed` 或 `canceled`
- **THEN** 录制卡片 SHALL 提供「重新双摄分析」入口（导航到 `MultiViewAnalysisSetupPage`）
- **AND** SHALL NOT 误显示为「分析中」

### Requirement: Analysis task recording origin display

双摄录制卡片的 CTA MUST 将主操作改为「双摄协同分析」，次级的「分析 A/B 机位」MUST 降级为工程调试入口，分析状态展示 MUST 基于当前 Parent 和各机位任务分组。存在多次任务时，状态和操作 SHALL 指向最新任务，历史任务 SHALL 可展开查看。

#### Scenario: 录制卡片主 CTA

- **WHEN** 双摄录制卡片渲染且存在对应 CaptureTake
- **THEN** 主操作 SHALL 为「双摄协同分析」
- **AND** A/B 单摄入口 SHALL 置于次级操作

#### Scenario: 录制卡片展示多次任务

- **WHEN** 双摄录制卡片下存在同一类型的多个公开分析任务
- **THEN** 主视图 SHALL 展示该类型最近更新任务的状态
- **AND** SHALL 显示历史任务数量与展开入口
- **AND** SHALL 不将旧任务静默覆盖或丢弃
