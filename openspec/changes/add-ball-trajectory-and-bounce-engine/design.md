## Context

当前真实分析主流程以球员检测、姿态、轨迹和运动指标为核心，`ball-tracking` 仍声明为当前产品流之外的 inactive 能力。但 `analysis-artifacts` 已经预留了 `ball_trajectory.json`、`cleaned_ball_trajectory.json` 和 `bounce_events.json` 的 artifact contract，说明系统需要先补齐球轨迹与弹跳点的独立算法层，再由后续 change 决定 pipeline 接入、前端展示和视频 overlay。

Good-Pickleball 中可迁移的核心位于 `pickleball_analysis/detection/pickleball_ball.py` 和 `pickleball_analysis/analysis/bounce.py`。前者包含球候选过滤、ROI 限制、轨迹预测、异常跳变过滤和短时缺失处理；后者包含完整轨迹后处理、离群点移除、短缺失插值和基于 20 帧窗口的规则弹跳检测。

本项目已有 CourtVision 标定、homography 和标准匹克球场几何。标准坐标为英尺制：x 为 0 到 20 ft，y 为 0 到 44 ft，球网为 y = 22 ft。因此迁移时不能直接使用 Good-Pickleball 的米制 CourtMapper 常量。

## Goals / Non-Goals

**Goals:**

- 新增一个可独立调用、可单元测试的球轨迹与弹跳点引擎。
- 将球检测模型输入抽象为 detector protocol，使核心后处理不依赖 YOLO 或具体权重。
- 将 Good-Pickleball 的候选筛选、连续性过滤、缺失记录、轨迹清洗、插值和规则弹跳检测迁移到项目结构中。
- 统一输出 image 像素坐标和 court 英尺坐标，并暴露 in-bounds 诊断。
- 输出与现有 artifact contract 兼容的原始轨迹、清洗轨迹和弹跳事件 payload。
- 用单元测试固定核心算法行为，不依赖真实模型、真实视频或前端。

**Non-Goals:**

- 不接入 `AnalysisPipeline`。
- 不修改 `routes_analysis.py` 或当前分析 job 的默认输出。
- 不生成 `ball_overlay.json`、`analysis_overlay.mp4`、小地图、热力图或散点图。
- 不迁移 Good-Pickleball 的 CLI、视频标注函数、Minimap 可视化或 classifier 弹跳模型。
- 不引入 Good-Pickleball 的米制 CourtMapper 作为新坐标标准。

## Decisions

### 1. 新增独立 vision package

在 `backend/app/vision/pickleball_game_analysis/` 下新增以下模块：

```text
schemas.py
ball_detector_protocol.py
detection_writer.py
ball_tracker.py
trajectory_cleaner.py
bounce_detector.py
court_adapter.py
```

理由：现有 vision 层已经按能力拆分，如 `player_tracking_engine`、`pickleball_performance_engine` 和 `courtvision_calibration_engine`。独立 package 能避免把尚未接入主流程的球逻辑混入 service 层。

备选方案是把模块放入现有 `player_tracking_engine`，但球候选、球轨迹和弹跳事件不是球员跟踪职责，会扩大该包边界。

### 2. Detector protocol 与后处理解耦

核心 tracker 消费 `BallDetectorProtocol.detect(frame, conf)` 返回的 `BallCandidate` 列表，而不是直接持有 YOLO model。

理由：Good-Pickleball 的 `PickleballBallTracker` 将 YOLO 调用和后处理耦合在一起。项目后续可能接 YOLO ball detector、TrackNetV2、HSV detector 或融合检测器。protocol 让本 change 只负责模型输出之后的稳定轨迹层。

备选方案是先迁移 YOLO 调用，但这会引入模型路径、设备、half precision 和权重管理问题，超出本 change 范围。

### 3. 轨迹处理分成 raw、cleaned、bounce 三层

数据流为：

```text
BallDetectorProtocol
        ↓
BallTracker
        ↓
raw BallFrameSample[]
        ↓
TrajectoryCleaner
        ↓
cleaned / interpolated TrajectoryPoint[]
        ↓
BounceDetector
        ↓
BounceEvent[]
```

理由：弹跳点不能由单帧即时判断，需要完整或至少局部窗口轨迹。拆分后可以分别测试检测后处理、轨迹清洗和事件检测。

备选方案是在 tracker 内直接判断 bounce，但会把逐帧状态机和后处理窗口规则混在一起，也不利于后续替换弹跳检测算法。

### 4. Court adapter 只复用现有英尺制 homography

`court_adapter.py` 使用现有 `image_to_court` / `project_point` 和 `PickleballCourtGeometry`，将图像点映射到 `[x_ft, y_ft]`。输出可以保留超出边界的点，但必须提供 `in_bounds` 诊断。

理由：项目标准球场模型已经明确为 feet。Good-Pickleball 的 `PICKLEBALL_COURT_WIDTH = 6.096` 和 `PICKLEBALL_COURT_LENGTH = 13.4112` 不能直接迁移，否则会导致 artifact 与现有 court-view、tracking overlay 和 API 语义冲突。

备选方案是输出米制坐标再转换，但这会引入双单位状态；本 change 保持 ball 产物为 feet，后续如需指标计算可单独转换。

### 5. 第一阶段只迁移规则弹跳检测

`BounceDetector` 实现 `trajectory_lag20` 规则评分：窗口大小、中心偏移、最小事件间隔、速度稳定性、局部 y 反转或极值、转向角、偏离直线距离和 court 辅助评分。

理由：Good-Pickleball 的 classifier 路径依赖 pickle、pandas、sklearn/sktime 兼容层和模型文件，迁移成本高且不利于确定性单元测试。规则版更适合作为第一阶段核心能力。

备选方案是同时迁移 classifier fallback，但这会让本 change 从“核心引擎”膨胀为“模型资产和运行时兼容”问题。

### 6. Writer 输出对齐 artifact contract

writer 应输出 JSON payload，而不是直接照搬 Good-Pickleball 的字段名。推荐字段使用：

```text
frame_index
timestamp_sec
image_xy
court_xy
confidence
source
status
detail
schema_version
```

理由：`analysis-artifacts` 已经规定这些 artifact 可以通过 API 被消费。即使本 change 不接入 API，文件结构也应提前兼容，避免 Change 3 再做 schema 迁移。

## Risks / Trade-offs

- [Risk] 球检测候选质量不足导致轨迹引擎输出大量 missing sample → Mitigation：tracker 记录 `visible`、`accepted`、`candidate_count` 和 `reject_reason`，测试中覆盖 no-candidate 与 rejected 场景。
- [Risk] 固定像素阈值在不同分辨率视频中表现不稳定 → Mitigation：阈值集中放入 config，先保留 Good-Pickleball 默认值，后续 pipeline 接入时可按 frame size 或 court scale 调参。
- [Risk] 英尺制 ball artifact 与现有 player trajectory 米制 artifact 并存，消费者可能误读 → Mitigation：每个 payload 必须声明 `coordinate_system` 或 `court_unit`，并在 spec 中要求 court 坐标为 feet。
- [Risk] 规则弹跳检测可能漏检或误检 → Mitigation：本 change 只声明候选事件和 diagnostics，不声明战术结论、回合分割或击球事件。
- [Risk] 独立引擎未接 pipeline，短期不可见 → Mitigation：这是有意的阶段边界；后续 change 再处理运行编排、artifact URLs 和前端展示。

## Migration Plan

1. 新增独立模块和单元测试，不改变现有运行路径。
2. 保持 `enable_ball_detection` 和 `enable_bounce_detection` 默认不改变；本 change 不读取这些开关。
3. 确认现有 API 对缺失球相关 artifact 仍返回 404，而不是把它们视为当前 job 失败。
4. 后续 Change 3 可在 pipeline 中实例化 detector、tracker、cleaner、bounce detector，并把 writer 输出写到 `StorageService` 已定义路径。

回滚策略：删除新增 `pickleball_game_analysis` 包和对应测试即可，不需要迁移数据库、配置或历史 artifact。

## Open Questions

- Change 3 接入 pipeline 时，球 detector 的首选实现是 YOLO ball model、TrackNetV2，还是 YOLO + HSV / TrackNet fusion？
- 是否需要在接入 pipeline 前增加一组真实视频 fixture，用于调参而不纳入常规 CI？
- 后续前端展示是否消费 raw trajectory、cleaned trajectory，还是只消费 cleaned trajectory 和 bounce events？
