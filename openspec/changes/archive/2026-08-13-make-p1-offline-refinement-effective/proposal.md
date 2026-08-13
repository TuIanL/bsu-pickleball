## Why

P1-A 的 online joint recovery 已通过真实 authoritative 60 秒 run，但现有 F1 scaffold 仍保留 append-sample 式近似实现：离线恢复没有完整 per-view 上下文，recovered observation 没有经过正式 re-fusion，安全门使用了简化指标。因此 F1 目前不能可靠地宣称“恢复后结果更好且没有恶化”，需要现在把已有设计闭合为可发布的 correctness 实现。

## What Changes

- 将 F1 offline refinement 改为真正的 per-view 流程：每个 `target_view` 使用自身 detector、homography、inverse homography、orientation、frame geometry 和 timing context，支持 Cam1/Cam2 双向离线恢复。
- 保持 `RecoveryWindow`、`RecoveryTickPlan` 和 `RecoveredViewObservation` 为独立证据契约；时间戳必须来自 F0 canonical trace，窗口两侧 anchor 必须选择最近的有效边界证据，donor 阈值必须来自 P1 配置。
- 删除 append recovered `FusedSample` 的近似路径。冻结全部 recovered observations 后，将原始 view observations 与 recovered observations 一起重新执行正式的 pair consistency、quality weighting、conflict gate、position fusion 和 temporal filtering，生成独立 F1。
- 取消 recovered evidence 对 `metric_eligible` 的强制赋值；最终资格由既有 fusion/metric policy 判定，`fusion_status` 继续表达融合状态而不是 observation origin。
- 将 `RefinementAcceptanceGate` 改为真实的 F0/F1 acceptance gate，计算 eligible coverage、original strong preservation、trajectory jump、speed violation、conflict、recovered residual P50/P90、donor consistency 和 recovered count。
- 保持四种 refinement 状态与 F0/F1/recovered immutable artifacts，并确保只有通过安全门才发布 F1；执行异常与安全门拒绝必须区分。
- 增加 synthetic regression、双向恢复、F0 不变性、真实 60 秒 authoritative F1 acceptance 和通过后的 699 秒全程验收；`late_fusion_v1` 不受影响。

## Capabilities

### New Capabilities

无。本 change 修正已有 F1 能力，不新增独立能力域。

### Modified Capabilities

- `multiview-offline-refinement`: 将 F1 从 append-sample 近似实现收敛为 per-view recovery、正式 re-fusion、temporal filtering 和真实安全门。
- `guided-player-redetection`: 明确 offline recovered evidence 的 target-view geometry、timestamp、pre-gate 和 provenance 契约，且不得修改 F0 runtime state。
- `multiview-analysis-result-composer`: 明确 F0/F1/recovered immutable artifact、refinement manifest 生命周期和最终产物选择语义。

## Impact

- Backend：`backend/app/vision/multiview/offline_refinement.py`、`multiview_joint_run.py`、`joint_artifact.py`、`fusion.py`/`pipeline.py` 相关复用边界，以及 `backend/app/services/multiview_joint_executor.py` 和 Composer。
- Tests：扩展 F1 单元、双向 synthetic integration、re-fusion/metric eligibility、safety gate、manifest 和真实 CaptureTake acceptance 测试。
- Artifact：新增或修正 F0、recovered、F1、refinement diagnostics 的稳定 schema/落盘语义；不覆盖历史 F0，不改变 `late_fusion_v1`。
- Frontend：不修改 `AnalysisJobPage`、任务进度 change 或可观测性 UI；debug summary/MP4 展示另立 change。
- Runtime：真实 60 秒 authoritative run 作为第一份 F1 acceptance fixture；通过后才执行约 699 秒全程分析。
