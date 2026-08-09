## Context

Change 2 的 `MultiViewJointRun`(F0)是 online-causal 联合感知:每 tick 用 pre-tick global state 预测生成 guidance,在线 pre-gate + `tracker.update ONCE`,无法利用未来帧。F0 已在 fused trajectory + diagnostics 里暴露 `view_status / quality / conflict / missing gaps`。

本 Change 引入 **F1 离线精修**:F0 跑完后,回看困难窗口,利用 donor 视角 + forward/backward 状态重新检测,再**重新融合**。这是 P1 的最后一环。

**能力边界**:本 Change 只扩展 `joint_tracking_v2` 的 JointRun 路径;`late_fusion_v1` / `MultiViewFusionRun` **永不接触 F1**。

前置:Change 2 已完成(executionMode / CanonicalAnalysisClock / GlobalPlayerState / GlobalPlayerAssociator / guidance / guided pre-gate / joint run / v2 artifact / composer)。

## Goals / Non-Goals

**Goals:**

- 挖掘 RecoveryWindow + 生成不可变 `RecoveryTickPlan`(含 target source frame 可用性 + per-tick donor)。
- F1 第二遍:re-open 精确 source frame → donor + forward + backward 合成搜索 envelope → `detect_regions` → pre-gate → `RecoveryTracklet` → recovered observation。
- **F1 永不修改 F0 的 tracker / lock / identity / global state**;输出仅为 `RecoveredViewObservation`。
- **Re-fusion**:original + recovered observations 重新执行既有 fusion math → final temporal filtering → immutable F1。
- **`RefinementAcceptanceGate`**:真正的安全门(非异常 fallback),决定 `refined_f1` 或回退 F0。
- manifest 4 状态 + immutable artifacts(F0 永不覆盖)。

**Non-Goals:**

- 不改已归档 P0 / Change 0/1/2 产物;不碰 `multiview-fusion-run` 能力。
- 不新增第三遍以上(refinement 严格一轮,invariant 6)。
- 不把 recovery 扩展到 ball/pose/serve(仍是球员位置协同)。
- 不引入新外部依赖;不重写融合数学(复用)。

## Decisions

### D1: Recovery Plan(窗口 + tick 两级资格 + 冻结)

**Window eligibility**(发现"这里值得尝试"):
```text
某视角(target_view)在窗口内存在 weak/missing/lost 段
AND donor 视角(另一视角)在该窗口整体观测强度 >= donor_min_quality
```

**Tick eligibility**(真正允许执行 recovery)—— per-tick 条件,满足才生成 `RecoveryTickPlan`:
```text
target source frame 存在(target_source_frame_available == true;source_frame_unavailable → NOT recoverable)
AND target observation ∈ {weak, missing, lost}
AND donor 当前 tick 有真实观测(donor 是 original/base observed,非 predicted、非 weak guided)
AND donor quality >= donor_min_quality
```

`RecoveryTickPlan`(不可变,随窗口一起冻结):
```python
RecoveryTickPlan {
    tick_id; take_timestamp_ms
    global_player_id
    target_view
    target_source_frame_index; target_source_timestamp_ms
    donor_view
    donor_source_frame_index; donor_canonical_position; donor_quality
    f0_global_position
}
```
`RecoveryWindow { global_player_id, target_view, donor_view, start_tick, end_tick, ticks: list[RecoveryTickPlan] }`。

**理由**：
- source-frame 不可用 ≠ 检测缺失——Change 3 只能恢复"帧存在但没检测到人",不能恢复"帧根本不存在"。
- RecoveryTickPlan 冻结保证 F1 重读的就是 F0 当时的源帧,不二次 sync mapping,可复现。
- donor 必须是 **per-tick** 的真实 base 观测(最保守的 `authoritative donor origin = base`),窗口聚合质量高不代表每 tick 都能 recovery。

### D2: Offline Recovery(不修改 F0 状态)

对每个 RecoveryTickPlan 的 target tick:

```text
Re-open target source video → 精确解 target_source_frame_index
        ↓
搜索 envelope(donor 为中心):
    donor canonical observation(中心证据)
    + forward boundary prediction(窗口前 F0 状态 → t)
    + backward boundary prediction(窗口后 F0 状态 → t)
        → image-space ROI(覆盖三证据一致区 + uncertainty)
        ↓
detect_regions
        ↓
guided PRE-GATE(bbox sanity → footpoint → projection → canonical residual)
        ↓
RecoveryTracklet(可选,轻量,仅存在于窗口内):
    { recovery_window_id, previous_bbox, previous_canonical_position, consecutive_hits }
        ↓
donor + motion strict gate
        ↓
RecoveredViewObservation
```

**边界 fallback(冻结)**:双边 anchor 有 → donor+forward+backward;只有 before → donor+forward;只有 after → donor+backward;都无 → donor-only(要求更严 donor quality / 更小 max uncertainty);donor 当前 tick 也无 → skip tick。实现不得出现临时 `if before_state is None` 自由发挥。

**理由**：donor 此刻看得清楚,它的 canonical 位置是极强空间先验;forward/backward 用于 consistency 与 uncertainty envelope,而非唯一 ROI 来源。真实快速跑动时 forward/backward 会滞后,donor 中心化 ROI 不会开偏。

### D3: F1 MUST NOT 修改 F0 状态(硬不变量)

F1 第二遍 SHALL 永不修改 F0 的:
- `ViewTrackingSession` / `MultiObjectTracker` / `PlayerLockManager` / `PlayerIdentityManager`
- `GlobalPlayerState` 的 F0 history

因为 F0 tracker 已完整跑到视频结尾,F1 回头喂 `frame_1800` 在状态机上非法(除非从 1800 整个 replay 到结尾,但那已不是 targeted refinement)。F1 是一条**独立、只读 F0 状态**的路径,输出仅为 `RecoveredViewObservation`。需要连续多帧证明时用窗口内轻量 `RecoveryTracklet`,不用原 tracker。

**理由**：offline refinement 的安全边界干净——不改任何在线状态,失败/丢弃零副作用。

### D4: Re-fusion(不是直接替换 sample)

F1 recover 的本质是"target camera 新获得一条真实 view observation",不是"一个新的 fused position"。因此拆两个阶段:

```text
Phase A — Recovery(immutable):
    F0 evidence(只读)
        → offline redetection → RecoveredViewObservation[]
        → 全部冻结

Phase B — Refusion:
    Original JointViewObservations
    + RecoveredViewObservations
        → effective per-view observations(original 强观测优先)
        → 重新执行既有 fusion math(ViewIntrinsicQuality / PairConsistency / Conflict Gate / PlayerPositionFusion)
        → final global temporal filtering(从 F0 开始统一重跑)
        → immutable F1 trajectory
```

**绝不**直接 `recovered Cam1 position → 覆盖 F0 fused position`,否则绕过双摄质量加权 / inter-view consistency / conflict detection / metric eligibility。

**理由**：F1 必须是一条统一生成的轨迹(如 t1=(8,20),t2=F0 missing, t3=(12,20);F1 找回 t2=(10,20) 后,重新跑时间滤波才不是"局部打补丁")。

### D5: RefinementAcceptanceGate(真正的安全门)

新增 `RefinementAcceptanceGate`,在 F1 生成后、发布前判定(无需 GT,用确定性内部指标):

```text
F0 vs F1 比较:
    eligible coverage
    trajectory jump count / rate
    speed violation count
    conflict count
    recovered residual P50/P90
    donor inconsistency count
    original strong-observation preservation

F1 accepted iff:
    accepted_recovered_count > 0
    AND eligible_coverage(F1) >= eligible_coverage(F0)
    AND new_jump_violations <= allowed_delta
    AND new_conflicts <= allowed_delta
    AND 无 original strong observation 被降级/替换
    AND recovery residual 统计在门内
否则:
    refinement.status = rejected_by_safety_gate
    final_source = first_pass_f0
```

**与 failed_fallback 区别**:failed_fallback = 算法执行异常;rejected_by_safety_gate = 算法正常执行但结果不值得采用。两者都回退 F0,但语义不同,实验统计要分开。

**理由**：一个算法无 exception 但恢复错两个人,不能被当成 `completed → refined_f1`。必须显式门控。

### D6: manifest 4 状态 + immutable artifacts

```text
refinement.status:
    skipped_no_windows     → final_source = first_pass_f0
    completed              → final_source = refined_f1
    rejected_by_safety_gate→ final_source = first_pass_f0
    failed_fallback        → final_source = first_pass_f0
```

产物文件(绝不覆盖 F0):
```text
joint run/
    fused_player_trajectory.f0.v2.json     ← F0 immutable
    recovered_view_observations.v1.json    ← recovery provenance
    fused_player_trajectory.f1.v2.json     ← F1(若生成)
    refinement_diagnostics.json            ← 门控/比较
```

Parent manifest:
```text
playerTrajectory         → 按 final_source 指向 F0 或 F1
refinement.firstPassArtifact      → F0
refinement.recoveredObservations  → recovery provenance
refinement.refinedArtifact        → F1(若生成)
```

Parent `canonicalStatus` 在 refinement 完成前保持 `running`。历史产物缺 refinement 字段 → 视为 F0-only。

**理由**：`first_pass_artifact` 若被 F1 原地覆盖,F0 vs F1 的 A/B 就丢了。

### D7: metric_eligible 措辞

`offline_refinement` 是真实图像证据(经 pre-gate + recovery gate),**MAY contribute to a metric-eligible fused sample**;最终 fused sample 的 `metric_eligible` 仍由既有 fusion / metric eligibility policy 统一决定(如 recovered 与 donor 重新 fusion 后触发 conflict → 按正常 policy)。原则:

```text
predicted           → 永远不能成为 metric evidence
offline_refinement  → 属于真实 evidence(可参与 metric-eligible fused sample)
最终 fused sample   → 走正常 eligibility policy
```

**理由**：不把 `offline_refinement => true` 硬绑定;最终 eligibility 由统一 fusion policy 决定。

### D8: 完整 F1 流程(冻结)

```text
F0 IMMUTABLE
    → Freeze RefinementPlan(只读 F0,不读任何 recovered)
    → RecoveryWindow mining → RecoveryTickPlan[]
    → Re-open target source video
    → donor + forward + backward evidence → image-space ROI
    → detect_regions → PRE-GATE → optional RecoveryTracklet → donor + motion strict gate
    → RecoveredViewObservation(所有窗口完成后统一冻结)
    → Original ViewObs + Recovered ViewObs → RE-FUSION → final temporal filtering → F1
    → RefinementAcceptanceGate → PASS(refined_f1) | REJECT(first_pass_f0)
    → Parent manifest → completed
```

核心:"先把所有 recovery evidence 冻结,再统一生成 F1"——invariant 6 天然成立,不会出现"recover tick 100 → 更新轨迹 → 帮 recover tick 101"。

## Risks / Trade-offs

- **[Risk] F1 引入新错误(观众/噪声当 recovered)** → 缓解:donor 中心 envelope + per-tick donor gate + `RefinementAcceptanceGate`(D5)。
- **[Risk] 循环自证** → 缓解:先冻结全部 recovered 再 re-fusion(D8),invariant 6。
- **[Risk] F1 劣于 F0** → 缓解:re-fusion + AcceptanceGate(rejected_by_safety_gate 回退 F0)。
- **[Risk] 离线重检成本** → 缓解:只重检 tick-eligible 的 RecoveryTickPlan(donor 强 + target 弱 + 帧存在)。
- **[Risk] 边界 anchor 缺失** → 缓解:D2 边界 fallback 冻结(before-only/after-only/none)。

## Migration Plan

- 新增 F0/F1/recovered 独立 artifact 文件;manifest `refinement` 字段向后兼容(旧产物 F0-only)。
- joint executor 在 F0 后调用 offline refinement pass;`late_fusion_v1` 完全不感知。
- 回滚 = revert 提交;F0-only 产物完全有效。

## Open Questions

无阻塞项。Recovery/门控阈值(`missing_after_ticks` / `donor_min_quality` / `allowed_delta` / residual 分位)留实验调参,语义已冻结。
