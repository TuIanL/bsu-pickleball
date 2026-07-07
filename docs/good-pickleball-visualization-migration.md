# Good-Pickleball 可视化迁移说明

## 目标

本项目的 `add-visualization-and-reporting-outputs` change 迁移 Good-Pickleball 的可视化输出思路，将现有分析 artifact 转换为教练可读的叠加视频、小地图、热力图和散点图。

本迁移不包含 Kinovea、annotation import、人工标注报告或 PDF 导出。

## 输出 artifact

| 输出 | 路径 | API |
| --- | --- | --- |
| 分析叠加视频 | `outputs/{job_id}/analysis_overlay.mp4` | `/api/analysis/jobs/{job_id}/artifacts/analysis-overlay-video` |
| 热力图 manifest | `outputs/{job_id}/position_visualizations/heatmaps/manifest.json` | `/api/analysis/jobs/{job_id}/artifacts/position-heatmaps` |
| 散点图 manifest | `outputs/{job_id}/position_visualizations/scatter_plots/manifest.json` | `/api/analysis/jobs/{job_id}/artifacts/position-scatter-plots` |
| 可视化图片 | `outputs/{job_id}/position_visualizations/{heatmaps,scatter_plots}/*.png` | `/api/analysis/jobs/{job_id}/artifacts/position-visualization-images/{kind}/{file_name}` |

Manifest item 包含 `id`、`kind`、`label`、`title`、`description`、`file_name`、`file_path`、`url`、`artifact_url`、`width`、`height` 和 `source_artifacts`。

## 输入 artifact

可视化模块按需读取以下输入，缺失时跳过对应图层：

- `tracking_overlay.json`
- `pose_overlay.json`
- `ball_overlay.json`
- `players_trajectory.json`
- `ball_trajectory.json`
- `cleaned_ball_trajectory.json`
- `bounce_events.json`
- source video

## 坐标约定

本项目使用现有 CourtVision 标准球场坐标：20 ft × 44 ft，球网位于 y = 22 ft。

Good-Pickleball 的米制球场常量不直接复制。若输入 artifact 声明 `court_unit: "m"`，可视化层会转换为英尺后再绘制；无法识别或格式错误的点会被跳过。

## 配置开关

- `PICKLEBALL_ENABLE_ANALYSIS_OVERLAY_VIDEO`：启用 `analysis_overlay.mp4` 生成。
- `PICKLEBALL_ENABLE_POSITION_VISUALIZATIONS`：启用热力图和散点图生成。
- `PICKLEBALL_VISUALIZATION_LANGUAGE`：支持 `zh-CN` 和 `en-US`，不支持的值回退到默认语言。

## 已迁移能力映射

| Good-Pickleball 能力 | 本项目模块 / 输出 |
| --- | --- |
| Minimap | `MinimapVisualizer`，作为 overlay video 面板和位置图底图 |
| Annotated output video | `OverlayVideoWriter` → `analysis_overlay.mp4` |
| Player position heatmap | `PositionVisualizer` → heatmap manifest + PNG |
| Position scatter plots | `PositionVisualizer` → scatter manifest + PNG |
| 中英文显示 | `visualization_schemas.labels_for()` + `visualization_language` |

## 限制

- 叠加视频生成成本随视频长度增长，建议按需启用。
- OpenCV mp4 writer 在少数环境可能不可用；失败时 pipeline 仍会 completed，并在 artifact detail 中记录原因。
- 中文字体渲染是增强能力，字体不可用时不阻断图形输出。
- 弹跳点图只表示候选事实，不代表比分、犯规、击球归因或正式落点判定。
