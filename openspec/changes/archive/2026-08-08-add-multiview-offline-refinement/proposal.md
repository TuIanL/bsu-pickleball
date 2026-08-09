## Why

Change 2 的 `joint_tracking_v2`(F0,在线因果联合感知)在"当前 tick 没救回的困难样本"上仍会留缺口——一摄短暂丢失/弱观测时,第一遍只能靠 guidance + 低阈值 pre-gate 在线找,来不及利用未来信息。Change 3 用**离线第二遍(F1)**回看困难窗口,利用 donor 视角 + forward/backward 状态重新检测,再**重新融合**(re-fusion),经**安全门**判定后采用。完成 P1 闭环:`F0 = online-causal joint perception`,`F1 = offline bidirectional refinement`。

**能力边界**:本 Change 只扩展 `joint_tracking_v2` 的 JointRun 路径;`late_fusion_v1` / `MultiViewFusionRun` 永不接触 F1。

## What Changes

- **Recovery Plan**:从 F0 诊断挖掘 RecoveryWindow(窗口级资格:donor 强 + target 弱)+ 生成不可变 `RecoveryTickPlan`(**tick 级资格**:target source frame 存在 + target weak/missing + donor 为 per-tick 真实 base 观测)。
- **Offline Recovery(F1 第二遍)**:re-open 精确 source frame → **donor + forward + backward** 合成搜索 envelope(ROI)→ `detect_regions` → pre-gate → 轻量 `RecoveryTracklet`(窗口内,不用 F0 tracker)→ recovered observation(`observation_origin=offline_refinement`)。
- **F1 MUST NOT 修改 F0 状态**:永不触碰 `ViewTrackingSession` / `MultiObjectTracker` / `PlayerLockManager` / `PlayerIdentityManager` / `GlobalPlayerState` F0 history;输出仅为 `RecoveredViewObservation`。
- **Re-fusion(不是直接替换 sample)**:F1 recover 的是"一条新 view observation",不是"新 fused position"。original + recovered observations 重新执行既有 fusion math(`ViewIntrinsicQuality / PairConsistency / Conflict Gate / PlayerPositionFusion`)→ final temporal filtering → immutable F1。
- **`RefinementAcceptanceGate`**(真正的安全门,非异常 fallback):F0 vs F1 内部指标比较(eligible coverage / jump count / speed violations / conflicts / recovered residual / donor inconsistency / original-strong preservation),通过才 `refined_f1`,否则 `rejected_by_safety_gate` 回退 F0。
- **manifest 4 状态 + immutable artifacts**:`skipped_no_windows / completed / rejected_by_safety_gate / failed_fallback`;F0 / recovered / F1 独立 artifact 文件,F0 永不覆盖。
- **metric_eligible**:`offline_refinement` 是真实证据,MAY contribute to metric-eligible fused sample;最终 eligibility 由统一 fusion policy 决定。

## Capabilities

### New Capabilities
- `multiview-offline-refinement`: Recovery Plan / Offline Recovery / F0 状态只读 / Re-fusion / RefinementAcceptanceGate / manifest 4 状态 + immutable artifacts。

### Modified Capabilities
- `guided-player-redetection`: ADD 离线第二遍检测语义(复用 pre-gate,`offline_refinement` origin,F1 不修改 F0 tracker)。
- `multiview-analysis-result-composer`: ADD refinement manifest 生命周期(Parent 保持 running 直至 refinement 完成;`refinement.status` 4 态 / `final_source` / immutable artifacts)。

## Impact

- **代码**:
  - 新增 `app/vision/multiview/offline_refinement.py`(RecoveryWindow / RecoveryTickPlan / OfflineRecovery / RecoveryTracklet / RefinementAcceptanceGate)
  - 改造 `multiview_joint_run.py`(F0 输出 recovery-window 诊断)、`joint_artifact.py`(f0/f1/recovered 独立 writer + manifest refinement)、`multiview_joint_executor.py`(F0 → refinement → re-fusion → gate)
  - `guided_detection.py` 复用 pre-gate(离线路径,只读)
- **不涉及**:已归档 P0 / Change 0/1/2 产物;`late_fusion_v1` / `MultiViewFusionRun`;P0 核心算法类。
- **测试**:tick 资格(target frame 存在 / per-tick donor / source_frame_unavailable 不可 recover)、F1 不修改 F0 状态、re-fusion、safety gate 通过/拒绝、manifest 4 态、immutable F0。
