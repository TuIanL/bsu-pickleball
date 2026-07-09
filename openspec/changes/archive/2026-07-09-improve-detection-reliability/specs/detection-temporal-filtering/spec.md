# detection-temporal-filtering Specification

## Purpose
为检测结果引入时序维度的过滤规则，使系统具备「跨帧记忆」的检测决策能力——球跟踪器的静止候选黑名单机制与姿态估计的 keypoint 可见性滞回机制——消除因逐帧独立判定导致的闪烁误报问题。

## ADDED Requirements

### Requirement: Ball stationary candidate blacklisting
BallTracker SHALL 维护一个跨帧静止候选黑名单，对在相同像素区域持续出现的候选做投票计数，超过阈值后永久过滤，避免因检测器在相邻帧间闪烁导致的静止物漏过滤。

#### Scenario: Stationary object detected on court surface
- **WHEN** 球检测器在连续帧中输出落在同一离散化像素网格（5px 容差）的候选，且该网格的跨帧静止帧计数累计超过 60 帧（约 2 秒 @30fps）
- **THEN** BallTracker SHALL 将该网格坐标加入静止黑名单
- **AND** 后续帧中落入该黑名单网格的候选 SHALL 被过滤，拒绝原因标记为 `stationary_blacklisted`

#### Scenario: Stationary object flickers in and out of detection
- **WHEN** 静止候选的检测不稳定（某些帧检测到、某些帧未检测到），但其累计静止帧数仍达到 60 帧阈值
- **THEN** 静止黑名单 SHALL 依然生效，不因检测闪烁而重置计数
- **AND** 网格坐标离散化容差 SHALL 为 5px，确保轻微抖动不产生新网格

#### Scenario: Moving ball passes through a blacklisted area
- **WHEN** 真实球运动轨迹经过某个已加入黑名单的网格坐标
- **THEN** 该候选 SHALL 仍按连续性检查（跳变距离、预测门限）判定
- **AND** 若通过连续性检查（与上一有效点距离 < max_jump_pixels 且偏差 < prediction_gate_pixels），SHALL 覆盖黑名单接受该候选
- **AND** 若未通过连续性检查，SHALL 被黑名单过滤

#### Scenario: Blacklisted area is cleared when court is recalibrated
- **WHEN** 同一 job 内球场标定被重新设置
- **THEN** 静止黑名单 SHALL 被清空，重新开始积累

#### Scenario: Blacklist does not affect artifact schema
- **WHEN** BallTracker 因静止黑名单拒绝候选
- **THEN** 该帧的 `BallFrameSample.accepted` SHALL 为 false
- **AND** `BallFrameSample.reject_reason` SHALL 包含 `stationary_blacklisted`
- **AND** 不影响 `ball_trajectory.json` 和 `ball_overlay.json` 的现有 schema 结构

### Requirement: Pose keypoint visibility hysteresis
RTMPose26Adapter SHALL 对关键点可见性判定引入滞回机制——关键点从「可见→不可见」使用低于进入阈值的退出阈值，消除临界置信度附近的闪烁。

#### Scenario: Keypoint confidence fluctuates near threshold
- **WHEN** 某关键点在连续帧中的 confidence 在 enter_threshold（默认 0.3）附近波动（例如 0.29 → 0.31 → 0.28 → 0.32）
- **THEN** 关键点的 visible 状态 SHALL 在首次达到 enter_threshold 后保持为 true
- **AND** 只有当 confidence 连续降至 exit_threshold（默认 0.2）以下时，visible SHALL 变为 false
- **AND** 从不可见恢复可见仍需 confidence >= enter_threshold

#### Scenario: Keypoint first appears with moderate confidence
- **WHEN** 某关键点首次出现且 confidence 介于 exit_threshold 和 enter_threshold 之间（如 0.25）
- **THEN** visible SHALL 为 false（未达到进入阈值）

#### Scenario: Keypoint is consistently high confidence
- **WHEN** 某关键点持续保持在 enter_threshold 以上
- **THEN** visible SHALL 保持为 true，hysteresis 无副作用

#### Scenario: Keypoint drops significantly below exit threshold
- **WHEN** 某关键点 confidence 从高位骤降至 exit_threshold 以下
- **THEN** visible SHALL 立即变为 false，无需等待连续多帧确认

#### Scenario: Hysteresis parameters are configurable
- **WHEN** 环境变量 `PICKLEBALL_POSE_CONFIDENCE_EXIT` 被设置
- **THEN** RTMPose26Adapter SHALL 使用该值作为 exit_threshold
- **AND** 默认 exit_threshold SHALL 为 0.20，默认 enter_threshold SHALL 为 0.30
- **AND** exit_threshold 与 enter_threshold 的取值不受相互约束（允许 exit > enter 的退化配置，此时退化为硬阈值）

#### Scenario: Hysteresis does not change pose artifact schema
- **WHEN** pose 结果被序列化为 pose_artifact JSON
- **THEN** `visible` 字段 SHALL 反映 hysteresis 后的最终判定
- **AND** `confidence` 字段 SHALL 保持原始模型输出值，不受 hysteresis 修改
