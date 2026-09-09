## ADDED Requirements

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

模型 SHALL 将预测保存为独立候选 artifact，包含状态概率、平滑参数、候选起止时间、置信度、输入 provenance 和人工复核状态；不得直接覆盖人工权威事件或正式比分。

#### Scenario: 生成候选回合

- **WHEN** 连续窗口满足最短持续时间和置信度门槛
- **THEN** 系统 SHALL 生成带模型版本和边界证据的候选 rally 区间，并标记为 `unreviewed`

#### Scenario: 人工确认后发布

- **WHEN** 用户复核并接受或修正候选区间
- **THEN** 系统 SHALL 保存人工决定和修订 provenance，只有确认结果才能进入正式时间线或下一版训练集

### Requirement: 模型包可复现和可降级

模型发布包 SHALL 包含权重、标签映射、采样配置、clip 配置、特征 schema、归一化参数、阈值、训练数据版本和评估报告；缺少模型或输入不满足条件时 SHALL 保持现有分析流程可用。

#### Scenario: 加载完整模型包

- **WHEN** 模型包版本、特征 schema 和输入数据版本匹配
- **THEN** 推理器 SHALL 加载模型并在输出中记录完整版本 provenance

#### Scenario: 模型包不可用

- **WHEN** 权重缺失、schema 不匹配或运行依赖不可用
- **THEN** 系统 SHALL 标记 learned-state stage 为 unavailable，并继续提供现有人工/规则分析结果
