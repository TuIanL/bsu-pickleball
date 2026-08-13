## Context

当前 `AnalysisJobPage` 会分别请求 fused manifest 和 fusion diagnostics，并在 React 中组合部分双摄结果。P1-0/P1-A/P1-B 后，实际需要表达的事实已分布在 timing provenance、sync authority resolution、fusion diagnostics、recovery funnel、refinement manifest/diagnostics 和可选 joint debug artifacts 中。如果新页面继续分别读取这些原始产物并自行推导状态，前端将变成第二个 Composer，并可能与后端策略产生双真值。

Joint debug trace 可达上百 MB，且只有 `debugTraceEnabled=true` 的调试或验收任务才保证生成。普通产品任务必须在没有 trace 和 debug MP4 时仍能显示同步、融合、恢复统计和精修发布状态。页面同时需要覆盖 `joint_authoritative`、degraded joint、`late_fusion_v1` 和非 multiview 任务，不能将“不适用”、“诊断未生成”和“算法失败”混为一种状态。

## Goals / Non-Goals

**Goals:**

- 以已有 P1 artifacts 为唯一语义真值，提供可重建的产品级 observability projection。
- 用单一 summary API 为前端提供 `SYNC / FUSION / RECOVERY / REFINEMENT` 四个独立状态域和用户可见 reason code/message。
- 将 recovery runtime evidence 投影为默认一行一个 episode 的可分页、可筛选产品契约。
- 在 opt-in debug video 存在时支持 episode seek，不存在时保持其他区域完整可用。
- 为双摄协同事实提供独立页面，避免继续扩大通用任务页。
- 使 F1 candidate 生成、Safety Gate 发布拒绝与稳定回退 F0 可以同时被准确表达。

**Non-Goals:**

- 不修改 P1 timing、tracking、association、recovery、refusion、metric eligibility 或 Safety Gate 算法。
- 不强制所有 joint 任务生成 raw debug trace 或 debug MP4。
- 不向浏览器暴露 raw trace，不将页面建成 runtime 日志查看器。
- 不实现双原视频同步播放器、交互式 canonical court 或证据时间线。
- 不允许用户在页面修改 sync calibration 或 recovery/F1 参数。
- 不以该页面替代含 GT precision/recall 的科研 A/B evaluation 工具。

## Decisions

### D1. 请求时动态组合可重建投影

新增 `MultiviewObservabilityProjector`，从已发布的 job/result、fusion manifest/diagnostics、joint diagnostics、refinement manifest/diagnostics 以及可选 debug summary 读取事实，在请求时组合 `multiview_observability_summary.v1` DTO。Projector 不运行任何算法门限，不根据 p95、conflict delta 等原始数值重新判定 authoritative 或 Safety Gate，只映射已有 authoritative fields 和 reason codes。

默认不持久化 summary，避免创造可与源 artifact 分歧的长期真值。如后续需要 cache，cache key 必须包含源 artifact identity/version 并且可丢弃重建。

备选方案是在 joint executor 内维护另一份 observability JSON。该方案会把展示层生命周期耦合到长时运行主流程，且可能在中途失败时产生不一致，因此不采用。

### D2. Summary 按状态域独立表达可用性

Summary 顶层包含 job/run identity 和 execution mode，并为 `sync`、`fusion`、`recovery`、`refinement`、`debug` 分别返回 `availability`、`status`、`reason_code` 和该域 payload。`availability` 使用稳定枚举 `available | partial | unavailable | not_applicable`；运行结论使用域自身状态，不用一个顶层红/绿值覆盖全部区域。

这使 `joint_authoritative + debug unavailable` 可同时表达，也使 degraded timing 显示为“joint 已执行但不具 authoritative eligibility”，而不是简化为“同步失败”。

备选方案是返回一个 `healthy` 布尔值。它会丢失缺失证据、不适用与执行失败之间的区别，因此不采用。

### D3. 执行模式的产品语义

- 非 multiview job：summary 和子资源返回 `404 not_applicable`，前端显示可返回任务页的不适用状态。
- `late_fusion_v1`：页面保留，sync/fusion 按已有诊断呈现，online recovery 与 offline F1 明确为 `not_applicable`，不伪装执行 P1 joint tracking。
- degraded joint：显示 joint execution 存在，同时展示 `authoritative_joint_eligible=false` 与后端 reason。
- authoritative joint：仅在后端投影已有 `joint_authoritative` 和 `authoritative_joint_eligible=true` 时显示权威联合分析。

### D4. Recovery API 默认投影 episode，不倾倒 raw ticks

`GET /api/analysis/jobs/{job_id}/multiview/recovery-events` 默认返回 recovery episode summary，支持 `cursor`、`limit`、`outcome`、`global_player_id`、`donor_view`、`target_view`、`from_ms` 和 `to_ms`。响应包含 `items`、opaque `next_cursor` 和 `total_estimate`。每个 episode 至少包含起止时间、global player、donor/target、outcome、attempt/rejection 计数，以及可用时的 `debug_video_seek_ms`。

Outcome 至少覆盖 `guided_recovery_success`、`base_recovered`、`guidance_failed`、`pre_gate_rejected`、`lock_rejected` 和 `global_mismatch`。多个 tick 属于同一 `recovery_episode_id` 时必须聚合为一个列表项；终局优先于中间 reject，中间计数保留用于展开摘要。如现有正式 diagnostics 仅支持 funnel 而无法构建 episode，recovery summary 仍为 `available/partial`，episode endpoint 返回空集及结构化 reason，不读取 raw trace 来临时填满普通任务。

备选方案是一 tick 一 event 或让 React 下载 trace 后聚合。这会产生海量噪声、大 payload 和前端语义漂移，因此不采用。

### D5. Debug MP4 保持 opt-in 并由后端给出 seek 时间

Debug video 仍只在 `debugTraceEnabled=true` 且 renderer 产物完整时可用。`GET /api/analysis/jobs/{job_id}/multiview/debug-video` 使用 `FileResponse`/HTTP Range 发送 canonical debug MP4；不存在时返回结构化 404，summary 的 `debug.availability` 同步表达原因。

Episode 的 `debug_video_seek_ms` 由后端根据 debug summary/manifest 的实际时基生成，前端不使用 `take_timestamp_ms - guessed_start` 计算偏移。页面仅使用一个 canonical MP4 播放器，不同时驱动两个原视频元素。

### D6. Refinement 分离执行、发布与最终来源

Projector 直接投影 refinement manifest 的四状态、candidate artifact availability、Safety Gate reason code/metrics 和 `final_source`。UI 使用三个正交概念呈现：精修是否完成、Candidate F1 是否生成、最终产品消费 F0 还是 F1。`rejected_by_safety_gate` 必须显示为候选生成成功但发布被拒绝，`failed_fallback` 才表示执行异常后回退。

### D7. 独立页面与前端组件边界

新路由 `/analysis/{jobId}/multiview` 渲染 `MultiviewObservabilityPage`，内部拆分为 `JointRunStatusHeader`、`SyncAuthorityPanel`、`FusionQualityPanel`、`RecoveryPanel`、`DebugReplayPanel` 和 `RefinementSafetyPanel`，技术详情使用折叠区域。页面只消费 observability API DTO，不另行请求 timing/refinement/raw debug artifacts 来补算状态。

`AnalysisJobPage` 完成态双摄区域仅显示后端摘要和“查看双摄协同详情”入口，不再扩展为完整诊断页。恢复 episode 点击时，如 seek 与视频都可用则定位；否则仍展开 episode 摘要，不禁用 recovery 列表。

## Risks / Trade-offs

- **[历史任务的诊断字段不完整]** → Projector 对每个 section 使用 `partial/unavailable + reason_code`，禁止使用虚假零值填充缺失事实。
- **[动态组合需要读取多个小 artifact]** → 仅读取已发布的小型 JSON，绝不读取 raw trace；性能数据证明需要时再加入可丢弃 cache。
- **[Episode 投影可能缺少正式细粒度源]** → 先保证 funnel 独立可用，episode 以 `partial` 明确降级；实现时若需新增产物，只写入小型 episode projection，不公开 raw trace。
- **[Reason code 文案可与后端枚举漂移]** → API 保留稳定 `reason_code` 并可携带后端 message；前端对已知 code 本地化，对未知 code 使用安全通用文案。
- **[Debug MP4 编码或解码成本]** → 继续 opt-in，不影响普通 joint 任务完成；前端延迟加载视频。
- **[页面信息密度过高]** → 首屏固定四域摘要，主体限制六个 MVP 区域，技术字段折叠；不在 V1 加入二维球场或证据时间线。

## Migration Plan

1. 先实现 projector DTO 和单元测试，对现有 artifacts 保持纯读取。
2. 增加 summary、episode 和 debug video routes，用 authoritative、degraded、late fusion 和 single-view fixtures 验证 HTTP 契约。
3. 增加独立前端页面与路由，再向 `AnalysisJobPage` 添加轻量入口。
4. 使用真实 P1-A authoritative run 和 P1-B Safety Gate rejected run 做页面契约与视觉验收，同时验证未开启 debug trace 的任务。
5. 该 Change 无数据库迁移；回滚时移除新路由/页面/API 和任务页入口，已有 P1 artifacts 不变。

## Open Questions

无阻塞性问题。实现前需在现有真实 P1-A 产物上确认 episode 细粒度证据是否已有独立小型产物；若仅存在 raw trace，则按 D4 新增 backend-only 的小型 episode projection 产物，但不改变 API 或浏览器边界。
