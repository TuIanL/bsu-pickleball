## 1. Phase 1：报告真实数据边界（去 Demo 化 P0）

- [x] 1.1 拆分 `mock_analysis.py` 的报告构建：新增 `build_demo_report()`（仅 demo 任务）与真实报告构建入口；demo 与 real 构建路径彻底分离
- [x] 1.2 新增 real report 构建链骨架（Evidence Assembler → Insights Engine → Report Projector 占位实现），worker 完成回调改走新链路
- [x] 1.3 编写 import 守卫测试：断言 real report builder / projector / insights 模块不引用 `DEMO_REPORT`
- [x] 1.4 前端 real-job 报告数据源收敛：`ReportPage` 及报告路由只消费权威 `/report` API；报告暂无/失败时显示显式"生成中/加载失败"状态，不回退 demo
- [x] 1.5 将 `pipelineReportAdapter.ts` 标记 deprecated（新 runtime 不调用，保留兼容旧测试），补充迁移注释
- [x] 1.6 端到端测试：真实任务报告（后端 payload 与前端渲染）零 demo 性能结论字符串断言

## 2. Phase 2：Performance Insights Contract

- [x] 2.1 定义 `performance-insights.v1` Pydantic schema：`PerformanceInsightsArtifact`（job_id / match_format / rule_profile_version / generated_at / evidence_input_signature / data_quality / subjects / dimensions / evidence / findings / recommendations / primary_focus_finding_id）
- [x] 2.2 定义 `PerformanceEvidence`（含 provenance 枚举、毫秒时间窗、source_artifacts、quality、`semantic_level ∈ {descriptive, confirmed, candidate}`、`rule_eligibility ∈ {eligible, display_only}`）与 `PerformanceFinding`（assessment 4 态 / priority / confidence / evidence_ids / evidence_windows / recommendation_id）
- [x] 2.3 定义 `DimensionAssessment`（dimension / subject_id / status 6 态含 not_applicable 与 unsupported / confidence / evidence_ids / finding_ids / summary）——维度状态由 Rule Engine 权威输出，Projector 只展示不做领域判断
- [x] 2.4 定义确定性 ID 与排序契约：`ev:{subject}:{metric}:{window_start_ms}` / `finding:{rule_id}:{subject}` / `rec:{rule_id}:{subject}`，禁用 uuid4；subjects / dimensions / evidence / findings / recommendations 固定排序（subject 升序、dimension 固定序、id 字典序）
- [x] 2.5 定义 `TrainingRecommendation`（baseline / next_target / direction / metric / finding_id / rule_id / threshold_source / evidence_ids，可审计链 recommendation → finding → evidence → artifact）与 `PerformanceDataQuality`（有效 Rally 数、轨迹覆盖率、维度可用性；计数类字段用 `value: null + status: unavailable` 区分"无法得知"与"确实为 0"）
- [x] 2.6 `AnalysisReport` schema 扩展：现有 `version` 字段扩展为 `Literal["analysis-report-v1", "analysis-report-v2"]`（不新增第二套 schema_version 字段）；v2 新增可选 `performanceInsights` 字段（旧字段全保留，旧 job v1 报告照常可读）

## 3. Phase 3：Evidence Assembler

- [x] 3.1 实现 `PerformanceEvidenceAssembler`：从已落盘 `result.json + artifacts` 只读组装 evidence（movement / zone stats / doubles spacing / rally 窗口 / ball-bounce 可用性），`timestamp_seconds` 在边界统一转毫秒
- [x] 3.2 接入 zone stats / 有效时间分母分层（clip 区间 → 时间线 rally 窗口 → 轨迹总时长回退），标注 `manual_timeline` provenance
- [x] 3.3 multiview 约束：Assembler 只消费 public Parent 最终产物，reference-view 来源 evidence 标 `reference_view`、融合轨迹标 `fused_multiview`
- [x] 3.4 artifact 可用性与 data_sufficiency 汇总进 `data_quality`（每维度 available / not_applicable / insufficient_players）
- [x] 3.5 Assembler 单元测试：own-side 厨房线距离口径（`avg_distance_to_kitchen_line_m` 量所属半场，无法判定时回退并标注）
- [x] 3.6 计算 `evidence_input_signature`：对 Insight Engine 实际消费的输入产物（result metrics、player trajectory、zone stats、doubles spacing、manual timeline revision、multiview provenance artifacts）生成确定性指纹（V1 可为路径 + mtime + 长度的结构化哈希），明确不复用 `AnalysisJobSummary.inputSignature`；bounce/ball 候选 evidence 在 Assembler 出口即标 `semantic_level=candidate, rule_eligibility=display_only`

## 4. Phase 4：Insight Rule Engine v1

- [x] 4.1 定义 `InsightRuleProfile` v1 结构：规则版本、适用赛制、所需 artifacts、最低数据覆盖率、计算方法、触发阈值（`threshold_source = product_reference_v1`）、文案与训练建议模板
- [x] 4.2 实现规则：`transition_zone_dwell`、`kitchen_line_proximity`、`movement_load`、`movement_coverage_balance`、`data_coverage_quality`
- [x] 4.3 实现双打规则：`doubles_spacing_stability`、`doubles_spacing_extremes`（player/team 双 scope）；单打任务双打维度在 `DimensionAssessment.status` 输出 `not_applicable`
- [x] 4.4 条件规则 `rally_window_movement_profile`：仅在人工时间线存在时启用，文案限定"在人工标记的有效回合窗口中"，不推断回合胜负/失误/战术
- [x] 4.5 降级路径：数据不足输出 `insufficient_evidence`；某类 artifact 缺失只降级对应维度，不使整个 insights 失败
- [x] 4.6 KCR 消费约束：规则禁止把 `kitchen_control_rate` / `nvz_occupancy_rate` 当作"越高越好"的能力评分输入
- [x] 4.7 Rule Engine 入口统一过滤 `rule_eligibility = display_only` 的 evidence（schema 约束级），任何规则无法消费候选证据产出 finding
- [x] 4.8 确定性测试：同输入 + 同 rule_profile_version 再生成，除 `generated_at` 外逐字段一致（含稳定 ID 与集合排序断言）；ball/bounce candidate 不进入任何 finding

## 5. Phase 5：产物接入与报告投影

- [x] 5.1 `StorageService` 新增 `performance_insights.json` 确定性路径（capture 任务 `analysis/<job_id>/`、普通任务 `outputs/<job_id>/`）与原子写入
- [x] 5.2 `AnalysisArtifacts` 新增 `performance_insights_*` 四字段；Worker 完成后按固定顺序执行（防 `/report` 与 `/result` 双真值）：保存基础 result → 生成 insights → `model_copy(update=...)` 更新 artifacts 字段 → 原子重写 `result.json` 并同步内存 RESULTS cache → 最后执行 Report Projector
- [x] 5.3 实现独立再生成入口：仅凭已落盘产物重跑 insights（含 `evidence_input_signature` 校验，明确不复用 `AnalysisJobSummary.inputSignature`），不触发视觉阶段重跑
- [x] 5.4 artifact API 注册 `performance-insights` name（200 JSON / 404，不返回 422）
- [x] 5.5 实现 `AnalysisReportProjector`：insights → 报告 `performanceInsights` 用户可读子集（总结 / 维度状态 / findings / recommendations / candidate facts / 下次训练目标）；insights 失败时报告显式降级"洞察暂不可用"
- [x] 5.6 KCR 兼容迁移：`zone_stats` / visualization-data API 输出 `nvz_occupancy_rate`（canonical）+ `kitchen_control_rate`（deprecated alias 同值）；`ZoneFeedback` 文案降级为描述性（near_line/moderate/deep 档位，删除"网前控制优秀/良好/不足"）；更新 `player-zone-heatmap` 相关测试
- [x] 5.7 集成测试：`GET /report` 与 `GET /result` 的 insights 状态一致性（二次持久化后两端口同步）；`AnalysisReport.version` v1 旧报告读取兼容、新 real report 为 v2

## 6. Phase 6：Performance Report UI

- [x] 6.1 注册 `/analysis/{job_id}/reports/performance` 路由与报告类型（任务完成入口默认指向）
- [x] 6.2 实现首屏总结（整体状态 / 最明显优势 / 首要问题 / 下一次最值得练 / 数据可信度）与六维状态卡（待改进 / 稳定 / 数据有限 / 暂不评价，无数值分）
- [x] 6.3 实现球员切换 chip（P1–P4 / team_near / team_far），findings、证据与训练目标按 subject 过滤
- [x] 6.4 实现 Findings 列表（priority / confidence / 证据链接）与"查看视频证据"跳转 `/analysis/{job_id}/vision?t={start_ms}`（无时间窗时禁用入口）
- [x] 6.5 实现 Vision 证据 seek 契约：`/analysis/{job_id}/vision` 路由解析 `t` 查询参数（毫秒）写入 RouteState 或由 VisionPage 读取 search（当前 router 的 parseLocation 未处理 vision 的 query，需扩展）；video metadata loaded 后执行 `currentTime = t / 1000` 并 clamp 到 [0, duration]；非法值（负数 / 非数字）忽略、超时长钳制；视频不可用时仍能正常打开 Vision 页面。测试：`?t=184200` → seek 184.2s、`?t=-1` → 忽略、`?t=abc` → 忽略、`?t` 超 duration → clamp
- [x] 6.6 实现独立"算法候选事实"区（弹跳候选数 / confidence 摘要 / 片段入口，标注 candidate 语义，不进入 findings）
- [x] 6.7 实现训练建议与下次训练目标区（baseline / next_target / metric / direction，无历史对比）
- [x] 6.8 demo 任务访问 performance 路由的降级处理（样例标识或重定向 demo 报告）
- [x] 6.9 前端 `StructuredZoneHeatmap` 切换消费 `nvz_occupancy_rate`（兼容读取旧字段），KCR 文案同步描述性措辞
- [x] 6.10 UI 状态测试：报告生成中 / 加载失败 / 洞察不可用 / demo 标识 / 球员切换 / 视频跳转参数

## 7. 验收与回归

- [x] 7.1 全链路验收清单执行：真实报告 0 demo 结论、每条 finding ≥1 真实 evidence、evidence 可追溯 artifact/metric/timeline、数据不足显示 insufficient_evidence、单打 doubles 维度 not_applicable、双打 player/team scope、缺失数据维度降级不整体失败
- [x] 7.2 回归：movement / diagnosis 报告路由、demo 报告、旧 job 的 v1 report.json 读取兼容、visualization-data API 旧消费者兼容
- [x] 7.3 后端与前端全量测试通过（含新 import 守卫、确定性再生成、KCR 兼容字段测试）
