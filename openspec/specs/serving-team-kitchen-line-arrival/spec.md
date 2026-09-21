# serving-team-kitchen-line-arrival Specification

## Purpose
TBD - created by archiving change add-serving-team-kitchen-line-arrival. Update Purpose after archive.
## Requirements
### Requirement: 发球队厨房线到位率的定义与前置输入
系统 SHALL 为具备 Job-bound `AnalysisRallyContextSnapshot`、confirmed identity audit、formal window binding 与真实轨迹的双打比赛级或正式 Rally 批次级任务计算 `Raw Serving-Rally Arrival`。某球员在其 Team A/B 发球的回合中，当其距该回合己方厨房线的距离不大于 `kitchen-arrival-reference.v1.arrival_band_m`，并稳定不少于 `stable_ms` 时，视为到位；该定义 MUST NOT 等同于进入非截击区。

#### Scenario: 前置分析上下文可用
- **WHEN** Rally 具有同一 Job 的冻结发球队、队伍端位、球员身份 audit 和 formal binding
- **THEN** 系统 SHALL 根据该 context 选择己方厨房线并计算到位
- **AND** SHALL NOT 读取当前 LiveCodingState、可编辑名册或 `initial_side`

#### Scenario: 前置输入缺失
- **WHEN** context、identity audit 或 formal binding 任一项 unavailable
- **THEN** 系统 SHALL 将该指标或样本标记 unavailable/excluded 并记录原因
- **AND** 不得将该回合加入有效分母

### Requirement: 到位与未到位的非对称证据门
系统 SHALL 使用 `arrival_min_detected_support_ms` 的真实 `detected` 轨迹点证明 `arrived`；插值点可辅助连续性但 MUST NOT 单独证明到位。只有真实覆盖率达到 `not_arrived_min_coverage_ratio`、最大连续缺口不超过 `not_arrived_max_gap_ms`，且不存在可从带外跨越到位带的不确定间隙时，系统才可判定 `not_arrived`。

#### Scenario: 真实检测点证明到位
- **WHEN** 球员在回合内的真实检测点和稳定时长满足到位带规则
- **THEN** 系统 SHALL 将样本记为 `arrived`
- **AND** 回合开始已满足规则时 SHALL 记为 `already_present`、`arrival_time_ms=0` 并计入成功

#### Scenario: 关键遮挡不能证明未到位
- **WHEN** 球员没有到位正证据但存在超出最大允许时长的轨迹缺口，或缺口可能跨越到位带
- **THEN** 系统 SHALL 分类为 `excluded=insufficient_track_coverage`
- **AND** 不得计为 `not_arrived` 或有效分母

### Requirement: Kitchen-arrival 汇总产物与指标镜像
系统 SHALL 生成 `kitchen-arrival.v1`，包含 player_id、display_name、team_id、arrived、eligible、already_present、excluded/原因、coverage、context/audit/formal/reference provenance。并 SHALL 向 `metric-snapshot.v1` 镜像 `serving_team_kitchen_line_arrival_rate`。

#### Scenario: 可用汇总
- **WHEN** 任务具有足够有效样本
- **THEN** metric SHALL 保存 `scope=player`、arrived numerator、eligible denominator、相同 sample_count、`status=available` 和 ratio value

#### Scenario: 样本不足或不适用
- **WHEN** 有效分母低于版本化最小样本数
- **THEN** artifact 和 metric SHALL 保留已知计数、使用 `status=insufficient_evidence` 且 `value=null`
- **WHEN** 任务为单打、单 Rally clip 或非比赛级聚合
- **THEN** 系统 SHALL 使用 `not_applicable` 和 null value
- **AND** 任一非 available 状态 MUST NOT 输出 0% 或由计数计算的展示百分比

### Requirement: V1 不混入击球机会或技能评分
V1 SHALL 将所有同时满足正式发球回合、身份、context、端位和轨迹证据门的回合纳入 raw serving-rally 语义，不得根据第三拍、接发质量、回合长度、机会模型或技能评分额外筛选。

#### Scenario: 发球回合很短
- **WHEN** 一个证据充分的发球回合很快结束
- **THEN** 系统 SHALL 仍按 raw serving-rally 规则分类
- **AND** 不得标记为第三拍推进质量、机会调整率或技能评分

