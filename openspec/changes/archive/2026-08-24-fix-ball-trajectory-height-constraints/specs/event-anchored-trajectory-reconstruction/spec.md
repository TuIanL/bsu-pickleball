## MODIFIED Requirements

### Requirement: 事件边界感知的高度模型

系统 SHALL 按段类型设置高度边界，不得统一把两端强制置零，也不得用已知端高度填充未知端。

#### Scenario: hit → bounce 段高度
- **WHEN** 飞行段类型为 `hit → bounce`
- **THEN** `z_start` SHALL 为带来源和不确定度的 `estimated_contact_height`
- **AND** `z_end` 严格为 0

#### Scenario: bounce → hit 段高度
- **WHEN** 飞行段类型为 `bounce → hit`
- **THEN** `z_start` 严格为 0
- **AND** `z_end` SHALL 为带来源和不确定度的 `estimated_contact_height`

#### Scenario: hit → hit 段高度
- **WHEN** 飞行段类型为 `hit → hit`
- **THEN** `z_start > 0` 且 `z_end > 0`
- **AND** 段内 SHALL 存在峰值
- **AND** 两个击球点 SHALL 分别解析各自的接触高度，不得无条件共享同一个常数

#### Scenario: bounce → loss 段高度
- **WHEN** 飞行段类型为 `bounce → loss`
- **THEN** `z_start` 严格为 0，`z_end` SHALL 标记为未知
- **AND** 系统 SHALL 仅显示可信区间，末端渐隐

#### Scenario: 未知起点 → 已知终点
- **WHEN** 段只有终点 `hit` 或 `bounce` 空间锚点
- **THEN** 未知起点 SHALL 使用朝终点收敛的反向开放弧
- **AND** 最后一个有效采样 SHALL 严格对齐终点高度
- **AND** 不得将终点高度复制到整个段

#### Scenario: 已知起点 → 未知终点
- **WHEN** 段只有起点 `hit` 或 `bounce` 空间锚点
- **THEN** 起点 SHALL 严格对齐起点高度
- **AND** 未知终点 SHALL 使用开放弧并逐渐降低高度置信度
- **AND** 不得生成精确落地或精确终点高度

#### Scenario: 未知到未知段高度
- **WHEN** 段两端均为 `unknown` 或 `loss`
- **THEN** 系统 SHALL NOT 伪造完整高度曲线
- **AND** 该段 SHALL 降级为无高度的图像模式或明确的低可信视觉弧

### Requirement: 可配置接触高度先验

系统 SHALL 使用证据优先的逐事件接触高度估计；全局低可信接触高度先验只能作为无更强证据时的兜底，不得按球场区域自动推导。

#### Scenario: 默认先验配置
- **WHEN** 系统无法获得事件时刻的合格双摄或图像/球员垂向证据
- **THEN** 默认使用 `default_contact_height_m = 1.10`，裁剪范围 `0.45–2.40m`
- **AND** `contact_height_uncertainty_m` SHALL 进入质量评分
- **AND** 高度来源 SHALL 标记为 `global_contact_prior`，置信度 SHALL 标记为低

#### Scenario: 合格双摄高度优先
- **WHEN** 击球事件时间窗内存在通过质量门的双摄高度证据
- **THEN** 接触高度 SHALL 使用该事件附近的稳健双摄高度估计
- **AND** 高度来源 SHALL 标记为 `stereo_event_estimate`
- **AND** 结果 SHALL 仍受配置范围和不确定度约束

#### Scenario: 图像或球员上下文高度其次
- **WHEN** 没有合格双摄高度但存在可验证的图像/球员垂向证据
- **THEN** 接触高度 SHALL 使用范围限制后的视觉估计
- **AND** 高度来源 SHALL 标记为 `visual_context_estimate`
- **AND** 结果 SHALL 标记为 visualization-only

#### Scenario: 不按球场区域自动修改
- **WHEN** 球员位于底线或非截击区（NVZ）
- **THEN** 系统 MUST NOT 依据球场区域自动修改接触高度先验

#### Scenario: serve 边界按 hit 类型处理
- **WHEN** 段边界由 serve 事件产生
- **THEN** 高度 SHALL 按 hit 类型处理
- **AND** 来源 SHALL 标记为对应的 `serve_prior` 或更强事件证据来源
