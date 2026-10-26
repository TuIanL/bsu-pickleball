## ADDED Requirements

### Requirement: 姿态输入的尺度归一

系统 SHALL 在提取动作分类特征前，把每名球员的关键点坐标按其自身人体框高度缩放到训练参考尺度（默认 254 px），使带像素量纲的特征回到训练分布。缩放 SHALL 以窗口内人体框高度的中位数为基准，且缩放因子 SHALL 记录在产物中。

#### Scenario: 正常尺度的球员
- **WHEN** 某球员在窗口内的框高中位数为 216 px
- **THEN** 系统以其坐标乘以约 1.176 后再提取特征，并在产物中记录 `scale_factor = 1.176` 与 `bbox_height_median_px = 216`

#### Scenario: 缩放因子越界
- **WHEN** 计算得到的缩放因子超出配置允许区间（默认 0.5 至 2.5）
- **THEN** 系统 SHALL 不对该窗口输出类别，并把该窗口标记为 `insufficient_evidence` 且记录越界原因

#### Scenario: 姿态帧不足
- **WHEN** 窗口内可用姿态帧比例低于配置阈值
- **THEN** 系统 SHALL 跳过该窗口的特征提取，不产生分类结果

### Requirement: 挥拍窗口与击球人归属

系统 SHALL 从姿态序列中识别挥拍窗口，并为每个窗口给出击球人。挥拍判定 SHALL 使用相对该球员自身速度分布的阈值，不得使用固定像素速度阈值。当多个球员在同一时间邻近范围内都满足挥拍条件时，系统 SHALL 返回并列候选并标记为不确定，不得强制只保留一人。

#### Scenario: 单人挥拍
- **WHEN** 某球员腕速峰值超过其自身速度分布分位阈值，且在该时间邻域内其他球员均未超过各自阈值
- **THEN** 系统输出一个挥拍窗口，`hitter` 为该球员，`ownership_status` 为 `confirmed`

#### Scenario: 双人同时挥拍
- **WHEN** 两名球员在同一时间邻域内都超过各自阈值且候选分差小于配置阈值
- **THEN** 系统输出该窗口的全部候选，`ownership_status` 为 `ambiguous`，且不指定唯一 `hitter`

#### Scenario: 球员尺度过小
- **WHEN** 某球员的框高中位数低于配置的最小可用高度（默认 150 px）
- **THEN** 系统 SHALL 不对该球员输出挥拍窗口，也不对其输出类别

### Requirement: 动作分类与弃判

系统 SHALL 对每个挥拍窗口输出动作类别、置信度与证据充分性。系统 MUST 在证据不足时输出 `unclassified`，不得把低置信度结果强行归入四个已知类别。类别取值 SHALL 限定为 `volley`、`dink`、`drop_shot`、`forehand_drive` 与 `unclassified`。

#### Scenario: 证据充分
- **WHEN** 集成概率的最大值不低于弃判阈值，且折间分歧度低于分歧阈值
- **THEN** 系统输出该最大概率对应的类别，并给出 `confidence` 与 `evidence_sufficiency`

#### Scenario: 置信度不足
- **WHEN** 集成概率的最大值低于弃判阈值
- **THEN** 系统输出类别 `unclassified`，保留最高概率作为 `confidence`，并把 `evidence_sufficiency` 标为不足

#### Scenario: 折间分歧过大
- **WHEN** 三个折模型给出的类别不完全一致且分歧度高于配置阈值
- **THEN** 系统输出 `unclassified`，并在产物中记录各折的类别分布

### Requirement: 分类产物与读取接口

系统 SHALL 为已完成的分析任务提供动作分类的触发与读取接口，并把结果写入该任务的产物目录。产物 MUST 包含推理配置指纹（`model_version`、`scale_reference_px`、`window_policy`、`abstain_threshold`），使任一次输出可追溯。接口 SHALL 在功能门控关闭时拒绝触发。

#### Scenario: 触发后读取
- **WHEN** 客户端对某个已完成的分析任务发起动作分类请求
- **THEN** 系统在产物目录写入 `action_classification.json`，并可通过 GET 接口读取同一份内容

#### Scenario: 重复触发
- **WHEN** 同一任务在相同推理配置下被重复请求
- **THEN** 系统 SHALL 复用已有产物，不重复计算，且返回相同内容

#### Scenario: 门控关闭
- **WHEN** 动作分类功能门控处于关闭状态
- **THEN** 触发接口返回明确的功能未启用错误，不写入任何产物

#### Scenario: 姿态产物缺失
- **WHEN** 目标任务没有可用的 `pose_overlay.json`
- **THEN** 系统返回明确的不可用状态，不生成空产物
