# formal-match-state-segmentation Specification

## Purpose

定义双摄正式分析的比赛回合切分能力：生产 Runtime 直接从已确认同步的 CaptureTake 媒体推理，以 `MatchStateSegmentationRun` 记录可复现的模型与输入 provenance，将结果非破坏式发布为 `source=algorithm` 的 Rally 片段，并把不可变窗口计划固定到触发它的分析任务上。正式双摄分析因此不再依赖赛后逐条人工确认，同时人工片段与 QA 候选链路保持独立且不被改写。
## Requirements
### Requirement: 正式双摄回合切分 Runtime

系统 SHALL 为双摄正式分析提供独立于训练与候选脚本的生产 Runtime。Runtime MUST 直接读取 CaptureTake 的 `cam_1`、`cam_2` CaptureTrack 和已确认同步资产，MUST NOT 依赖 dataset manifest、RGB JPEG cache、人工 labels、ground-truth 或 evaluation 数据。Runtime SHALL 在 artifact 中记录模型包、权重、decoder、输入视频、同步 revision、时间 authority、窗口 coverage 与 view mask。

#### Scenario: 以正式媒体推理
- **WHEN** 可分析的双摄 CaptureTake 进入正式回合切分
- **THEN** Runtime SHALL 从两个 CaptureTrack 的媒体和其权威时间映射构造模型输入
- **AND** 输出 SHALL 不包含训练期 ground truth 或 evaluation 作为正式运行依赖

#### Scenario: 同步采样 secondary view
- **WHEN** Runtime 为公共 take 时间 `T` 采样 secondary view
- **THEN** 它 MUST 使用该 CaptureTake 当前绑定的 sync calibration 将 `T` 映射为 secondary 媒体时间
- **AND** SHALL 在 artifact 保存同步 revision、映射覆盖和不足证据原因

#### Scenario: 生产 Runtime 不导入训练脚本
- **WHEN** 后端加载正式模型
- **THEN** 模型结构、预处理和 decoder SHALL 来自 `backend/app/vision/match_state/` 或等价生产模块
- **AND** MUST NOT 反向导入 `scripts/train_match_state_rgb.py` 或候选推理 CLI

### Requirement: 可部署且可复现的模型包

系统 SHALL 用已签名的生产模型 package 执行正式切分。package MUST 包含 model metadata、权重、标签映射、采样/预处理配置、decoder 阈值和 SHA-256 可验证引用；Settings MUST 配置 package 目录、device、batch size 和 required profile。Worker SHALL 按 `(package_sha256, device)` 缓存已校验的模型实例。

#### Scenario: 加载有效模型包
- **WHEN** Worker 领取一个需要正式切分的 prerequisite job
- **THEN** 它 SHALL 在推理前校验 package schema 和所有受引用文件的 SHA-256
- **AND** 成功 artifact 与 SegmentationRun SHALL 记录 package id、version、package hash 和 weights hash

#### Scenario: 同一模型复用已加载实例
- **WHEN** 同一 Worker 连续执行 package hash 和 device 均相同的两次正式切分
- **THEN** Worker SHALL 复用已校验的模型实例
- **AND** 两次运行仍 SHALL 分别保存各自输入与产物 provenance

#### Scenario: 模型包不可用
- **WHEN** package、权重、schema、设备或 Runtime 依赖不可用
- **THEN** Runtime SHALL 返回 `model_unavailable` 或等价稳定原因
- **AND** `match_default` 双摄 Parent SHALL 不得静默按整场视频继续

### Requirement: SegmentationRun 与不可变窗口计划

系统 SHALL 为每次正式切分持久化 `MatchStateSegmentationRun`。Run MUST 关联 CaptureTake 和 planning job，并记录状态、模型/输入/sync provenance、artifact hash、unknown rate、片段数、`supersedes_run_id` 和开始/结束时间。成功或正常零回合运行 MUST 写出带 run id 与 hash 的不可变 `AnalysisWindowPlan`；若一个窗口可绑定该 Job 的 `AnalysisRallyContextSnapshot`，计划 MUST 保存 context reference/hash、binding method 和诊断。分析 Parent MUST 绑定 run id 与 plan hash，后续消费者 SHALL 仅使用该计划及其冻结 context，不得查询可变现场状态或可编辑名册。

#### Scenario: 成功运行绑定 Parent
- **WHEN** 正式切分识别出一个或多个 Rally
- **THEN** 系统 SHALL 创建 succeeded SegmentationRun、窗口计划和对应 algorithm Rally Segments
- **AND** Parent SHALL 在后续视觉执行开始前持久化该 run id 与 plan hash

#### Scenario: 上下文绑定优先级
- **WHEN** formal window 需要关联一个分析回合上下文
- **THEN** 系统 SHALL 按 `direct_segment_link`、`direct_start_event_link`、`unique_temporal_match` 的顺序选择第一个唯一有效候选
- **AND** 无直接或唯一时间关联时 SHALL 标记 context unavailable 并保存候选诊断

#### Scenario: 运行中出现新版本
- **WHEN** Job A 已绑定 Run 1，随后同一 CaptureTake 成功发布 Run 2 或产生新的 context 版本
- **THEN** Job A 的指标、事件归属和报告 SHALL 继续使用 Run 1 的窗口计划及其 context
- **AND** MUST NOT 改为查询当前最新的自动 Segment、LiveCodingState 或名册

#### Scenario: 正常零回合
- **WHEN** 模型输入有效且推理完成，但没有满足发布条件的 Rally
- **THEN** Run SHALL 记录 `valid_no_rallies`
- **AND** 窗口计划 SHALL 是显式空集合而非未设置
- **AND** 回合派生指标 SHALL 表达 `no_active_rallies`，不得将全视频当作有效比赛时间

### Requirement: 自动 Rally 的非破坏式发布

系统 SHALL 通过专用发布服务生成正式自动 Rally，不得复用人工候选确认的创建路径。每个自动 Rally MUST 使用 `source=algorithm`、`status=inferred`、`segment_type=rally`、`edit_status=active` 并关联 `segmentation_run_id`。新 Run 仅在 artifact 校验与数据库发布均成功后才替代旧自动 Run；人工 Segment 和现场 TimelineEvent MUST 永不被该事务修改。

#### Scenario: 发布自动 Rally
- **WHEN** Runtime 写出边界有效、排序合法的成功窗口计划
- **THEN** 发布服务 SHALL 创建带 `segmentation_run_id` 的 algorithm/inferred Rally Segments
- **AND** MUST NOT 调用 `create_manual_rally()` 或写入 `source=manual`

#### Scenario: 新 Run 成功替代旧 Run
- **WHEN** 同一 CaptureTake 的 Run 2 成功发布
- **THEN** Run 1 的 active algorithm Rally Segments SHALL 在同一发布事务中变为 `superseded`
- **AND** Run 2 Segments SHALL 变为 active
- **AND** 人工 Segment 保持原 `source`、边界和 edit status

#### Scenario: 新 Run 失败
- **WHEN** 新 Runtime 在 artifact 校验或数据库发布前失败
- **THEN** 新 Run SHALL 记录失败诊断或保持不可发布状态
- **AND** 旧 active algorithm Rally Segments SHALL 保持 active
- **AND** 系统 SHALL 不删除或覆盖人工 Segment

### Requirement: 正式结果策略

正式双摄 `match_default` SHALL 将切分视为 required prerequisite，并区分 `succeeded`、`valid_no_rallies`、`low_evidence`、`input_unavailable`、`sync_unavailable`、`model_unavailable` 与 `inference_failed`。`succeeded` 与 `valid_no_rallies` 可形成已绑定窗口计划；其余状态 SHALL 阻止后续正式视觉执行。单摄与明确 engineering profile SHALL 标记该双摄 Runtime 为 `not_applicable` 或 optional，且不得伪装为带正式窗口计划的 `match_default` 成功结果。

#### Scenario: 低证据阻止正式分析
- **WHEN** 双摄输入覆盖或同步质量低于模型 package 的正式证据门槛
- **THEN** Run SHALL 结束为 `low_evidence` 或等价稳定状态
- **AND** Parent SHALL 以用户可解释的切分阶段失败结束
- **AND** late-fusion source child SHALL 不得被释放执行

#### Scenario: 取消 prerequisite
- **WHEN** 用户取消仍在运行的正式切分 prerequisite
- **THEN** prerequisite job SHALL 协作式停止并记录 canceled
- **AND** Parent SHALL 进入 canceled
- **AND** 不得发布部分窗口计划或部分自动 Segment

### Requirement: V1 连续视觉执行与回合计划消费

V1 双摄视觉分析 SHALL 保持连续媒体解码和身份状态维护。`AnalysisWindowPlan` SHALL 优先用于有效时间、ball/shot 事件的 rally 关联、回合级统计、可视化和报告；本能力 MUST NOT 将每个 Rally 变为独立 AnalysisJob 或要求 tracker 在大量非连续窗口间 seek。

#### Scenario: 计划用于有效时间
- **WHEN** 已绑定窗口计划的 Parent 计算指标或渲染回合级结果
- **THEN** 它 SHALL 使用该计划的半开 Rally 范围
- **AND** SHALL 不因之后的人工事件或自动 Run 重跑而改变范围

#### Scenario: 连续身份保持
- **WHEN** 同一 Parent 在两个 Rally 之间经过 non-play 视频
- **THEN** V1 执行 SHALL 保持连续解码/身份状态语义
- **AND** MUST NOT 为了跳过 non-play 而将后一个 Rally 作为无上下文的新 Job 处理

