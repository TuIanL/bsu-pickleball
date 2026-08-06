## 1. 后端 footpoint 显式 fallback 标记

- [x] 1.1 `FootpointEstimator.estimate` 在 hybrid 模式且 pose 关键点不可用时显式设置 `metadata.pose_unavailable=true`，并继续走 bbox 底部中心（已有 hybrid fallback，补 metadata）
- [x] 1.2 复用现有 `near_frame_bottom` / `bbox_clip_suspected` metadata，确保两者并存时被正确记录
- [x] 1.3 后端测试：增加"hybrid 模式无 pose → bbox fallback + metadata.pose_unavailable=true"用例

## 2. 后端 projection 诊断输出与场外放行

- [x] 2.1 `analysis_pipeline` `_project_players` 后为每位球员每位 sample 输出到 `projection_diagnostics.json`：image_footpoint、footpoint_method、footpoint_confidence、court_position_raw、court_position_smoothed、projection_status（accepted/out_of_bounds_allowed/filtered_out_of_range/invalid_homography）、filter_reason
- [x] 2.2 球员过滤边界从严格 `0≤x≤20, 0≤y≤44` 放宽为与前端 TRACKING_BOUNDS 对齐的 `-4≤x≤24, -8≤y≤52`；范围内场外样本记 `out_of_bounds_allowed` 并正常写入主轨迹（发球站位不再被丢弃）；仅超范围记 `filtered_out_of_range` + filter_reason
- [x] 2.3 球轨迹保持严格边界校验，不受球员放行影响（确认现有 ball 路径未共用球员过滤代码）
- [x] 2.4 文档化主轨迹（players_trajectory.json）维持现有行为：被过滤样本不写入，不使用 `[0,0]` 兜底（已是当前行为，加注释确认）
- [x] 2.5 后端测试：增加"球员场外（发球站位）样本记 out_of_bounds_allowed 且写入主轨迹"用例；"超合理范围记 filtered_out_of_range + filter_reason"用例

## 3. 前端标定四点 Y 顺序校验

- [x] 3.1 `CourtCornerCalibrator` 在四点完成后计算 far/near baseline 平均 Y，差值大于阈值时不提示；差值过小或反向时弹出"近端/远端可能颠倒"确认框
- [x] 3.2 阈值取 frame_height × 0.1（约 10% 画面高度）作为"明显"，小于则视为颠倒或可疑
- [x] 3.3 前端测试：增加"四点 Y 反向给出提示"用例

## 4. 验证

- [x] 4.1 后端 `pytest` 全量通过；前端 `npm test` 与 `npm run build` 通过；`openspec validate --changes` 通过
- [x] 4.2 重启后端（推理开关开启）→ 用同一视频重新创建任务（pose 推理启用）→ 视觉分析页验证 P1-P4 与视频实时位置对齐（已由 5.6 完成：job-6c0cc96f86，P3 1→633、P4 1→576，位置随视频动态移动）
- [x] 4.3 检查新任务的 `projection_diagnostics.json`：每位球员 footpoint method、courtY 范围合理，被过滤样本原因清晰（已由 5.6 完成：raw 与 homography 重算一致、raw/smoothed 分离 4540/4624）
- [x] 4.4 验证发球/接发球站位：球员在底线外时小地图显示在场外区域（TRACKING_BOUNDS 留白内），不被过滤（已由 5.7 完成：P1 326、P2 159 个场外样本保留在留白内，异常外推过滤=0）

## 5. 验证中发现的两处位置链路 bug（2026-08-04 追加）

- [x] 5.1 `CourtPositionSmoother` 增加 `frame_stride` 参数：gap 语义改为"额外缺失帧数"（`frame_index - last_frame - frame_stride`），避免抽帧 stride>1 时相邻处理帧被误判为断帧导致平滑值永远冻结在 track 首帧（P3/P4 位置恒定在场外根因）
- [x] 5.2 `analysis_pipeline` 构造平滑器时传入与抽帧一致的 `frame_stride`（任务级覆盖优先，否则全局 `overlay_frame_stride`）
- [x] 5.3 修复 `projection_debug.jsonl` 诊断的 `court_position_raw`：改为从 5b 保存的 `render_raw_by_track` 读取平滑前的原始投影值（原实现读的是已被 5c 覆盖的 `pos.court_position`，raw 与 smoothed 恒等，诊断失真）
- [x] 5.4 后端测试：`test_court_projection_bounds.py` 增加 `test_frame_stride_keeps_smoothing`（stride=2 相邻处理帧应正常平滑；真正缺帧仍 gap_hold）
- [x] 5.5 后端 `pytest` 全量通过（531 passed）
- [x] 5.5b 修复 `_is_outlier` 误判：outlier 判定改用**相邻帧 raw 位移**（原实现用 raw 与 smoothed 的差除以小帧间隔，smoothed 滞后积累误差 → 连续 outlier_clamped → 位置再次冻结；重放真实数据 637 帧冻结 → 修复后 0 冻结，仅 3 个真实 outlier）
- [x] 5.6 重启后端 → 用同一视频重建任务（job-6c0cc96f86）→ P3 唯一位置 1→633、P4 1→576，位置随视频动态移动；诊断 raw 与 homography 重算一致、raw/smoothed 分离 4540/4624
- [x] 5.7 验证发球/接发球站位：P1 326、P2 159 个场外样本（底线外）保留在 tracking 留白内，均未被过滤（应过滤异常外推=0）