## MODIFIED Requirements

### Requirement: Evidence 分支决策链

每个 `(Player_N, canonical_tick)` 在参考画面上的展示证据 SHALL 按**分支决策链**（而非固定优先级排序）判定：reference view 有 F0 **strong** observation（origin=base/guided_roi）→ `base_observed`/`guided_observed`；否则 `final_source == refined_f1` 且该 view/tick 存在 accepted recovered observation → `refined_observed`；否则 reference view 有 F0 **weak** observation → `base_observed`/`guided_observed`；否则 donor view 有真实 observation 且 final fused sample 非 predicted/conflict 且 geometry 有效 → `cross_view_projected`；否则存在短时 predicted sample 且 TTL 未过 → `predicted_only`；否则不渲染。`refined_observed` SHALL 优先于 weak F0 observation，但 SHALL NOT 覆盖 strong F0 observation。系统 SHALL NOT 为了"始终显示全部球员"而制造无证据的展示框。**分支决策链 SHALL 仅决定 `evidence_type`（真实证据来源，权威不变）；实际展示形态（display_state）SHALL 由跨 tick 迟滞状态机（stabilize-multiview-overlay-display）决定，且 MUST NOT 反写或伪装 `evidence_type`。** **reference view 单边 strong observation SHALL 足以渲染该球员（`base_observed`/`REAL_BOX`），SHALL NOT 因该玩家无 cross-view binding（另一 view binding 缺失/过期）而拒绝渲染；该分支的 fused sample 数据源（final fused trajectory / roster map）SHALL 包含单视图 binding 玩家的 `single_view_fallback` sample 或等价证据供给。**

#### Scenario: 参考机位 strong 检测优先

- **WHEN** reference view 在 canonical tick 有 F0 strong observation（origin=base）
- **THEN** 该帧该球员的 `evidence_type` SHALL 为 `base_observed`
- **AND** `display_state` SHALL 为 `REAL_BOX`（或经迟滞保持的等价状态）

#### Scenario: 单视图 binding 玩家 strong 观测渲染

- **WHEN** reference view 有 F0 strong observation 且该玩家无 cross-view binding（如仅 cam_1 观测、cam_2 缺失）
- **THEN** `evidence_type` SHALL 为 `base_observed`
- **AND** `display_state` SHALL 为 `REAL_BOX`
- **AND** SHALL NOT 因跨视图 binding 缺失而降级为 `HIDDEN` 或依赖 donor 投影

#### Scenario: 单视图玩家断帧后恢复渲染

- **WHEN** 单视图 binding 玩家在 reference view 短暂漏检（≤ 数帧）后恢复 strong observation
- **THEN** 恢复帧 SHALL 重新渲染该球员（`base_observed`/`REAL_BOX`）
- **AND** SHALL NOT 因先前断帧使该球员永久隐藏

#### Scenario: 跨摄 guidance 重检测成功

- **WHEN** reference view 在 canonical tick 有 F0 strong observation（origin=guided_roi，guidance ROI 重检测成功）
- **THEN** `evidence_type` SHALL 为 `guided_observed`
- **AND** `display_state` SHALL 为 `ASSISTED_BOX`（或经迟滞保持的等价状态）

#### Scenario: 离线找回优先于弱观测

- **WHEN** reference view 的 F0 observation 为 weak、`final_source == refined_f1` 且该 view/tick 存在 accepted recovered observation
- **THEN** `evidence_type` SHALL 为 `refined_observed`
- **AND** 渲染 SHALL 使用 recovered bbox 且 provenance 标注为 offline_refinement

#### Scenario: 离线找回不覆盖 strong 观测

- **WHEN** reference view 在 canonical tick 有 F0 strong observation 且同时存在 accepted recovered observation
- **THEN** `evidence_type` SHALL 为 `base_observed` / `guided_observed`
- **AND** recovered observation SHALL 被抑制，不替换 original strong evidence

#### Scenario: 弱 F0 观测兜底

- **WHEN** reference view 有 F0 weak observation 且无 accepted recovered observation
- **THEN** `evidence_type` SHALL 为 `base_observed` / `guided_observed`
- **AND** SHALL 使用该 F0 bbox 渲染（接受较低质量）

#### Scenario: 双摄补全

- **WHEN** reference view 无真实观测，但 donor view 当前有真实 observation、final fused sample 非 predicted/conflict 且投影 geometry 有效（donor_quality / recency 通过门限）
- **THEN** `evidence_type` SHALL 为 `cross_view_projected`
- **AND** SHALL 经 canonical→target-image 投影渲染 footpoint / bbox（真实 bbox → fresh memory → view scale profile → stale memory grace → footpoint 光圈逐级 fallback），并以虚线或半透明呈现
- **AND** SHALL 携带 `donor_view`

#### Scenario: 短时预测兜底

- **WHEN** 双 view 均无当前观测，但 confirmed Player 存在短时 predicted sample 且未超预测 TTL
- **THEN** `evidence_type` SHALL 为 `predicted_only`
- **AND** `display_state` SHALL 为 `PREDICTED_POINT`（淡化 footpoint / identity badge / uncertainty halo）

#### Scenario: 证据不足隐藏

- **WHEN** 全部证据不足、或预测 TTL / last real observation age 超限
- **THEN** 该帧 SHALL 不渲染该球员（`display_state` 进入 `HIDDEN`）
