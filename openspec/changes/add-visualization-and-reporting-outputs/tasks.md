## 1. Visualization module structure

- [x] 1.1 Create `backend/app/vision/pickleball_game_analysis/visualization_schemas.py` for visualization configs, manifest models, label maps, and status payload helpers
- [x] 1.2 Create `backend/app/vision/pickleball_game_analysis/minimap_visualizer.py`
- [x] 1.3 Create `backend/app/vision/pickleball_game_analysis/position_visualizer.py`
- [x] 1.4 Create `backend/app/vision/pickleball_game_analysis/overlay_video_writer.py`
- [x] 1.5 Keep visualization modules independent from FastAPI routes and avoid moving existing tracking, pose, ball, bounce, or player trajectory logic

## 2. Artifact loading and coordinate normalization

- [x] 2.1 Add helper logic to load optional `tracking_overlay.json`, `pose_overlay.json`, `ball_overlay.json`, `players_trajectory.json`, `ball_trajectory.json`, `cleaned_ball_trajectory.json`, and `bounce_events.json`
- [x] 2.2 Normalize player, ball, and bounce court points into the project standard 20 ft × 44 ft coordinate system
- [x] 2.3 Use existing court unit metadata and conversion helpers when an input artifact declares meters
- [x] 2.4 Skip malformed or unrecognized points without failing visualization generation
- [x] 2.5 Add unit tests for feet and meter coordinate normalization

## 3. Minimap visualization

- [x] 3.1 Implement court-to-minimap pixel mapping with configurable width, height, and padding
- [x] 3.2 Draw court boundary, kitchen lines, net line, center lines, and service boxes from existing `standard_court()` geometry
- [x] 3.3 Draw player positions and trails from `players_trajectory.json`
- [x] 3.4 Draw ball positions and recent ball trail from cleaned ball trajectory when available
- [x] 3.5 Draw bounce candidate markers from `bounce_events.json`
- [x] 3.6 Add unit tests for mapping corners, center court, net line, and out-of-bounds skip behavior

## 4. Position visualizations

- [x] 4.1 Implement `PositionVisualizer` heatmap generation for player court positions
- [x] 4.2 Implement player position scatter plots with per-player colors or labels
- [x] 4.3 Implement ball trajectory scatter plot from cleaned ball trajectory with raw trajectory fallback
- [x] 4.4 Implement bounce point scatter plot from bounce candidate events
- [x] 4.5 Save heatmap images under `position_visualizations/heatmaps`
- [x] 4.6 Save scatter images under `position_visualizations/scatter_plots`
- [x] 4.7 Write `position_visualizations/heatmaps/manifest.json`
- [x] 4.8 Write `position_visualizations/scatter_plots/manifest.json`
- [x] 4.9 Include `id`, `kind`, `label`, `title`, `description`, `file_name`, `file_path`, `url`, `artifact_url`, `width`, `height`, and `source_artifacts` for each manifest item
- [x] 4.10 Write `no_data` or `unavailable` manifests when enabled but no valid points exist

## 5. Overlay video generation

- [x] 5.1 Implement `OverlayVideoWriter` using OpenCV video read/write
- [x] 5.2 Read source video from existing uploaded or recorded video storage metadata
- [x] 5.3 Align tracking, pose, ball, bounce, and minimap data by frame index or timestamp
- [x] 5.4 Draw player bounding boxes, stable player labels, and track IDs
- [x] 5.5 Draw pose skeleton when `pose_overlay.json` is available
- [x] 5.6 Draw ball marker and recent ball trail when ball artifacts are available
- [x] 5.7 Draw bounce candidate markers when `bounce_events.json` is available
- [x] 5.8 Draw minimap panel on each output frame when court-coordinate data is available
- [x] 5.9 Write output to `analysis_overlay.mp4`
- [x] 5.10 Degrade gracefully when optional artifacts are missing or source video cannot be opened

## 6. Overlay labels and language support

- [x] 6.1 Reuse existing `visualization_language` setting
- [x] 6.2 Add Chinese labels for player, ball, bounce, speed, distance, and frame time
- [x] 6.3 Add English labels for player, ball, bounce, speed, distance, and frame time
- [x] 6.4 Add fallback behavior for unsupported language values
- [x] 6.5 Keep text rendering optional so missing fonts do not fail video or image generation

## 7. Pipeline integration

- [x] 7.1 Replace current fixed skipped visualization placeholder in `AnalysisPipeline` with a real conditional visualization stage
- [x] 7.2 Run visualization after metrics, ball trajectory, bounce detection, pose, and player trajectory artifacts are finalized
- [x] 7.3 Respect `enable_analysis_overlay_video`
- [x] 7.4 Respect `enable_position_visualizations`
- [x] 7.5 Set `analysis_overlay_video_path`, `analysis_overlay_video_url`, `analysis_overlay_video_status`, and `analysis_overlay_video_detail`
- [x] 7.6 Set `heatmaps_manifest_json_path`, `heatmaps_url`, `scatter_plots_manifest_json_path`, and `scatter_plots_url`
- [x] 7.7 Set `position_visualizations_status` and `position_visualizations_detail`
- [x] 7.8 Mark visualization stage as skipped, done, partial, failed, or unavailable based on generated outputs
- [x] 7.9 Ensure visualization failures do not fail the whole analysis job

## 8. API compatibility

- [x] 8.1 Keep existing artifact names backward compatible
- [x] 8.2 Ensure `analysis-overlay-video` returns generated mp4 with `video/mp4`
- [x] 8.3 Ensure `position-heatmaps` returns heatmap manifest JSON
- [x] 8.4 Ensure `position-scatter-plots` returns scatter manifest JSON
- [x] 8.5 Return clear 404 when optional visualization artifact is disabled or missing
- [x] 8.6 Ensure URLs in `AnalysisArtifacts` match existing route names
- [x] 8.7 If image files need direct browser access, add or reuse a stable route and reference it from manifest item URLs

## 9. Frontend integration

- [x] 9.1 Add visualization artifact fields to `src/types/report.ts`
- [x] 9.2 Add analysis overlay video URL resolving and manifest fetch helpers in `src/services/analysisClient.ts`
- [x] 9.3 Load heatmap and scatter manifests in the analysis result or vision page data hook
- [x] 9.4 Display generated `analysis_overlay.mp4` when available while preserving existing source video + JSON overlay behavior
- [x] 9.5 Display heatmap manifest items with image, title, description, and source status
- [x] 9.6 Display scatter plot manifest items with image, title, description, and source status
- [x] 9.7 Show skipped, unavailable, missing, and failed states without broken images or blank video containers

## 10. Documentation

- [x] 10.1 Document generated visualization artifact outputs and paths
- [x] 10.2 Document required and optional input artifacts for each visualization type
- [x] 10.3 Document `enable_analysis_overlay_video`, `enable_position_visualizations`, and `visualization_language`
- [x] 10.4 Document Good-Pickleball migration mapping for minimap, overlay video, heatmaps, scatter plots, and bilingual labels
- [x] 10.5 Document known limitations including font rendering, optional video generation cost, and candidate-only bounce semantics

## 11. Tests and validation

- [x] 11.1 Test minimap coordinate mapping and court line drawing
- [x] 11.2 Test position visualizer heatmap manifest generation
- [x] 11.3 Test position visualizer scatter manifest generation
- [x] 11.4 Test position visualizer no-data manifest behavior
- [x] 11.5 Test overlay writer with tracking-only artifacts
- [x] 11.6 Test overlay writer with ball and bounce artifacts
- [x] 11.7 Test pipeline when visualization is disabled
- [x] 11.8 Test pipeline when position visualization succeeds and overlay video is disabled
- [x] 11.9 Test pipeline when overlay video generation fails
- [x] 11.10 Test artifact API returns generated overlay video
- [x] 11.11 Test artifact API returns heatmap manifest
- [x] 11.12 Test artifact API returns scatter plot manifest
- [x] 11.13 Run backend unit tests relevant to analysis artifacts and pipeline
- [x] 11.14 Run frontend type check or build for updated visualization artifact UI
