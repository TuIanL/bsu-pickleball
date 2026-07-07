## MODIFIED Requirements

### Requirement: Visualization manifests are stable

系统 SHALL 使用 manifest JSON 描述位置热力图和散点图，而不是把目录 listing 作为 API 契约。

#### Scenario: Heatmap manifest describes generated images

- **WHEN** 后续可视化模块生成位置热力图
- **THEN** `position_visualizations/heatmaps/manifest.json` MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含 `items` 数组
- **AND** 每个 item MUST 能表达 `id`、`kind`、`label`、`file_name`、`url`、`width` 和 `height`
- **AND** 每个 item MUST 能表达 `title`、`description`、`file_path`、`artifact_url` 和 `source_artifacts`。

#### Scenario: Scatter plot manifest describes generated images

- **WHEN** 后续可视化模块生成位置散点图
- **THEN** `position_visualizations/scatter_plots/manifest.json` MUST 包含 `schema_version`
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `status`
- **AND** MUST 包含 `detail`
- **AND** MUST 包含 `items` 数组
- **AND** 每个 item MUST 能表达 `id`、`kind`、`label`、`file_name`、`url`、`width` 和 `height`
- **AND** 每个 item MUST 能表达 `title`、`description`、`file_path`、`artifact_url` 和 `source_artifacts`。
