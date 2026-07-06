## 1. 模块结构与数据模型

- [ ] 1.1 创建 `backend/app/vision/pickleball_game_analysis/` package 和 `__init__.py`
- [ ] 1.2 在 `schemas.py` 定义 `BallCandidate`、`BallFrameSample`、`TrajectoryPoint`、`BounceEvent` 和相关 artifact payload helper
- [ ] 1.3 在 `ball_detector_protocol.py` 定义 detector-agnostic `BallDetectorProtocol`
- [ ] 1.4 为 schema 增加 numpy 标量、tuple/list、null 坐标的 JSON 序列化辅助

## 2. Court Adapter

- [ ] 2.1 在 `court_adapter.py` 封装 image-to-court homography 投影
- [ ] 2.2 使用 `PickleballCourtGeometry` 输出 feet 坐标和标准 20 ft × 44 ft metadata
- [ ] 2.3 为缺失 homography、无效矩阵、非有限坐标和越界坐标提供安全降级与 `in_bounds` 诊断

## 3. Ball Tracker

- [ ] 3.1 在 `ball_tracker.py` 定义 `BallTrackerConfig` 和 `BallTracker`
- [ ] 3.2 实现候选点面积比例、长宽比和 ROI padding 过滤
- [ ] 3.3 实现基于 confidence、预测距离和尺寸惩罚的候选点选择
- [ ] 3.4 实现上一有效点、线性预测、最大跳变、预测 gate 和 strict missing gate
- [ ] 3.5 实现 missing detection 记录、超限后轨迹重建和逐帧 `BallFrameSample` 输出

## 4. Trajectory Cleaner

- [ ] 4.1 在 `trajectory_cleaner.py` 定义 `TrajectoryCleanerConfig` 和 `TrajectoryCleaner`
- [ ] 4.2 实现基于鲁棒 step 阈值的孤立离群点清洗
- [ ] 4.3 实现短缺失段 image 坐标线性插值
- [ ] 4.4 实现短缺失段 court 坐标同步插值和 `interpolated=true` 标记
- [ ] 4.5 确保长缺失段保持 missing，不合成连续轨迹

## 5. Bounce Detector

- [ ] 5.1 在 `bounce_detector.py` 定义 `BounceDetectorConfig` 和规则版 `BounceDetector`
- [ ] 5.2 实现窗口坐标数组、速度序列、平滑、斜率、角度和点到线距离计算
- [ ] 5.3 实现 `trajectory_lag20` 评分，包括 y 反转或极值、转向、偏离、速度和 court 辅助评分
- [ ] 5.4 实现英尺制 court margin 校验、低分过滤和不稳定速度过滤
- [ ] 5.5 实现最小事件间隔去重，并按 frame 顺序输出 `BounceEvent`
- [ ] 5.6 明确不加载 classifier、不依赖 pickle、sklearn 或 sktime

## 6. Artifact Writer

- [ ] 6.1 在 `detection_writer.py` 实现 raw trajectory JSON payload 构建和写入
- [ ] 6.2 实现 cleaned trajectory JSON payload 构建和写入
- [ ] 6.3 实现 bounce events JSON payload 构建和写入
- [ ] 6.4 确保 payload 包含 `schema_version`、`job_id`、`status`、`detail`、坐标单位和配置摘要
- [ ] 6.5 确保 writer 不接入 `StorageService` 必需路径之外的 pipeline 行为

## 7. Unit Tests

- [ ] 7.1 新增 schema 和 writer 序列化测试，覆盖空 events、null 坐标和 numpy 类型
- [ ] 7.2 新增 court adapter 测试，覆盖 feet 投影、缺失 homography 和越界诊断
- [ ] 7.3 新增 ball tracker 测试，覆盖无候选、候选筛选、ROI 过滤、跳点拒绝和 missing 重建
- [ ] 7.4 新增 trajectory cleaner 测试，覆盖孤立离群点、短缺失插值和长缺失跳过
- [ ] 7.5 新增 bounce detector 测试，覆盖有效弹跳候选、missing 窗口跳过、court margin 拒绝和事件去重
- [ ] 7.6 新增回归测试确认当前 pipeline 默认不生成球轨迹或弹跳事件 artifact

## 8. Validation

- [ ] 8.1 运行新增测试文件并修复失败
- [ ] 8.2 运行相关现有测试，包括 artifact route、storage path、homography 和 current ball inactive behavior
- [ ] 8.3 运行 `openspec status --change add-ball-trajectory-and-bounce-engine`
- [ ] 8.4 运行 `openspec validate add-ball-trajectory-and-bounce-engine --strict`
