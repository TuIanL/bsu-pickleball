## Why

joint_tracking_v2 双摄分析实测（job-3b411aefe6 / mvr_109696ea4110）存在一条结果链路缺陷：解帧语义错误导致检测跑在错误帧上；fused 轨迹缺失时间戳导致速度/小地图失效；joint 结果不产出视觉层产物导致前端框架/骨架不可用；聚合 stage 误报 A/B 机位失败；debug replay 前 3.4s 副摄无画面。这些问题叠加使双摄分析结果不可信、前端展示残缺，必须在本轮修复。

## What Changes

- 修复 `JointViewRuntime.get_frame` 解帧语义错误：`cap.set(0, source_frame_index)` 中 `0 = CAP_PROP_POS_MSEC`（毫秒），被当作帧号使用。实测 `set(0, 400)` 实际解码到 ≈帧 25，每 tick 仅前进 ~0.12 帧，导致检测框每 ~5-8 tick 才更新一次、且整个 joint 分析检测跑在视频开头错误帧上。改为 `cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)`。
- fused trajectory v2 样本补充 `timestamp_seconds`（由 `take_timestamp_ms` 派生），恢复 composer 位置类指标重算（速度/厨房停留）与前端小地图时间窗口过滤（`videoOverlayHud` 按 `timestamp_seconds` 窗口丢弃全部点）。
- `compose_joint_result` 产出或继承 tracking_overlay、pose_overlay、heatmaps、player_render_trajectory 等视觉层产物（对齐单摄 artifact 契约），前端框架/骨架/热力图恢复可用。
- 聚合 stage（`_build_aggregate_stages`）A/B 机位状态不再依赖 joint 模式下永不更新的 `viewRuns`（创建后停在 queued），消除"A/B 机位分析失败"误报。
- CanonicalAnalysisClock 对 sync 有效区间起点之前（`valid_start_seconds` 前，实测 cam_2 前 3.4s）的 secondary 帧选择提供回退策略，debug replay 前段不再显示 UNAVAILABLE 黑屏。

## Capabilities

### New Capabilities

（无，全部为既有 capability 的修复）

### Modified Capabilities

- `multiview-synchronized-analysis-clock`: 分析帧获取必须使用帧号语义（`CAP_PROP_POS_FRAMES`），禁止把帧号当毫秒消费；sync 有效区间起点前的 secondary 帧选择需提供回退策略，保证窗口开头（clipStart=0）副摄可参与分析。
- `multiview-analysis-result-composer`: fused 样本必须携带可计算的 `timestamp_seconds` 时间戳契约；joint 模式结果必须产出/继承前端视觉层产物（tracking/pose/heatmap/render-trajectory）；聚合 stage 的 A/B 机位状态来源需修正（joint 模式不得误报 failed）。
- `multiview-joint-observability`: debug replay 对 sync 有效区间外 view 的呈现需与回退后的帧选择一致（若涉及渲染器变更）。

## Impact

- `backend/app/vision/multiview/joint_view_runtime.py`：`get_frame` 解帧参数（核心修复，影响全部分析帧对齐）。
- `backend/app/services/multiview_result_composer.py`：`fused_to_projected_tracks` 时间戳映射、`compose_joint_result` 视觉层产物、`_build_aggregate_stages` 状态来源。
- `backend/app/vision/multiview/analysis_clock.py`：secondary 帧选择在有效区间起点前的回退。
- `backend/app/vision/multiview/joint_artifact.py`（如涉及 fused v2 schema 时间戳字段）与 `backend/app/services/joint_debug_renderer.py`（如涉及渲染）。
- 前端 `src/services/videoOverlayHud.ts`、`src/pages/VisionPage.tsx`：产物恢复后自动可用，预期无需改动。
- 测试：`backend/tests/` 下 multiview / joint / composer 相关用例需补充时间戳、解帧对齐、stage 状态断言。
