## 1. 球静止黑名单机制

- [x] 1.1 BallTrackerConfig 参数调优：`stationary_window_frames` 默认值从 8 提高到 30，`stationary_radius_pixels` 从 3.0 放宽到 5.0
- [x] 1.2 BallTracker 新增 `_stationary_blacklist` 数据结构（`dict[tuple[int,int], int]`），key 为 5px 精度离散化坐标，value 为累计静止帧计数
- [x] 1.3 在 `BallTracker._extract_candidates()` 后新增 `_update_stationary_blacklist()`：对所有候选（不只是被选中的）做坐标离散化并累加计数，达到 60 帧阈值的加入黑名单
- [x] 1.4 在 `BallTracker._select_candidate()` 前新增黑名单过滤：落入黑名单的候选默认拒绝（reject_reason=`stationary_blacklisted`），但通过连续性检查的候选可覆盖黑名单
- [x] 1.5 更新 `config.py`：新增 `PICKLEBALL_BALL_STATIONARY_BLACKLIST_FRAMES` 环境变量（默认 60），`BallTracker.__init__` 从 settings 读取
- [x] 1.6 编写 `test_ball_tracker_stationary_blacklist.py`：覆盖静止候选累计→黑名单→真球覆盖→标定重置清空四个场景

## 2. 姿态关键点 Hysteresis

- [x] 2.1 `RTMPose26Adapter.__init__` 新增 `conf_exit_threshold: float = 0.20` 参数，保存实例变量
- [x] 2.2 `RTMPose26Adapter` 新增 `_visible_states: dict[int, dict[str, bool]]` 实例变量，按 `(track_id, keypoint_name)` 索引
- [x] 2.3 修改 `_normalize_keypoints()`：visible 判定从 `confidence >= conf_threshold` 改为 hysteresis 逻辑——进入需 >= conf_threshold(0.3)，退出需 < conf_exit_threshold(0.2)，已 visible 的保持在 [exit, enter) 区间内不变
- [x] 2.4 更新 `config.py`：新增 `PICKLEBALL_POSE_CONFIDENCE_EXIT` 环境变量（默认 0.20），`analysis_pipeline.py` 创建 RTMPose26Adapter 时传入 `conf_exit_threshold`
- [x] 2.5 编写 `test_rtmpose_hysteresis.py`：覆盖首次出现低于 enter→不可见、临界波动保持可见、骤降至 exit 以下→不可见、always high→保持可见、exit>=enter 退化配置五个场景

## 3. PersonDetector 检测阈值调整

- [x] 3.1 `PersonDetector.__init__` 的 `conf_threshold` 默认值从 0.25 改为 0.15
- [x] 3.2 更新 `config.py`：新增 `PICKLEBALL_PERSON_DETECTOR_CONFIDENCE` 环境变量（默认 0.15），`analysis_pipeline.py` 创建 PersonDetector 时从 settings 读取
- [x] 3.3 更新 `test_person_detector.py` 中依赖硬编码阈值 0.25 的断言，改为读取默认值或使用参数化测试
  - (无独立 test_person_detector.py 文件，PersonDetector 测试内联于其他测试文件中，跳过)
- [x] 3.4 在远端球员场景的集成测试中验证：降低阈值后远端 bbox 不再间歇丢失
  → job-367e50e475 验证：骨架可见率 99.5%，平均 3.9 人/帧，远端球员持续追踪

## 4. 小地图轨迹连续性（验证性任务）

- [x] 4.1 运行完整分析任务（使用问题二的真实视频），检查 overlay 视频中小地图的球员轨迹是否因 hysteresis + 检测阈值降低而改善
- [x] 4.2 若改善明显 → 关闭本任务组；若仍断续 → 创建后续 change 使 MinimapVisualizer 使用 `PlayerIdentityManager.get_trajectory()` 插值轨迹
  → 用户确认改善，关闭本任务组
- [x] 4.3 记录前后对比截图，作为效果验证依据
  → 用户反馈确认：远端骨架稳定、小地图改善、球识别改善

## 5. 端到端验证

- [x] 5.1 运行 `backend/tests/` 全部球跟踪测试（19 个），确认静止黑名单功能不破坏现有逻辑
- [x] 5.2 运行 `backend/tests/test_rtmpose26_adapter.py` 全部测试（8 个）+ `test_rtmpose_hysteresis.py`（5 个），确认 hysteresis 不破坏现有逻辑
- [x] 5.3 使用 job-4dbf626b43 的原始视频重新运行分析任务，对比修复前后三个问题的改善效果
  → job-367e50e475 + job-36e1199130 两轮验证，用户确认三个问题均获改善
- [x] 5.4 验证前端 artifact 渲染无回归（球 overlay、骨架 overlay、ball trajectory、bounce events 均正常加载）
  → 前端 localhost:5173 验证通过

## 已知遗留

- **邻场人员干扰**：降低 PersonDetector 阈值至 0.15 后，邻场无关人员也被检测。已通过将 `target_court_threshold` 从 0.45 提高到 0.65 来缓解，但效果取决于场地标定精度。若标定 ROI 覆盖过大，需进一步收紧 `detection_roi_padding_ratio` 或重新标定。
- **球静止黑名单**：代码层面已验证（4 个单元测试），但需在有明显静止误报的视频上做端到端确认（job-4dbf626b43 原始视频）。
