# stabilize-multiview-overlay-display Specification

## Purpose
fused overlay 展示稳定性：跨 tick 展示状态机（迟滞稳定 geometry、`evidence_type` 与 `display_state` 正交、真实 bbox 立即升级、ms 时间单位、硬 stop/reset）、整场两遍式 `ViewPersonScaleProfile` 透视尺度模型、bbox fallback 层级（freshness 优先）、`bbox_stale/bbox_age_ms` 展示 freshness 契约。
## Requirements
### Requirement: Overlay 展示状态机（迟滞稳定 geometry，不伪造 evidence）

系统 SHALL 对每个 `(Player_N, displayed_view)` 维护跨 tick 的展示状态，状态集为 `REAL_BOX | ASSISTED_BOX | PROJECTED_BOX | PROJECTED_POINT | PREDICTED_POINT | HIDDEN`。展示状态 SHALL 由迟滞状态机决定，MUST NOT 每 tick 直接根据瞬时证据切换形态。**`evidence_type` SHALL 永远反映当前 tick 的真实证据来源（由分支决策链权威决定），状态机 MUST NOT 修改它；`display_state` 是正交的展示层状态。** 冻结映射：`base_observed → REAL_BOX`、`guided_observed / refined_observed → ASSISTED_BOX`、`cross_view_projected + bbox → PROJECTED_BOX`、`cross_view_projected 无 bbox → PROJECTED_POINT`、`predicted_only → PREDICTED_POINT`、`none → HIDDEN`。迟滞稳定的是几何形态（box→point→hidden 渐进降级），**不得把 synthetic bbox 伪装为真实检测**：tick 本视角 miss 时 `evidence_type` SHALL 变为 `cross_view_projected`（而非保持 `base_observed`），展示形态从实线降级为虚线但保持框。

#### Scenario: 短暂漏检诚实降级证据

- **WHEN** `REAL_BOX` 状态下的球员在当前 view 连续漏检 ≤ `hysteresis_grace_ms`，但 donor view 有可靠位置
- **THEN** 展示形态 SHALL 保持框（`PROJECTED_BOX`，用 last_good bbox 或 scale profile 补框）
- **AND** `evidence_type` SHALL 为 `cross_view_projected`（MUST NOT 保持 `base_observed`）
- **AND** 线型 SHALL 为虚线（诚实降级，不伪装真实检测）

#### Scenario: 连续漏检渐进降级

- **WHEN** 真实框状态下的球员连续漏检超过 `hysteresis_grace_ms`
- **THEN** 展示状态 SHALL 依次降级：`REAL_BOX/ASSISTED_BOX → PROJECTED_BOX → PROJECTED_POINT`（bbox 模板失效时）→ `HIDDEN`（predicted TTL 过期时）
- **AND** 每一步 SHALL 有明确触发条件（grace 用尽 / bbox 失效 / TTL 过期）

#### Scenario: synthetic 恢复需稳定确认

- **WHEN** `PROJECTED_POINT` 状态的球员恢复 synthetic evidence（donor 恢复 + 可靠 bbox 模板），但仅 1 帧
- **THEN** 展示状态 SHALL NOT 立即升回 `PROJECTED_BOX`
- **AND** 仅当连续 ≥ `synthetic_upgrade_confirm_ticks` 帧（且满足 gap 约束）才升级

#### Scenario: 逐帧抖动消除

- **WHEN** 同一 evidence 序列输入（无真实证据变化）
- **THEN** 相邻 tick 的展示形态 SHALL 稳定（不出现 REAL↔POINT 交替）
- **AND** 该性质 SHALL 由验收测试断言

### Requirement: 真实 bbox 恢复立即升级

当前 target-view 真实 bbox（`base / guided_roi / accepted refined`）出现时，展示状态 SHALL **立即**升级为 `REAL_BOX`/`ASSISTED_BOX` 并清空 recovery confirmation counter，MUST NOT 等待 `synthetic_upgrade_confirm_ticks`。恢复确认参数 SHALL 仅控制 synthetic upgrade（如 `PROJECTED_POINT → PROJECTED_BOX`），MUST NOT 延迟真实观测的展示。

#### Scenario: 真实重检测立即显示

- **WHEN** `PROJECTED_POINT` 状态的球员在当前 view 重新被真实检测到（`base` observation）
- **THEN** 当前 tick 展示 SHALL 立即为 `REAL_BOX` 实线框
- **AND** SHALL NOT 因 confirm 计数未满而继续显示点

#### Scenario: confirm 只控 synthetic

- **WHEN** `PROJECTED_POINT` 状态的球员仅恢复 synthetic evidence（无当前真实 bbox）
- **THEN** 升级到 `PROJECTED_BOX` SHALL 需连续 ≥ `synthetic_upgrade_confirm_ticks` 帧（且 gap ≤ `confirm_max_gap_ms`）

### Requirement: 迟滞时间单位与 freshness 权威

迟滞参数 SHALL 以**毫秒**为单位（`hysteresis_grace_ms` / `projected_box_hold_ms`），MUST NOT 以 tick 为单位（canonical tick 间距随 `frameStride` 变化）。恢复确认 SHALL 同时要求连续 N 次有效 evidence 与 gap 约束（`confirm_max_gap_ms`）。系统 SHALL 统一由 bbox source 报告 freshness/age（`bbox_age_ms` 与 `last_real_observed_ms` 一致），状态机 SHALL 只消费该 freshness 信息；SHALL NOT 存在第二套独立的过期权威（如 tick 计数的 stale 判定）。

#### Scenario: ms 单位跨 stride 稳定

- **WHEN** 同一球员在 `frameStride=1` 与 `frameStride=3` 下发生相同时长的短暂漏检
- **THEN** 迟滞保持窗口 SHALL 一致（ms 语义），不随 tick 间距变化

#### Scenario: 单一 freshness 权威

- **WHEN** bbox memory 过期判定发生
- **THEN** 判定 SHALL 基于 `bbox_age_ms`（与 `last_real_observed_ms` 一致）
- **AND** 状态机 SHALL NOT 使用独立的 tick 计数 stale 判定

### Requirement: ViewPersonScaleProfile 整场两遍式静态模型

系统 SHALL 以两遍式构建 `ViewPersonScaleProfile`：Pass 1 整场收集该 view 的可靠真实 bbox 并冻结静态尺度模型（`scale(y) → (width, height)`）；Pass 2 逐 tick 查询已冻结模型。**硬约束**：只收 `base / guided_roi / accepted refined` 的真实 target-view bbox；`last_good_bbox_reanchored`、`view_scale_profiled` 等 synthetic bbox MUST NOT 回喂 profile 或 BBoxMemory（防自我强化）；clipped / 极端长宽比 / 尺寸异常的 bbox MUST NOT 作为 scale sample（除 `is_qualifying_bbox` 外需额外过滤）。查询 SHALL 用邻桶 linear interpolation（非 nearest bucket），受 `min_total_samples` / `min_samples_per_bin` 门限与 width/height physical bounds 约束；样本不足 → None。

#### Scenario: 有样本生成 projected bbox

- **WHEN** 某球员在目标 view 无历史真实 bbox，但该 view 冻结尺度模型有足够样本，且 fused footpoint 投影 y 在模型覆盖范围
- **THEN** 系统 SHALL 生成 projected bbox（`bbox_source=view_scale_profiled`）
- **AND** bbox 尺寸 SHALL 由该 y 的插值尺度决定

#### Scenario: 样本不足不伪造

- **WHEN** 某 view 尺度模型样本不足（低于 `min_total_samples` 或该桶低于 `min_samples_per_bin`）
- **THEN** 查询 SHALL 返回 None
- **AND** 该球员 SHALL 降级为 footpoint 光圈（不制造不可靠 bbox）

#### Scenario: synthetic 不回喂

- **WHEN** 某 view 产生 `last_good_bbox_reanchored` 或 `view_scale_profiled` 的 synthetic bbox
- **THEN** 该 bbox SHALL NOT 被收集为 scale sample
- **AND** SHALL NOT 更新 `TargetViewBBoxMemory` 的 `last_good_bbox`

#### Scenario: 邻桶插值防抖动

- **WHEN** 某球员 footpoint y 相邻两 tick 落在不同分桶
- **THEN** 查询 SHALL 返回邻桶 linear interpolation 结果
- **AND** 两 tick 的 projected bbox 尺寸 SHALL 连续变化（不出现跳跃）

### Requirement: bbox fallback 层级（freshness 优先）

`cross_view_projected` 的 bbox SHALL 按扩展 fallback 层级生成：当前 tick 真实 bbox → fresh personal bbox memory（`age ≤ bbox_memory_ttl_ms`）→ view scale profile（当前 projected footpoint 深度估计尺寸）→ stale personal memory grace（`age ≤ ttl + bbox_memory_grace_ms`，仅 profile 不可用时兜底）→ footpoint 光圈。freshness SHALL 优先于 stale personal memory：过期个人 bbox（如球员已从后场跑到网前）SHALL NOT 压过当前 footpoint 深度估计的 scale profile。`bbox_source` SHALL 为 `last_good_bbox_reanchored` / `view_scale_profiled` / `none`。

#### Scenario: fresh memory 优先于 scale profile

- **WHEN** 球员有 `age ≤ bbox_memory_ttl_ms` 的个人 bbox 记忆
- **THEN** fallback SHALL 使用 `last_good_bbox_reanchored`
- **AND** SHALL NOT 因 scale profile 可用而跳过 fresh memory

#### Scenario: scale profile 优先于 stale memory

- **WHEN** 球员个人 bbox 记忆已过期（`age > bbox_memory_ttl_ms`）但 scale profile 可用
- **THEN** fallback SHALL 使用 `view_scale_profiled`（当前 footpoint 深度估计）
- **AND** SHALL NOT 使用过期个人尺寸（可能已不匹配当前位置）

#### Scenario: stale memory 仅兜底

- **WHEN** 个人 bbox 记忆过期且 scale profile 不可用，但 `age ≤ ttl + bbox_memory_grace_ms`
- **THEN** fallback SHALL 使用 stale memory（`bbox_stale=true`）
- **AND** 前端 SHALL 可据此淡化

#### Scenario: 全 fallback 失效降级光圈

- **WHEN** 无当前真实 bbox、无 fresh memory、无 scale profile、无 stale memory
- **THEN** 渲染 SHALL 仅含 footpoint + identity badge + uncertainty halo
- **AND** `bbox` SHALL 为 null

### Requirement: 展示 freshness 契约

overlay player SHALL 可选携带 `display_state`（状态机当前状态）、`bbox_stale: bool`（该 bbox 是否来自 stale memory）、`bbox_age_ms: float | null`（last real observed 距今毫秒）。`bbox_stale/bbox_age_ms` SHALL 与 `last_real_observed_ms` 一致（单一 freshness 权威），供前端淡化展示。旧产物缺省兼容。

#### Scenario: stale bbox 可淡化

- **WHEN** overlay player 的 `bbox_source == "last_good_bbox_reanchored"` 且 `bbox_stale=true`
- **THEN** 前端 SHALL 可据此淡化 bbox 展示
- **AND** 后端 SHALL 提供 `bbox_age_ms` 供前端决策

#### Scenario: 旧产物兼容

- **WHEN** 查询历史 fused overlay 产物（无 `display_state / bbox_stale / bbox_age_ms` 字段）
- **THEN** 前端 SHALL 按缺省处理（无淡化、无状态标签）
- **AND** SHALL NOT 因字段缺失报错

### Requirement: 状态机硬 stop 与 reset

状态机 SHALL 遵守硬 stop 不变量：target geometry invalid → 不允许 synthetic projected box；当前无有效 fused/projected point 且 prediction 已超 TTL → MUST `HIDDEN`（即使上一状态是 PROJECTED_BOX）；bbox memory > ttl + grace 且 profile 不可用 → 不得继续画框。状态机 SHALL 在 new build / new job / roster reset 时 reset（有状态实例不得跨 job 复用上一场状态）。

#### Scenario: geometry 无效禁止 synthetic box

- **WHEN** 目标 view 的 geometry 无效（无 orientation / 无逆单应 / 尺寸缺失）
- **THEN** 状态机 SHALL 不允许 `PROJECTED_BOX`
- **AND** 展示 SHALL 降级为 `PROJECTED_POINT` 或 `HIDDEN`

#### Scenario: 无证据硬隐藏

- **WHEN** 当前无有效 fused/projected point 且 prediction 已超 TTL
- **THEN** 状态机 SHALL 强制 `HIDDEN`
- **AND** 不得因上一状态是 `PROJECTED_BOX` 继续画框

#### Scenario: 跨 job 状态隔离

- **WHEN** 同一 builder/状态机实例被用于新的 job 或 roster reset
- **THEN** 状态机 SHALL 清空全部 `(player, view)` 状态
- **AND** 不得把上一场 P1 的展示状态带进下一场

### Requirement: 毫秒级迟滞参数真正参与状态转移

`OverlayDisplayStateMachine` 的 `hysteresis_grace_ms` / `projected_box_hold_ms` SHALL 真正参与 box → point → hidden 的渐进降级判定，MUST NOT 仅为构造参数而未进入 `step()`。迟滞判定 SHALL 以毫秒（`now_ms`）而非 tick 为单位驱动，跨 `frameStride` 保持稳定。`hysteresis_grace_ms` SHALL 仅在仍存在当前跨视角位置证据（`evidence_type = cross_view_projected`）的降级上生效：真实 bbox 丢失后 `display_state` SHALL 立即降级为 `PROJECTED_BOX`（复用最后可靠 presentation box geometry，MUST NOT 继续输出 `REAL_BOX`），以保持 BOX topology 不塌成 POINT。`hysteresis_grace_ms` MUST NOT 应用于无 projected 位置证据的降级（如 `observed → predicted_only`）。

#### Scenario: 短暂漏检保持框形态

- **WHEN** `REAL_BOX` 状态下的球员在当前 view 漏检，但当前有 donor / global projected evidence，且缺失时长 ≤ `hysteresis_grace_ms`
- **THEN** `display_state` SHALL 立即降级为 `PROJECTED_BOX`（MUST NOT 保持 `REAL_BOX`），复用最后可靠 presentation box geometry
- **AND** `evidence_type` SHALL 立即诚实降级为 `cross_view_projected`（MUST NOT 保持 `base_observed`）

#### Scenario: 无 projected 位置证据直接点

- **WHEN** 真实框状态下的球员下一 tick 无 projected 位置证据，仅剩 prediction（`evidence_type = predicted_only`）
- **THEN** `display_state` SHALL 直接进入 `PREDICTED_POINT`
- **AND** MUST NOT 用 `hysteresis_grace_ms` 或旧 bbox 继续画人体框

#### Scenario: 迟滞跨 frameStride 一致

- **WHEN** 同一球员在 `frameStride=1` 与 `frameStride=3` 下发生相同时长的短暂漏检
- **THEN** 迟滞保持窗口 SHALL 一致（ms 语义），MUST NOT 随 tick 间距漂移

### Requirement: projected_box_hold_ms 的模板瞬失宽限语义

`projected_box_hold_ms` SHALL 表示：在已存在可信 projected/display bbox 之后，bbox template 在短时间内瞬时不可用时的 geometry hold grace，而非 synthetic box 的无限生命周期。template 瞬失时长 ≤ `projected_box_hold_ms` 时 SHALL 短暂保持上一份 presentation box geometry；donor / global evidence 失效时 SHALL 由更高层 hard TTL 强制收敛，MUST NOT 让合成框长期赖在画面。

#### Scenario: template 瞬失保持框

- **WHEN** `PROJECTED_BOX` 状态的球员其 synthetic bbox template 瞬时不可用，但缺失时长 ≤ `projected_box_hold_ms`
- **THEN** renderer SHALL 短暂保持上一份 presentation box geometry（不塌成 POINT）
- **AND** SHALL NOT 发生 BOX → POINT → BOX 的逐 tick 抖动

#### Scenario: hold 用尽降级点

- **WHEN** synthetic bbox template 持续不可用超过 `projected_box_hold_ms`
- **THEN** `display_state` SHALL 降级为 `PROJECTED_POINT`

#### Scenario: hold 从最后有效演示几何计时

- **WHEN** `PROJECTED_BOX` 已持续 hold（如 100ms→300ms 均复用最后有效 presentation bbox），随后 300ms 才 template 瞬失
- **THEN** `projected_box_hold_ms` SHALL 从 `last_valid_box_geometry_ts`（=300ms，最后成功 presentation bbox）起算
- **AND** MUST NOT 从 `last_real_bbox_ts`（更早的真实观测）起算

#### Scenario: hard TTL 收敛不赖屏

- **WHEN** donor / global evidence 已失效（`prediction TTL` 超限或 `identity reset`）
- **THEN** hard stop SHALL 优先于任何 `hysteresis_grace_ms` / `projected_box_hold_ms` hold
- **AND** 人物 SHALL 进入 `HIDDEN`，合成框不得长期留在画面

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
