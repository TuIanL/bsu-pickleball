## 1. Recovery Plan

- [x] 1.1 新增 `app/vision/multiview/offline_refinement.py`:`RecoveryTickPlan { tick_id, take_timestamp_ms, global_player_id, target_view, target_source_frame_index, target_source_timestamp_ms, donor_view, donor_source_frame_index, donor_canonical_position, donor_quality, f0_global_position }`;`RecoveryWindow { ..., start_tick, end_tick, ticks: list[RecoveryTickPlan] }`
- [x] 1.2 窗口级挖掘:F0 诊断中 target_view weak/missing/lost 段 + donor 视角窗口整体强度 ≥ `donor_min_quality`
- [x] 1.3 **tick 级资格**:仅当 `target_source_frame_available=true`(source_frame_unavailable → NOT recoverable)+ target weak/missing + donor 当前 tick 为 original/base observed(非 predicted、非 weak guided)+ donor quality ≥ 阈值 → 生成 RecoveryTickPlan
- [x] 1.4 **plan 冻结**:RecoveryWindow + RecoveryTickPlan 生成后不可变,后续只读(F1 不二次 sync mapping)
- [x] 1.5 单测:source frame 不存在不可 recover、donor 为 predicted 不可 recover、per-tick donor 条件

## 2. Offline Recovery

- [x] 2.1 re-open target source video,按 `target_source_frame_index` 精确解帧
- [x] 2.2 合成搜索 envelope:**donor canonical observation(中心)+ forward boundary prediction + backward boundary prediction** → image-space ROI;边界 fallback 冻结(双边 / 仅 before / 仅 after / donor-only 更严 / donor 无则 skip tick)
- [x] 2.3 对 ROI 执行 `detect_regions` → 复用 guided pre-gate → donor + motion strict gate → `RecoveredViewObservation(observation_origin=offline_refinement)`
- [x] 2.4 实现 `RecoveryTracklet { recovery_window_id, previous_bbox, previous_canonical_position, consecutive_hits }`(窗口内连续证明,不用 F0 tracker)
- [x] 2.5 单测:donor 中心 ROI、forward+backward envelope、边界 fallback、RecoveryTracklet 连续证明

## 3. Safety / No Feedback

- [x] 3.1 **F1 MUST NOT 修改 F0 状态**:永不调用 F0 `ViewTrackingSession` / `MultiObjectTracker` / `PlayerLockManager` / `PlayerIdentityManager` / `GlobalPlayerState` F0 history 的 update
- [ ] 3.2 一轮上限:每个 RecoveryWindow 只跑一遍 F1;所有 recovered evidence 完成后统一冻结,再进入 Refusion(不做"recover tick100 → 更新轨迹 → 帮 recover tick101")
- [x] 3.3 拒绝的 recovered 直接丢弃,零副作用(invariant 9 + 3)
- [x] 3.4 单测:F1 不修改 F0 状态(git 式断言 tracker/lock/identity 状态不变)、一轮上限、拒绝零副作用

## 4. Refusion

- [ ] 4.1 实现 Refusion:original view observations + recovered observations → effective per-view observations(**original 强观测优先**)
- [ ] 4.2 复用既有 fusion math:`ViewIntrinsicQuality / PairConsistency / Conflict Gate / PlayerPositionFusion`,不重写
- [ ] 4.3 重新执行 final temporal filtering(从 F0 起点统一重跑),产出 immutable `fused_player_trajectory.f1.v2.json`
- [ ] 4.4 单测:re-fusion 后 fused sample、original 强观测优先、F1 是统一生成轨迹(非局部打补丁)

## 5. Acceptance + Manifest

- [x] 5.1 实现 `RefinementAcceptanceGate`:F0 vs F1 内部指标比较(eligible coverage / jump count / speed violations / conflict count / recovered residual P50/P90 / donor inconsistency / original-strong preservation)
- [x] 5.2 F1 采用规则:`accepted_recovered_count > 0` + `eligible_coverage(F1) >= eligible_coverage(F0)` + 新增 jump/conflict ≤ allowed_delta + 无 original 强观测被降级/替换 + residual 统计在门内;否则 `rejected_by_safety_gate` → F0
- [x] 5.3 manifest 4 状态:`skipped_no_windows / completed / rejected_by_safety_gate / failed_fallback`,对应 `final_source = first_pass_f0 | refined_f1`
- [ ] 5.4 immutable artifacts:`fused_player_trajectory.f0.v2.json`(永不覆盖)+ `recovered_view_observations.v1.json` + `fused_player_trajectory.f1.v2.json` + `refinement_diagnostics.json`;Parent canonicalStatus 在 refinement 完成前保持 running
- [x] 5.5 单测:gate 通过→refined_f1、gate 拒绝→rejected_by_safety_gate、无窗口→skipped_no_windows、异常→failed_fallback、F0 不可变

## 6. Metrics / Regression

- [x] 6.1 `offline_refinement` 为真实 evidence,MAY contribute to metric-eligible fused sample;最终 `metric_eligible` 由既有 fusion policy 统一决定(`predicted` 永不成为 metric evidence)
- [x] 6.2 joint executor 在 F0 后调用 offline refinement pass(late_fusion_v1 完全不感知)
- [x] 6.3 运行 `late_fusion_v1` 与 joint 既有测试套件全绿(回归);确认 P0 核心未被修改、不扩展 ball/pose/serve
- [x] 6.4 确认 invariant 6(一轮 + 先冻结再 re-fusion)与 invariant 4(predicted 不进指标)落实
