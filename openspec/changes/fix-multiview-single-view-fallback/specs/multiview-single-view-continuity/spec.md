## ADDED Requirements

### Requirement: 单视图 binding 玩家的融合连续性

roster 内仅有单视图 binding（如仅 cam_1、cam_2 缺失/过期）且该视图持续可观测的 global player，SHALL 在融合与展示层保持连续：每 canonical tick 该玩家存在单视图真实观测时，系统 SHALL 为其产出 `fusion_status=single_view_fallback` 的 fused measurement（而非不出 sample），使 fused trajectory 覆盖该玩家全时段；fused overlay SHALL 以 reference view 单边 strong observation 渲染该玩家。**跨视图 binding 缺失 SHALL NOT 导致单视图活跃玩家从融合/展示中消失。**

#### Scenario: 仅 cam_1 观测的 P2 持续出 sample

- **WHEN** roster 内 global_player_4（P2）仅 cam_1 binding 且 cam_1 在连续 canonical ticks 持续观测（conf≥0.5）
- **THEN** 每个观测 tick 系统 SHALL 为 P2 产出 `fusion_status=single_view_fallback` 的 fused measurement
- **AND** fused trajectory SHALL 包含 P2 的连续样本（而非仅 global_player_1/2/3）

#### Scenario: 单视图观测中断不永久丢失

- **WHEN** P2 在 cam_1 短暂漏检（如 0.4s 断帧）后恢复观测
- **THEN** 恢复后的观测 tick 系统 SHALL 重新为 P2 产出 `single_view_fallback` measurement
- **AND** fused overlay SHALL 重新渲染 P2（`base_observed`/`REAL_BOX`），SHALL NOT 因断帧历史永久隐藏该玩家

#### Scenario: 全视图离场仍按既有 stale 语义

- **WHEN** 某 roster 玩家所有 view binding 均过期（离场/遮挡超阈值）
- **THEN** 该玩家 SHALL 按既有 stale 语义退出普通匹配，等待 recovery
- **AND** 单视图豁免 SHALL NOT 阻止其进入 stale（豁免仅适用于至少一个视图持续新鲜观测的玩家）

### Requirement: stale 门控的单视图活跃豁免

`update_stale_eligibility` 判定 stale 时 SHALL 区分"单视图持续活跃"与"跨视图缺失"：若玩家存在任一 view binding 且 `last_seen_s` 新鲜（`now_s - last_seen_s <= stale_last_seen_s`），则该玩家 SHALL 保持 `association_eligible=True`，即使其他 view binding 缺失/过期。豁免前提是该视图 binding 处于 `observed`/`weak` 且 `last_seen_s` 未超 `stale_last_seen_s`。

#### Scenario: 单视图活跃玩家不 stale

- **WHEN** global_player_4 仅 cam_1 binding 为 `observed` 且 last_seen 距当前 < `stale_last_seen_s`
- **THEN** `association_eligible` SHALL 为 True
- **AND** `predict_all()` SHALL 返回该玩家的预测（供 min_cost_matching 分配观测）

#### Scenario: 离场即失去豁免

- **WHEN** 玩家所有 view binding 均过期（last_seen 距当前 > `stale_last_seen_s`）
- **THEN** `association_eligible` SHALL 为 False（恢复既有 stale 语义）
- **AND** 该玩家 SHALL 仅经 historical continuity / guided recovery / strong reacquire 回归

### Requirement: 单视图 sample 的指标资格与质量标注

`single_view_fallback` measurement 为真实观测（非 predicted），默认 `metric_eligible=True` 可进指标；系统 SHALL 保留按配置门控 `metric_eligible` 的能力（如 `single_view_metric_eligible` 开关 / `single_view_min_quality` 阈值）。单视图样本的融合置信度 SHALL 基于该视图 intrinsic quality，`fusion_status=single_view_fallback` SHALL 显式标注单视图来源，MUST NOT 伪装为 `dual_observed`。

#### Scenario: 单视图样本默认可进指标

- **WHEN** P2 单视图观测产出 `single_view_fallback` measurement
- **THEN** 默认 `metric_eligible=True`
- **AND** 速度/覆盖/停留等指标 SHALL 覆盖 P2 的观测时段

#### Scenario: 配置门控可关闭

- **WHEN** 配置 `single_view_metric_eligible=False` 或观测 quality 低于 `single_view_min_quality`
- **THEN** 该 sample SHALL `metric_eligible=False` 且不进入指标计算
- **AND** fused trajectory SHALL 仍包含该 sample（仅指标资格受限）

### Requirement: fused_diagnostics 单视图路径可观测

`fused_diagnostics` SHALL 使 `single_view_fallback` 计数真实反映单视图路径使用量，且 SHALL 支持按 `global_player_id` 归因（如 `single_view_fallback_by_player` 计数或等价观测字段），以便诊断"某玩家全程单视图"与"偶发单视图"的区别。

#### Scenario: 单视图计数可归因

- **WHEN** P2 全程单视图观测而其他玩家双视图
- **THEN** diagnostics 中 `single_view_fallback` 计数 SHALL 主要归因于 P2
- **AND** 归因信息 SHALL 足以区分"结构性单视图玩家"与"偶发单视图帧"
