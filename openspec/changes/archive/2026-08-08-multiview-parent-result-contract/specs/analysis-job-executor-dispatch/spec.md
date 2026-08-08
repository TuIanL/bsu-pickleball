# analysis-job-executor-dispatch Delta Specification

## MODIFIED Requirements

### Requirement: MultiViewAnalysisExecutor

系统 MUST 提供 `MultiViewAnalysisExecutor`，其 `execute` 流程为：读取两个 child 的单摄产物 → 构建/复用 `MultiViewFusionRun`（`fusionRunId` 已在 Parent 持久化）→ 执行融合 → `MultiViewResultComposer` 生成 Parent 结果 → 返回 `AnalysisPipelineResult`（completed + 聚合 stages）。该 Executor 在 `resource_limiter` 内的计算是纯 artifact 数学（不解码视频）。Executor MUST 在 compose 完成后将 Parent 的 `AnalysisPipelineResult` 落盘到 `result.json`（先 `publicize_pipeline_result` 再写 `output_json_path`），使结果可跨后端重启读取。

#### Scenario: 双摄执行链路

- **WHEN** Parent（`orchestrationStatus=fusion_ready`）被 claim
- **THEN** MultiViewExecutor SHALL 消费两路 child 的 `player_render_trajectory` 产物构建 `MultiViewViewInput`
- **AND** 执行融合并产出 Parent-owned 报告

#### Scenario: job-level fallback 不生成 fused artifact

- **WHEN** 任一 view `court_orientation=None` 或 sync authority unavailable（P0 job-level gate）
- **THEN** MultiViewExecutor SHALL NOT 生成 fused artifact
- **AND** 按确定性单视角降级规则 compose Parent 报告

#### Scenario: Parent result 落盘

- **WHEN** MultiViewExecutor 完成 compose 并生成 Parent 结果
- **THEN** 系统 SHALL 把该 `AnalysisPipelineResult` 写入 `result.json`
- **AND** 后端重启后 `GET /jobs/{parent_id}/result` SHALL 返回完整结果而非仅 job summary
