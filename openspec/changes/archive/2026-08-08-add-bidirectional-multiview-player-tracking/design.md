## Context

P0（`late_fusion_v1`）的执行边界:`MultiViewFusionRun` 等待两个 source AnalysisJob → 读 `player_render_trajectory` → `run_fusion_pipeline()` → Composer;`MultiViewAnalysisExecutor` 是"纯 artifact 数学(不解码视频)"。

本 Change 引入第二个执行模式 `joint_tracking_v2`,让 `GlobalPlayerState` 在视频分析过程中就存在。P0 完整保留为兼容路径 + A/B baseline。

前置完成:Change 0 修复 `min_cost_matching` rectangular / per-candidate prediction(已成为共享 primitive);Change 1 抽出 `ViewTrackingSession`(含 `guidance` 钩子、`detect_regions` 契约、工厂 + DI)。

**本 Design 的核心原则:Additive P1。** P0 的核心算法类在 `late_fusion_v1` 路径下语义完全不变;P1 的能力全部由新类承载,只在 `joint_tracking_v2` 执行路径生效。绝不出现"executionMode 看起来兼容、底层却偷偷改变 P0"。

## Goals / Non-Goals

**Goals:**

- 引入 `multiviewExecutionMode`(late_fusion_v1 | joint_tracking_v2),两模式共存,历史任务零迁移。
- **Additive P1**:P0 核心算法类(`GlobalTrackFilter` / `CrossViewPlayerAssociator` / `CanonicalTimelineBuilder` / `MultiViewFusionRun`)语义不变;P1 用新类(`GlobalMotionEstimator` / `GlobalPlayerRegistry` / `GlobalPlayerAssociator` / `CanonicalAnalysisClock` / `MultiViewJointRun`)。
- 持久化 joint 输入(`jointViewInputs`)、`jointRunId`、`executionMode` 进 `inputSignature`(A/B 不被幂等去重)。
- Canonical clock source-frame 单调不重复;guided re-detection **residual pre-gate 在 tracker 之前**。
- `CrossViewGuidancePolicy` 冻结触发语义;`confirmed + cross_view_anchored` 才允许强 guidance。
- `JointViewRuntime` / `ReferenceRichAnalysisContext` 承载 runtime glue;`fused_player_trajectory.v2` 独立 writer + 公共 version-aware reader。

**Non-Goals:**

- 不改已归档 P0 文档;不改 Change 0/1 产物。
- 不实现 offline refinement(Change 3)。
- 不扩展 ball/pose/serve/action 到双摄协同(cam_2 perception scope)。
- 不引入新外部依赖;不重写位置融合数学(复用 P0 fusion)。
- 第一版不做 checkpoint resume(restart-from-zero)。

## Decisions

### D0: Additive P1(新硬不变量)

P0 / late_fusion_v1 的 `GlobalTrackFilter` / `CrossViewPlayerAssociator` / `CanonicalTimelineBuilder` / `MultiViewFusionRun` SHALL 语义完全不变。P1 能力全部由新类承载:

```text
P0 / late_fusion_v1:               P1 / joint_tracking_v2:
  GlobalTrackFilter                   GlobalMotionEstimator      (新)
  CrossViewPlayerAssociator           GlobalPlayerRegistry       (新)
  CanonicalTimelineBuilder            GlobalPlayerAssociator     (新)
  MultiViewFusionRun                  CanonicalAnalysisClock     (新)
                                      MultiViewJointRun          (新)
```

Change 0 的 `min_cost_matching()` 作为共享 primitive 被新 `GlobalPlayerAssociator` 复用;P0 reference-centric associator 本身**不被改成** global-centric。

**理由**：避免"executionMode 看起来兼容,底层却偷偷改变 P0";A/B 对比的变量才是"是否存在协同感知与 guided recovery"。

### D1: 执行模式 + 持久化输入

- 字段名冻结:`multiviewExecutionMode = late_fusion_v1 | joint_tracking_v2`,缺省 `late_fusion_v1`。
- joint 模式持久化输入:`jointViewInputs: [JointViewInput { cameraSlot, captureTrackId, cameraId, videoId, calibrationId, courtOrientation }]`,Parent `sourceJobs = []`。**必须进入 `AnalysisJobSummary` 持久化**(重启后能重建 `MultiViewJointRun`,不能只靠内存)。
- 保留 `cameraId`:sync calibration 可能以真实 camera id 为 mapping key(非 `cam_1/cam_2`),不要依赖 P0 `_resolve_secondary_sync_key()` 猜测逻辑。
- **`executionMode` 进入 `inputSignature`/`configSignature`**:否则同一 CaptureTake 的 late_fusion_v1 与 joint_tracking_v2 会被幂等/去重当成同一分析任务,直接破坏 A/B baseline。

**理由**：joint 无 child 后,P0 的 `Parent.sourceJobs → child.videoId/calibrationId` 持久化链断裂;必须显式持久化 joint 输入。

### D2: CanonicalAnalysisClock —— source-frame 单调不重复

`FrameSample` 正式定义:

```python
@dataclass
class FrameSample:
    source_frame_index: int
    source_timestamp_ms: float
    mapped_take_timestamp_ms: float
    selection_error_ms: float | None
    frame: object
```

`SynchronizedFrameBundle { take_timestamp_ms, views: dict[str, FrameSample | None], frame_status, mapping_diagnostics }`。

**关键不变量:同一 `ViewTrackingSession` 的 `source_frame_index` 必须严格单调、不重复消费。** Cam2 后挂的是有状态 tracker;若两个 canonical tick 映射到同一 Cam2 source frame 且两次 `session.step()`,就违反 D11 invariant 2(每 source frame 至多 update 一次)。

处理规则:
- 记录 `last_consumed_source_frame_index[view]`。
- 若当前 tick 映射到已消费过的 secondary frame → `views.cam_2 = None` / `frame_status = no_new_frame`,**不调用 step**。
- 测试必含:两个 canonical tick 映射同一 Cam2 frame → Cam2 `session.step()` 只调用一次。

### D3: GlobalMotionEstimator(新类,冻结 motion model)

新增 `GlobalMotionEstimator`,不动 P0 `GlobalTrackFilter`。

**冻结 motion model:4-state constant-velocity Kalman `[x, y, vx, vy]` + covariance**。不保留 "Kalman / α-β" 斜杠——`position_uncertainty_ft` 是 guidance ROI 的核心输入,两种算法的 uncertainty 概念不同,不能留到编码时自由发挥。

- `predict(t) → (position, covariance)`;ROI 尺寸由 prediction covariance 自然推导。
- 吸收真实融合测量更新状态并缩小 covariance;`predicted` 样本不回灌(避免自我喂养)。

**理由**：需要 predict position + prediction covariance;Kalman 协方差天然给出 uncertainty。α-β 若要坚持,必须定义 uncertainty 随 dt 增长/测量后缩小,本 Design 直接选 Kalman 避免开放项。

### D4: GlobalPlayerAssociator(新类,非修改 P0)

新增 `GlobalPlayerAssociator` 做观测→global 分配:

```text
GlobalState.predict(t)
    ├── assign Cam1 observations → global states
    ├── assign Cam2 observations → global states
    ├── unmatched observations → tentative global candidates
    └── fusion/update GlobalState(t)
```

复用 Change 0 的 `min_cost_matching()` 作为共享 primitive;P0 `CrossViewPlayerAssociator`(reference-centric)语义不变,只在 `late_fusion_v1` 使用。

### D5: 每 tick 流程

```text
GlobalState(t-1) → predict(t) → guidance snapshot (per CrossViewGuidancePolicy)
        ├── View A: base + guided(pre-gated) → merge → tracker.update ONCE
        └── View B: base + guided(pre-gated) → merge → tracker.update ONCE
                        → tick barrier
        → GlobalPlayerAssociator → 复用 P0 fusion math → GlobalState(t)
```

- **MUST:同一 tick 两路用相同 pre-tick snapshot**。
- **MUST:每 view 每 source frame `tracker.update()` 至多一次**(由 D2 clock 保证不重复喂帧)。
- **MUST:tick barrier 后才更新 global**。
- **位置融合复用 P0 已有 mathematics**:`ViewIntrinsicQuality / PairConsistency / Conflict Gate / PlayerPositionFusion`。不要 Change 2 重写"两个位置怎么融合"——否则 A/B 对比会连融合数学一起换,实验无法解释。
- V1 串行执行两路、共享模型实例;Future 允许并行(pre-tick snapshot + tick barrier 语义不变)。

### D6: CrossViewGuidancePolicy + guided re-detection pre-gate

**触发策略(冻结,防"每个 confirmed × 每个 view × 每 tick 都跑 ROI YOLO"):**

```text
confirmed global
AND target-view binding ∈ {weak, missing, lost}
AND other-view/global evidence strong
AND uncertainty <= max_guidance_uncertainty_ft
AND guidance_cooldown 已过
→ 生成 guidance
```

- `ViewBinding { visibility: observed | weak | missing | lost, last_seen_take_timestamp_ms, quality }`。
- 只有 weak/missing/lost 触发 high-recall ROI;上一 tick 已稳定 observed 则不再每帧补跑。
- `CrossViewGuidancePolicy` 冻结参数(值之后实验调,语义现在定):`min_global_confidence` / `max_uncertainty_ft` / `missing_after_ticks` / `guidance_cooldown_ticks` / `max_regions_per_view_per_tick`。

**guided re-detection 顺序修正:residual PRE-GATE 必须在 `tracker.update` 之前。**

```text
base detection
+
guided ROI detection
        ↓
guided candidate PRE-GATE
        ├─ bbox/image sanity
        ├─ candidate footpoint
        ├─ Homography projection
        ├─ canonical residual
        └─ motion residual
        ↓
只保留 accepted guided candidates
        ↓
与 base detections merge / deduplicate
        ↓
tracker.update ONCE
```

- Candidate **无需 track id**:从 `Detection.bbox → 临时 footpoint → image_to_court → canonical` 先做 candidate validation。
- pre-gate 拒绝的 guided detection **绝不碰 tracker**(否则低阈值找错的人先污染 track state,gate 才发现错,即使不输出 measurement,tracker 已被污染)。
- tracker 之后可做 second validation,但 pre-gate 是第一道硬门。

### D7: lifecycle confirmed 与 cross_view_anchored 分离

```python
GlobalPlayerState {
    lifecycle: tentative | confirmed | lost
    cross_view_anchored: bool   # 新增
    ...
}
```

- `lifecycle = confirmed` 可仅由单摄稳定达成(不阻止 local identity 稳定)。
- `cross_view_anchored = true` 仅当历史上存在 **≥N 次稳定双视角 canonical 一致观测**。
- **强 guidance 要求 `confirmed AND cross_view_anchored`**。单摄错误锁定不能主动去另一摄"找证据证明自己"(防自证闭环)。

**理由**：第一版不接受"非常稳定的单视角 locked player → 直接产生 guidance"。

### D8: JointViewRuntime + ReferenceRichAnalysisContext

Change 1 把 decode/gate/ROI/calibration/ball/pose/debug/progress/final 留在 Pipeline 外层。Change 2 不能直接 `JointRun → ViewTrackingSession A/B`,需要 runtime glue:

```python
@dataclass
class JointViewRuntime:
    view_input: JointViewInput
    capture: object          # 视频解码
    fps: float
    frame_size: tuple[int, int]
    homography: list[list[float]]
    roi_artifact: object
    court_view_scorer: object
    court_view_state: object
    tracking_session: ViewTrackingSession
    scope: Literal["full", "perception"]
    counters: dict[str, int]
```

```text
MultiViewJointRun
    ├─ JointViewRuntime(cam1, full)
    └─ JointViewRuntime(cam2, perception)
```

CanonicalAnalysisClock 只告诉 runtime 下一 `source_frame_index`;ViewRuntime 负责解帧 / court-view gate / `session.step` / per-view diagnostics。否则 Joint Executor 会复制一遍 AnalysisPipeline 外层的几十段逻辑。

**cam_1 full scope 的 pose/ball/overlay 在哪跑:**

```text
Cam1 JointViewRuntime
    player perception → ViewFrameResult
        ↓
    ReferenceRichAnalysisContext
        ├─ pose
        ├─ ball
        ├─ debug
        └─ 后续 serve/action helpers
```

都消费**同一次 reference frame decode** 的 `ViewFrameResult`。**不要**为了 "full" 再调用一次完整 `AnalysisPipeline.run()`——否则 Cam1 视频又解码第二遍、local tracking 重跑一遍。

### D9: v1/v2 独立 writer + 公共 version-aware reader

```text
late_fusion_v1 → writer_v1 → fused_player_trajectory.v1   (P0 writer 永远保留)
joint_tracking_v2 → writer_v2 → fused_player_trajectory.v2
```

新增公共 loader:

```python
def load_fused_trajectory(path) -> NormalizedFusedTrajectory:
    if schema == v1: return normalize_v1(...)
    if schema == v2: return normalize_v2(...)
```

Composer 消费 normalized internal model。**不依赖"v2 字段向后兼容,reader 能读新 schema"的假设**——"字段向后兼容"和"reader 能读取新 schema_version"是两回事。A/B 是两个稳定版本,而非 joint 上线后把 late 的 writer 一起升级。

### D10: orchestrationStatus 冻结 + jointRunId + 失败语义

**状态枚举现在冻结(进入 is_runnable / reconciliation / cancel / restart / 前端进度):**

```text
late_fusion_v1:  waiting_sources / fallback_ready / fusion_ready / fusing / composing / completed
joint_tracking_v2: joint_ready / joint_tracking / composing / completed
共同:             none / composing / completed
```

`is_runnable()`:

```text
single_view:        canonicalStatus == queued
multiview/late:     canonicalStatus == queued AND orchestrationStatus ∈ {fusion_ready, fallback_ready}
multiview/joint:    canonicalStatus == queued AND orchestrationStatus == joint_ready
```

`fusion_ready` 绝不在 joint 模式表示"准备开始 tracking"(语义混乱)。

**持久化与重试:**
- 新增 `jointRunId`(不复用 `fusionRunId`);`AnalysisJobSummary { fusionRunId?(late only), jointRunId?(joint only) }`。
- Parent 被 claim → **先持久化 `jointRunId` → 再打开视频/模型**。
- 失败重试:同一 Parent → 复用 `jointRunId` → 清理 incomplete temp outputs → 从头安全重跑。第一版无 checkpoint resume。
- **原子 finalize**:临时产物 → atomic finalize,避免前一次 crash 留下半个 `fused_player_trajectory.v2` 被下一次误认完成。

**长任务语义**(joint executor 不再是 P0 那种很快的 artifact math):
- 每 tick 检查 cancellation token;进度 = canonical clock processed / total;两个 capture finally release。
- 失败规则:
  - Cam2 中途永久解码失败 → 该时刻起 view unavailable → 继续 Cam1 → final diagnostics = `joint_degraded`。
  - Cam1/reference 永久失败 → `MultiViewJointRun failed`(canonical clock 依赖 reference source)。

### D11: 硬不变量(扩展)

1. **View state 独立,Global state 共享**——Tracker/Lock/Identity 不跨摄像机共享内部状态。
2. **Tracker 每 source frame 至多 update 一次**——guided detection 必须在该次 update 前合并;由 D2 保证不重复喂帧。
3. **Guidance 不能创造 measurement**——只有目标摄像机自身重新检测出的真实像素证据才能成为 observed sample。
4. **Prediction 不进入运动指标**——`predicted` 永远 `metric_eligible=false`;真实 accepted guided detection 可以进。
5. **Confirmed global 才能产生强 guidance**——且 `cross_view_anchored`(D7),禁止单帧错误 detection 形成跨摄反馈闭环。
6. **Offline refinement 最多一轮**(属 Change 3,本 Change 预留契约位)。
7. **Additive P1**——P0 核心算法类(late_fusion_v1)语义不变,新类只在新执行路径(D0)。
8. **Source-frame 单调不重复**——同一 ViewTrackingSession 的 `source_frame_index` 严格单调,不重复消费(D2)。
9. **Guided pre-gate 在 tracker 之前**——pre-gate 拒绝的 guided candidate 绝不碰 tracker(D6)。

## Risks / Trade-offs

- **[Risk] joint 模式复杂度显著高于 late_fusion** → 缓解:additive P1(D0)+ late_fusion 回归基线 + `JointViewRuntime` 收敛外层逻辑(D8)。
- **[Risk] 低阈值 guided candidate 污染 tracker** → 缓解:pre-gate 前移到 tracker 之前(D6),invariant 9。
- **[Risk] 双摄时钟 drift 导致同帧重复消费** → 缓解:clock source-frame 单调不重复(D2),invariant 8,专项测试。
- **[Risk] A/B 被幂等/去重误判同一任务** → 缓解:`executionMode` 进 `inputSignature`(D1)。
- **[Risk] 重启后无法重建 JointRun** → 缓解:`jointViewInputs` + `jointRunId` 持久化(D1/D10)。
- **[Risk] joint 长任务中途失败留半成品** → 缓解:原子 finalize + 失败语义(joint_degraded / failed)(D10)。
- **[Risk] 单摄错误锁定自证** → 缓解:`confirmed AND cross_view_anchored` 门(D7),invariant 5。

## Migration Plan

- `executionMode` 缺省 `late_fusion_v1`,历史任务零迁移、零数据迁移。
- joint 独立 `jointRunId` / 产物目录;late_fusion 产物/路径完全不变。
- 回滚 = revert 提交;joint 产物未完成时不覆盖 late_fusion 产物。

## Open Questions

已全部关闭(本 Design 完成 tightening):
- **orchestrationStatus** → 冻结(D10),不再实施时决定。
- **artifact v1/v2** → 独立 writer + 公共 version-aware reader(D9)。
- **motion model** → 4-state constant-velocity Kalman(D3),不留斜杠。

`CrossViewGuidancePolicy` 的具体参数值留待实验调参,但触发语义已冻结(D6)。
