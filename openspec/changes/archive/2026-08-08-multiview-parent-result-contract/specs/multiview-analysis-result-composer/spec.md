# multiview-analysis-result-composer Delta Specification

## MODIFIED Requirements

### Requirement: 继承 reference-view 结果

Composer MUST 从 reference view 继承非位置类结果：pose / ball / action classification / overlay video / serve 等，并如实标注其来源是 reference view（不伪装成融合结果）。继承 MUST 补齐产物契约：除复制文件与填写 `*_json_path` 外，SHALL 设置 `*_url`（指向 Parent 命名空间）与 `*_status`/`*_detail`（继承自 reference child 的落盘结果）。GB 级叠加视频 SHALL NOT 复制到 Parent 命名空间，改为引用 child 的 URL。

#### Scenario: 数据来源如实标注

- **WHEN** Parent 报告同时包含 fused 位置指标与 reference-view 的非位置结果
- **THEN** 报告 SHALL 明确区分哪些数据来自多视角融合、哪些来自 reference view
- **AND** 不得将 reference-view 结果标注为融合结果

#### Scenario: 产物契约完整

- **WHEN** Composer 继承 reference child 的产物
- **THEN** 每个继承产物的 `*_url` SHALL 指向 Parent 命名空间（`/api/analysis/jobs/{parent_id}/artifacts/{route}`）
- **AND** 对应 `*_status` / `*_detail` SHALL 继承自 child 落盘结果，使前端视觉层状态正确

#### Scenario: 大视频引用 child 而非复制

- **WHEN** reference child 存在叠加视频（`analysis_overlay.mp4`）
- **THEN** Parent 的 `analysis_overlay_video_url` SHALL 引用 child 的 URL
- **AND** SHALL NOT 复制该视频文件到 Parent 命名空间

## ADDED Requirements

### Requirement: 修复 getter 名不匹配产物继承

对 storage 访问器名与 `*_json_path` 后缀不一致的产物（`detections` / `analysis_overlay_video` / `serve_debug_overlay` / `player_render_trajectory`），Composer MUST 使用显式访问器名继承，不得再因 getter 名不匹配被静默跳过。

#### Scenario: 四类产物被正确继承

- **WHEN** reference child 生成了 `detections`、`analysis_overlay_video`、`serve_debug_overlay`、`player_render_trajectory`
- **THEN** 这些产物 SHALL 通过显式访问器名复制到 Parent 命名空间（或引用 child URL）
- **AND** 对应 `*_url` / `*_status` SHALL 在 Parent 结果中可用

### Requirement: Parent 结果补全视频源与球员数

Composer 生成的 Parent `AnalysisPipelineResult` SHALL 提供 `source_video_url`（基于 Parent 的 `videoId`）与 `observed_player_count`（fused 轨迹中的去重球员数），使前端能展示视频源与球员统计。

#### Scenario: 补全字段

- **WHEN** Composer 生成 Parent 结果
- **THEN** `artifacts.source_video_url` SHALL 基于 Parent 的 `videoId` 生成
- **AND** `observed_player_count` SHALL 等于 fused 轨迹中不同 `global_player_id` 的数量
