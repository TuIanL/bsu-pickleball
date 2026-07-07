## 1. 补齐 ball_overlay.json artifact

- [x] 1.1 新建 `backend/app/schemas/ball.py`，定义 `BallOverlayFrame`、`BallOverlayArtifact` 等 Pydantic 模型（含 `source`、`coverage`、`frames` 结构）。
- [x] 1.2 在 `detection_writer.py` 中新增 `build_ball_overlay_payload()` 函数，从 `BallFrameSample` 列表构造 ball overlay payload。
- [x] 1.3 在 `_finalize_ball_analysis()` 中写入 `ball_overlay.json`（通过 `StorageService.ball_overlay_json_path()`）。
- [x] 1.4 在 `_BallArtifactFields` 中填充 `ball_overlay_json_path`、`ball_overlay_url`、`ball_overlay_status`、`ball_overlay_detail`。
- [x] 1.5 确保球检测 unavailable 或 skipped 时，`ball_overlay.json` 仍返回稳定结构（`status: "unavailable"` 或 `"skipped"`、空 `frames`、完整 `source`/`coverage` metadata）。

## 2. 阶段通知与 counters 补齐

- [x] 2.1 将 `_finalize_ball_analysis()` 中的三个阶段收敛为两个：`ball-trajectory` 和 `bounce-detection`（移除独立 `ball-detection` 阶段，将检测信息并入 `ball-trajectory` 的 counters）。
- [x] 2.2 在 `ball-trajectory` 和 `bounce-detection` 阶段创建前后通过 `_notify_progress()` 发送进度回调（active → done/skipped/failed）。
- [x] 2.3 为 `ball-trajectory` stage 填充完整 counters：`processed_frame_count`、`ball_detection_count`、`raw_sample_count`、`missing_frame_count`、`detection_rate`、`frame_stride`、`court_unit`、`model_enabled`。
- [x] 2.4 为 `bounce-detection` stage 填充完整 counters：`input_sample_count`、`cleaned_sample_count`、`interpolated_sample_count`、`bounce_event_count`、`detection_mode`、`status`。
- [x] 2.5 确保 counters 可 JSON 序列化，且与 artifact 内容一致。

## 3. 新增 strict mode 配置与行为

- [x] 3.1 在 `backend/app/core/config.py` 中新增 `ball_analysis_strict` 配置项（默认 `false`），环境变量 `PICKLEBALL_BALL_ANALYSIS_STRICT`。
- [x] 3.2 在 `_finalize_ball_analysis()` 中实现默认非 strict 行为：球检测/弹跳检测异常记录 detail 但 pipeline 继续。
- [x] 3.3 在 `run()` 中实现 strict mode 行为：`ball_analysis_strict=true` 时球分析异常导致 pipeline failed。
- [x] 3.4 确保 `no_candidates` 永远不触发失败（无论 strict mode）。
- [x] 3.5 确保视频读取失败和 tracking 主流程失败不受 strict mode 影响（这些在任何模式下都致命）。

## 4. 提取 bounce 后处理逻辑

- [x] 4.1 从 `_run_tracking()` 末尾提取 trajectory cleaning + bounce detection 逻辑为独立方法 `_run_bounce_detection()`。
- [x] 4.2 `_run_bounce_detection()` 接收 `job_id`、`video_id`、`ball_samples: list[BallFrameSample]`，返回 `_BounceRunOutput`（含 cleaned_points、bounce_events、counters）。
- [x] 4.3 `_run_bounce_detection()` 负责调用 `TrajectoryCleaner.clean()` 和 `BounceDetector.detect()`，不负责写文件。
- [x] 4.4 确保 `_run_bounce_detection()` 在 ball samples 为空或不足时返回 `no_candidates` 而非抛异常。

## 5. 提取逐帧球处理逻辑

- [x] 5.1 定义局部 dataclass `_BallRunContext`（tracker、samples、detections、error、disabled_reason），替代当前分散在 `_run_tracking()` 中的局部变量和 `self._ball_tracker`、`self._ball_run_error` 实例状态。
- [x] 5.2 提取 `_process_ball_frame()` 静态/实例方法，接收 `context: _BallRunContext`、`frame`、`frame_index`、`timestamp`、`homography`，封装 try/except 和 `context.tracker = None` 的降级逻辑。
- [x] 5.3 在 `_run_tracking()` 循环中用 `_process_ball_frame(context, ...)` 替换内联球检测代码块。
- [x] 5.4 保持单视频读取循环，不引入第二次 `cv2.VideoCapture`。
- [x] 5.5 确保人体 tracking 逻辑不受影响：现有 player detection、tracking、projection、identity、pose 流程保持不变。

## 6. 球/弹跳指标并入 metrics summary

- [x] 6.1 在 `PerformanceMetrics` 或 pipeline result 的 metrics 摘要中增加 `ball_detected_frame_count`。
- [x] 6.2 增加 `ball_detection_rate`。
- [x] 6.3 增加 `ball_trajectory_sample_count`。
- [x] 6.4 增加 `cleaned_ball_trajectory_sample_count`。
- [x] 6.5 增加 `bounce_event_count`。
- [x] 6.6 增加 `first_bounce_timestamp_seconds` 和 `last_bounce_timestamp_seconds`（当有弹跳事件时）。
- [x] 6.7 确保无球轨迹时对应指标为 0 或 null，不破坏原有 `PerformanceMetrics` 字段。

## 7. 集成测试

- [x] 7.1 使用 fake ball samples 验证 `_finalize_ball_analysis()` 成功写入所有 5 个 artifact（ball_overlay、detections、ball_trajectory、cleaned_ball_trajectory、bounce_events）并填充完整 status/detail。
- [x] 7.2 验证球检测关闭或模型不可用时 ball 和 bounce 阶段均为 `skipped`，pipeline 仍 `completed`。
- [x] 7.3 验证默认（非 strict）模式下球检测/弹跳检测异常不导致 pipeline failed，tracking/pose/serve 仍正常执行。
- [x] 7.4 验证 strict mode 下球分析异常导致 pipeline failed，错误信息可定位到具体阶段。
- [x] 7.5 验证无标定路径 ball/bounce 阶段 skipped，且不生成 fake ball artifact。
- [x] 7.6 验证 ball 成功但 bounce `no_candidates` 时 bounce_events.json 写入空 events 数组，pipeline 不 failed。
- [x] 7.7 运行现有 tracking / pose / serve 相关测试，确保全部通过。
