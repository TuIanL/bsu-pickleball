# learned-match-state-segmentation Specification

## Purpose

定义学习式比赛状态分割的研究与 QA 链路：输入方案消融与粗标注鲁棒训练、多模态双摄输入对齐、候选时间线的安全发布与模型包降级，以及候选决定的事务、重试与历史复核绑定。
## Requirements
### Requirement: 视觉输入独立于语义裁决

模型数据管线 SHALL 直接从源视频生成 RGB clip，并将现有 `rally`、`non_play`、比分或语义阶段结果排除为模型特征和绝对真值；这些结果只能作为审计参照或对照实验。

#### Scenario: RGB-only 数据生成

- **WHEN** 用户选择 RGB-only 实验
- **THEN** 数据集 SHALL 只包含源视频帧、时间戳、机位 provenance 和标签质量字段，不读取现有语义预测作为输入

#### Scenario: 使用视觉中间表征

- **WHEN** 用户选择骨架或球路输入
- **THEN** 数据集 SHALL 同时保留关键点/球体坐标、置信度、可见性和缺失 mask，并标记其视觉提取器版本

### Requirement: 多模态和双摄输入对齐

系统 SHALL 基于权威 take 时间和同步资产对齐双摄窗口，并为每个机位和模态记录时间戳、质量和缺失状态；不能对齐的窗口 SHALL 被标记为不可用。

#### Scenario: 双摄窗口成功对齐

- **WHEN** 两个机位存在有效同步映射且窗口覆盖范围足够
- **THEN** 系统 SHALL 生成带 camera slot、同步 revision 和残余偏差诊断的联合样本

#### Scenario: 一个机位短时缺失

- **WHEN** 一个机位在窗口内没有可用帧或视觉特征
- **THEN** 系统 SHALL 保留另一机位样本并写入 view/mode missing mask，模型训练和推理不得静默填充不存在的证据

### Requirement: 比赛状态时序预测

模型 SHALL 对连续时间窗输出版本化状态概率，至少支持 `rally_active`、`pre_serve`、`post_rally`、`timeout_or_side_change` 和 `unknown`，并通过时序解码生成连续状态段。

#### Scenario: 输出状态概率

- **WHEN** 模型收到覆盖有效时间戳的视觉窗口
- **THEN** 系统 SHALL 输出每个状态的概率、最高状态、输入覆盖率和模型版本

#### Scenario: 视觉证据不足

- **WHEN** 输入覆盖率、同步质量或所有视觉分支置信度低于配置门槛
- **THEN** 系统 SHALL 输出 `unknown` 或 `insufficient_evidence`，不得强制输出比赛/非比赛二分类

### Requirement: 粗标注鲁棒训练

训练 SHALL 区分高可信标签、边界不确定标签和排除标签；不确定标签不得以普通硬标签参与边界损失。

#### Scenario: 忽略边界不确定区间

- **WHEN** 时间窗落在人工起止点配置的 uncertain 区间
- **THEN** 训练器 SHALL 将该窗口从硬分类或边界损失中屏蔽，且在统计中单独计数

#### Scenario: 只使用可靠 split

- **WHEN** 数据集审计发现媒体错误、跨集泄漏或 manifest 哈希不一致
- **THEN** 训练器 SHALL 拒绝开始训练并返回具体审计失败原因

### Requirement: 输入方案消融实验

系统 SHALL 在相同数据切分、标签版本和评估配置下比较 RGB-only、骨架/球路和 RGB+骨架+球路至少三种输入方案。

#### Scenario: 生成消融报告

- **WHEN** 三种实验完成或任一实验不可用
- **THEN** 报告 SHALL 列出每种方案的输入覆盖率、状态 F1、比赛状态 precision/recall、边界误差、unknown 比例和失败原因

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

### Requirement: 候选决定事务和重试契约

决定请求 MUST 包含 artifact_version、request_id、expected_revision；决定、revision、片段和编辑操作 MUST 原子提交，JSON SHALL 仅为可重建导出。

#### Scenario: 提交前失败
- **WHEN** 写决定或片段后发生异常或数据库提交失败
- **THEN** 所有业务修改 SHALL 回滚，读取 API SHALL 不显示未提交的 accepted/corrected/rejected

#### Scenario: 重复请求
- **WHEN** 已成功 request_id 以相同内容重试，即使当前候选文件已更新
- **THEN** 系统 SHALL 返回原决定，不重复新建片段、操作或增加 revision
- **AND** 同 request_id 携带不同内容 SHALL 返回 409

#### Scenario: 两个标签页同时复核
- **WHEN** 两个独立连接对同一版本的同一 expected_revision 提交不同 request_id
- **THEN** 至多一个请求 SHALL 成功，另一个 SHALL 返回 409 或明确可重试的锁超时错误，且无部分写入

#### Scenario: 过期候选与重复决定
- **WHEN** 新请求携带过期 artifact_version、过期 revision 或已决定 candidate_id
- **THEN** 系统 SHALL 返回 409，不改变正式片段；前端 SHALL 刷新状态而不自动重提旧草稿

#### Scenario: 导出失败
- **WHEN** 数据库提交成功后 JSON 导出失败
- **THEN** 已提交决定 SHALL 仍可从 API 读取和幂等重试，导出 SHALL 可重新生成

#### Scenario: 拒绝候选
- **WHEN** 用户拒绝合法候选
- **THEN** 系统 SHALL 仅保存决定与审计，不创建正式片段或改写比分

### Requirement: 候选载入和历史复核绑定

系统 MUST 校验候选 schema、take 身份、唯一 candidate_id 和有效数值边界；历史记录只有完整版本和引用验证通过才能绑定，否则 SHALL 保留为 legacy_unbound 审计。

#### Scenario: 损坏或错场次 artifact
- **WHEN** 文件 schema 无效、take_id 不符、候选 ID 重复或边界无效
- **THEN** 读取 SHALL 返回可诊断 unavailable，决定 SHALL 拒绝且不产生副作用，人工流程 SHALL 保持可用

#### Scenario: 无法证明旧复核来源
- **WHEN** 旧 reviews 缺少可验证的完整 artifact 版本或正式片段引用断裂
- **THEN** 迁移 SHALL 保留原文件与 legacy_unbound 审计，不自动确认当前候选或补造片段

#### Scenario: 重复迁移
- **WHEN** 对同一备份重复执行迁移
- **THEN** 系统 SHALL 不重复插入决定或业务片段，冲突 SHALL 留在迁移清单中

