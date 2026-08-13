## Context

P1-A 的 `joint_tracking_v2` 已经完成 F0 online-causal joint perception，并在真实 authoritative 60 秒 run 中观察到 guided recovery。已有 F1 scaffold 也已经具备窗口挖掘、离线 ROI 检测、`RecoveryTracklet` 和四态 manifest，但当前实现与已归档的 `multiview-offline-refinement` 设计不一致：

- `multiview_joint_executor.py` 将 secondary detector、secondary homography 和 reference inverse homography 传给 F1，target view 不是 per-view 的。
- `RecoveryTickPlan.take_timestamp_ms` 使用 `tick * 1000 / 30`，不是 F0 canonical trace 的权威时间；forward/backward anchor 选择也不是窗口两侧最近有效状态。
- `refuse_f1()` 把 recovered observation 直接追加为 `FusedSample`，没有重新执行 pair consistency、quality weighting、conflict gate、position fusion 和 temporal filtering。
- recovered sample 被直接标记为 `metric_eligible=True`，且 `offline_refinement` 被用作 `fusion_status`，混淆 observation provenance 与融合状态。
- `RefinementAcceptanceGate` 的 coverage、jump、conflict、residual 等指标仍有简化或固定值，不能作为真实 F0→F1 发布门。

本 change 只修正和闭合 F1，不改变 F0 的 runtime state，不改变 `late_fusion_v1`，也不把 debug trace 或大体积 debug MP4 直接暴露给前端。

## Goals / Non-Goals

**Goals:**

- 建立不可变的 F0 refinement evidence snapshot，保留 canonical tick/timestamp、每路 source frame、view observation、global identity、origin、quality 和 frame availability。
- 为 Cam1/Cam2 提供独立的 `RefinementViewContext`，由 `RecoveryTickPlan.target_view` 选择 detector、geometry、orientation、frame provider 和 timing context。
- 使用 F0 canonical timestamp、窗口两侧最近有效 anchor 和 P1 配置中的 donor quality threshold 生成冻结的 `RecoveryTickPlan`。
- 在全部 `RecoveredViewObservation` 完成后，基于 original + recovered view observations 执行正式 re-fusion 和统一 temporal filtering，生成 immutable F1。
- 计算真实、可审计的 F0/F1 acceptance metrics，并区分 `completed`、`rejected_by_safety_gate`、`skipped_no_windows` 和 `failed_fallback`。
- 保持 F0、recovered、F1 和 refinement diagnostics 的独立 artifact 语义，F0 永不被覆盖。
- 通过 synthetic regression、真实 60 秒 authoritative F1 acceptance 后，再执行约 699 秒全程验收。

**Non-Goals:**

- 不修改 `joint_tracking_v2` F0 的 tracker、lock、identity、global registry 或 online guidance 语义。
- 不在 F1 中重新运行 F0 tracker、association 或改变既有 global player identity；F1 使用 F0 已冻结的 global identity 映射。
- 不重写融合数学；复用 `view_intrinsic_quality`、`pair_consistency`、`fuse_observation` 和既有 temporal filter 机制。
- 不修改 `late_fusion_v1`、`MultiViewFusionRun`、ball、pose、serve 或 action pipeline。
- 不实施 `AnalysisJobPage`、`improve-job-progress-visualization` 或 `surface-multiview-joint-observability`。
- 不把自然视频中的 F1 恢复数量当作算法普适性结论；真实 run 只验证输入与链路行为。

## Decisions

### D1. 以 F0 evidence snapshot 作为 F1 唯一输入

F0 完成后先冻结一个内部 `F0RefinementSnapshot`，至少包含：

```text
canonical_tick
canonical_timestamp_ms
reference_frame_index
per-view frame status/source frame/source timestamp/mapped timestamp
per-view original observations and detection_origin
global_player_id and F0 association identity
global position/prediction
metric eligibility scope
```

F1 只读该 snapshot。`RecoveryTickPlan` 的 `take_timestamp_ms`、target source frame 和 donor source frame 都从 snapshot 复制，禁止再次通过 FPS 推导时间或重新运行 sync mapping。当前任务生命周期内 snapshot 可在 executor 内存中传递；F0 artifact 先原子写出，确保 F1 失败仍可消费 F0。

备选方案是让 F1 重新读取 debug trace。该方案会把 opt-in debug trace 变成 F1 的必要输入，并使普通 joint run 无法运行 F1，因此不采用。

### D2. per-view `RefinementViewContext`

F1 接收 `dict[view_id, RefinementViewContext]`，每个 context 固定：

```text
view_id
frame_provider
detector
homography / inverse_homography
orientation
frame_width / frame_height
timing authority metadata
```

`target_view` 选择 target context，`donor_view` 只提供 frozen canonical evidence。Cam1 target 和 Cam2 target 必须走同一套 recovery 逻辑但各自的 detector/geometry。

备选方案是保留 `secondary_detector` 参数并对 reference target 做条件分支。该方案会继续保留 secondary-only 的隐性假设，且容易错误使用 reference geometry，因此不采用。

### D3. window/tick 资格和 anchor 选择

窗口级资格使用 P1 配置快照中的 `min_donor_quality`；tick 级资格必须同时满足 target frame available、target weak/missing/lost、donor 为该 tick 的 original/base observation、donor quality 达标。

对 target tick `t`：

- before anchor 取 `max(anchor_tick < t)`；
- after anchor 取 `min(anchor_tick > t)`；
- forward/backward 只用于 envelope 的一致性和不确定性边界，donor canonical position 始终是中心证据；
- 两侧都没有时使用 donor-only 的更严格门；donor 当前 tick 不合格时跳过。

所有窗口的 recovered evidence 生成完毕后才进入 re-fusion，禁止 recovered evidence 反哺下一 tick 的 donor、global state 或 tracklet 之外的任何状态。

### D4. recovered evidence 与 original evidence 的合并边界

`RecoveredViewObservation` 始终是 view-level measurement evidence，不是 `FusedSample`。在相同 `(global_player_id, canonical_tick, target_view)` 上：

- original strong/base evidence 保留并抑制 recovered duplicate；
- original weak evidence 可与 recovered 一起进入正常 quality/pair gate；
- original 缺失时 recovered 作为该 view 的候选 measurement；
- recovered 不能创建新的 global identity、cross-view anchor 或 F0 tracker state。

合并后使用现有 `CanonicalObservation`/`FusionMeasurement` 兼容模型，将 `observation_origin=offline_refinement` 保存在 `view_observations`，但 `fusion_status` 只能取既有融合状态。

备选方案是把 recovered 直接转换为一条 F1 fused sample。该方案绕过双视角 pair consistency 和 temporal filtering，正是当前错误，明确禁止。

### D5. formal re-fusion 与 temporal filtering

新增内部 `run_joint_refusion`（或等价的 JointRun refusion adapter），输入为 F0 frozen original observations、frozen recovered observations、F0 global identity map、canonical timing 和 fusion config。它复用：

```text
view_intrinsic_quality
pair_consistency
fuse_observation
GlobalTrackFilter / final temporal filtering
metric eligibility policy
```

F1 不重新做 F0 association；沿用 F0 global identity 仅是为了保证 offline refinement 不改变身份语义。re-fusion 从 F0 的 canonical tick 序列统一重跑，不能只在缺口处追加或局部替换样本。F0 和 F1 使用不同的 sample list 与文件，F0 对象不被原地修改。

### D6. metric eligibility 与 provenance 分离

`offline_refinement` 只写入 `observation_origin`/view evidence provenance。最终 `metric_eligible` 由 `fuse_observation` 和既有 policy 根据融合状态、质量、冲突和 prediction 决定；代码中不得出现 `offline_refinement => metric_eligible=True` 的硬绑定。`predicted` 永远不能成为 metric evidence。

### D7. 真实 acceptance gate

为 F0 和 Candidate F1 在相同 global/tick 范围计算可序列化指标：

```text
eligible_coverage
recovered_count
original_strong_preservation
jump_violation_count/rate
speed_violation_count/rate
conflict_count/rate
recovered_residual_p50/p90
donor_inconsistency_count
```

接受条件至少为：recovered_count > 0、F1 coverage 不下降、original strong evidence 未被降级、jump/conflict 增量在配置门内、speed violation 在配置门内、recovered residual P90 在阈值内、donor inconsistency 为 0。所有阈值写入 refinement diagnostics。门拒绝回退 F0 但保留 Candidate F1（若已生成）供 A/B；异常则为 `failed_fallback`。

### D8. artifact publication 顺序

发布顺序固定为：

```text
write F0 atomically
write recovered observations atomically when produced
write candidate F1 atomically when produced
write refinement diagnostics atomically
update Parent manifest/refinement last
mark Parent completed only after manifest is coherent
```

F1 不覆盖 F0。`completed` 时最终产品指向 F1；`rejected_by_safety_gate`、`failed_fallback`、`skipped_no_windows` 时最终产品指向 F0。已有无 refinement 字段的历史产物继续按 F0-only 读取。

## Risks / Trade-offs

- [Risk] F0 snapshot 体积增加或与 debug trace 重复 → Mitigation：snapshot 只保留 F1 所需的 view evidence，不作为浏览器产品数据；debug trace 仍 opt-in。
- [Risk] 真正 re-fusion 改变历史 F0 的 global identity 或序列长度 → Mitigation：固定 F0 global mapping、从完整 canonical tick 集重跑，并增加 F0 hash/样本不变性测试。
- [Risk] recovered observation 与弱 original 同时进入导致重复计数 → Mitigation：按 global/tick/view 做 deterministic precedence，并把 suppressed/duplicate reason 写入 diagnostics。
- [Risk] F1 运行时间显著增加 → Mitigation：只处理 tick-eligible RecoveryTickPlan，视频随机 seek 复用已有 runtime/frame provider，不对无窗口任务执行二次检测。
- [Risk] safety gate 过严导致真实素材长期回退 F0 → Mitigation：先用 synthetic fixtures 校准阈值，再用 60 秒 authoritative run 观察 diagnostics；门拒绝仍保留 F1 A/B 产物。
- [Risk] F1 异常时 Parent 状态和 artifact 不一致 → Mitigation：F0 先落盘、manifest 最后原子更新，异常统一写 `failed_fallback` 后再完成 Parent。

## Migration Plan

1. 先改 F1 contracts 和 executor wiring，补齐 per-view contexts、F0 snapshot、authoritative timestamp 和 threshold snapshot。
2. 实现 offline recovery 的双向 target path，固化最近 before/after anchor、local-space pre-gate、RecoveryTracklet 和 immutable recovered evidence。
3. 实现 Joint refusion adapter，删除 append-sample 路径，补充 origin/status/metric eligibility 的 schema regression。
4. 实现真实 F0/F1 metrics、AcceptanceGate 和原子 publication；验证 `late_fusion_v1` 回归。
5. 运行 synthetic tests 和已有 backend tests；再用同一 authoritative 60 秒窗口执行 F1 acceptance。
6. 60 秒通过后执行约 699 秒全程 run，记录 F0/F1 adoption、rejected/failed/skipped 状态和资源耗时。
7. 回滚时关闭 F1 或回退到 F0-only publication；已写出的 F0 artifact 保持可读，不删除历史文件。

## Open Questions

- 真实数据上的 jump/speed/conflict/residual 阈值需要由 60 秒 acceptance 与后续全程 run 校准；语义和配置可追溯性先冻结，具体数值不在本 proposal 中硬编码。
- 当前项目是否需要将 F0 refinement snapshot 作为独立 backend artifact 长期保留，留待长任务重启/断点恢复需求出现时再决定；本 change 先保证单次 executor 生命周期内可复现。
