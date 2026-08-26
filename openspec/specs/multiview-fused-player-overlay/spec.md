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

`cross_view_projected` 的 bbox SHALL 按扩展 fallback 层级生成：当前 tick 真实 bbox → fresh personal bbox memory（`age ≤ bbox_memory_ttl_ms`，`last_good_bbox` 纯平移 reanchor）→ view scale profile（当前 projected footpoint 深度估计，`view_scale_profiled`）→ stale personal memory grace（`age ≤ ttl + bbox_memory_grace_ms`，仅 profile 不可用时兜底，`bbox_stale=true`）→ 否则仅 footpoint 光圈。MUST NOT 把 guidance ROI 直接当作 bbox。`TargetViewBBoxMemory` SHALL 仅由合格真实观测刷新（bbox 几何合法 + confidence/quality 过门 + width/height 在合理范围），错误检测 SHALL NOT 污染记忆；synthetic bbox（reanchor / scale profile）SHALL NOT 回喂记忆。`bbox_source` SHALL 为 `last_good_bbox_reanchored` / `view_scale_profiled` / `none`。

#### Scenario: 有历史 bbox 时纯平移 reanchor

- **WHEN** reference view 曾在历史帧合格观测过某 Player，且当前需要 `cross_view_projected`，且记忆 fresh
- **THEN** 渲染 bbox SHALL 以最近合格真实 bbox 的 width/height + 新投影 footpoint 纯平移重建
- **AND** `bbox_source` SHALL 标注为 `last_good_bbox_reanchored`

#### Scenario: 无历史 bbox 时 scale profile 投影

- **WHEN** reference view 从未真实观测过某 Player，但 view scale profile 有足够样本
- **THEN** 渲染 bbox SHALL 由 scale profile 生成（`bbox_source=view_scale_profiled`）
- **AND** 视觉上 SHALL 为虚线（不伪装 YOLO 检测）

#### Scenario: 无历史 bbox 且无 scale profile 不伪造

- **WHEN** reference view 从未真实观测过某 Player 且 view scale profile 样本不足
- **THEN** 渲染 SHALL 仅包含投影 footpoint + identity badge + uncertainty halo
- **AND** `bbox` SHALL 为 `null`

#### Scenario: 低质量观测不刷新记忆

- **WHEN** reference view 的观测 bbox 几何非法、或 confidence/quality 未过门、或 width/height 超出合理范围
- **THEN** `TargetViewBBoxMemory` SHALL NOT 更新 `last_good_bbox`
- **AND** 后续 cross-view 补全 SHALL 继续使用此前的合格记忆

#### Scenario: bbox 记忆过期降级

- **WHEN** `last_real_observed_at` 距今超过 `bbox_memory_ttl_ms + bbox_memory_grace_ms` 且 scale profile 不可用
- **THEN** 该 Player 的展示 SHALL 从 bbox 降级为 footpoint 光圈

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

### Requirement: bootstrap display 证据分支（最低优先级兜底）
`fused_overlay_builder` 既有「五种 evidence（`base_observed` / `guided_observed` / `refined_observed` / `cross_view_projected` / `predicted_only`）+ hidden outcome」决策链 SHALL 增加最低优先的 `bootstrap_backfill` 分支：仅当五级证据全部缺失、且 `frame < 该 player 的 locked_frame_index`、且存在 `bootstrap_backfill` 真实观测时启用。该分支 MUST NOT 覆盖任何更高级别证据，也 MUST NOT 产生「不渲染」之外的额外 outcome。

#### Scenario: 填补 bootstrap 空窗
- **WHEN** 五级证据在 bootstrap 窗口内均缺失，但存在该 player 的 `bootstrap_backfill` 真实观测
- **THEN** `evidence_type` SHALL 为 `bootstrap_backfill`
- **AND** 展示状态映射 SHALL 将其归为带真实 bbox 的展示态（如 `REAL_BOX`）

#### Scenario: 不降级既有证据
- **WHEN** 某帧某 player 同时存在 stronger 证据与 `bootstrap_backfill` 数据
- **THEN** 系统 SHALL 优先采用 stronger 证据
- **AND** `bootstrap_backfill` 数据 SHALL 被抑制，不替换原证据

#### Scenario: 契约一致性
- **WHEN** overlay 写出 player entity 且 `evidence_type=bootstrap_backfill`
- **THEN** 后端 `EvidenceType` Literal 与前端 `FusedPlayerEvidenceType` SHALL 均包含 `bootstrap_backfill`，且 `FUSED_EVIDENCE_STYLE` SHALL 提供其展示样式；否则验证/构建 SHALL 失败

### Requirement: player entity 携带 canonical court position
`fused_player_overlay` 的每个 player entity SHALL 携带 `canonical_court_position_ft`（由回填或既有路径经 `local_to_canonical` 得到），使人物框与小地图共用同一展示时间语义、同源同 tick。

#### Scenario: 小地图同源
- **WHEN** 前端 `CourtMinimap` 读取展示轨迹
- **THEN** SHALL 可从 overlay 的 `canonical_court_position_ft` 获取球员位置（joint 模式 display authority = fusedPlayerOverlay）
- **AND** 单摄模式仍保持 `pipelineTracks` 路径；joint 模式若 fused overlay 可用则用 overlay-derived display tracks，仅旧任务/不可用时 fallback `result.tracks`
- **AND** MUST NOT 新增第三个 `display_player_trajectory` artifact，也 MUST NOT 直接修改 authoritative `result.tracks` 语义

#### Scenario: 坐标契约
- **WHEN** overlay 写出 `canonical_court_position_ft`
- **THEN** 字段 SHALL 为 `[x, y] | null`（英尺，canonical court 坐标系）
- **AND** 建议同时携带 `court_frame_version="canonical_court_frame.v1"` 与 `court_unit="ft"` 以强化契约，避免前端单位猜测

### Requirement: display_state 作为正式展示契约

fused overlay entity 的 `display_state` SHALL 作为 bundle 的正式展示契约（供 renderer 决定 geometry topology / 时间保持 / 渐进降级），而非仅被序列化但未消费的可选 metadata。`evidence_type` SHALL 继续保持当前 tick 的真实 evidence provenance（raw），MUST NOT 被 display hysteresis 修改或伪造。旧 artifact 缺失 `display_state` 时 SHALL 保持兼容 fallback，MUST NOT 因字段缺失报错。

#### Scenario: display_state 被 renderer 消费

- **WHEN** overlay entity 携带 `display_state`
- **THEN** renderer SHALL 以 `display_state` 作为人物几何形态（BOX / POINT / HIDDEN）的权威
- **AND** SHALL NOT 仅凭 `evidence_type` 决定形态

#### Scenario: evidence_type 不因迟滞修改

- **WHEN** 状态机通过 `hysteresis_grace_ms` / `projected_box_hold_ms` 保持几何形态
- **THEN** 该 tick 的 `evidence_type` SHALL 仍反映真实证据来源（MUST NOT 被保持为之前的 `base_observed` / `guided_observed`）
- **AND** SHALL 诚实降级为实际来源（如 `cross_view_projected` / `predicted_only`）

#### Scenario: 旧产物缺失 display_state 兼容

- **WHEN** 历史 fused overlay entity 缺失 `display_state`
- **THEN** 前端 SHALL 按既有逻辑渲染，不做形态保持或迟滞处理
- **AND** SHALL NOT 因字段缺失报错

### Requirement: 参考视角跨视角投影几何门控

`cross_view_projected` overlay SHALL 明确绑定当前任务的 `reference_view_id`。除 donor recency、canonical position 和 geometry valid 外，投影还 MUST 通过目标视角连续性、脚点运动、bbox 尺寸变化和与其他强/可信球员框的碰撞门控。仅因为投影点落在图像边界内，不得判定为可发布的 projected bbox。

#### Scenario: 参考视角强观测优先
- **WHEN** reference view 当前 tick 存在 strong 或 accepted real bbox
- **THEN** overlay SHALL 使用该真实证据
- **AND** donor 投影不得覆盖、替换或改变该球员的真实 bbox

#### Scenario: 投影目标视角固定
- **WHEN** 当前任务的 `reference_view_id` 为 `cam_1` 且 reference view 缺少真实 bbox
- **THEN** 生成的 `cross_view_projected` geometry SHALL 使用 `cam_1` 的投影结果
- **AND** SHALL 携带 `donor_view` 说明证据来源，但不得把 donor image-space bbox 直接作为 cam_1 bbox

#### Scenario: 投影框与可信球员框冲突
- **WHEN** projected bbox 与另一名球员的 strong/accepted bbox 发生超过配置门限的空间重叠，或脚点/速度跳变超过连续性门限
- **THEN** 系统 SHALL 禁止发布该 synthetic bbox
- **AND** SHALL 降级为稳定的 `PROJECTED_POINT`、上一份合格 presentation geometry 或 `HIDDEN`
- **AND** SHALL 记录 projection collision 或 continuity rejection reason

#### Scenario: synthetic geometry 不污染记忆
- **WHEN** projected bbox 通过 reanchor 或 view scale profile 生成
- **THEN** 该 bbox SHALL NOT 刷新 `TargetViewBBoxMemory` 或 scale profile
- **AND** 下一次投影 SHALL 只能使用合格真实 target-view bbox 建立的记忆

#### Scenario: 证据来源保持诚实
- **WHEN** renderer 为了保持几何稳定而复用上一份 presentation geometry
- **THEN** 当前 tick 的 `evidence_type` SHALL 仍反映当前真实来源
- **AND** SHALL NOT 将 `cross_view_projected` 改写为 `base_observed`

### Requirement: 正式 Player overlay 支持按 view 输出

joint 模式正式 Player overlay SHALL 为每个可用 view 提供以 canonical tick/timestamp 对齐的 image-space frames。所有 view SHALL 只读复用同一份 canonical Player roster；view-specific bbox、footpoint、evidence、donor 和质量字段不得改变 `player_id` 或 `render_slot`。

#### Scenario: 两路都可生成 overlay

- **WHEN** joint 任务包含 `cam_1` 与 `cam_2` 的 view geometry
- **THEN** overlay artifact 或其 view-scoped API SHALL 能分别返回 `cam_1` 与 `cam_2` 的 frames
- **AND** 同一 tick 的 P1-P4 SHALL 在两路使用相同 canonical identity

#### Scenario: 目标 view 没有可靠 bbox

- **WHEN** 某 Player 在目标 view 没有通过质量门的 bbox
- **THEN** 该 view 的 entity SHALL 保留 canonical identity、canonical position 或明确缺失状态
- **AND** bbox SHALL 为 `null` 或由已有合法 view-specific evidence 生成
- **AND** SHALL NOT 复制其他 Player 的 bbox 或重新分配 roster

### Requirement: 旧 overlay artifact 安全归一化

读取仅包含顶层 `reference_view_id` 和单路 `frames` 的历史 overlay 时，系统 SHALL 将其归一化为仅 reference view 可用的 view-scoped 结构。系统 SHALL NOT 宣称历史 artifact 包含另一 view 的 Player overlay。

#### Scenario: 历史 v1 overlay

- **WHEN** 前端读取旧版单路 fused overlay
- **THEN** 默认 reference view SHALL 正常展示
- **AND** 另一 view 的切换控件 SHALL 禁用或显示明确的产物不可用状态

