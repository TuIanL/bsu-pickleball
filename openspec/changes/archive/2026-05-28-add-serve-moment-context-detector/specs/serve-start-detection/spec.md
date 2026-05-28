## MODIFIED Requirements

### Requirement: 发球开始候选事件 artifact

系统 SHALL 为完成的真实上传视频分析任务生成或明确标记发球时刻候选事件 artifact，用于定位每个回合的发球击球时刻或其附近候选时间点。

#### Scenario: 发球事件可用
- **WHEN** 真实视频分析任务完成且检测器从可用 tracking、player trajectory、pose、视频帧或其他支持信号中识别出发球时刻候选
- **THEN** 系统 SHALL 写入发球事件 artifact，包含 job/video 标识、状态、检测器版本、源视频时长信息、检测模式、事件列表和可用信号摘要

#### Scenario: 每个事件包含可复盘时间信息
- **WHEN** 发球事件 artifact 包含候选事件
- **THEN** 每个事件 SHALL 包含稳定 id、`timestamp_seconds`、`frame_index`、`confidence`、`seek_time_seconds`、`reason`、来源信号摘要，并在可用时包含候选片段的 `start_time_seconds` 和 `end_time_seconds`

#### Scenario: 点击跳转时间早于 anchor
- **WHEN** 系统为发球候选事件计算 `seek_time_seconds`
- **THEN** `seek_time_seconds` SHALL 小于或等于 `timestamp_seconds` 且不得小于 0，以便播放器可跳到发球前准备时刻

#### Scenario: 事件包含信号分解
- **WHEN** 检测器输出发球时刻候选事件
- **THEN** 每个候选 SHALL 在可用时包含底线站位、发球前静止、手臂或 ROI 运动峰值、发球后回合激活等 signal scores，使误报和漏报可复盘

### Requirement: 发球事件可用状态

系统 SHALL 区分发球事件 artifact 的 `available`、`no_candidates`、`partial` 和 `unavailable` 状态，而不是把缺失候选或降级候选伪装成完整成功结果。

#### Scenario: 没有识别出候选点
- **WHEN** 检测器运行完成但没有达到阈值的发球候选事件
- **THEN** 系统 SHALL 输出 `no_candidates` 状态和解释原因，而不是生成空白的成功结论

#### Scenario: 输入信号不足
- **WHEN** 任务缺少可用 tracking、player trajectory、视频帧时间或其他最低检测输入
- **THEN** 系统 SHALL 将发球事件状态标记为 `unavailable` 并说明缺失前置条件

#### Scenario: 部分信号可用
- **WHEN** 检测器只能使用低信息量输入生成候选点，例如缺少 pose 但可使用 tracking、trajectory 或 ROI 差分
- **THEN** 系统 SHALL 允许输出 `partial` 状态，并保留每个事件的置信度、检测模式、降级原因和依据说明

### Requirement: 发球检测阶段记录

系统 SHALL 在 pipeline 阶段记录中暴露上下文发球时刻检测的执行状态和摘要，使任务进度、失败诊断和复现实验可追踪。

#### Scenario: 检测阶段完成
- **WHEN** 发球时刻候选检测运行结束
- **THEN** pipeline 阶段 SHALL 记录阶段 id、状态、候选数量、可用输入类型、检测模式、公开说明和关键 counters

#### Scenario: 检测阶段失败
- **WHEN** 发球时刻候选检测发生可恢复或不可恢复错误
- **THEN** 系统 SHALL 标记发球检测阶段失败或 unavailable，同时保持基础分析结果、视频播放、tracking overlay 和 pose overlay 可用

#### Scenario: 阶段记录包含调试引用
- **WHEN** 发球检测生成 score、候选调试 JSON、候选 clips 或 debug overlay artifact
- **THEN** pipeline 阶段或 pipeline result artifacts SHALL 暴露这些 artifact 的状态或 URL 引用，并不得要求前端先加载调试 artifact 才能播放视频

## ADDED Requirements

### Requirement: 上下文发球时刻检测

系统 SHALL 将发球候选识别为比赛状态上下文事件，优先检测“底线附近发球准备状态 → 局部击球运动峰值 → 后续进入回合”的时间点，而不是仅依赖球员整体位移突增。

#### Scenario: 通过上下文门槛产生候选
- **WHEN** 候选球员位于底线附近、候选前存在低速准备窗口，且候选与前一候选满足最小时间间隔
- **THEN** 检测器 SHALL 允许该时间段进入发球时刻候选评分

#### Scenario: 缺少发球前上下文
- **WHEN** 某个手臂运动峰值或整体移动峰值发生在连续回合运动中，且候选前没有低速准备窗口
- **THEN** 检测器 SHALL 降低或拒绝该候选，避免把普通正手击球当作发球

#### Scenario: 姿态峰值定位击球时刻
- **WHEN** pose keypoints 可用且手腕或肘部关键点置信度满足检测要求
- **THEN** 检测器 SHALL 使用平滑后的手腕/肘部速度峰值辅助定位 `timestamp_seconds`

#### Scenario: 无 pose 时退化到 ROI 运动
- **WHEN** pose keypoints 不可用或关键点置信度不足但视频帧、bbox 或 tracking 可用
- **THEN** 检测器 SHALL 可退化为目标球员 ROI 帧间差分或 bbox 局部运动峰值，并在 artifact 中记录降级检测模式

#### Scenario: 发球后进入回合验证
- **WHEN** 候选时刻后配置窗口内至少两名主要球员或双方阵营出现持续运动和 tracking 连续性
- **THEN** 检测器 SHALL 提高候选的后续回合激活信号分数

### Requirement: 场地单位安全

系统 SHALL 根据 player trajectory 或 court metadata 的 `court_unit` 解释球场坐标，并在使用底线、场地长宽或速度阈值时进行必要的米/英尺换算。

#### Scenario: 米制轨迹使用米制阈值
- **WHEN** player trajectory artifact 声明 `court_unit` 为 `m`
- **THEN** 检测器 SHALL 将标准场地长宽和 `baseline_margin_ft` 等设计参数换算为米后再判断底线附近

#### Scenario: 英尺轨迹使用英尺阈值
- **WHEN** player trajectory artifact 声明 `court_unit` 为 `ft`、`feet` 或兼容旧式英尺坐标
- **THEN** 检测器 SHALL 使用标准 20ft × 44ft 场地语义判断底线附近

#### Scenario: 单位缺失时保守降级
- **WHEN** 检测输入缺少 court unit metadata 且无法可靠推断单位
- **THEN** 检测器 SHALL 标记发球检测为 `partial` 或 `unavailable`，并在 detail 中说明无法安全应用底线阈值
