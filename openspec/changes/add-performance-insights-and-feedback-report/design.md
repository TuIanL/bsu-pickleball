## Context

当前报告链路（已核实）：

- 后端 `mock_analysis.py::build_mock_report()` 深拷贝 `DEMO_REPORT` 后由 `_apply_pipeline_feedback()` 覆盖部分字段；真实任务的 `diagnoses` 固定为"动作诊断暂不可用"，`trainingRecommendations` 为空。
- 前端 `pipelineReportAdapter.ts::adaptPipelineResultToReport()` 以 `demoAnalysisReport` 为默认 fallback，`...fallback` spread 后覆盖——任何未显式覆盖的字段会把 demo 值透传给 source=job 的报告。
- pipeline 产物已远比报告消费的丰富：zone stats（三区占用、有效时间分母分层）、doubles spacing、ball trajectory / bounce candidates、reconstructed trajectory、serve events、canonical Player_N 身份、multiview 融合产物。
- `player-zone-heatmap` spec 已把 KCR（NVZ 内停留时间占比）与"网前控制优秀/良好/不足"评价文案固化为正式 Requirement；`interactive-performance-report` spec 允许 real report 过渡期混合 sample-only sections。

约束：语言中文；spec 体系已归档大量相关 capability（report-detail-pages、analysis-artifacts、player-zone-heatmap、interactive-performance-report、multiview-* 系列）；不允许在缺乏 confirmed semantics 时输出落点/战术结论。

## Goals / Non-Goals

**Goals:**

- source=job 的报告端到端（含前端降级路径）零 demo 性能结论。
- `performance_insights.json` 成为机器可读、可审计、可确定性再生成的洞察事实层。
- V1 Rule Engine 只输出有证据支撑的 Finding/Recommendation，数据不足时显式 `insufficient_evidence`。
- KCR 语义迁移不破坏现有 visualization-data API 消费者。
- Performance Report UI 支持球员切换、证据回溯、视频片段跳转。

**Non-Goals:**

- 不做历史趋势 / 跨场次对比（无稳定 athlete identity）。
- 不做数值技能评分（雷达图打分）、不输出"X.X 级"。
- 不做 shot classification / rally segmentation / landing statistics / 战术结论。
- 不改动视觉 pipeline 各算法模块、录制链路、`analysis-details-page`。
- 不做视频片段导出（MP4 clip 生成）。
- 不建立 Player_N → 真实姓名/账号的映射（仅展示层切换）。

## Decisions

### D1：报告构建拆分为 Demo Builder 与 Real Insights 链（P0）

```text
AnalysisPipelineResult
        │
        ▼
PerformanceEvidenceAssembler        ← 只读已落盘 artifacts
        ▼
Evidence Bundle（内存态）
        ▼
InsightRuleEngine（rule_profile v1）
        ▼
performance_insights.json（落盘）
        ▼
AnalysisReportProjector
        ├──► Real AnalysisReport（source=job，含 performanceInsights）
        └──► build_demo_report()（source=demo，仅 demo 任务）
```

- 硬约束（测试守卫）：real report 构建模块不得 import `DEMO_REPORT` / `demoAnalysisReport`；用 import-lint 测试断言。
- 备选「继续 allowlist 覆盖」被否决：无法从类型层保证零泄漏，且新增字段忘覆盖即泄漏。
- 前端 real-job 报告只消费 `GET /api/analysis/jobs/{job_id}/report`；`pipelineReportAdapter` 保留一个 deprecated 版本兼容旧测试/旧 job，新 runtime 不调用。

### D2：Insight Engine 为 post-pipeline 独立服务，可再生成（含 result 二次持久化）

- Worker 完成后立即调用一次生成 insights；同时暴露内部再生成入口：仅凭已落盘 `result.json + artifacts` 重跑。
- 换 rule_profile 版本（v1→v2）只重新生成 insights + report，不重跑视觉 pipeline。
- 确定性契约：`same inputs + same rule_profile_version → same dimensions/evidence/findings/recommendations`（`generated_at` 除外）。
- **缓存失效签名**：`performance_insights.json` 携带 `rule_profile_version` 与 `evidence_input_signature`。后者是 Insight Engine 实际消费的 evidence 输入指纹（覆盖 result metrics、player trajectory、zone stats、doubles spacing、manual timeline revision、multiview provenance 等输入产物），**不是** `AnalysisJobSummary.inputSignature` 的复用——job signature 描述"输入视频 + 配置"，无法感知 artifact 被修复/重生成导致的 evidence 变化（同一 job、同配置、zone artifact 手工修复后 job signature 不变但 insights 应失效）。缓存键 = `evidence_input_signature` + `rule_profile_version`。V1 可实现为输入产物清单（路径 + mtime + 长度）的结构化哈希，后续升级为 content hash。
- **Worker 完成后的持久化顺序（防止 `/report` 与 `/result` 双真值）**：pipeline 返回时 `performance_insights_*` 尚不存在，必须按固定顺序收尾——① 保存基础 `result.json` → ② 生成 `performance_insights.json` → ③ 用 `model_copy(update=...)` 更新 `AnalysisArtifacts` 的 `performance_insights_*` 四字段 → ④ 重新原子写 `result.json` 并同步内存 `RESULTS` cache → ⑤ 最后才执行 Report Projector。否则会出现 `/report` 已含 insights 而 `/result` 的 `performance_insights_status` 仍缺失的漂移。

### D3：Evidence / Finding / Dimension / Recommendation 数据契约（performance-insights.v1）

- `subject_id`：canonical `Player_1..Player_4`；双打团队 Finding 用 `team_near` / `team_far`。不做姓名映射。
- `PerformanceEvidence`：`id / subject_id / dimension / metric / value / unit / numerator / denominator / start_ms / end_ms / rally_id / source_artifacts / quality / provenance / semantic_level / rule_eligibility`。所有用户可跳转时间统一毫秒（`timestamp_seconds` 在 assembler 边界转换，Rule Engine 不处理秒/毫秒混合）。
- **候选语义为 schema 约束而非约定**：`semantic_level ∈ {descriptive, confirmed, candidate}`、`rule_eligibility ∈ {eligible, display_only}`。bounce/ball 候选 evidence 在 Assembler 出口即标 `semantic_level=candidate, rule_eligibility=display_only`；InsightRuleEngine 入口统一过滤 `display_only`，任何规则都无法消费候选证据产出 Finding——防止后续新增规则无意中把候选包装成"落点控制不足"。
- `provenance ∈ {pipeline_metric, structured_visualization, manual_timeline, fused_multiview, reference_view, derived_rule}`；multiview 只消费 public Parent 最终产物，reference-view 来源的 Evidence 标 `reference_view`。
- `PerformanceFinding`：`assessment ∈ {strength, stable, needs_improvement, insufficient_evidence}`（Finding 是具体发现，4 态）、`priority 1-3`、`confidence`、`evidence_ids[]`（每条 Finding ≥1 条真实 evidence）、`evidence_windows[]`（前端跳转 `/analysis/{job_id}/vision?t=ms`）。
- **`DimensionAssessment`（维度状态权威契约）**：`dimension / subject_id / status / confidence / evidence_ids[] / finding_ids[] / summary`，`status ∈ {strength, stable, needs_improvement, insufficient_evidence, not_applicable, unsupported}`（6 态）。维度整体状态由 Rule Engine 综合该维度下全部 findings 与数据可用性后权威输出；Report Projector 只做展示、不做领域判断。`not_applicable`（单打的双打协同）与 `unsupported`（证据能力缺失，如攻防转换）是维度级状态，不落入 Finding 的 4 态——解决"维度 5 类展示状态"与"Finding 4 态"的职责区分。
- **确定性 ID 与排序契约**：所有 id 禁用随机值（uuid4）。`evidence.id = ev:{subject}:{metric}:{window_start_ms}`、`finding.id = finding:{rule_id}:{subject}`、`recommendation.id = rec:{rule_id}:{subject}`；`subjects / dimensions / evidence / findings / recommendations` 固定排序（subject 升序、dimension 固定序、id 字典序），保证确定性测试不被随机 ID 或集合迭代顺序打破。
- `TrainingRecommendation`：`baseline / next_target / metric / direction / finding_id / rule_id / threshold_source / evidence_ids[]`——训练建议本身可审计，形成 `recommendation → finding → evidence → artifact` 全链路追溯。
- `PerformanceDataQuality`：计数类字段（如有效 Rally 数）用 `value: null + status: unavailable` 表达"无法得知"，与 `value: 0`（确实为零）严格区分。
- 六维维度 V1 只给状态（待改进/稳定/数据有限/暂不评价），不给数值分。

### D4：KCR 兼容迁移（不 breaking rename）

- `zone_stats` / visualization-data API：新增 `nvz_occupancy_rate`（canonical，语义=NVZ 占用率，无评价）；`kitchen_control_rate` 保留并输出相同数值，标注 deprecated（响应中加 `deprecation` 说明字段或文档标注）；`avg_distance_to_kitchen_line_m` 修正为量球员所属半场（own-side）厨房线，消除跨半场量到对方线的偏差。
- `ZoneFeedback` 文案降级为描述性："平均站位较接近厨房线，NVZ 占用率 X%"；删除"网前控制优秀/良好/不足"。
- 评价性 `net_front_control` 判断移入 Insight Engine（综合 kitchen_line_proximity + transition occupancy + movement evidence + data quality）。
- Insight Rules 禁止把 `kitchen_control_rate` 当作"能力越高越好"的评分输入。
- 备选「直接 rename」被否决：`player-zone-heatmap` spec 与前端 `StructuredZoneHeatmap` 均消费该字段，直接改破坏面大。

### D5：V1 Rule Profile 红线裁决

- 正式支持：`transition_zone_dwell`、`kitchen_line_proximity`、`movement_load`、`movement_coverage_balance`、`doubles_spacing_stability`、`doubles_spacing_extremes`、`data_coverage_quality`。
- 条件支持（存在人工 `rally_start/rally_end` 时间线时）：`rally_window_movement_profile`——文案只能表达"在人工标记的有效回合窗口中…"，不得推断回合胜负/失误类型/战术效果。
- 明确推迟：`placement_concentration`（bounce 仅为 candidate，现有 spec 禁止包装成 landing statistics）、`rally_consistency`（rally 边界语义未 confirmed）。
- ball/bounce 在 Performance Report 中仅出现在独立"算法候选事实"区（候选数、confidence、查看片段），不进入 finding；该红线由 `rule_eligibility = display_only` 的 schema 约束在 Rule Engine 入口强制执行（见 D3），不依赖人工约定。
- 所有阈值声明 `threshold_source`（V1 为 `product_reference_v1`），文案不称"专业标准"。
- 单打：doubles 类维度在 `DimensionAssessment.status` 输出 `not_applicable`（非 Finding 级状态）；双打：player/team 双 scope。

### D6：Report schema 扩展（非破坏，沿用现有 `version` 字段）

- 现有 `AnalysisReport.version: Literal["analysis-report-v1"]` 扩展为 `Literal["analysis-report-v1", "analysis-report-v2"]`，**不新增第二套 `schema_version` 字段**（避免新旧报告出现 `version` / `schema_version` 双版本机制）。
- v2 新增可选字段 `performanceInsights`（projector 投影后的用户可读子集：summary、dimension 状态、findings、recommendations、candidate facts）；旧字段全保留，旧消费者不受影响。
- 版本策略：旧 job 已落盘的 `report.json` → `v1`（照常可读）；demo report → 可继续 `v1`；新 real report → `v2`。
- 旧 `skillRatings`（mock 六维 0-10 分）在 real report 中不再输出 demo 值；demo report 保留原样。

## Risks / Trade-offs

- [real report 拆分后字段覆盖遗漏导致空报告] → Projector 按"必填字段缺失即构建失败并显式报错"实现，不静默回退 demo；端到端测试断言 real report 零 demo 字符串。
- [KCR 双字段并存期前端混用] → 前端一次性切换到 `nvz_occupancy_rate`，`kitchen_control_rate` 仅保留一个兼容版本并标注 deprecated；spec 明确移除时点。
- [规则阈值无标定依据被质疑] → 所有阈值带 `threshold_source` 版本标识，UI 文案标注"产品参考基准"；后续升级 coach_validated_v2。
- [insights 再生成与落盘版本漂移] → `evidence_input_signature` 指纹 + 再生成前校验；确定性回归测试排除 `generated_at`，并断言稳定 ID 与固定排序。
- [`/report` 与 `/result` 的 insights 状态漂移] → D2 的五步持久化顺序（result 二次原子写入 + RESULTS cache 同步后再投影）+ 集成测试断言两端口状态一致。
- [数据不足时 UI 空洞] → dimension 状态含"数据有限/暂不评价"显式展示，配 data_quality 摘要（有效 Rally 数、轨迹覆盖率）。
- [deprecated adapter 残留双真值] → 本 Change 内新 runtime 停止调用，物理删除留给下一轮，测试标记 todo。

## Migration Plan

1. Phase 1 落地后（报告链拆分），旧 job 的 report.json 仍可读（v1 schema 向后兼容）；新完成任务产出 v2。
2. KCR 字段：后端同时输出新旧字段 ≥1 个版本；前端切换后，旧字段进入 deprecated 清单，下一轮删除。
3. 回滚：insights 生成失败时 report 降级为"移动数据 + 洞察暂不可用"（显式状态，不回退 demo）；KCR 迁移可按字段开关回退。

## Open Questions

- 无阻塞项。`pipelineReportAdapter` 物理删除时点、`kitchen_control_rate` 字段删除时点均留给后续 change。
