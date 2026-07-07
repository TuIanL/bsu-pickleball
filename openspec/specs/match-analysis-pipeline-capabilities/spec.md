# match-analysis-pipeline-capabilities Specification

## Purpose
TBD - created by archiving change activate-match-analysis-pipeline-capabilities. Update Purpose after archive.
## Requirements
### Requirement: 可配置激活比赛分析能力
系统 SHALL 通过配置和依赖检查激活新增比赛分析能力，而不是把历史 MVP 边界作为永久禁用规则。

#### Scenario: 默认环境保持现有流程
- **WHEN** 后端在没有新增球分析启用配置的环境中运行真实分析任务
- **THEN** 系统 SHALL 保持现有 player、pose、tracking、serve 和 movement 输出兼容
- **AND** 系统 MUST NOT 要求球模型文件或 CUDA 环境存在

#### Scenario: 配置启用新增能力
- **WHEN** 管理员启用球检测、弹跳检测或可视化输出配置且依赖满足
- **THEN** pipeline SHALL 执行对应分析阶段并在结果中暴露阶段状态、artifact 引用和诊断摘要

#### Scenario: 配置启用但依赖缺失
- **WHEN** 新增能力被启用但模型路径、adapter、输入 artifact 或运行时依赖不可用
- **THEN** pipeline SHALL 将对应阶段标记为 `skipped`、`unavailable` 或 `failed`
- **AND** 基础 player、pose、tracking、serve 和 movement 结果 MUST 继续可用

### Requirement: 事实 artifact 优先于语义结论
系统 SHALL 优先输出可复盘的检测、轨迹、弹跳候选和可视化 artifact，并把完整比赛语义留给后续能力。

#### Scenario: 事实 artifact 可用
- **WHEN** 真实分析任务生成球检测、球轨迹、清洗轨迹或弹跳候选 artifact
- **THEN** 系统 SHALL 允许前端和报告展示这些 artifact 支撑的事实、候选点和状态
- **AND** 展示内容 MUST 引用真实任务 artifact 而不是模拟数据

#### Scenario: 需要完整比赛语义
- **WHEN** UI、报告或 API 需要击球类型、完整回合边界、比分、犯规、落点统计或战术结论
- **THEN** 系统 SHALL 在专门能力实现前标记为 unavailable 或省略
- **AND** 系统 MUST NOT 从球轨迹或弹跳候选直接伪造这些结论

### Requirement: 能力状态可复盘
系统 SHALL 为新增分析能力提供可复盘的状态、原因和 counters，使用户和开发者能区分配置关闭、依赖缺失、无检测、部分可用和已完成。

#### Scenario: 阶段被配置关闭
- **WHEN** 新增分析阶段因配置未启用而不运行
- **THEN** pipeline 阶段记录或结果摘要 SHALL 表达 `skipped` 状态和配置原因

#### Scenario: 阶段运行但没有候选
- **WHEN** 新增分析阶段成功运行但没有达到阈值的候选或事件
- **THEN** 对应 artifact 或阶段记录 SHALL 表达 `no_candidates` 或等价状态
- **AND** SHALL 提供输入覆盖、阈值或候选数量摘要

#### Scenario: 阶段部分可用
- **WHEN** 新增分析阶段只能使用部分输入生成结果
- **THEN** 对应状态 SHALL 表达 `partial`
- **AND** SHALL 说明缺失输入和仍然使用的信号

