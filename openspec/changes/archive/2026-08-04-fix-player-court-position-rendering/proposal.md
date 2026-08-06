## Why

视觉分析页小地图（Court HUD）对球员实时位置的渲染与实际画面位置偏差明显：网前/厨房区线附近的 P3、P4 显示在底线附近，P1、P2 也不准确；但球的位置基本正确。后端 stages 同时显示「projection | 0 个有效场地坐标球员位置」，说明很多球员点被坐标范围过滤，但仍在范围边界的点被渲染到底线附近。根因方向已通过 explore 确认（bbox 底部 footpoint 在画面底边受地面接触点影响 + homography 在画面底部外推不稳 + 缺诊断输出定位具体数据）。需要综合修复。

## What Changes

- 后端 `FootpointEstimator` 优先使用 pose 踝关节中点（已有 hybrid 路径），无 pose 时保留 bbox 底部中心作为 fallback，避免 bbox 底部接触地面造成 footpoint 偏下。
- 后端 `PlayerProjector` / `analysis_pipeline` projection 阶段为每位球员输出脚点方法、原始 courtY、smoothed courtY、投影状态、被过滤原因到 debug artifact（`projection_diagnostics.json`），便于真实任务复现与定位。
- **后端球员投影过滤边界放宽**：球员允许站在场地外（发球/接发球站位在底线外），过滤边界由严格的 `0≤x≤20, 0≤y≤44` 改为与前端 `TRACKING_BOUNDS` 对齐的合理范围 `-4≤x≤24, -8≤y≤52`（单位英尺）；仅在该范围外（homography 外推严重异常）才过滤并记录 `filter_reason`。球的过滤边界保持不变（球应基本在场地附近）。
- 前端四角标定页（`CourtCornerCalibrator`）在用户点击标定四点时校验四点 Y 坐标单调性，提示"近端底线/远端底线"是否颠倒（homography 标定错误是系统偏差主因之一）。
- 修复后用新创建的真实视频任务验证：小地图上 P1-P4 与视频实时位置一致（误差在容忍范围内），发球站位时球员显示在场外区域，球位置保持准确。

## Capabilities

### New Capabilities

（无新增能力）

### Modified Capabilities

- `match-analysis-pipeline-capabilities`: pipeline 在投影阶段 SHALL 优先 pose 踝关节脚点、保留 bbox 底部兜底；SHALL 在投影诊断 artifact 中暴露每位球员样本的 footpoint 方法、原始与平滑 courtY、投影状态与被过滤原因；前端的 `validPoint` 范围过滤 SHALL 在被过滤样本上输出明确原因。
- `automatic-court-line-calibration`: 四角标定页 SHALL 在用户标定四点后校验四点 Y 坐标单调性（远端底线两点 Y 不应大于近端底线两点 Y，且不应接近相反极值），在检测到疑似颠倒时给出可操作的提示（"近端/远端可能颠倒，请确认画面顶/底对应的场地底线"）。

## Impact

- 后端：
  - `backend/app/vision/player_tracking_engine/footpoint_estimator.py`：确保 hybrid 模式在 pose 关键点缺失时显式记 metadata `pose_unavailable`，避免静默走 bbox 但仍标记为 hybrid。
  - `backend/app/vision/player_tracking_engine/player_projector.py`：投影结果附带 method/quality 元数据，方便诊断。
  - `backend/app/services/analysis_pipeline.py`：projection 阶段在 `_projection_out_of_range` / `valid=False` 时把原因写入 `projection_diagnostics.json`；保证主轨迹不在被过滤样本上写入 `[0,0]` 兜底（已是当前行为，文档化）。
- 前端：
  - `src/components/platform/CourtCornerCalibrator.tsx`：标定四点提交前校验 Y 单调性 + 极值范围，弹出确认。
- 测试：
  - 后端：`test_footpoint_estimator.py` 增加"pose 缺失 → bbox fallback + 标记 metadata"用例；`test_player_projector.py` 增加"投影越界样本不写入主轨迹"用例；`test_projection_diagnostics.py` 增加"诊断输出含 method/courtY/原因"用例。
  - 前端：`CourtCornerCalibrator.test.tsx` 增加"四点 Y 反向给出提示"用例。
- 兼容性：完全向后兼容（旧任务不重跑，行为不变）。