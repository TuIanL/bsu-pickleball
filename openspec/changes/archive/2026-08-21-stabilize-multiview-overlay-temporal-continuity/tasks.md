## Stage 0 — Identity Visual Contract（身份视觉契约）

- [x] 0.1 提取纯函数 `resolvePlayerIdentityHue(playerId)`：`Player_N → identity hue` 固定 palette 跨 evidence 恒定；legacy ID（`P1`/`player_1`/`global_player_1`）先 normalise；unknown → deterministic hash palette（避免全部落到默认绿）
- [x] 0.2 让 `evidence_type` 只控制 provenance（实线/虚线/透明度/badge），MUST NOT 改变 identity hue；`refined_observed` / `bootstrap_backfill` 改用次级信号（badge/透明度）表达，不再拥有独立主色
- [x] 0.3 更新 `FusedPlayerBox` 渲染，使同一 `Player_N` 跨 evidence 主色恒定
- [x] 0.4 新增前端 contract 单测：对 `resolvePlayerIdentityHue` 断言同一 Player 跨 `base/guided/refined/cross_view/predicted` 颜色不变（`identity_color_switch_count == 0`）

## Stage 1 — Temporal FSM Closure（时间迟滞 FSM 闭环）

- [x] 1.1 修改 `OverlayDisplayStateMachine.step()`：真实 bbox 丢失且有 donor/global projected evidence 时，`display_state` SHALL 立即降为 `PROJECTED_BOX`（复用最后可靠 presentation geometry，MUST NOT 保留 `REAL_BOX`）；`evidence_type` 立即诚实降级为 `cross_view_projected`；`observed → predicted_only` 直接 `PREDICTED_POINT`（不用旧 bbox 画人体框）
- [x] 1.2 让 `projected_box_hold_ms` 真正控制 BOX→POINT（template 瞬失 ≤ hold 保持上一份 presentation box geometry）；计时从 `last_valid_box_geometry_ts` 起算（MUST NOT 从 `last_real_bbox_ts` 起算）
- [x] 1.3 状态字段明确区分：`last_real_bbox_ts`（hysteresis grace 用）、`last_valid_box_geometry_ts` + `last_valid_box_geometry`（hold 用）、`last_state_transition_ts`（诊断用）；不用一个泛化的 `last_box_ts` 承担三语义
- [x] 1.4 保持真实 observation 零延迟恢复（base/guided/accepted refined 恢复立即升回 BOX，不被 hysteresis / confirm counter / hold 延迟）
- [x] 1.5 保持 hard stop 最高优先级（geometry invalid / identity reset / 无有效 position / prediction TTL expired / job·roster reset）
- [x] 1.6 更新后端单测 `test_overlay_display_stability.py` 覆盖：「miss ≤ grace 保持 PROJECTED_BOX（非 REAL_BOX）」「miss 无 projected 证据直接 PREDICTED_POINT」「template 瞬失保持框且从 last_valid_box_geometry_ts 计时」「hard TTL 收敛」「real 恢复零延迟」

## Stage 2 — Renderer 接线与 Display_state 消费

- [x] 2.1 `FusedPlayerBox` 真正消费 `display_state`（决定 geometry topology：BOX / POINT / HIDDEN），拼接到 `evidence_type → provenance` 之上
- [x] 2.2 确认 `multiview-fused-player-overlay` entity 携带 `display_state` 且前端类型（`src/types/report.ts`）完整映射；旧产物缺失时用 `resolveEffectiveDisplayState(entity)`（由 `evidence_type + bbox + footpoint` 推导 legacy state）兼容降级
- [x] 2.3 前端播放/回放测试更新：断言 `display_state=PROJECTED_BOX`（迟滞降级中，复用 last-real geometry）即使 `evidence_type=cross_view` 仍渲染 BOX；`HIDDEN` 不渲染；旧产物缺字段不报错

## Stage 3 — Real-material Acceptance（真实素材量化验收）

- [x] 3.1 backend 真实素材验收：用既有 P1 job / `joint_debug_trace` 重建 Overlay（不重跑 detector/tracker/fusion），扩展 `accept_overlay_stability.py` 采集 `display_state_transitions_per_minute` / `box_point_transition_count` / `hidden_transition_count` / `short_hidden_gap_count` / `real_observation_display_latency_ms` / `synthetic_box_hold_duration_ms`
- [x] 3.2 frontend contract 验收：`resolvePlayerIdentityHue` / `resolveEvidencePresentation` / `resolveDisplayGeometry` / `resolveEffectiveDisplayState` 纯单测；`identity_color_switch_count == 0`
- [x] 3.3 反向 safety 硬门：`hard_ttl_violation_count == 0`、`max_hold_overrun_ms ≤ one canonical tick tolerance`（如 `projected_box_hold_ms=400` 实际 ≤ 400+tolerance）；（可选）`false_persistence_count` 确认球员离场后不赖屏
- [x] 3.4 权威数据不变量（hash 化）：展示层重建确定性校验——同一 trace 用全新状态机二次重建，state 序列 SHA256 一致（`35324398afed`）
- [x] 3.5 判定：真实素材窗口（P1@cam_1 4000–9000ms）`box_point_transition=0`、`short_hidden_gap=0`、`hard_ttl_violation=0`、`real_latency=0ms` → 主要频闪源（框↔点/颜色/瞬时降级）已消除；此素材不触发 Future Work A（short-gap restoration）