## Context

项目当前已经具备分析任务、文件存储、Pipeline 结果模型和 artifact API。`StorageService` 已经管理 `tracking_result.json`、`tracking_overlay.json`、`pose_overlay.json`、`serve_events.json`、`players_trajectory.json/csv`、`court_view_roi.json` 等本地产物路径，`AnalysisPipelineResult.artifacts` 也能向前端报告现有产物的 path、url、status 和 detail。

Good-Pickleball 的可迁移能力包含球检测、球轨迹、弹跳点、标注视频、热力图和散点图。直接迁算法前，如果没有稳定产物契约，后续 Pipeline、API、前端和报告会各自临时定义文件名和字段，增加兼容成本。

当前还有一个历史语义：代码中已经存在 `ball_overlay_json_path()`，但 artifact API 不接受 `ball-overlay`，测试也覆盖了“已移除 ball-overlay”。本 change 需要把语义从“拒绝该 artifact name”调整为“artifact name 稳定存在；如果文件未生成则返回 404，并在 PipelineResult 中可表达 unavailable 状态”。

## Goals / Non-Goals

**Goals:**

- 为新增分析产物定义稳定 artifact name、文件路径和 `AnalysisArtifacts` 字段。
- 让 artifact API 支持读取新增 JSON、JSONL、视频和 visualization manifest。
- 定义后续算法可写入、前端可消费的 JSON / JSONL schema。
- 为球模型、弹跳检测、叠加视频和位置可视化增加配置入口。
- 保持现有 artifact 名称、路径和 API 行为兼容。

**Non-Goals:**

- 不实现球检测模型调用。
- 不实现球轨迹清洗、插值或弹跳检测算法。
- 不生成标注视频、热力图、散点图或小地图。
- 不改造前端展示这些新增产物。
- 不重构现有 tracking、pose、serve 或 player trajectory 产物结构。

## Decisions

### Decision: 新增 `analysis-artifacts` capability

这次 change 新增 `analysis-artifacts` 作为产物契约层，而不是修改 `ball-tracking`。原因是本 change 的核心不是算法正确性，而是跨 `StorageService`、`AnalysisPipelineResult`、API 和 schema 的通用 artifact contract。

替代方案是把需求写进 `ball-tracking`。这个方案会让第一步看起来像算法实现，并且无法自然覆盖标注视频、热力图、散点图等非球检测本身的输出。

### Decision: artifact name 使用短横线，文件名使用下划线

API 层使用：

```text
ball-overlay
detections
ball-trajectory
cleaned-ball-trajectory
bounce-events
analysis-overlay-video
position-heatmaps
position-scatter-plots
```

文件层使用：

```text
ball_overlay.json
detections.jsonl
ball_trajectory.json
cleaned_ball_trajectory.json
bounce_events.json
analysis_overlay.mp4
position_visualizations/heatmaps/manifest.json
position_visualizations/scatter_plots/manifest.json
```

这样 API 名称继续符合现有 `tracking-overlay`、`serve-events` 风格，本地文件名继续符合现有 `tracking_overlay.json`、`serve_events.json` 风格。

### Decision: 逐帧检测使用 JSONL，聚合结果使用 JSON

`detections.jsonl` 每一行表示一帧检测记录，适合后续长视频逐帧追加写入、调试和流式处理。`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json` 和 `ball_overlay.json` 是聚合结果，使用 JSON 便于一次性读取和 schema 版本管理。

替代方案是所有内容都写成一个大 JSON。这个方案简单，但长视频会产生较大的单文件写入和解析压力，也不利于中途恢复或调试。

### Decision: 位置图通过 manifest 暴露，不直接暴露目录

`position-heatmaps` 和 `position-scatter-plots` 对应 `manifest.json`，manifest 内列出图片文件、指标、player_id、label、尺寸和 URL。API 不直接返回目录。

替代方案是让 API 返回目录 listing。这个方案对前端不够稳定，也会把目录结构泄漏成接口契约。

### Decision: 不存在的新增 artifact 返回 404

新增 artifact name 必须被 API 接受。如果对应文件尚未生成，API 返回 404。PipelineResult 则通过对应 status/detail 字段表达 `unavailable`、`disabled`、`not_generated` 或后续实现定义的状态。

替代方案是未实现时继续 422。这个方案会让前端无法区分“不认识该 artifact”与“当前任务没生成该 artifact”，不利于渐进迁移。

### Decision: schema 带 `schema_version`

新增 JSON / JSONL artifact 必须包含 `schema_version`。JSONL 中每一行也必须包含 `schema_version`，避免单行记录在脱离文件上下文时丢失版本信息。

替代方案是只在文件级别记录版本。这个方案对 JSONL 不够稳，因为 JSONL 常被切片、采样或单行调试。

## Risks / Trade-offs

- [Risk] 第一阶段只定义契约但不生成真实产物，前端看到 URL 后可能立即请求并得到 404。→ Mitigation：只有文件存在或状态可表达时才填充 URL；或者在 detail 中明确产物未生成原因。
- [Risk] 过早固定 schema 会限制后续算法输出。→ Mitigation：所有新增 schema 使用 `schema_version`，并把模型特有调试字段放进可选 `metadata` 或 `diagnostics`。
- [Risk] `detections.jsonl` 不能直接用现有 `read_json()` 读取。→ Mitigation：API 对 JSONL 使用文本响应或逐行解析后返回兼容结构，任务中明确测试该行为。
- [Risk] 视频 artifact 与 JSON artifact 响应类型不同。→ Mitigation：沿用现有 `serve-debug-overlay` 的 `FileResponse` 模式，新增 `analysis-overlay-video` 单独指定 `video/mp4`。
- [Risk] manifest 中的图片 URL 需要后续静态文件服务或 artifact 子路由配合。→ Mitigation：第一阶段 manifest 契约允许 `url` 为空或相对 artifact URL，后续 visualization change 再落实图片读取方式。

## Migration Plan

1. 增加 `StorageService` 新路径方法，保留已有 `ball_overlay_json_path()`。
2. 扩展 `AnalysisArtifacts` 新字段，默认值全部为 `None`，避免破坏旧结果反序列化。
3. 扩展 artifact API Literal 和路径映射；未生成文件返回 404。
4. 增加配置项并写入 `get_settings()` 环境变量解析。
5. 更新测试，把 `ball-overlay` 从 422 迁移为已识别 artifact name；不存在文件时返回 404，存在文件时返回 JSON。
6. 后续算法 change 可以在同一路径和字段上填充真实产物，不需要再改 contract。

Rollback 时可移除新增 API name 和字段；由于字段默认可选且不改变旧 artifact，回滚不需要数据迁移。

## Open Questions

- 位置图 PNG 文件后续是否通过现有 artifact API 增加子资源读取，还是通过独立静态文件路由暴露？
- `analysis-overlay-video` 是否长期作为最终标注视频名称，还是后续需要区分 `ball-overlay-video`、`match-overlay-video` 等更细粒度产物？
- `court_xy` 的单位是否统一沿用现有 player trajectory 的公制字段，还是在球相关 schema 中同时支持 feet 和 meters？
