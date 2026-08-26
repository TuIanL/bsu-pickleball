## MODIFIED Requirements

### Requirement: 高度字段语义

系统 SHALL 对重建采样的高度字段声明估值语义，不声称真实三维测量，并 SHALL 声明高度是否满足展示物理约束。

#### Scenario: 高度为视觉估计
- **WHEN** 系统输出 `estimated_height_ft`
- **THEN** 该字段 SHALL 为基于事件边界、可用证据与弧线先验的视觉估计
- **AND** 配合 `height_source`、`height_confidence` 与 `height_uncertainty_ft` 使用
- **AND** 文档 SHALL 标注 `metric_validity = visualization_only`

#### Scenario: 高度有效性可审计
- **WHEN** segment 或 sample 输出高度
- **THEN** SHALL 包含或可推导 `height_validity`，至少区分 `valid`、`invalid_below_ground`、`non_finite` 和 `unknown_open_end`
- **AND** segment SHALL 在高度约束失败时保存 `height_quality_reason`
- **AND** 无效高度 MUST NOT 被用来声明可用 3D 或真实测量指标

### Requirement: 弹地与击球边界高度不变量

系统 SHALL 对事件边界处及整段内部的高度值施加物理不变量约束。

#### Scenario: 弹地点高度为零
- **WHEN** 飞行段以 bounce 事件为端点锚点
- **THEN** 端点采样高度 SHALL 为 0 英尺（硬锚点）
- **AND** 段内其他采样高度 SHALL 不小于 0

#### Scenario: 击球点高度受证据和先验约束
- **WHEN** 飞行段以击球事件为端点锚点
- **THEN** 端点采样高度 SHALL 落在可配置接触高度范围内
- **AND** SHALL 记录实际来源、置信度和不确定度
- **AND** 无更强证据时才允许使用全局先验

#### Scenario: 负高度拟合不得发布
- **WHEN** 任何 3D sample 或密集校验点高度小于 0 或不是有限值
- **THEN** segment SHALL 标记为高度无效
- **AND** MUST NOT 以可用 3D 轨迹发布
- **AND** SHALL 保存降级或拒绝原因

### Requirement: 混合轨迹 provenance 与端点分类

每个 segment 和 sample SHALL 保存来源视角、detected/interpolated/predicted/stereo-anchor provenance、质量、时间范围与端点语义；场外端点 SHALL 保存相对于标准球场和比赛环境的分类；高度 SHALL 保存来源和有效性。

#### Scenario: 保存可能真实界外的 bounce
- **WHEN** bounce 位于边线外但未被判为环境离群点
- **THEN** endpoint SHALL 保存 `court_location = outside_line`、`outcome_classification = legal_out_candidate`、证据置信度和标定不确定度
- **AND** MUST NOT 将 `legal_out_candidate` 解释为自动比赛判罚

#### Scenario: 保存高度降级原因
- **WHEN** segment 因负高度、无高度证据或未知端而降级
- **THEN** artifact SHALL 保存 `height_quality_reason`、`height_source` 或 `unknown_open_end` 语义
- **AND** 前端、报告和诊断消费者 SHALL 能区分无效 3D 与合法的 visualization-only 2.5D
