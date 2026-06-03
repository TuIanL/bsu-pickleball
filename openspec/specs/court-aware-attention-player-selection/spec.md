# court-aware-attention-player-selection Specification

## Purpose
TBD - created by archiving change add-court-aware-attention-player-selection. Update Purpose after archive.
## Requirements
### Requirement: 目标球场感知候选评分
后端 SHALL 基于目标场标定结果为每个候选 player tracklet 计算目标球场归属分，并将该分数用于主球员锁定。

#### Scenario: 候选长期位于目标场范围
- **WHEN** 一个候选 tracklet 在时间窗口内的大多数有效脚点投影位于目标球场容差范围内
- **THEN** 系统将其目标球场归属分评为高，并保留其参与四人组选择

#### Scenario: 候选长期位于隔壁场方向
- **WHEN** 一个候选 tracklet 持续运动但其脚点相对目标场 homography 的投影长期位于目标场容差范围外
- **THEN** 系统降低其目标球场归属分，并在诊断中记录其可能为非目标场人员

#### Scenario: 候选短暂越界
- **WHEN** 一个高质量目标场候选在正常跑动或脚点估计抖动时短暂越出标准场地线
- **THEN** 系统不得仅因短暂越界排除该候选，而应结合窗口内目标场占用比例和轨迹连续性评分

### Requirement: 窗口级四人组锁定
后端 SHALL 在一段时间窗口内从候选 tracklet 中选择最符合目标场双打关系的最多四名主球员，而不是仅按单帧检测结果独立选择。

#### Scenario: 同时存在目标场和隔壁场球员
- **WHEN** 目标场四名球员和隔壁场多名球员都被检测并持续运动
- **THEN** 系统优先选择目标场四名候选作为 overlay 和 player trajectory 的 eligible tracks

#### Scenario: 候选人数超过四人
- **WHEN** 一个窗口内存在超过四个高置信度 person tracklet
- **THEN** 系统使用目标球场归属分、tracklet 质量和四人组一致性分选择最多四名主球员

#### Scenario: 四人暂时不完整
- **WHEN** 遮挡或漏检导致窗口内少于四个目标场候选达到阈值
- **THEN** 系统保留可确认的目标场候选，并不得用低分隔壁场候选补满四人

### Requirement: 可选 self-attention selector
后端 SHALL 定义可选 self-attention player selector 的输入、输出、模型加载和 fallback 行为；该 selector MUST 显式消费目标球场几何特征。

#### Scenario: Attention 模型权重可用
- **WHEN** 配置启用 attention selector 且模型权重与运行依赖可用
- **THEN** 系统使用候选 tracklet 时间序列特征运行模型，并输出每个候选的目标场球员概率、非目标人员概率和选择置信度

#### Scenario: Attention 模型不可用
- **WHEN** 模型权重缺失、依赖不可用或推理失败
- **THEN** 系统回退到规则增强 selector，并在诊断中记录 fallback reason

#### Scenario: Attention 置信度过低
- **WHEN** attention selector 对四人选择结果的整体置信度低于配置阈值
- **THEN** 系统回退或混合使用规则增强 selector，并记录 attention 分数与最终选择来源

### Requirement: 训练样本导出
后端 SHALL 能导出用于训练 self-attention selector 的候选 tracklet 样本，包含目标场几何特征、时序运动特征和人工标注所需字段。

#### Scenario: 导出候选样本
- **WHEN** 一个真实视频分析完成并生成候选 tracklet 与目标场投影
- **THEN** 系统可以生成训练样本 artifact，包含每个候选的 track id、时间窗口、bbox 序列、court 坐标序列、目标场距离特征、置信度和诊断分数

#### Scenario: 标注 hard negatives
- **WHEN** 人工复核训练样本时发现隔壁场球员、场边人员或不确定候选
- **THEN** 样本格式 MUST 支持标注 `target_player`、`neighbor_court_player`、`spectator` 和 `uncertain`

### Requirement: 选择诊断
后端 SHALL 输出主球员选择诊断，使用户或研发人员可以复盘每个候选为何被保留、排除或由模型回退。

#### Scenario: 候选被保留
- **WHEN** 一个候选被选为目标场主球员
- **THEN** 诊断记录其 track id、目标球场归属分、tracklet 质量分、四人组分、selection mode 和最终原因

#### Scenario: 候选被排除
- **WHEN** 一个候选被排除在目标场四名球员之外
- **THEN** 诊断记录其 track id、主要排除原因和可用分数组成

#### Scenario: 模型路径回退
- **WHEN** selection mode 从 attention 回退到规则增强
- **THEN** 诊断记录 fallback reason，且最终分析任务仍可完成

