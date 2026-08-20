## Why

当前真实任务的报告链路是"深拷贝 DEMO_REPORT 再覆盖部分字段"（后端 `build_mock_report` + 前端 `pipelineReportAdapter` 双轨），类型层无法保证真实报告不混入 demo 性能结论；同时 pipeline 已产出丰富的可追溯数据（区域占用、轨迹、双打间距、球轨迹候选、有效回合窗口），但中间缺少一层把"数据证据"转成"诊断与训练建议"的洞察引擎——报告里真实任务的 `diagnoses` 只有"动作诊断暂不可用"，`trainingRecommendations` 为空。本 Change 把报告链路升级为基于真实 Evidence 的可追溯 Performance Insights 系统，使"采集 → 视觉感知 → 数据分析 → 诊断 → 训练建议"第一次真正闭环。

## What Changes

- **真实报告去 Demo 化（P0）**：拆分 `build_demo_report()` 与真实报告构建链（Evidence Assembler → Insights Engine → Report Projector）；代码层硬约束：real report builder 不得 import `DEMO_REPORT` / `demoAnalysisReport`。
- **新增 `performance_insights.json` artifact**：机器可读、可审计的洞察事实层（schema `performance-insights.v1`），含 `data_quality`、`subjects`（canonical Player_N / team）、`dimensions[]`（DimensionAssessment 维度状态权威契约，6 态含 not_applicable/unsupported）、`evidence[]`（含 provenance、semantic_level/rule_eligibility 与毫秒时间窗）、`findings[]`（assessment/priority/confidence/evidence_ids/evidence_windows）、`recommendations[]`（可审计链 recommendation → finding → evidence → artifact）、`evidence_input_signature`（evidence 输入指纹，非 job inputSignature 复用，支撑缓存失效）。
- **新增 InsightRuleProfile v1（后端版本化规则）**：V1 仅支持可由现有数据支撑的规则（transition_zone_dwell、kitchen_line_proximity、movement_load、movement_coverage_balance、doubles_spacing_stability/extremes、data_coverage_quality，及有人工时间线时的 rally_window_movement_profile）；阈值显式标注 `threshold_source`，不输出未经校准的技术评分。
- **Insight Engine 独立可再生成**：post-pipeline 阶段执行，可仅凭已落盘的 `result.json + artifacts` 重新运行；换 rule_profile 版本无需重跑视觉 pipeline；确定性验收排除 `generated_at`。
- **KCR 语义迁移（兼容版）**：新增 `nvz_occupancy_rate` 为 canonical 字段；`kitchen_control_rate` 保留一个兼容版本并标记 deprecated；`avg_distance_to_kitchen_line_m` 修正为量球员所属半场的厨房线；ZoneFeedback 文案降级为描述性（移除"网前控制优秀/不足"评价）。
- **结束 mixed-source 过渡期**：source=job 的报告零 demo 性能结论（端到端含前端降级路径）；前端 real-job 报告只消费权威 `/report` API，`pipelineReportAdapter` 标记 deprecated。
- **新增 Performance Report UI**：`/analysis/{job_id}/reports/performance` 路由，含球员切换（P1–P4）、总结、六维状态卡（待改进/稳定/数据有限/暂不评价，无数值分）、Findings、证据、视频片段跳转（`?t=ms`）、下次训练目标。
- **candidate 语义约束**：ball/bounce 候选事实只出现在独立"算法候选事实"区，不进入 performance finding，不做落点/战术结论。
- **multiview provenance**：Insight Engine 只消费 public Parent 最终产物；Evidence 携带 `fused_multiview` / `reference_view` 等 provenance。

## Capabilities

### New Capabilities

- `performance-insights`: Performance Insights Engine 的核心契约——Evidence/Finding/Recommendation 数据结构、DataQuality 与 provenance 语义、版本化 Rule Profile（含适用赛制、prerequisites、不可用降级）、确定性再生成要求，以及四条硬不变量（真实报告零 demo 结论、Finding 必须绑定真实 evidence、数据不足显示 insufficient_evidence 而非硬算分、不生成未经校准的技能分/历史趋势/战术结论）。

### Modified Capabilities

- `analysis-artifacts`: 新增 `performance_insights.json` 产物注册（路径/URL/status 字段、落盘与再生成的存储语义、artifact API 暴露）。
- `report-detail-pages`: 新增 `performance` 报告类型路由与球员切换、Finding→视频片段跳转；real-job 报告数据源收敛为权威 `/report` payload（结束前端自行拼装报告的 mixed-source 过渡）。
- `player-zone-heatmap`: `kitchen_control_rate` 语义迁移——新增 `nvz_occupancy_rate` canonical 字段、旧字段 deprecated 兼容、`avg_distance_to_kitchen_line_m` 改为 own-side 口径、ZoneFeedback 文案降级为描述性（评价性判断移交 Insight Engine）。
- `interactive-performance-report`: 结束 mixed-source transition requirement——real job 报告不再允许混合 sample-only 性能结论；bounce/ball 候选事实区不构成 landing/战术语义。

## Impact

- **后端**：`app/services/mock_analysis.py`（报告构建拆分）、新增 insights 引擎服务（assembler/rule engine/projector）、`app/schemas/`（新 artifact 与 report schema 扩展）、`StorageService`（新产物路径）、`zone_stats.py` / `zone_metrics.py`（KCR 迁移）、visualization-data API（字段兼容迁移）。
- **前端**：`pipelineReportAdapter.ts`（deprecated）、`analysisClient.ts`、`ReportPage.tsx`（或新 PerformanceReportPage）、路由注册、`StructuredZoneHeatmap`（消费新字段）。
- **测试**：真实报告零 demo 结论的端到端断言、确定性再生成测试、KCR 兼容字段测试、单打 not_applicable / 双打 team scope 测试、multiview provenance 测试。
- **不受影响**：视觉 pipeline 本身、录制链路、`analysis-details-page`（本 Change 不动）。
