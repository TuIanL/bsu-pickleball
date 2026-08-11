## Context

当前产品入口创建的双摄任务默认走 `late_fusion_v1`：Parent 创建两路 dedicated single-view child，child 产出 `player-render-trajectory.v2`，Parent 再读取两路观测执行 association、canonical timeline、quality、fusion 和 Composer。`joint_tracking_v2` 已有独立的运行实体，但前端尚未显式选择该模式。

当前可靠性问题集中在四个边界：

- association pass 在时间容差窗口内接收多张副摄 source frame，正式 fusion 又重新选择 nearest frame，两个阶段的证据不一致。
- sync artifact 的存在性和整体 quality 被当作 authority，但没有验证当前 Parent 所需的 reference/secondary mapping。
- 只要生成了 fused artifact，结果就容易被标成 `multiview_fused`，无法区分零副摄证据和真正的双摄证据。
- `CanonicalCourtFrameDefinition` 已有 domain type 和规范，但没有从 CaptureTake/Parent 传到 FusionRun/JointRun。

本 Change 只处理这些跨模块的闭环问题，保持现有单摄 artifact 和 late-fusion schema 兼容。

## Goals / Non-Goals

**Goals:**

- 建立唯一的 `FramePairingPlan`，使 association、canonical timeline 和 fusion 使用同一 source frame 决策。
- 对当前 Parent 的真实 camera identity 执行严格 sync authority 校验，禁止以唯一 mapping 猜测副摄身份。
- 让 effective mode、fallback、dual evidence coverage 与诊断统计真实反映运行结果。
- 让同一 CaptureTake 的 canonical frame 定义写入并复用于 Parent、`MultiViewFusionRun` 和 `MultiViewJointRun`。
- 统一当前 API 使用的执行模式字段为 `multiview.executionMode`，并将显式的 `joint_tracking_v2` 请求接入前端协议。
- 增加能捕获错误配对、缺 mapping、零副摄证据和 canonical frame 漂移的测试。

**Non-Goals:**

- 不在本 Change 内把 `frame_index / fps` 全链路替换为 source PTS。
- 不修改录制、分段、FFmpeg 或 CaptureTake 的生成流程。
- 不删除 `late_fusion_v1`，也不把 joint tracking 的算法逻辑重写为 late-fusion 实现。
- 不改变已有单摄 artifact 的坐标和时间字段语义。
- 不在没有真实 A/B 数据和 smoke test 之前把 joint tracking 声明为唯一默认产品路径。

## Decisions

### 1. 使用一次性、可追溯的 FramePairingPlan

新增不可变的配对计划，输入为 reference observation 时间序列、secondary frame timing 和当前 secondary sync mapping。每个 reference tick 最多选择一张 secondary source frame，并保留 `source_frame_index`、source timestamp、mapped take timestamp、selection error 和 status。

association pass 按 plan 取出该 source frame 上的全部球员观测，再交给 associator；canonical timeline/fusion 复用同一个 plan。这样选择单位是“视频帧”，而不是“球员”，避免同一 canonical tick 的多个球员来自副摄不同视频帧。

计划本身不负责身份关联，也不改变 sample-level fallback。超过容差、没有 mapping 或没有对应 source frame 时，计划记录 unavailable，后续按现有 fallback 语义处理。

备选方案是让 association 继续独立 nearest-select。该方案改动小，但无法保证 association 和 fusion 的证据一致，因此不采用。

### 2. 以当前 view 的 camera identity 验证 sync authority

新增 `SyncAuthorityValidator`，由 coordinator preflight 和两个 executor 共享。validator 接收 reference view、secondary view 以及各自持久化的 camera identity，要求 sync artifact 的 schema、top-level reference、mapping reference/camera id、rate、offset、quality 和 valid range 均有效。

缺少当前 secondary mapping 时，不再通过 `_resolve_secondary_sync_key()` 猜测唯一 non-reference mapping。任务进入显式 job-level single-view fallback，并在 diagnostics/manifest 中记录原因。已有的硬件 camera id 仍会被保留在 Parent 输入中，供 mapping 精确匹配。

### 3. 用 evidence 计算 effective mode

`fusion_performed` 只表示管线是否运行，不再直接决定产品模式。Composer 根据实际 measurements 和 diagnostics 计算：

- `dual_evidence_samples > 0` 且覆盖正常时为 `multiview_fused`；
- 有双摄证据但覆盖明显不足时为 `multiview_degraded`；
- `dual_evidence_samples == 0` 时为 `single_view_fallback`；
- prediction 只计入 predicted 统计，不计入 dual evidence。

manifest、Parent result message 和 diagnostics 使用同一个 effective mode，避免技术执行状态与用户可见语义分离。

### 4. canonical frame 按 take 写入并只读复用

在 CaptureTake 范围内使用 write-once 的 `CanonicalCourtFrameDefinition`。首次创建新分析时由已声明的端点定义创建；后续 Parent 必须加载同一 `frame_id`。如果本次 view orientation 与既有 frame 定义冲突，preflight 失败并要求显式处理，不自动整体翻转。

Parent 保存 `canonicalFrameId`，late `MultiViewFusionRun` 和 joint `MultiViewJointRun` 保存完整 `canonical_frame_ref` 或等价引用，并在 artifact/diagnostics 中回显 frame id。

### 5. 统一执行模式协议，但保留历史默认

当前代码已经使用 `AnalysisJobSummary.executionMode` 和 `MultiViewCreateRequest.executionMode`，因此将 `multiview.executionMode` 作为规范请求字段和 `executionMode` 作为持久化字段。OpenSpec 中旧的 `multiviewExecutionMode` 仅作为历史命名修正，不再新增同名顶层字段。

缺少或未知模式仍默认 `late_fusion_v1`，保证旧 Parent 可读；新前端请求显式发送 `joint_tracking_v2` 时才进入 joint path。两种模式继续进入 input signature，允许同一 take 做独立 A/B。

### 6. 先做 reliability hardening，再做 PTS migration

本 Change 的 pairing plan 继续消费现有 `timestamp_seconds`，因为把 tracking、clip、pose、ball、serve 和 overlay 全部切换到 PTS 需要独立时间轴迁移。PTS Change 应新增统一 `FrameTimingProvider`，并在本 Change 的完成条件中保留为未关闭的后续风险，而不是在这里部分替换。

## Risks / Trade-offs

- [Risk] 严格 mapping 校验会让历史上能“勉强运行”的任务进入 fallback。→ 只对新运行启用 strict authority；保留历史 artifact，不删除数据，并在 manifest 中说明原因。
- [Risk] `FramePairingPlan` 会增加内存和产物结构。→ 只保存 reference tick 与 source frame 索引/时间诊断，不复制完整观测，计划可按 run atomic 写入。
- [Risk] effective mode 改变可能影响前端按 `multiview_fused` 判断的逻辑。→ 保留原始 `fusion_status` 和 `fusion_performed`，新增字段采用向后兼容的默认值，并补充前端协议测试。
- [Risk] 同一 take 缺少历史 canonical frame 定义时无法自动推断物理端点。→ 新分析要求显式端点定义；历史已完成结果保持只读，不强制迁移。
- [Risk] 前端切换 joint 后会暴露 joint 路径尚未经过真实视频验收。→ 先支持显式 A/B 和 smoke test，再决定默认开关，不在本 Change 中删除 late baseline。
