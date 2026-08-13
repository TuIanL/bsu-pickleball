## Why

P1-0 Timing Authority、P1-A Online Recovery 与 P1-B Offline Refinement 已经产出可审计的权威诊断事实，但用户仍需要阅读日志或本地 artifact，才能判断双路是否权威同步、是否真正联合分析、跨视角恢复是否发生，以及 F1 候选结果是否发布。现在需要将这些已有真值投影为稳定的产品级可观测接口和独立页面，而不是再建一套算法状态。

## What Changes

- 新增双摄联合可观测后端投影层，动态组合已有 timing、fusion、recovery、refinement 和可选 debug artifacts，并明确后端为语义权威。
- 新增稳定的 summary REST API，分别呈现 `SYNC`、`FUSION`、`RECOVERY` 和 `REFINEMENT` 四个独立状态域；诊断证据缺失不得被解释为算法失败。
- 新增按 recovery episode 聚合的分页和筛选 API，同时表达成功、base 自恢复及结构化失败结果，不将逐 tick runtime trace 直接暴露为前端日志。
- 新增可选 canonical debug MP4 解析接口。Debug trace 与 MP4 继续由 `debugTraceEnabled` opt-in；summary 和其他状态域不得依赖 raw trace 或 debug video 才可用。
- 新增 `/analysis/{jobId}/multiview` 独立双摄协同分析页，包含 Joint Status、Sync Authority、Fusion Quality、Recovery、Debug Replay 和 Refinement Safety 六个 MVP 区域；`AnalysisJobPage` 仅保留轻量摘要和入口。
- 为 `joint_authoritative`、degraded joint、`late_fusion_v1` 和非 multiview 任务定义明确的 available、degraded、not-applicable 页面语义。
- 明确显示 F1 执行、Candidate F1 生成、Safety Gate 发布决策和 `final_source`，不将 `rejected_by_safety_gate` 错误表达为离线精修执行失败。
- 禁止浏览器请求 `joint_debug_trace.v1.json`，禁止前端重算 authoritative、sync quality、Safety Gate 或 final source。
- 不修改 tracking、association、online recovery、offline refusion 或 Safety Gate 算法；不在该页面修改 sync calibration 或 P1 参数，不用其替代科研 A/B evaluation 工具。

## Capabilities

### New Capabilities

- `multiview-joint-observability`: 定义已有双摄 timing、fusion、online recovery、offline refinement 和可选 debug 证据的产品级投影、REST API、recovery episode 交互与独立前端页面。

### Modified Capabilities

无。本 Change 消费现有 P1 能力的权威产物，不改变其算法需求或发布语义。

## Impact

- Backend：新增 `MultiviewObservabilityProjector` 及 summary、recovery episodes 和 debug video REST routes，复用现有存储路径、fusion manifest/diagnostics、joint diagnostics、refinement manifest/diagnostics 和可选 debug summary/video。
- Frontend：新增独立页面、路由、API client/types 和六个主要展示区域；调整 `AnalysisJobPage` 的双摄完成态入口。
- Artifact 边界：不将 observability summary 定义为新的算法真值；默认按请求动态 compose，后续若增加 cache 也必须是可重建的派生数据。
- Runtime：普通 joint 任务不因本 Change 额外强制生成 raw trace 或编码 debug MP4。
- Tests：覆盖 authoritative、degraded、late fusion、single-view not-applicable、debug unavailable、episode 分页/筛选和 F1 Safety Gate reject 但最终使用 F0 等契约与页面状态。
