## MODIFIED Requirements

### Requirement: 候选时间线安全发布

模型 SHALL 将预测保存为独立候选 artifact，包含状态概率、平滑参数、候选起止时间、置信度、输入 provenance 和人工复核状态；不得直接覆盖人工权威事件或正式比分。系统 MUST 将复核决定绑定到 take_id、artifact_version 和 candidate_id，其中 artifact_version 为经校验的原始文件 bytes 的 SHA-256，并保存不可变快照。

#### Scenario: 生成候选回合
- **WHEN** 连续窗口满足最短持续时间和置信度门槛
- **THEN** 系统 SHALL 生成带模型版本和边界证据的候选 rally 区间，并标记为 `unreviewed`

#### Scenario: 人工确认后发布
- **WHEN** 用户复核并接受或修正候选区间
- **THEN** 系统 SHALL 在同一数据库事务中保存人工决定、修订 provenance、编辑操作与正式片段修改
- **AND** 只有确认结果才能进入正式时间线或下一版训练集，既有边界复核及训练质量门控 SHALL 保持有效

#### Scenario: 新版本复用候选 ID
- **WHEN** 同一 take 生成不同 artifact_version 且复用 candidate_id
- **THEN** 新版本候选 SHALL 为 unreviewed，不继承旧版本决定
- **AND** 旧正式片段与复核证据 SHALL 保留，不自动删除或重新生成

## ADDED Requirements

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
