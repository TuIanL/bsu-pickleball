# Tasks: fix-multiview-reacquire-after-fusion-pollution

## 1. D1 — Prediction-aware conflict arbitration

- [x] 1.1 新增单测 `test_conflict_poison_rejects_cam2_outlier`（回归先行，失败态）：pre_tick_prediction≈cam_1；cam_2 相距 40ft 且 `conf=0.81 > cam_1=0.31` → `fuse_assignments` 必须选 cam_1（`fusion_conflict_cam1_selected`），不得因 confidence 选 cam_2
- [x] 1.2 修改 `fuse_assignments`：由 `@staticmethod` 改为 instance method，新增 `predictions` 参数（pre-tick prediction dict）；conflict 时**显式计算** `r_cam1 = dist(cam1, pred)`、`r_cam2 = dist(cam2, pred)`（不依赖 `pair_consistency` 的 `residual_to_prediction_ft`）
- [x] 1.3 实现 design D1 决策树：仅一路 plausible 选该路；两路 plausible 且 `|r1-r2| > residual_margin_ft`（默认 2.0）选 residual 更小者；两路 plausible 且 residual 接近时按 intrinsic 仲裁（接近再 continuity/binding tie-break）；两路都不 plausible → `conflict_no_measurement` 不产出 fused entry
- [x] 1.4 修改 `multiview_joint_run.py` 调用处：传入 tick barrier 冻结的 pre-tick prediction（复用 `f0_predictions[tick_number]` 或等价冻结预测）；`pair_consistency` 的 `predicted` 参数**不改**（保持 None，仅负责 inter-view/conflict 检测）
- [x] 1.5 新增单测 `test_conflict_both_implausible_no_measurement`：两路均超门限 → 不产出 fused entry（不 absorb、本 tick 无 metric sample），计 `fusion_conflict_no_measurement`
- [x] 1.6 新增单测 `test_conflict_both_plausible_residual_dominates_intrinsic`：cam1 residual 0.8ft/intrinsic 0.42 vs cam2 residual 5.5ft/intrinsic 0.87 → 必须选 cam1（residual 主导，intrinsic 不得反超）

## 2. D2 — Global measurement innovation guard

- [x] 2.1 新增单测 `test_innovation_guard_rejects_catastrophic_jump`（回归先行，失败态）：measurement 距预测 15ft、uncertainty ~1ft → `absorb_measurement` 返回 `accepted=False`，位置/速度不变，计 `measurement_innovation_rejected`
- [x] 2.2 新增 `MeasurementUpdateResult`（accepted/x_ft/y_ft/innovation_ft/gate_ft/reason）并修改 `GlobalPlayerRegistry.absorb_measurement()` 返回该结构：前置 guard `innovation > max(innovation_floor_ft, innovation_uncertainty_k × uncertainty)`（floor 独立配置，默认 8.0；k 默认 2.0）→ rejected 时不调 `estimator.update`
- [x] 2.3 新增单测 `test_innovation_reject_does_not_refresh_last_seen`：rejected 后 `last_seen_s` 不变、`roster_confirm_ticks` 不增、position/velocity/uncertainty 不变（reject 语义 = 没看见）
- [x] 2.4 新增单测 `test_innovation_guard_allows_legitimate_maneuver`：5ft 位移且 uncertainty 已扩展 → `accepted=True` 正常吸收，不误报

## 3. D3 — Trusted Historical Identity Reanchor（决策与执行分离）

- [x] 3.1 新增单测 `test_reanchor_restores_after_pollution`（回归先行，失败态）：prediction 偏 14ft + 历史绑定 `(cam_1, Player_2)→global_player_4` + G 处于 risk 状态 + 连续 3 帧稳定观测 + 无歧义 → associator 产出 `reanchor=True` 决策
- [x] 3.2 扩展 `AssociationUpdate` 增加 `reanchor` 标志；`process_tick` 弱历史绑定分支前插入 reanchor 五条件评估（含 `last_state_risk_tick` 窗口检查）；**associator 内 SHALL NOT 直接 reseed/absorb**
- [x] 3.3 修改 `multiview_joint_run.py`：fusion 后对 `reanchor=True` 的 update 执行 `registry.reseed(gid, x, y, t)`（position=观测、velocity=0、covariance=初始、timestamp=当前）；其余走 `absorb_measurement`——保持 JointRun 为唯一 state update owner
- [x] 3.4 新增单测 `test_reanchor_reseed_clears_pollution`：reanchor 后 estimator 位置=观测、velocity=0、covariance=初始值（不保留污染前速度）
- [x] 3.5 新增单测 `test_reanchor_rejects_ambiguous`：恢复观测对两个 global residual 都接近 → 不 reanchor，计 `reanchor_rejected_ambiguous`，走 unresolved
- [x] 3.6 新增单测 `test_reanchor_skips_when_not_risk`：G 无风险标记（或窗口已过）→ 不进入 reanchor 路径，仅按普通 gate 评估
- [x] 3.7 实现 risk 标记生命周期：`last_state_risk_tick` + `state_risk_reason`；清除条件（连续 M=5 帧 clean accepted / reanchor_succeeded / 超 `reanchor_risk_window_ticks`=90）；新增单测 `test_risk_marker_clears_after_clean_window`

## 4. D4 — Fusion / Innovation / Reanchor 可诊断事件（分层）

- [x] 4.1 associator `diagnostics`（纯计数）扩展键：`fusion_conflict / fusion_conflict_cam1_selected / fusion_conflict_cam2_selected / fusion_conflict_prediction_selected / fusion_conflict_no_measurement / measurement_innovation_rejected / reanchor_pending / reanchor_succeeded / reanchor_rejected_ambiguous`
- [x] 4.2 新增 `last_tick_fusion_decisions: list[dict]` 结构化明细：`{global_player_id, timestamp, cam1_xy, cam2_xy, inter_view_distance, r_cam1, r_cam2, intrinsic1, intrinsic2, gate, selected_source, reason}`
- [x] 4.3 `artifact.py` 仅汇总 JointRun 提供的 counters 落入 `fused_diagnostics`（含 `fusion_conflict_*` 与 `reanchor_*` 计数），不做 runtime 重推导
- [x] 4.4 新增单测 `test_diagnostics_conflict_attribution`：构造 conflict 场景 → diagnostics 含两路 residual 与 selected_source 归因（经 `last_tick_fusion_decisions` 与聚合计数）

## 5. 回归与验收

- [x] 5.1 新增 D1 regression 单测 `test_single_view_active_not_stale_regression`：单视图持续活跃玩家仍不因 stale 被踢出（防 D1/D2/D3 回退 `fix-multiview-single-view-fallback`）
- [x] 5.2 跑 `pytest backend/tests/` 全量回归（重点 `test_multiview_*`、`test_global_roster`、`test_fused_overlay`、`test_multiview_artifact`）
- [x] 5.3 跑 `npm test` 前端回归
- [x] 5.4（用户手动重跑 job-131dcc0477 验收通过，见 5.5 数据） 真实 60s acceptance：外接盘挂载后重跑同源 joint job（cam_1=174/identity + cam_2=175/rotate_180，clip 0–60s），验收窗口 24–30s：
  - 25.83s 附近异常 cam_2 不污染 P4 state（gpos 保持 [19.8,-3.4] 邻域）
  - 26.367s cam_1/Player_2 恢复后重新形成 P4 observation
  - `global_player_4` fused sample 穿过 26.2s 继续
  - 27s overlay P2 有 REAL_BOX；P4 轨迹持续到 60s 末尾
  - **不强求 `reanchor_succeeded`**：D1 修好后 26.2s 后大概率无需 reanchor（ordinary reacquire 成功即达标；仅当确实形成 catastrophic drift 时才要求 reanchor 恢复）
- [x] 5.5（P4 samples 658→1667、last ts 26.20→59.97、27s REAL_BOX、conflict 归因生效） 验收产物对比（方向修正：不要求 fallback 下降）：
  - P4 total sample count（旧 658 → 新应显著增加）
  - P4 last sample timestamp（旧 26.20s → 新应 ≥ 59s）
  - 26.367s–60s P4 trajectory coverage / longest fused gap（旧 33.8s 死区 → 新应大幅缩短）
  - 27s overlay 是否 REAL_BOX
  - `fused_diagnostics` 出现 `fusion_conflict_cam1_selected`/`no_measurement`（D1 生效证据）；`single_view_fallback_by_player[P4]` 允许上升（P4 活得更久、cam_2 对 P4 长期不可靠时 fallback 增加是正确结果）
- [x] 5.6（cam_2 离群观测经 D1 归因为 conflict，reanchor 未触发属预期，详见 memory） 更新 design.md Open Questions：根据 acceptance 数据回填 cam_2 离群观测首帧证据与 reanchor 参数（residual_margin / risk window / N 帧）标定结论
