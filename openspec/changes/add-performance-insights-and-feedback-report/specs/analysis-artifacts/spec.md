## ADDED Requirements

### Requirement: performance_insights 产物字段与再生成语义

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中新增 `performance_insights_json_path` / `performance_insights_url` / `performance_insights_status` / `performance_insights_detail` 四个可选字段，作为 `performance-insights.v1` artifact 的产物契约；该产物由 post-pipeline 的 Insight Engine 服务写入确定性路径（capture 任务位于 `analysis/<job_id>/` 下，普通任务位于 `outputs/<job_id>/`），并支持仅凭已落盘输入产物独立再生成。

#### Scenario: 真实任务填充产物字段

- **WHEN** 真实分析任务完成且 insights 生成成功
- **THEN** `performance_insights_json_path` SHALL 指向该任务的 `performance_insights.json` 文件
- **AND** `performance_insights_url` SHALL 为浏览器可访问的 artifact URL
- **AND** `performance_insights_status` SHALL 为 `available`

#### Scenario: 洞察生成失败显式状态

- **WHEN** insights 生成失败或被跳过
- **THEN** `performance_insights_status` SHALL 为 `skipped`、`unavailable` 或 `failed` 之一，`performance_insights_detail` SHALL 说明原因
- **AND** 该状态 MUST NOT 使视觉 pipeline 结果本身判定为失败

#### Scenario: artifact API 读取洞察产物

- **WHEN** 客户端请求已生成的 `performance-insights` artifact
- **THEN** API SHALL 返回 200 与 JSON 内容
- **WHEN** 客户端请求已知但当前任务未生成的 `performance-insights`
- **THEN** API SHALL 返回 404，MUST NOT 返回 422

#### Scenario: 再生成覆盖旧版本

- **WHEN** Insight Engine 以新 `rule_profile_version` 对同一 job 再生成
- **THEN** 系统 SHALL 原子覆盖同一确定性路径下的 `performance_insights.json`
- **AND** 再生成过程 MUST NOT 触发视觉分析阶段重跑或改写视觉 artifacts
