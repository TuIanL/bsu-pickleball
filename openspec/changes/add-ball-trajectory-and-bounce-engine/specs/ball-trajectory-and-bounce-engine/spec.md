## ADDED Requirements

### Requirement: Detector-agnostic ball candidate input
球轨迹引擎 SHALL 通过 detector protocol 消费球候选点，而不是直接依赖 YOLO、TrackNet、HSV 或具体模型权重。

#### Scenario: Detector returns candidates
- **WHEN** detector 为一帧返回一个或多个球候选点
- **THEN** 球轨迹引擎 SHALL 使用候选点的 image 坐标、confidence、bbox 尺寸和可选诊断字段进行后处理
- **AND** 球轨迹引擎 MUST NOT 调用具体模型对象或读取模型权重路径

#### Scenario: Detector returns no candidates
- **WHEN** detector 为一帧返回空候选列表
- **THEN** 球轨迹引擎 SHALL 输出该帧的 missing sample
- **AND** sample SHALL 标记 `visible=false`、`accepted=false` 和 `candidate_count=0`

### Requirement: Ball candidate filtering and continuity tracking
球轨迹引擎 SHALL 对 detector 返回的候选点执行面积、长宽比、ROI、轨迹连续性和预测位置过滤，并输出逐帧原始球轨迹 sample。

#### Scenario: Candidate passes filters
- **WHEN** 候选点通过面积比例、长宽比、ROI 和轨迹连续性检查
- **THEN** 输出 sample SHALL 包含 `frame_index`、`timestamp_sec`、`image_xy`、`court_xy`、`confidence`、`visible=true`、`accepted=true` 和 `candidate_count`
- **AND** 该点 SHALL 更新 tracker 的有效轨迹历史

#### Scenario: Candidate is rejected by shape or ROI
- **WHEN** 候选点 bbox 过大、长宽比异常或位于 ROI 外
- **THEN** 输出 sample SHALL 标记 `visible=true`、`accepted=false`
- **AND** sample SHALL 包含可诊断的 `reject_reason`
- **AND** 被拒绝候选 MUST NOT 更新有效轨迹历史

#### Scenario: Candidate jumps too far
- **WHEN** 候选点相对上一有效点或预测点超过连续性阈值，且连续缺失帧数仍处于 strict gate 内
- **THEN** 输出 sample SHALL 标记 `accepted=false`
- **AND** tracker SHALL 记录一次 missing detection

#### Scenario: Missing frames exceed limit
- **WHEN** 连续 missing detection 数量超过配置的最大缺失帧数
- **THEN** tracker SHALL 清空或失效上一有效位置，使后续候选可以重新建立轨迹

### Requirement: Court coordinate adaptation in feet
球轨迹引擎 SHALL 使用项目现有 CourtVision homography 和标准球场几何，将 image 坐标映射为英尺制 court 坐标。

#### Scenario: Homography is available
- **WHEN** sample 有有效 image 坐标且提供 image-to-court homography
- **THEN** 引擎 SHALL 输出 `court_xy`，单位为 feet
- **AND** 输出 SHALL 包含 `in_bounds` 或等价诊断，表示该 court 坐标是否位于标准 20 ft × 44 ft 球场内

#### Scenario: Homography is unavailable
- **WHEN** sample 有有效 image 坐标但没有可用 homography
- **THEN** 引擎 SHALL 保留 image 坐标
- **AND** `court_xy` SHALL 为 null
- **AND** 该情况 MUST NOT 阻止 raw trajectory sample 输出

#### Scenario: Court coordinate is outside bounds
- **WHEN** 投影后的 court 坐标超出标准球场边界
- **THEN** 引擎 MAY 保留该 court 坐标用于诊断
- **AND** 引擎 SHALL 标记 `in_bounds=false`

### Requirement: Trajectory cleaning and short-gap interpolation
球轨迹引擎 SHALL 提供独立轨迹清洗器，用于移除孤立离群点并对短缺失段进行线性插值。

#### Scenario: Isolated jump is detected
- **WHEN** 一个有效轨迹点与前后有效点距离异常，而前后有效点之间的桥接距离处于合理范围
- **THEN** 清洗器 SHALL 将该点视为离群点
- **AND** 清洗后的 sample SHALL 清空该点的 image 和 court 坐标或标记为 rejected

#### Scenario: Short gap can be interpolated
- **WHEN** 两个有效轨迹点之间的缺失帧数不超过 `max_interpolation_gap`
- **THEN** 清洗器 SHALL 为缺失帧生成线性插值 sample
- **AND** 插值 sample SHALL 标记 `interpolated=true`
- **AND** 如果两端都有 court 坐标，court 坐标也 SHALL 同步插值

#### Scenario: Long gap is not interpolated
- **WHEN** 两个有效轨迹点之间的缺失帧数超过 `max_interpolation_gap`
- **THEN** 清洗器 MUST NOT 为该间隔合成连续轨迹点
- **AND** 缺失帧 SHALL 保持 unavailable 或 missing 状态

### Requirement: Rule-based bounce event detection
球轨迹引擎 SHALL 基于清洗和插值后的轨迹执行规则窗口弹跳检测，并输出弹跳候选事件。

#### Scenario: Window score reaches threshold
- **WHEN** 固定窗口内的轨迹满足局部 y 反转或极值、转向、偏离直线、速度和 court 位置评分阈值
- **THEN** detector SHALL 输出一个 bounce event
- **AND** event SHALL 包含 `event_id`、`frame_index`、`timestamp_sec`、`image_xy`、`court_xy`、`confidence`、`detection_method` 和 `diagnostics`

#### Scenario: Window contains missing image coordinates
- **WHEN** 检测窗口内存在缺失或非有限 image 坐标
- **THEN** detector SHALL 跳过该窗口
- **AND** detector MUST NOT 为该窗口生成 bounce event

#### Scenario: Event is outside court margin
- **WHEN** bounce event 中心点 court 坐标存在且超出配置的英尺制 court margin
- **THEN** detector SHALL 拒绝该 event
- **AND** 该 event MUST NOT 出现在最终 `events` 数组中

#### Scenario: Duplicate events are close in time
- **WHEN** 多个候选 event 的 frame 间隔小于配置的最小事件间隔
- **THEN** detector SHALL 保留 confidence 更高的 event
- **AND** detector SHALL 按 frame 顺序输出去重后的 events

### Requirement: Ball trajectory and bounce JSON serialization
球轨迹引擎 SHALL 能将 raw trajectory、cleaned trajectory 和 bounce events 序列化为与 artifact contract 兼容的 JSON payload。

#### Scenario: Raw trajectory is serialized
- **WHEN** writer 序列化 raw ball trajectory
- **THEN** payload SHALL 包含 `schema_version`、`job_id`、`status`、`detail`、`coordinate_system` 和 `samples`
- **AND** 每个 sample SHALL 能表达 `frame_index`、`timestamp_sec`、`image_xy`、`court_xy`、`confidence`、`visible`、`accepted`、`candidate_count` 和 `source`

#### Scenario: Cleaned trajectory is serialized
- **WHEN** writer 序列化 cleaned ball trajectory
- **THEN** payload SHALL 包含 `schema_version`、`job_id`、`status`、`detail`、`filtering` 和 `samples`
- **AND** 每个 sample SHALL 能表达是否由插值生成

#### Scenario: Bounce events are serialized
- **WHEN** writer 序列化 bounce events
- **THEN** payload SHALL 包含 `schema_version`、`job_id`、`status`、`detail`、`detection_method` 和 `events`
- **AND** 没有弹跳事件时 `events` SHALL 为空数组

### Requirement: Engine remains disconnected from current pipeline
本 change 中新增的球轨迹与弹跳点引擎 SHALL 保持独立调用，不改变当前真实分析 job 的默认 pipeline 行为。

#### Scenario: Current analysis job runs
- **WHEN** 当前真实分析 job 在未进行后续 pipeline 接入 change 的情况下运行
- **THEN** 系统 MUST NOT 自动生成 ball trajectory、cleaned ball trajectory 或 bounce events artifact
- **AND** 现有球员、pose、tracking、serve 和 court-view 行为 MUST 保持不变

#### Scenario: Engine is used in unit tests or standalone code
- **WHEN** 测试或独立调用方直接实例化球轨迹与弹跳点引擎
- **THEN** 引擎 SHALL 能在不启动 FastAPI、不创建 analysis job、不访问前端的情况下运行核心处理逻辑
