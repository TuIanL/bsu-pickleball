## Purpose

`multiview-fused-player-overlay` 定义 joint_tracking_v2 模式下的正式球员视频叠加层：把双摄融合后的全局球员证据（F0 观测、F1 离线找回、最终融合轨迹、Global Roster）以只读方式重新投影到用户正在观看的 reference camera，生成来源可解释、证据分级、身份统一的融合预览叠加层。它取代"参考摄像头本地 YOLO 检测"成为 joint 模式视频回放的数据源。

## Requirements

### Requirement: 正式 fused overlay 不依赖 debug trace

joint 模式正式视频叠加层 SHALL 以 `F0RefinementSnapshot`、accepted F1 recovered observations、final fused trajectory、roster map 与 target-view geometry 为数据源，MUST NOT 依赖 `joint_debug_trace`（opt-in 诊断产物）。`debugTraceEnabled=false` 时 fused overlay 仍 MUST 正常生成。

#### Scenario: 默认配置下 fused overlay 可生成

- **WHEN** joint run 完成且 `debugTraceEnabled=false`
- **THEN** 系统 SHALL 仍生成 `multiview-fused-player-overlay.v1` 产物
- **AND** SHALL NOT 因缺少 debug trace 而跳过或失败

#### Scenario: debug trace 仅用于诊断

- **WHEN** 系统生成正式 fused overlay
- **THEN** SHALL NOT 从 `joint_debug_trace` 读取任何检测框或标签
- **AND** debug trace 产物 SHALL 仅作为 visual acceptance 诊断使用

### Requirement: Evidence 分支决策链

每个 `(Player_N, canonical_tick)` 在参考画面上的展示证据 SHALL 按**分支决策链**（而非固定优先级排序）判定：reference view 有 F0 **strong** observation（origin=base/guided_roi）→ `base_observed`/`guided_observed`；否则 `final_source == refined_f1` 且该 view/tick 存在 accepted recovered observation → `refined_observed`；否则 reference view 有 F0 **weak** observation → `base_observed`/`guided_observed`；否则 donor view 有真实 observation 且 final fused sample 非 predicted/conflict 且 geometry 有效 → `cross_view_projected`；否则存在短时 predicted sample 且 TTL 未过 → `predicted_only`；否则不渲染。`refined_observed` SHALL 优先于 weak F0 observation，但 SHALL NOT 覆盖 strong F0 observation。系统 SHALL NOT 为了"始终显示全部球员"而制造无证据的展示框。

#### Scenario: 参考机位 strong 检测优先

- **WHEN** reference view 在 canonical tick 有 F0 strong observation（origin=base）
- **THEN** 该帧该球员的 `evidence_type` SHALL 为 `base_observed`
- **AND** SHALL 使用该真实 bbox 渲染实线框

#### Scenario: 跨摄 guidance 重检测成功

- **WHEN** reference view 在 canonical tick 有 F0 strong observation（origin=guided_roi，guidance ROI 重检测成功）
- **THEN** `evidence_type` SHALL 为 `guided_observed`
- **AND** SHALL 使用真实 bbox 渲染，并可携带协同恢复标识

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
- **AND** SHALL 经 canonical→target-image 投影渲染 footpoint / reanchor bbox，并以虚线或半透明呈现
- **AND** SHALL 携带 `donor_view`

#### Scenario: 短时预测兜底

- **WHEN** 双 view 均无当前观测，但 confirmed Player 存在短时 predicted sample 且未超预测 TTL
- **THEN** `evidence_type` SHALL 为 `predicted_only`
- **AND** SHALL 以淡化 footpoint / identity badge / uncertainty halo 呈现

#### Scenario: 证据不足隐藏

- **WHEN** 全部证据不足、或预测 TTL / last real observation age 超限
- **THEN** 该帧 SHALL 不渲染该球员

### Requirement: F0 origin provenance mapper

Builder SHALL 通过统一的 provenance mapper `classify_f0_origin(origin)` 将 F0 detection origin 映射为展示证据类型：`base → base_observed`、`guided_roi → guided_observed`、未知 origin 按 base 兜底并记录 warning。SHALL NOT 在 builder 内直接以字符串字面量判断 origin（如 `origin == "guided"`），以防止实际命名 `guided_roi` 与判断不一致导致 guided recovery 被错误分类。

#### Scenario: guided_roi 正确分类

- **WHEN** F0 observation 的 origin 为 `guided_roi`
- **THEN** 映射结果 SHALL 为 `guided_observed`
- **AND** SHALL 不因字符串命名差异被分类为 `base_observed`

#### Scenario: 未知 origin 兜底

- **WHEN** F0 observation 的 origin 不在已知枚举
- **THEN** 映射结果 SHALL 按 `base_observed` 兜底
- **AND** builder SHALL 记录 warning

### Requirement: bbox 补全与脚点光圈降级

`cross_view_projected` 的 bbox SHALL 通过 `TargetViewBBoxMemory` 的 `last_good_bbox` 以新投影 footpoint 为锚点**纯平移**重建（尺寸不变，V1 不做透视缩放/高度微调），MUST NOT 把 guidance ROI 直接当作 bbox。`TargetViewBBoxMemory` SHALL 仅由合格真实观测刷新（bbox 几何合法 + confidence/quality 过门 + width/height 在合理范围），错误检测 SHALL NOT 污染记忆。当 `(global_player_id, target_view_id)` 在目标视角从无真实 bbox 历史时，SHALL 只渲染投影 footpoint + identity badge + uncertainty halo，不伪造人体框。

#### Scenario: 有历史 bbox 时纯平移 reanchor

- **WHEN** reference view 曾在历史帧合格观测过某 Player，且当前需要 `cross_view_projected`
- **THEN** 渲染 bbox SHALL 以最近合格真实 bbox 的 width/height + 新投影 footpoint 纯平移重建
- **AND** `bbox_source` SHALL 标注为 `last_good_bbox_reanchored`
- **AND** bbox 尺寸 SHALL 与最近合格真实 bbox 一致（不做透视缩放）

#### Scenario: 无历史 bbox 不伪造

- **WHEN** reference view 从未真实观测过某 Player，且当前需要 `cross_view_projected`
- **THEN** 渲染 SHALL 仅包含投影 footpoint + identity badge + uncertainty halo
- **AND** `bbox` SHALL 为 `null`

#### Scenario: 低质量观测不刷新记忆

- **WHEN** reference view 的观测 bbox 几何非法、或 confidence/quality 未过门、或 width/height 超出合理范围
- **THEN** `TargetViewBBoxMemory` SHALL NOT 更新 `last_good_bbox`
- **AND** 后续 cross-view 补全 SHALL 继续使用此前的合格记忆

#### Scenario: bbox 记忆过期降级

- **WHEN** `last_real_observed_at` 距今超过 bbox 记忆 TTL
- **THEN** 该 Player 的展示 SHALL 从 reanchor bbox 降级为 footpoint 光圈

### Requirement: 置信度语义拆分

overlay contract SHALL 区分 `source_confidence`（真实 detector / recovered evidence 的原始置信）与 `overlay_confidence`（该 presentation entity 值得展示的程度），SHALL NOT 使用单一 `confidence` 字段混两种语义。`cross_view_projected` 的 `source_confidence` SHALL 来自 donor 视图的真实观测置信，SHALL NOT 伪装为 reference-view 检测置信。`uncertainty_ft` SHALL 可空：当前 snapshot 无 prediction covariance 时 SHALL 为 `null`，并以 `donor_quality + fusion_status + geometry_valid + recency` 作为 gate，SHALL NOT 制造无依据的数值 uncertainty。

#### Scenario: 双置信字段独立

- **WHEN** overlay 输出任一 player entry
- **THEN** 字段 SHALL 包含 `source_confidence` 与 `overlay_confidence`
- **AND** 两字段 SHALL 允许取不同值

#### Scenario: cross_view 置信来源 donor

- **WHEN** player entry 的 `evidence_type` 为 `cross_view_projected`
- **THEN** `source_confidence` SHALL 为 donor view 真实观测的原始置信
- **AND** `donor_view` SHALL 非空

#### Scenario: 无 covariance 时 uncertainty 为空

- **WHEN** snapshot 未持久化 prediction covariance
- **THEN** `uncertainty_ft` SHALL 为 `null`
- **AND** 门禁 SHALL 基于 donor_quality / fusion_status / geometry_valid / recency，而非数值 uncertainty

### Requirement: 身份只读 canonical Player_N

overlay 中所有用户可见身份 SHALL 为 canonical `Player_1`..`Player_4`（展示为 P1-P4），MUST NOT 出现 `global_player_<id>` 或局部 `track_id`。身份映射 SHALL 只读复用 Global Roster 的 `_build_roster_map`，overlay SHALL NOT 反写 roster / tracker / association。

#### Scenario: 身份标签统一

- **WHEN** fused overlay 生成任一帧任一球员
- **THEN** `player_id` SHALL 为 canonical `Player_N`
- **AND** `label` SHALL 为对应 P1-P4 形式

#### Scenario: overlay 不反写分析真值

- **WHEN** builder 消费 F0/F1 evidence 与 roster
- **THEN** SHALL NOT 修改 tracker、association、metrics 或 roster 状态

### Requirement: 融合时间轴与参考帧对齐

overlay 帧 SHALL 以 `F0TickSnapshot.reference_frame_index` 为 `frame_index`、以 canonical timestamp 为时间轴，与 fused trajectory 完全对齐，保证"数据层与视觉层同一 tick 同一语义"。

#### Scenario: 帧索引对齐

- **WHEN** builder 生成 canonical tick 的 overlay 帧
- **THEN** `frame_index` SHALL 等于该 tick 的 `reference_frame_index`
- **AND** `timestamp_seconds` SHALL 等于 canonical timestamp（秒）
