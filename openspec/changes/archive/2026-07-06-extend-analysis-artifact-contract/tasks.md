## 1. Contract Tests

- [x] 1.1 增加 `StorageService` 路径测试，覆盖 `detections.jsonl`、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`、`analysis_overlay.mp4`、heatmap manifest 和 scatter plot manifest。
- [x] 1.2 增加 `AnalysisArtifacts` 序列化测试，确认新增 path、url、status、detail 字段可选且不会破坏旧 payload。
- [x] 1.3 更新 `ball-overlay` artifact API 测试，将历史 422 预期改为已知 artifact 缺失时 404、存在时 200 JSON。
- [x] 1.4 增加新增 JSON artifact API 测试，覆盖 `ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events`、`position-heatmaps` 和 `position-scatter-plots`。
- [x] 1.5 增加 `detections` JSONL artifact API 测试，确认响应保留逐帧记录边界。
- [x] 1.6 增加 `analysis-overlay-video` API 测试，确认存在文件时返回 `video/mp4`。
- [x] 1.7 增加 Settings 默认值和环境变量覆盖测试，覆盖球模型、球检测、弹跳检测、叠加视频、位置可视化和可视化语言配置。

## 2. Storage And Artifact Model

- [x] 2.1 在 `StorageService` 中新增 `detections_jsonl_path()`、`ball_trajectory_json_path()`、`cleaned_ball_trajectory_json_path()`、`bounce_events_json_path()` 和 `analysis_overlay_video_path()`。
- [x] 2.2 在 `StorageService` 中新增 `position_visualizations_dir()`、`heatmaps_dir()`、`scatter_plots_dir()`、`heatmaps_manifest_json_path()` 和 `scatter_plots_manifest_json_path()`。
- [x] 2.3 保留现有 `ball_overlay_json_path()`，并将其纳入新增 artifact contract。
- [x] 2.4 扩展 `AnalysisArtifacts`，加入新增 artifact 的 path、url、status 和 detail 字段，所有字段默认 `None`。

## 3. Artifact API

- [x] 3.1 扩展 `read_analysis_artifact()` 的 `artifact_name` Literal，加入 `ball-overlay`、`detections`、`ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events`、`analysis-overlay-video`、`position-heatmaps` 和 `position-scatter-plots`。
- [x] 3.2 将新增 artifact name 映射到对应 `StorageService` 路径，确保已知但未生成的 artifact 返回 404。
- [x] 3.3 为 JSON artifact 继续返回 `JSONResponse`，并读取对应 JSON 文件。
- [x] 3.4 为 `detections` 返回保留 JSONL 记录边界的响应，避免使用 `read_json()` 解析整个 JSONL 文件。
- [x] 3.5 为 `analysis-overlay-video` 返回 `FileResponse`，media type 为 `video/mp4`。
- [x] 3.6 确认现有 artifact name 的响应行为不变。

## 4. Configuration

- [x] 4.1 在 `Settings` 中新增球模型路径、启用球检测、启用弹跳检测、启用分析叠加视频、启用位置可视化和可视化语言字段。
- [x] 4.2 在 `get_settings()` 中接入对应 `PICKLEBALL_` 环境变量解析。
- [x] 4.3 确认默认配置不要求新增模型文件存在，且不强制生成尚未实现的产物。

## 5. Pipeline Contract Touchpoints

- [x] 5.1 在 Pipeline 结果组装处预留新增 artifact 字段变量，默认保持 `None`。
- [x] 5.2 确认未实现算法时 Pipeline 仍能返回成功结果，并且不会填充不存在 artifact 的 URL。
- [x] 5.3 确认后续算法只需要写入约定路径并填充 `AnalysisArtifacts` 字段即可接入。

## 6. Verification

- [x] 6.1 运行 `openspec validate extend-analysis-artifact-contract --strict` 并修正所有规范问题。
- [x] 6.2 运行后端相关测试，至少覆盖 `backend/tests/test_api_smoke.py` 和 `backend/tests/test_config.py`。
- [x] 6.3 手动检查新增 artifact name、文件路径、schema 字段和 tasks 是否与 spec 保持一致。
