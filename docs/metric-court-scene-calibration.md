# Metric Court Scene Calibration

## Purpose

双摄同一 `capture_take_id` 使用一个可复用的 Canonical Court 3D 场景。球场地面仍以 20 × 44 ft 表示，球网位于 `y=22 ft`，场景 revision 与采集任务绑定；同一任务下的多个录制视频复用同一 revision，不做逐帧或逐视频动态重标定。

## Net profile

首版支持人工确认的 `standard` 和 `measured` profile。标准匹克球网的控制点为：两侧 91.44 cm（3.0 ft），中心 86.36 cm（34/12 ft）。后端以 feet 存储，生成确定性的顶部采样曲线；网柱可使用独立的 `post_world_points`，因此允许网柱位于球场边线之外。

每个 view 保存左端、中心、右端的 image-space 点，并通过 `image_by_view` 映射到同一组三维控制点。当前 provider 只使用 `manual` / `manual_verified`；`auto_suggested` 是兼容字段，首版不包含公开数据集训练或自动标注模型上线。

## Lifecycle and fallback

场景文件位于 CaptureTake 的 `analysis/metric_court_scene/` 下：`draft.json` 用于恢复工作台，`current.json` 指向当前 revision，`revisions/revision-N.json` 为不可变历史引用。

创建双摄 joint 任务时，`sceneCalibrationMode` 明确为 `metric` 或 `approximate`：

- `metric` 必须携带属于当前 CaptureTake、覆盖目标 views 且 camera/video/image-size provenance 一致的 ready revision；否则 preflight 拒绝创建。
- `approximate` 保留旧 Homography virtual camera，并在 evidence、trajectory 和前端场景中标为 approximate fallback。
- metric 场景 refinement 失败时保留审计证据，但不将该证据升级为 metric high-quality anchor。

Artifact 中保留 `scene_calibration_revision`、`camera_model_source`、`metric_validity`、`height_uncertainty_ft` 和质量分量，历史 v1/v2/v3 产物仍按原语义只读读取，不回写为新的 scene semantics。
