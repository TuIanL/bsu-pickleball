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

### Requirement: PrimaryPlayerSelector 降级为建议器

`PrimaryPlayerSelector.select()` SHALL 保持不变，继续作为候选排序器运行，但下游 SHALL 不再将其输出作为硬门控。调用方 SHALL 将其输出视为建议集合而非授权集合。

#### Scenario: select() 仍然返回 top 4 建议

- **WHEN** `PrimaryPlayerSelector.select()` 被调用
- **THEN** 返回结果 SHALL 为 `list[PrimaryPlayerSelection]`，长度为 0 到 4
- **AND** 结果按 `(score, rolling_confidence, confidence)` 降序排列

#### Scenario: select() 不负责身份持久性

- **WHEN** 已锁定球员 `Player_3` 的当前 track 本帧未进入 top 4
- **THEN** `select()` SHALL 不将 `Player_3` 的 track 包含在结果中
- **AND** 这 SHALL 不导致 `Player_3` 身份被释放（由 `PlayerLockManager` 负责）

### Requirement: Bootstrap 阶段（动态窗口）

后端 SHALL 使用具有最短帧数和最长帧数的动态 bootstrap 窗口，任意候选满足条件时可以提前锁定，不必等窗口完全结束。

#### Scenario: bootstrap 阶段收集候选（最短窗口内）

- **WHEN** `frame_index < bootstrap_min_frames`（默认 60）
- **THEN** 系统 SHALL 收集所有在 near_court_area 内的 tracklet 统计信息
- **AND** SHALL NOT 立即分配 player_1~player_4

#### Scenario: 候选满足条件即提前锁定，不等窗口结束

- **WHEN** `frame_index >= bootstrap_min_frames` 且未达 `bootstrap_max_frames`
- **AND** 某候选连续 `lock_min_hits` 帧在 near_court_area 内且置信度 ≥ `bootstrap_min_conf`
- **THEN** 该候选 SHALL 立即锁定（transition to LOCKED）
- **AND** 未锁定 slot SHALL 继续 SEARCHING 直到 `bootstrap_max_frames`

#### Scenario: bootstrap 最大窗口后强制选出主球员

- **WHEN** `frame_index == bootstrap_max_frames`（默认 180）
- **THEN** 系统 SHALL 从所有收集的候选 tracklet 中选出最多 `target_player_count` 个
- **AND** 未满额空 slot SHALL 保持 SEARCHING
- **AND** 后续帧中出现新候选时 SHALL 尝试填入空位

#### Scenario: bootstrap 不足 target_player_count 人

- **WHEN** bootstrap 结束后收集到 2 个符合资格的候选（target=4）
- **THEN** 系统 SHALL 将 2 个候选分配为 Player_1、Player_2 并设为 LOCKED
- **AND** Player_3、Player_4 SHALL 保持 SEARCHING
- **AND** 后续帧中出现新候选时 SHALL 尝试填入空位

#### Scenario: bootstrap 期间 candidate 必须靠近球场

- **WHEN** bootstrap 期间候选投影坐标不在 near_court_area 内
- **THEN** 候选 SHALL NOT 被纳入 bootstrap 统计

#### Scenario: side_hint 仅作提示不绑死身份

- **WHEN** bootstrap 结束分配 identity_id
- **THEN** `side_hint` SHALL 基于预期球场位置设置（near_left / near_right / far_left / far_right）
- **AND** 后续球员换位/走位时 `identity_id` SHALL 保持不变，`side_hint` SHALL 允许更新
