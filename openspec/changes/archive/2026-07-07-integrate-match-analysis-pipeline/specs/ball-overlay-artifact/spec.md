# ball-overlay-artifact Specification

## Purpose
定义 `ball_overlay.json` 的 schema、写入逻辑和 API 读取路径，产出帧级球检测叠加数据（image-space bbox/center/confidence + court-space point），前端可通过 `/api/analysis/jobs/{job_id}/artifacts/ball-overlay` 读取。

## ADDED Requirements

### Requirement: Ball overlay schema is defined
系统 SHALL 定义 `ball_overlay.json` 的稳定 schema，包含 source metadata、coverage 摘要和按帧 ball overlay 数据，且 SHALL 只包含球分析实际运行过的抽样帧。

#### Scenario: Ball overlay contains source metadata
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** 文件 MUST 包含 `schema_version`（固定为 `"ball_overlay.v1"`）
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `video_id`
- **AND** MUST 包含 `status`（`available`、`partial`、`no_detections` 或 `unavailable`）
- **AND** MUST 包含 `detail`（人类可读的状态说明）
- **AND** MUST 包含 `source` object，含 `width`、`height`、`fps`、`frame_stride`、`processed_frame_count`

#### Scenario: Ball overlay contains coverage metadata
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** 文件 MUST 包含 `coverage` object
- **AND** `coverage` MUST 包含 `overlay_frame_count`（有球 overlay 记录的帧数）
- **AND** `coverage` MUST 包含 `missing_frame_count`（球检测未发现候选的帧数）
- **AND** `coverage` MUST 包含 `detection_rate`（`overlay_frame_count / processed_frame_count`）

#### Scenario: Ball overlay frame represents a single processed frame
- **WHEN** pipeline 为某个抽样帧写入 ball overlay 记录
- **THEN** 该帧记录 MUST 包含 `frame_index`
- **AND** MUST 包含 `timestamp_seconds`
- **AND** MUST 包含 `ball` object
- **AND** `ball` MUST 包含 `center` object（`x`、`y`，image-space 球中心坐标，可为 null 表示未检测到）
- **AND** `ball` MUST 包含 `bbox`（`[x1, y1, x2, y2]`，image-space 检测框，可为 null）
- **AND** `ball` MUST 包含 `confidence`（可为 null）
- **AND** `ball` MUST 包含 `track_status`（`detected`、`missing`、`rejected`）
- **AND** `ball` MAY 包含 `court` object（`x`、`y`、`unit`，court-space 投影坐标，可为 null）

#### Scenario: Ball overlay only includes processed frames
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** `frames` 数组 MUST 只包含球检测实际运行的抽样帧
- **AND** `frames` 数组 MUST NOT 强制补全每个 frame_index 或包含 `ball: null` 作为占位

#### Scenario: Ball overlay remains stable when tracking is unavailable
- **WHEN** 球检测未启用或不可用
- **THEN** `ball_overlay.json` MUST 仍然可写入
- **AND** `status` MUST 为 `unavailable` 或 `skipped`
- **AND** `frames` MUST 为空数组
- **AND** `source` 和 `coverage` MUST 仍然包含 metadata（其中 `overlay_frame_count` 为 0）

### Requirement: Ball overlay artifact is retrievable via API
系统 SHALL 通过现有 artifact API 端点暴露 `ball_overlay.json`，路径为 `/api/analysis/jobs/{job_id}/artifacts/ball-overlay`。

#### Scenario: Ball overlay is available
- **WHEN** 客户端请求已生成 `ball_overlay.json` 的 job 的 `ball-overlay` artifact
- **THEN** API MUST 返回 200
- **AND** 响应 MUST 是 JSON
- **AND** 响应 MUST 包含完整 schema（包括 source、coverage 和 frames）

#### Scenario: Ball overlay is not generated
- **WHEN** 客户端请求未生成 `ball_overlay.json` 的 job 的 `ball-overlay` artifact
- **THEN** API MUST 返回 404
- **AND** MUST NOT 返回 422

### Requirement: Ball overlay is distinct from ball trajectory
系统 SHALL 保持 `ball_overlay.json` 与 `ball_trajectory.json` 的职责分离 —— 前者是帧级叠加数据（面向视频渲染），后者是轨迹连续采样（面向分析和统计）。

#### Scenario: Ball overlay carries image-space data
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** 每条帧记录 MUST 包含 image-space bbox 和 center
- **AND** court-space point 是可选字段（当 homography 不可用时可为 null）

#### Scenario: Ball trajectory carries trajectory continuity data
- **WHEN** pipeline 写入 `ball_trajectory.json`
- **THEN** 每条 sample MUST 包含 `image_xy`、`court_xy`、`confidence` 和 `source`
- **AND** trajectory sample MUST NOT 包含 bbox 或 overlay-specific 渲染字段

#### Scenario: Frame indices align between overlay and trajectory
- **WHEN** `ball_overlay.json` 和 `ball_trajectory.json` 同时生成
- **THEN** 两者的 `frame_index` 和 `timestamp_seconds` MUST 对齐
- **AND** 同一 `frame_index` 的 `ball_overlay.frames[].ball.center` 与 `ball_trajectory.samples[].image_xy` MUST 一致

### Requirement: Ball overlay writer is added to detection_writer
系统 SHALL 在 `detection_writer.py` 中新增 `build_ball_overlay_payload()` 函数，遵循与 `build_raw_trajectory_payload()`、`build_cleaned_trajectory_payload()`、`build_bounce_events_payload()` 一致的接口风格。

#### Scenario: Ball overlay payload builder can construct full payload
- **WHEN** 调用 `build_ball_overlay_payload()` 并传入 job_id、video_id、source metadata、coverage 和 ball samples
- **THEN** 函数 MUST 返回包含 schema_version、job_id、video_id、status、detail、source、coverage 和 frames 的完整 payload dict
- **AND** 每个 frame 的 ball 数据 MUST 从 `BallFrameSample` 构造

#### Scenario: Ball overlay payload builder handles empty samples
- **WHEN** 调用 `build_ball_overlay_payload()` 并传入空 samples 列表
- **THEN** 函数 MUST 返回 status 为 `no_detections` 或 `unavailable` 的 payload
- **AND** frames MUST 为空数组
- **AND** source 和 coverage metadata MUST 仍然完整
