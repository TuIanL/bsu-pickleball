# multiview-analysis-result-composer Specification

## Purpose

定义 `MultiViewResultComposer`：把 P0 的 fused trajectory 与诊断产物组装成 Parent-owned 的分析报告。三步流程——Select/Recompute（用 fused + `metric_eligible` 重算位置类指标）、Inherit（继承 reference-view 的 pose/ball/action/overlay）、Normalize（发布到 Parent namespace 并携带 provenance）。fallback 时同样由 Composer 重新 compose Parent 报告，保证"用户永远只知道 Parent"。

## ADDED Requirements

### Requirement: 位置类指标基于 fused 重算

Composer MUST 使用 fused trajectory + `metric_eligible` 重新计算位置类指标（movement distance / speed / heatmap / zone stats），复用单摄 metrics 阶段同一套数学但输入换为 fused 轨迹。MUST NOT 复制 child 在 local frame 计算好的位置指标。

#### Scenario: fused 可用时指标来自 fused

- **WHEN** 两个 child 完成且融合产出 fused trajectory
- **THEN** Parent 报告的 movement / speed / heatmap / zone stats SHALL 由 fused 轨迹重算
- **AND** SHALL NOT 复制任一 child 的 local-frame 位置指标

#### Scenario: metric eligibility 生效

- **WHEN** fused 轨迹含 `dual_observed / single_view_fallback / conflict / predicted / unavailable` 样本
- **THEN** `predicted` 与 `unavailable` 样本 SHALL 不计入 movement / heatmap（`metric_eligibility_policy`）
- **AND** `predicted` 样本仍可用于可视化

### Requirement: 继承 reference-view 结果

Composer MUST 从 reference view 继承非位置类结果：pose / ball / action classification / overlay video / serve 等，并如实标注其来源是 reference view（不伪装成融合结果）。

#### Scenario: 数据来源如实标注

- **WHEN** Parent 报告同时包含 fused 位置指标与 reference-view 的非位置结果
- **THEN** 报告 SHALL 明确区分哪些数据来自多视角融合、哪些来自 reference view
- **AND** 不得将 reference-view 结果标注为融合结果

### Requirement: 归一化到 Parent namespace

Composer MUST 把 P0 fused artifacts 与 diagnostics 发布到 Parent artifact namespace（`/jobs/{parent_id}/artifacts/...`），并生成 Parent-owned `report.json` 与 artifact manifest。报告内 `job_id`、artifact URL、`report_id` 均 MUST 指向 Parent，MUST NOT 指向 internal child。

#### Scenario: 产物归 Parent

- **WHEN** Composer 完成组装
- **THEN** `fused_player_trajectory.v1` 与 `fused_diagnostics.json` SHALL 经 Parent artifact 端点可访问
- **AND** Parent 报告内的所有引用 SHALL 解析到 Parent 自身

#### Scenario: 内部 child 不泄漏

- **WHEN** Parent 报告已生成
- **THEN** 报告 SHALL NOT 包含 child 的 `job_id`、child `report_id` 或指向 child 的 artifact URL
- **AND** child 标识只出现在 provenance / 技术详情中

### Requirement: artifact manifest 作为 Parent 唯一产品出口

Parent 报告 MUST 内嵌 `artifacts` 清单作为产品层唯一出口（`playerTrajectory / fusionDiagnostics / referenceOverlay`，各带 `source` 与 `url`）。P0 的 `MultiViewFusionRun` 产物目录（`multiview/run/<run_id>/`）MUST 视为中间产物，Composer MUST 把 fused artifacts 与 diagnostics **复制/改写 URL 到 Parent artifact 命名空间**，产品层 MUST NOT 引用 fusion run 目录。

#### Scenario: manifest 列出产品产物

- **WHEN** 双摄融合完成
- **THEN** Parent 报告 SHALL 内嵌 `artifacts` 清单，列出 `playerTrajectory`（`source: fused`）、`fusionDiagnostics`、`referenceOverlay`（`source: cam_1`）及各自 Parent 命名空间 URL
- **AND** 清单内所有 URL SHALL 解析到 Parent 自身

#### Scenario: 前端只消费 Parent 命名空间

- **WHEN** 前端渲染双摄结果
- **THEN** 所有数据来源 SHALL 经 Parent artifact 命名空间 / manifest 取得
- **AND** SHALL NOT 出现指向 `multiview/run/<run_id>/` 的引用

### Requirement: fallback 同样 compose Parent 报告

当执行确定性单视角降级（sync 不可用或单路失败）时，Composer MUST 仍重新生成 Parent-owned 报告：内容可继承成功 child 的结果，但所有权必须归 Parent，并携带 `analysis_source` provenance（`mode / source_job_id / source_view / reason`）。

#### Scenario: B 机位失败降级

- **WHEN** cam_2 失败、Parent 以 cam_1 单视角降级
- **THEN** Parent 报告 SHALL 包含 cam_1 的结果但所有权归 Parent
- **AND** provenance SHALL 记录 `{mode: "single_view_fallback", source_job_id: <child-a>, source_view: "cam_1", reason: "cam_2_failed"}`

#### Scenario: sync 不可用降级

- **WHEN** 两路均完成但 sync 不可用、未执行融合
- **THEN** Parent 报告 SHALL 使用确定性单视角结果（reference view 优先）
- **AND** 展示「未执行多视角融合」的明确提示
- **AND** provenance SHALL 记录 `mode: "single_view_fallback"` 及原因
