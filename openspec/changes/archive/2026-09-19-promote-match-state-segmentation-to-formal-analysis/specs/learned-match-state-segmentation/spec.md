## MODIFIED Requirements

### Requirement: 候选时间线安全发布

研究/QA 模式下，模型 SHALL 将预测保存为独立候选 artifact，包含状态概率、平滑参数、候选起止时间、置信度、输入 provenance 和人工复核状态；候选 artifact 不得自动成为正式双摄分析的窗口计划，也不得覆盖人工权威事件或正式比分。系统 MUST 将候选复核决定绑定到 take_id、artifact_version 和 candidate_id，其中 artifact_version 为经校验的原始文件 bytes 的 SHA-256，并保存不可变快照。人工接受或修正候选时，仍 SHALL 通过人工来源的正式片段与审计记录表达该人工决定；生产 `SegmentationRun` 的 algorithm/inferred 片段由独立正式发布契约管理。

#### Scenario: 生成候选回合
- **WHEN** QA 推理的连续窗口满足最短持续时间和置信度门槛
- **THEN** 系统 SHALL 生成带模型版本和边界证据的候选 rally 区间，并标记为 `unreviewed`
- **AND** 该候选 SHALL 不被普通 Segment 页面或正式分析 Job 自动采用

#### Scenario: 人工确认候选
- **WHEN** QA 用户复核并接受或修正候选区间
- **THEN** 系统 SHALL 在同一数据库事务中保存人工决定、修订 provenance、编辑操作与人工来源正式片段修改
- **AND** 该片段 SHALL 保持可与正式 algorithm Segment 并存的人工语义

#### Scenario: 新版本复用候选 ID
- **WHEN** 同一 take 生成不同 artifact_version 且复用 candidate_id
- **THEN** 新版本候选 SHALL 为 unreviewed，不继承旧版本决定
- **AND** 旧正式片段与复核证据 SHALL 保留，不自动删除或重新生成

#### Scenario: 正式运行与候选隔离
- **WHEN** 双摄 `match_default` 运行正式回合切分
- **THEN** 系统 SHALL 创建 SegmentationRun 和正式 artifact，而不是读写 candidate review sidecar
- **AND** candidate 的 accept/correct/reject 状态 SHALL 不改变该 Parent 的窗口计划

### Requirement: 模型包可复现和可降级

模型发布 package SHALL 包含权重、标签映射、采样配置、clip 配置、特征 schema、归一化参数、阈值、训练数据版本和评估报告。QA 候选 Runtime 缺少模型或输入时 SHALL 保持现有人工/规则流程可用；正式双摄 `match_default` Runtime 缺少模型或输入时 SHALL 以可解释的 prerequisite 失败结束，不得将无切分计划的整场分析伪装为同等结果。工程或单摄 profile 必须明确报告 optional/not_applicable 状态。

#### Scenario: 加载完整模型包
- **WHEN** 模型包版本、特征 schema 和输入数据版本匹配
- **THEN** 推理器 SHALL 加载模型并在输出中记录完整版本 provenance

#### Scenario: QA 模型包不可用
- **WHEN** 权重缺失、schema 不匹配或运行依赖不可用，且请求为候选/QA 推理
- **THEN** 系统 SHALL 标记 learned-state candidate 为 unavailable
- **AND** 现有人工/规则分析流程 SHALL 保持可用

#### Scenario: 正式双摄模型包不可用
- **WHEN** 权重缺失、schema 不匹配或运行依赖不可用，且请求为 `match_default` 双摄分析
- **THEN** 系统 SHALL 标记正式切分 prerequisite 为 `model_unavailable`
- **AND** Parent SHALL 不得继续执行为未绑定窗口计划的正式分析
