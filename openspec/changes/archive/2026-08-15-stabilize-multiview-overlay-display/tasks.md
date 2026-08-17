## 1. 迟滞状态机（geometry 稳定，evidence 正交）

- [x] 1.1 新增 `OverlayDisplayStateMachine`（独立类，无 I/O）：`(player_id, view_id) → DisplayState`（`REAL_BOX | ASSISTED_BOX | PROJECTED_BOX | PROJECTED_POINT | PREDICTED_POINT | HIDDEN`）；输入 = raw evidence decision + display context，输出 = `DisplayPlan(state, preferred_bbox_source, bbox_stale, bbox_age_ms)`
- [x] 1.2 **正交语义**：`evidence_type` 由 `_decide_entity` 权威决定且状态机 MUST NOT 修改；映射冻结 `base_observed→REAL_BOX`、`guided/refined→ASSISTED_BOX`、`cross_view+bbox→PROJECTED_BOX`、`cross_view 无 bbox→PROJECTED_POINT`、`predicted_only→PREDICTED_POINT`、`none→HIDDEN`；短暂漏检时 `evidence_type` 变 `cross_view_projected`（虚线）而非保持 `base_observed`
- [x] 1.3 **真实 bbox 立即升级**：当前 tick 真实 bbox（base/guided/accepted refined）→ 立即 `REAL_BOX`/`ASSISTED_BOX` 并清空 confirmation counter；`synthetic_upgrade_confirm_ticks` 只控 `PROJECTED_POINT → PROJECTED_BOX`
- [x] 1.4 **ms 时间单位 + 统一 freshness**：配置用 `hysteresis_grace_ms` / `projected_box_hold_ms` / `confirm_max_gap_ms`（不用 tick）；删除 `projected_box_stale_ticks`；状态机只消费 `bbox_age_ms`（单一 freshness 权威）
- [x] 1.5 **硬 stop / reset**：geometry invalid → 禁 synthetic box；无有效 point 且 prediction 超 TTL → 强制 HIDDEN；bbox > ttl+grace 且 profile 不可用 → 不画框；`reset()` 方法在 new build / new job / roster reset 时调用（跨 job 状态隔离）

## 2. ViewPersonScaleProfile（整场两遍式静态）

- [x] 2.1 新增 `ViewPersonScaleProfile`：Pass 1 整场收集该 view 真实 bbox 样本（`footpoint_y, width, height`）→ 冻结静态模型；Pass 2 逐 tick 查询
- [x] 2.2 **硬约束**：只收 `base/guided_roi/accepted refined` 真实 target-view bbox；synthetic bbox（reanchor / scale profile）绝不回喂 profile 或 BBoxMemory；clipped / 极端长宽比 / 尺寸异常 bbox 不作为样本（`is_qualifying_bbox` 之外额外过滤）
- [x] 2.3 查询：footpoint_y 分桶（32 桶）robust median + **邻桶 linear interpolation**（非 nearest bucket）+ `min_total_samples`（默认 50）/ `min_samples_per_bin`（默认 5）+ width/height physical bounds；样本不足 → None

## 3. bbox fallback 层级 + freshness 契约

- [x] 3.1 扩展 fallback 顺序：当前真实 bbox → fresh memory（age ≤ ttl）→ view scale profile → stale memory grace（age ≤ ttl+grace，仅 profile 不可用时，`bbox_stale=true`）→ footpoint 光圈
- [x] 3.2 `TargetViewBBoxMemory.reanchor()` 支持 grace：`ttl + bbox_memory_grace_ms` 内返回 stale 标记结果，超过返回 None；`bbox_age_ms` 统一由 `last_real_observed_ms` 推导
- [x] 3.3 `fused_overlay_types.py`：`BBoxSource` 新增 `view_scale_profiled`；`FusedPlayerOverlayPlayer` 可选新增 `display_state / bbox_stale / bbox_age_ms`（缺省兼容）

## 4. 包装器接入（raw evidence + display context → DisplayPlan → materialize）

- [x] 4.1 `FusedPlayerOverlayBuilder` 新增 `_decide_display_entity` 包装器：先 `_decide_entity`（raw evidence 权威不变），再组装 display context（projected_footpoint / prediction / geometry_valid / bbox_memory_freshness / scale_profile_result / timestamp），驱动状态机得到 `DisplayPlan`，最后按 DisplayPlan materialize entity
- [x] 4.2 补框来源如实标注：状态保持阶段用 last_good bbox / scale profile 生成展示 bbox，`bbox_source` 与 `bbox_stale` 如实填写（不伪装真实检测）

## 5. 前端展示

- [x] 5.1 `src/types/report.ts`：`FusedPlayerBBoxSource` 新增 `view_scale_profiled`；`FusedPlayerOverlayEntity` 可选新增 `display_state / bbox_stale / bbox_age_ms`
- [x] 5.2 `src/components/platform/VideoAnalysisCard.tsx`：`view_scale_profiled` 虚线样式族；`bbox_stale=true` 时按 `bbox_age_ms` 淡化；`display_state` 驱动视觉语义（REAL 实线 / PROJECTED 虚线 / POINT 光圈）

## 6. 测试与验收

- [x] 6.1 后端单测：状态机（真实 bbox 立即升级 / synthetic upgrade 需 confirm + gap 约束 / geometry 无效 hard stop / 无证据硬 HIDDEN / reset 跨 job 隔离 / 逐帧抖动消除断言）；ViewPersonScaleProfile（两遍式 / 只收真实 bbox / synthetic 不回喂 / 邻桶插值防 2px 跳跃 / 样本不足 fallback）
- [x] 6.2 后端单测：bbox fallback 顺序（fresh memory 优先于 scale profile / scale profile 优先于 stale memory / stale 仅兜底 / 全失效降级光圈）；`bbox_source` 新枚举过 validator；`display_state/bbox_stale/bbox_age_ms` 序列化
- [x] 6.3 后端集成测试：`_decide_display_entity` 在相同 evidence 序列下输出稳定 DisplayPlan；synthetic bbox 不回喂 memory/profile
- [x] 6.4 前端测试：`view_scale_profiled` 虚线、`bbox_stale` 淡化（基于 bbox_age_ms）、旧枚举兼容
- [x] 6.5 真实素材验收（`mvr_35ac365aec96` / job-95132a7a53）：重建 00:07 附近证据序列，报告固定指标 `box_point_transition_count / hidden_transition_count / synthetic_box_hold_duration_ms / real_observation_display_latency_ms / profiled_bbox_count / profile_fallback_failure_count`，并断言不变量：真实 observation 出现 → 当前 tick 显示真实框；无证据超 hard TTL → 不显示；synthetic bbox 不进 memory/profile；状态切换次数 ≤ baseline（先用真实素材跑出 baseline 再定阈值，不预设数字）
