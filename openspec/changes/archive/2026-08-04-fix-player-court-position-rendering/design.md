## Context

视觉分析页 Court HUD 显示 P1-P4 球员位置与实际视频画面系统性偏差（网前/厨房区球员被画到底线附近），球位置准确。stages 同时显示「projection | 0 个有效场地坐标球员位置」。explore 阶段已确认：
- HUD 严格用 `track.court_point`（`buildVideoOverlayHud`），`validPoint` 校验 0≤x≤20, 0≤y≤44
- 小地图 mapper 无 Y 翻转（courtY=0→SVG 顶=courtY 大→SVG 底）
- footpoint 用 bbox 底部中心 `((x1+x2)/2, y2)`——球员在画面底部（网前）时 y2 含地面接触点 → 投影 courtY 偏大
- `_check_near_frame_bottom` 仅降 confidence（0.35）不修 footpoint 值
- `[0,0]` 兜底仅在 debug 写入，不影响主轨迹

## Goals / Non-Goals

**Goals:**
- footpoint 优先用 pose 踝关节，避免 bbox 底部地面接触点造成的系统性偏移
- projection 阶段把被过滤样本的原因写入 `projection_diagnostics.json`，便于真实任务复现
- 标定页四点 Y 单调性校验，避免用户标反近/远端导致的整体偏差
- 新建一个真实任务验证修复效果

**Non-Goals:**
- 不重写整个投影管线
- 不修改球检测/ball_tracker 路径（球位置准确，无需改）
- 不改 `image_to_court` / homography 矩阵计算逻辑
- 不修改视觉分析页整体布局

## Decisions

### D1: footpoint 优先 pose，bbox 兜底并标记 metadata
`FootpointEstimator.estimate` 在 `method="hybrid"` 时：先尝试 pose ankle midpoint（已有），若 pose 关键点不可用**显式**记录 `metadata.pose_unavailable=true`，再走 bbox 底部中心。这样：
- pose 启用时 → 用踝关节（精确）
- pose 不可用（之前任务 pose 全 skipped）→ bbox 但明确标记 `pose_unavailable + near_frame_bottom`，便于诊断
- 减少 bbox 底部地面接触点的影响（未来 pose 启用后根本性改善）

### D2: projection 阶段输出诊断
`analysis_pipeline` 在 `_project_players` 后对每位球员每位 sample 输出到 `projection_diagnostics.json`：
- `image_footpoint`、`footpoint_method`、`footpoint_confidence`、`court_position_raw`、`court_position_smoothed`、`projection_status`（`accepted`/`out_of_bounds_allowed`/`filtered_out_of_range`/`invalid_homography`）、`filter_reason`
- 主轨迹（`players_trajectory.json`）维持现有行为：被过滤样本不写入，不使用 `[0,0]` 兜底
- 前端不展示诊断文件，仅供后端排查；UI 调试可在 job 输出 artifact 列表直接下载

### D2b: 球员过滤边界与前端 TRACKING_BOUNDS 对齐（允许场外站位）
- 现状：后端 `analysis_pipeline.py:2522` 用严格 `0≤x≤20, 0≤y≤44` 过滤球员点；前端 `CourtMinimap` 的 `TRACKING_BOUNDS = {x:-4~24, y:-8~52}` 且 `validPoint` 不拒绝场外点（仅标 `inBounds`）。二者矛盾——发球/接发球站位在底线外，后端把合理场外点全部丢弃（stages「projection | 0 个有效场地坐标」的直接原因之一）。
- 决策：后端球员过滤边界放宽为 `-4≤x≤24, -8≤y≤52`（与前端留白一致）；该范围内但场外的样本记 `projection_status="out_of_bounds_allowed"` 并正常写入主轨迹；仅超出该范围（homography 外推严重异常）记 `filtered_out_of_range` + `filter_reason`。
- 球的过滤边界保持不变（球应基本在场内/邻近区域，沿用现有严格校验）。
- 备选：不动后端、仅前端放宽——不可行，后端丢弃后前端无数据可用，否决。

### D3: 标定四点 Y 顺序校验（前端）
`CourtCornerCalibrator` 在用户标完四点提交前校验：
- 两个"远端底线"点（top_left/top_right，按当前 UI 标注为画面顶端的底线）的 imageY 平均
- 两个"近端底线"点（bottom_left/bottom_right，画面底端的底线）的 imageY 平均
- 若 bottom_avg < top_avg（近端底线 Y 比远端小，颠倒）或差值 < 一定阈值（如 20px），弹出确认框："检测到近端/远端可能颠倒，请确认画面顶/底对应的场地底线"
- 这是 UI 层防御，不能替代后端修复，但能阻止最常见的系统性偏差来源

### D4: 验证流程
修复完成后：
1. 重启后端（带推理开关 true）→ 重新上传同一视频创建任务（pose 推理启用后跑出新结果）
2. 对比新旧任务：小地图 P1-P4 位置与实际视频对齐
3. `projection_diagnostics.json` 输出确认每位球员 footpoint 方法+ courtY 范围合理
4. 验证发球/接发球站位：球员站在底线外时小地图显示在场外区域（TRACKING_BOUNDS 留白内），不被过滤

## Risks / Trade-offs

- [旧任务产物已消失，无法直接对比新结果] → 新建任务验证
- [pose 推理首次加载慢（YOLO + RTMPose），跑一次新任务需 ~2-3 分钟] → 接受一次性开销
- [标四点校验是软提示，用户可忽略] → 优先提示，不强制阻止提交（避免阻塞合法标定）
- [D2 诊断文件会膨胀] → 限制为 sample 级（不每像素写），并复用现有 `projection_diagnostics.json` artifact 路径

## Migration Plan

- 无数据库迁移，零停机
- 部署：合并后端先于前端（前端 UI 校验独立）
- 回滚：所有改动向后兼容（旧前端不传新字段，行为不变）

## Open Questions

- （无，explore 阶段已与用户确认走综合修复路径。）