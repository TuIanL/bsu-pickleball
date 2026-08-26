## ADDED Requirements

### Requirement: 证据切换下展示几何连续

展示层 SHALL 为每个 `(job_id, reference_view_id, canonical_player_id)` 维护 presentation geometry continuity。`base_observed`、`guided_observed` 与 `cross_view_projected` 在相邻 tick 间切换时，bbox 中心、脚点、宽高 SHALL 经过基于真实时间差的连续性门控，不得出现由证据切换直接造成的全尺寸跳变或闪烁。该连续性 SHALL 不修改 `evidence_type` 的 provenance 语义。

#### Scenario: base 与 projected 快速交替
- **WHEN** 同一球员的 evidence 序列在相邻 tick 中出现 `base_observed → cross_view_projected → base_observed`
- **THEN** renderer SHALL 复用或连续 reanchor 最近合格 presentation geometry
- **AND** SHALL 不得让实线框和投影框在相邻 tick 之间发生不可解释的中心/尺寸跳变
- **AND** 每个 tick 的 evidence_type 仍 SHALL 如实输出

#### Scenario: 合法快速移动不被无限平滑
- **WHEN** 新的真实 bbox 与上一份 geometry 的位移满足真实时间差对应的运动门限
- **THEN** renderer SHALL 允许该 geometry 向新 bbox 更新
- **AND** SHALL 不得为了消除闪烁而永久锁定旧位置

#### Scenario: 几何跳变无法解释
- **WHEN** 新 bbox 或 projected bbox 超过速度、尺寸或脚点连续性门限
- **THEN** renderer SHALL 不得直接显示该跳变 geometry
- **AND** SHALL 依次使用合格的 hold、projected point 或 hidden 降级
- **AND** SHALL 输出可查询的 geometry continuity rejection reason

#### Scenario: 新任务清空展示状态
- **WHEN** job、roster 或 reference view 发生 reset
- **THEN** presentation geometry、hold timer 和 continuity counter SHALL 全部清空
- **AND** 不得复用上一场比赛的 P2/P4 几何状态
