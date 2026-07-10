# projection-diagnostics Specification

## Purpose
TBD - created by syncing change improve-player-court-projection-reliability.

## Requirements
### Requirement: 投影全链路 JSONL 诊断日志

系统 SHALL 在启用 `enable_projection_debug_jsonl` 时，对每帧每个已跟踪球员输出一条 JSONL 记录，包含 bbox、脚点、投影坐标、分类状态等全链路信息。写入采用 line-buffered 模式，每 `flush_interval_frames`（默认 30）帧 flush 一次，异常/结束时强制 flush。

#### Scenario: 标准帧诊断记录

- **WHEN** 一帧内一个 track_id 被投影为 inside_court
- **THEN** JSONL 记录 SHALL 包含 `frame_index`, `track_id`, `bbox`, `image_footpoint`, `footpoint_method`, `footpoint_confidence`, `court_position_raw`, `court_position_smoothed`, `projection_status`, `minimap_pixel`, `homography`, `calibration_quality` 字段
- **AND** `footpoint_confidence` SHALL 为 0.0~1.0 的浮点数

#### Scenario: bbox 底边接近画面底部时记录

- **WHEN** bbox 的 y2 > frame_height * near_clip_threshold 且 footpoint_method 为 `bbox_bottom_center`
- **THEN** JSONL 记录 SHALL 包含 `near_frame_bottom: true` 和 `bbox_clip_suspected: true` 字段
- **AND** `projection_confidence` SHALL <= 0.35

#### Scenario: 投影分类为 outside_court_visible

- **WHEN** court_position 在 tracking_bounds 内但不在 court_bounds 内
- **THEN** `projection_status` SHALL 为 `"outside_court_visible"`
- **AND** 该点 SHALL 仍在 JSONL 记录中（不因界外而丢弃诊断）

#### Scenario: JSONL flush 策略

- **WHEN** debug JSONL 写入进行中
- **THEN** 系统 SHALL 使用 line-buffered 模式打开文件
- **AND** 每 `flush_interval_frames`（默认 30）帧执行一次 `file.flush()`
- **AND** 异常退出或正常结束时 SHALL 强制 flush 剩余缓冲

#### Scenario: 诊断开关关闭

- **WHEN** `enable_projection_debug_jsonl` 为 False
- **THEN** 系统 SHALL NOT 生成 JSONL 文件
- **AND** 系统 SHALL NOT 产生额外 I/O 开销

### Requirement: 投影诊断叠加视频

系统 SHALL 在启用 `enable_projection_debug_overlay` 时，生成 `projection_debug_overlay.mp4`，在源视频帧上绘制 bbox、脚点标记、投影 court 坐标文本。

#### Scenario: Debug overlay 绘制内容

- **WHEN** debug overlay 渲染一帧
- **THEN** 系统 SHALL 绘制以下元素：
  - 球员 bbox（绿色矩形）
  - 脚点标记（红色十字，圆心为 image_footpoint）
  - 投影坐标文本（如 "court: (10.2, 15.8)"）
  - footpoint_method 文本（如 "method: pose_ankle_midpoint"）
  - projection_status 文本（如 "status: inside_court"）
  - 球场四角编号（可选，用于验证标定）

#### Scenario: 裁切脚点在 debug overlay 中高亮

- **WHEN** bbox 被标记为 `near_frame_bottom: true` + `bbox_clip_suspected: true`
- **THEN** 该球员的 bbox SHALL 以黄色（而非绿色）绘制
- **AND** footpoint_method 文本 SHALL 显示 "method: bbox_bottom_center ⚠ clip_suspected"

#### Scenario: Debug overlay 使用半透明绘制

- **WHEN** debug overlay 绘制在源视频帧上
- **THEN** 调试元素 SHALL 使用半透明叠加（alpha ≈ 0.5~0.7），确保源视频内容仍可见

#### Scenario: Debug overlay 无可用数据时

- **WHEN** 某帧没有球员跟踪数据
- **THEN** 系统 SHALL 输出原始视频帧（不加任何叠加元素）
- **AND** JSONL 记录 SHALL 跳过该帧（不输出空记录）

#### Scenario: 诊断开关关闭

- **WHEN** `enable_projection_debug_overlay` 为 False
- **THEN** 系统 SHALL NOT 生成 debug overlay 视频
