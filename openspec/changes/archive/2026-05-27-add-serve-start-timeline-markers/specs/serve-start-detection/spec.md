## ADDED Requirements

### Requirement: 发球开始候选事件 artifact

系统 SHALL 为完成的真实上传视频分析任务生成或明确标记发球开始候选事件 artifact，用于定位每个回合的开始候选时间点。

#### Scenario: 发球事件可用
- **WHEN** 真实视频分析任务完成且检测器从可用 tracking、pose 或其他支持信号中识别出发球开始候选
- **THEN** 系统 SHALL 写入发球事件 artifact，包含 job/video 标识、状态、检测器版本、源视频时长信息和事件列表

#### Scenario: 每个事件包含可复盘时间信息
- **WHEN** 发球事件 artifact 包含候选事件
- **THEN** 每个事件 SHALL 包含稳定 id、`timestamp_seconds`、`frame_index`、`confidence`、`seek_time_seconds`、`reason` 和来源信号摘要

#### Scenario: 点击跳转时间早于 anchor
- **WHEN** 系统为发球候选事件计算 `seek_time_seconds`
- **THEN** `seek_time_seconds` SHALL 小于或等于 `timestamp_seconds` 且不得小于 0，以便播放器可跳到发球前准备时刻

### Requirement: 发球事件可用状态

系统 SHALL 区分发球事件 artifact 的 `available`、`no_candidates`、`partial` 和 `unavailable` 状态，而不是把缺失候选伪装成成功结果。

#### Scenario: 没有识别出候选点
- **WHEN** 检测器运行完成但没有达到阈值的发球候选事件
- **THEN** 系统 SHALL 输出 `no_candidates` 状态和解释原因，而不是生成空白的成功结论

#### Scenario: 输入信号不足
- **WHEN** 任务缺少可用 tracking、pose、视频帧时间或其他最低检测输入
- **THEN** 系统 SHALL 将发球事件状态标记为 `unavailable` 并说明缺失前置条件

#### Scenario: 部分信号可用
- **WHEN** 检测器只能使用低信息量输入生成候选点
- **THEN** 系统 SHALL 允许输出 `partial` 状态，并保留每个事件的置信度和依据说明

### Requirement: 发球检测阶段记录

系统 SHALL 在 pipeline 阶段记录中暴露发球开始检测的执行状态和摘要，使任务进度、失败诊断和复现实验可追踪。

#### Scenario: 检测阶段完成
- **WHEN** 发球开始检测运行结束
- **THEN** pipeline 阶段 SHALL 记录阶段 id、状态、候选数量、可用输入类型和公开说明

#### Scenario: 检测阶段失败
- **WHEN** 发球开始检测发生可恢复或不可恢复错误
- **THEN** 系统 SHALL 标记发球检测阶段失败或 unavailable，同时保持基础分析结果、视频播放、tracking overlay 和 pose overlay 可用

### Requirement: 发球事件 artifact API

系统 SHALL 通过分析任务 artifact API 暴露发球事件 artifact，并在 pipeline result 中提供可选引用。

#### Scenario: 结果引用发球事件 artifact
- **WHEN** 完成的真实分析任务生成或记录发球事件 artifact
- **THEN** pipeline result 的 artifacts SHALL 包含发球事件 URL、状态和说明字段

#### Scenario: 客户端读取发球事件 artifact
- **WHEN** 客户端请求完成任务的发球事件 artifact URL
- **THEN** API SHALL 返回浏览器可消费的 JSON artifact

#### Scenario: artifact 不存在
- **WHEN** 客户端请求不存在的发球事件 artifact
- **THEN** API SHALL 返回明确的 404 或等效错误，而不是返回模拟事件数据

### Requirement: 发球检测不产生完整回合结论

系统 SHALL 将本能力限定为发球开始候选点检测，不得在没有后续能力支持时输出完整回合边界、回合结束、比分或战术结论。

#### Scenario: 当前任务只有发球候选点
- **WHEN** 发球事件 artifact 可用但没有回合结束检测能力
- **THEN** 系统 SHALL 仅声明发球开始候选点，不得生成完整 rally segmentation 或比赛净时长统计

#### Scenario: 报告需要战术语义
- **WHEN** 报告或 UI 表面需要击球类型、得分原因、落点或战术判断
- **THEN** 系统 SHALL 继续使用 unavailable 或候选说明，而不是从发球开始事件推断战术结论
