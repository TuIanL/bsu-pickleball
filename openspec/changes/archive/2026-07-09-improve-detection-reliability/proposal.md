## Why

运行分析任务 job-4dbf626b43 后暴露出三个影响分析质量的检测可靠性问题：①球场上的细小静止物被误识别为球；②远端球员的骨架关键点时有时无、闪烁跳跃；③右上角小地图中球员轨迹断断续续。三个问题的共同根因是当前系统缺乏**时序持久性的检测决策**——逐帧独立判断、硬阈值一刀切、没有滞回与记忆机制。这三个修复直接提升运动分析产出的可信度，是进入比赛级分析前必须解决的基础可靠性问题。

## What Changes

- **球静止误报过滤增强**：将 BallTracker 的静止误报检测窗口从 8 帧扩大到 30 帧，并新增「静止候选黑名单」机制——对连续在相同像素区域出现的候选做跨帧投票计数，超过阈值后永久过滤，解决静止物因检测闪烁而绕过过滤的问题。
- **姿态关键点滞回机制**：在 RTMPose26Adapter 中引入 hysteresis——关键点从「可见→不可见」使用更低的退出阈值（0.20），从「不可见→可见」保持进入阈值（0.30），消除临界置信度附近的闪烁。同时将 PersonDetector 的检测丢弃阈值从 0.25 下调至 0.15，提高远端小目标的检测召回率。
- **小地图轨迹连续性保障**：确保 MinimapVisualizer 在 overlay 视频渲染时使用 PlayerIdentityManager 已插值补齐的完整轨迹，而非逐帧原始观测，避免因单帧检测丢失导致轨迹截断（此改动为问题二的连带修复，若问题二解决后自动改善则降级为参数调优）。

## Capabilities

### New Capabilities
- `detection-temporal-filtering`：为检测结果引入时序维度的过滤规则——球跟踪器的静止候选黑名单机制与姿态估计的 keypoint 可见性滞回机制，使系统具备"跨帧记忆"的检测决策能力，而非逐帧独立判定。

### Modified Capabilities
- `ball-tracking`：球跟踪器的静止误报检测行为变更——`BallTrackerConfig.stationary_window_frames` 默认值从 8 提高到 30，`stationary_radius_pixels` 从 3.0 放宽到 5.0，并新增 `stationary_blacklist` 跨帧候选位置投票机制（不影响现有 artifact schema 和 API 合约）。
- `pose-estimation-engine`：关键点置信度判定行为变更——「低置信度关键点被排除」的判定从单一硬阈值改为带滞回的进入/退出双阈值机制；新增 `keypoint_confidence_exit_threshold` 配置项；关键点在 exit_threshold 以上保持 visible 状态。不影响 `pose_artifact` 的 schema 结构。

## Impact

- **后端 Python**：
  - `backend/app/vision/pickleball_game_analysis/ball_tracker.py`：BallTrackerConfig 默认值变更 + 新增 `_stationary_blacklist` 逻辑
  - `backend/app/vision/pose/rtmpose26_adapter.py`：RTMPose26Adapter 新增 hysteresis 逻辑 + `conf_exit_threshold` 参数
  - `backend/app/vision/player_tracking_engine/person_detector.py`：`conf_threshold` 默认值从 0.25 调到 0.15
  - `backend/app/core/config.py`：新增 `PICKLEBALL_POSE_CONFIDENCE_EXIT` 和 `PICKLEBALL_PERSON_DETECTOR_CONFIDENCE` 环境变量
  - `backend/app/vision/pickleball_game_analysis/minimap_visualizer.py`：如需，改用插值轨迹数据源
- **前端**：无变更——artifact schema 和 API 合约均不受影响
- **配置**：新增两个环境变量，修改两个默认参数值；old config values will be overridden silently
- **向后兼容**：所有变更向后兼容，不影响现有任务产物的解析和使用
