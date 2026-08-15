## 1. 解帧语义修复（核心，先行）

- [x] 1.1 `backend/app/vision/multiview/joint_view_runtime.py` 的 `get_frame`：`cap.set(0, source_frame_index)` 改为 `cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)`，并更新注释说明帧号语义
- [x] 1.2 补充单元测试：模拟 cap 断言 `get_frame(400)` 解出第 400 帧（用帧哈希或 mock 断言 POS_FRAMES 参数），并验证相邻 source_frame_index 严格前进
- [x] 1.3 用本 take（174_merged.mp4）写最小复现脚本验证：`set(POS_FRAMES, 400)` 实际帧号 ≈400（对照修复前 ≈25），检测框逐 tick 变化

## 2. fused 轨迹时间戳契约

- [x] 2.1 `backend/app/vision/multiview/joint_artifact.py` 的 `write_fused_v2` 与 F0 轨迹构造处：每个样本写 `timestamp_seconds = take_timestamp_ms / 1000.0`
- [x] 2.2 `multiview_result_composer.py` 的 `fused_to_projected_tracks`：时间戳读取优先级改为 `timestamp_seconds` → 回退 `take_timestamp_ms / 1000.0` → 才默认 0.0（兼容历史产物）
- [x] 2.3 补充测试：构造缺 `timestamp_seconds` 与带 `timestamp_seconds` 的 fused 样本，断言 tracks 时间戳与速度/厨房停留指标正确

## 3. joint compose 视觉层产物

- [x] 3.1 从 joint debug trace（`joint_debug_trace.v1.json` 每 tick detections）聚合生成 tracking_overlay artifact，对齐单摄 `tracking_overlay.json` 契约（bbox / footpoint / player_id / timestamp），经 Parent artifact 路由发布
- [x] 3.2 `compose_joint_result`：由 fused 轨迹生成 heatmaps / scatter 产物并发布 URL；由 tracks 生成 `player_render_trajectory`
- [x] 3.3 `compose_joint_result`：`pose_overlay` 显式标记 unavailable + 结构化 reason（joint_tracking_v2 未接入姿态推理），不静默缺失
- [x] 3.4 补充测试：断言 joint 结果 artifacts 含 tracking_overlay_url / heatmaps_url / player_render_trajectory_url / pose_overlay_status=unavailable

## 4. 聚合 stage 状态来源修正

- [x] 4.1 `_build_aggregate_stages`（或 `compose_joint_result` 调用处）：joint 模式 A/B 状态取 joint run 完成结论（succeeded），不再读 `viewRuns`；`late_fusion_v1` 保持读 viewRuns 不变
- [x] 4.2 补充测试：joint 模式 `viewRuns` 停在 queued 时聚合 stage 的 `multiview-view-a/b` 仍为 done

## 5. 窗口开头副摄帧回退

- [x] 5.1 `CanonicalAnalysisClock`：canonical 时间早于 `valid_start_seconds` 时，用最近有效映射外推 secondary 帧，`FrameSample.status=fallback` 并携带 reason；外推失败时保持细分不可用
- [x] 5.2 `joint_debug_renderer.py`：trace 前段 status=fallback 时渲染回退帧画面并叠加 fallback 标记；仍不可用时显示 UNAVAILABLE 面板 + 结构化原因
- [x] 5.3 用本 take 验证外推段质量：cam_2 前 3.4s 是否有有效画面；若内容错位（片头/黑屏）则回退兜底方案并记录结论

## 6. 回归验证与测试

- [x] 6.1 用 job-3b411aefe6 同源双摄素材重跑 joint 任务（仅前 60s + yolo + debug），核对：trace 检测框逐 tick 变化、速度非 0、小地图有轨迹、框架可用、stage 无 failed、debug replay 前段无黑屏
- [x] 6.2 跑通 `backend/tests/` 相关 multiview / joint / composer 测试套件，确认无回归
- [x] 6.3 更新 `docs/` 或 `structure picture.md` 中 joint_tracking_v2 结果链路说明（解帧语义、时间戳、视觉层产物来源）
