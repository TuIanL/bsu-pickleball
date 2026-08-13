## 1. 产物来源审计与契约冻结

- [x] 1.1 在真实 P1-A authoritative run 和 P1-B Safety Gate rejected run 上盘点 timing、fusion、recovery funnel/episode、refinement 与 debug summary/video 的实际路径和字段，记录历史任务缺失情况。
- [x] 1.2 根据盘点结果冻结 `multiview_observability_summary.v1`、section availability/status/reason、recovery episode 分页和结构化 API error DTO，确保不引入第二套 authoritative/Safety Gate 规则。
- [x] 1.3 确认正式 diagnostics 是否已能构建 episode；若不能，定义小型 backend-only recovery episode projection 的写入时机和兼容 reader，禁止以浏览器或请求时 raw trace 扫描作为替代。

## 2. 后端可观测投影

- [x] 2.1 实现 `MultiviewObservabilityProjector`，从已发布 job/result、fusion manifest/diagnostics、joint diagnostics 和 refinement manifest/diagnostics 纯读取组合 summary，不读 raw debug trace。
- [x] 2.2 实现 per-section `available | partial | unavailable | not_applicable` 与 reason code 投影，覆盖 authoritative joint、degraded joint、`late_fusion_v1` 和历史部分产物。
- [x] 2.3 实现 timing 投影，包含 reference view、per-view authority、sync quality、execution mode、authoritative eligibility、selection error 和 frame selection status，仅映射已有后端结论。
- [x] 2.4 实现 fusion 投影，包含 fusion status counts、metric eligibility 和视角差异摘要，不将 fusion completion 解释为 authoritative sync。
- [x] 2.5 实现 recovery funnel 投影，区分 opportunity、guidance、ROI/candidate/gates、formal identity、expected-global preservation、guided success 和 base recovery，缺失字段时使用 partial/reason 而非虚假零值。
- [x] 2.6 实现 refinement 投影，独立返回执行状态、Candidate F1 availability、Safety Gate decision/reason/metrics 和 `final_source`，严格区分 `rejected_by_safety_gate` 与 `failed_fallback`。
- [x] 2.7 实现 debug availability 和 canonical video resolver，保持 `debugTraceEnabled` opt-in，不因 trace/video 缺失影响其他 summary sections。

## 3. Recovery Episode 投影与 API

- [x] 3.1 实现以 `recovery_episode_id` 聚合 ticks/evidence 的 episode projector，冻结 success 终局优先级和 `guided_recovery_success | base_recovered | guidance_failed | pre_gate_rejected | lock_rejected | global_mismatch` outcome 语义。
- [x] 3.2 为 episode 投影保留起止时间、global player、donor/target view、guidance attempts、gate/lock rejection 计数和可选 backend-derived `debug_video_seek_ms`。
- [x] 3.3 实现 opaque cursor 分页和 `limit`、`outcome`、`global_player_id`、`donor_view`、`target_view`、`from_ms`、`to_ms` 组合筛选，返回 `items/next_cursor/total_estimate`。
- [x] 3.4 为仅有 funnel 而无 episode 证据的历史任务实现空 items + structured reason 降级，不扫描 raw trace 临时填充。

## 4. REST 路由与安全产物边界

- [x] 4.1 新增 `GET /api/analysis/jobs/{job_id}/multiview/observability`，校验 Parent job/analysis kind，对非 multiview job 返回结构化 `404 not_applicable`。
- [x] 4.2 新增 `GET /api/analysis/jobs/{job_id}/multiview/recovery-events`，接入 episode 分页/筛选契约并对无证据状态返回稳定响应。
- [x] 4.3 新增 `GET /api/analysis/jobs/{job_id}/multiview/debug-video`，仅解析已发布 canonical MP4，支持 HTTP Range/seek，未生成时返回结构化 404。
- [x] 4.4 增加路径穿越、job 归属与 artifact 完整性检查，并添加回归测试确认通用 artifact API 与新 API 都不公开 `joint_debug_trace.v1.json`。

## 5. 前端 API 与页面框架

- [x] 5.1 增加 observability summary、section availability、recovery episode page/filter 的 TypeScript types 和 API client，对 structured not-applicable/unavailable errors 提供稳定适配。
- [x] 5.2 增加 `/analysis/{jobId}/multiview` 路由和 `MultiviewObservabilityPage`，实现 loading、not found、not applicable、partial data 和 request failure 状态。
- [x] 5.3 实现 `JointRunStatusHeader`，独立显示 SYNC、FUSION、RECOVERY 和 REFINEMENT 摘要，不用单一总体红/绿标签覆盖各域差异。
- [x] 5.4 实现 `SyncAuthorityPanel` 与 `FusionQualityPanel`，准确呈现 authoritative、degraded、late fusion 及部分诊断语义，不在 React 中计算后端结论。
- [x] 5.5 实现 `RecoveryPanel`，包含漏斗、episode 筛选/分页/展开摘要，视觉上明确区分 guidance、guided success 和 base recovery。
- [x] 5.6 实现 `DebugReplayPanel`，延迟加载单个 canonical MP4，支持 episode seek；无视频时显示独立 unavailable 文案而不禁用页面其他部分。
- [x] 5.7 实现 `RefinementSafetyPanel`，将 F1 执行、candidate 生成、publication decision 和 final source 分开呈现，并为 reject/failed/completed/skipped 提供准确中文文案。
- [x] 5.8 增加默认折叠的技术运行详情，并确认页面不包含 calibration/P1 参数修改、GT A/B、双原视频播放、canonical court 或证据时间线。

## 6. 任务页入口与前端契约测试

- [x] 6.1 将 `AnalysisJobPage` 完成态双摄区域收敛为轻量摘要和“查看双摄协同详情”入口，保留现有任务返回与 query context。
- [x] 6.2 增加页面测试，覆盖 authoritative GOOD/source_pts、degraded joint、late fusion not-applicable P1 sections、single-view not applicable 和历史 partial data。
- [x] 6.3 增加 recovery 交互测试，验证组合筛选、cursor 续页、episode 展开、success/base/failure 区分与 backend-provided seek。
- [x] 6.4 增加 debug unavailable 测试与浏览器请求监测，断言其他四域仍正常且从未请求 raw joint debug trace。
- [x] 6.5 增加 refinement 语义测试，覆盖 Candidate F1 已生成 + Safety Gate reject + final F0、`failed_fallback` 和 final F1 三类状态。

## 7. 验证与真实任务验收

- [x] 7.1 运行 backend projector/API 单元与集成测试，确认非 multiview 404、section 独立降级、episode 分页/筛选、video Range 和 raw trace 禁止边界。
- [x] 7.2 运行前端相关测试、TypeScript 检查和 production build，修复路由、响应式布局与可访问性回归。
- [x] 7.3 在真实 P1-A authoritative joint job 上验收 GOOD/source_pts/authoritative、guided success episode 和可用时的 debug MP4 seek。
- [x] 7.4 在未开启 `debugTraceEnabled` 的 joint job 上验收 Debug Replay unavailable，同时 Sync/Fusion/Recovery/Refinement 仍正常且网络请求不含 raw trace。
- [x] 7.5 在真实 P1-B rejected candidate 上验收“精修完成 + Candidate F1 已生成 + 发布拒绝 + reason + 最终 F0”，确认页面不显示精修执行失败。
- [x] 7.6 使用桌面与移动端截图检查六个 MVP 区域的布局、长文案、筛选控件、视频 unavailable 和 episode 展开状态，确认无重叠或溢出。
