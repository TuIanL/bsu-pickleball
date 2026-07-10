## Why

现有 `BallTracker` 在处理球检测结果时缺乏轨迹锁定感知机制。系统一旦形成稳定轨迹，仍可能被远处杂物、反光、白点等高置信度假阳性候选抢走当前球轨迹，导致后续弹跳检测、球速分析、回合切分全部被污染。

核心矛盾：**当前系统在 LOCKED 场景下倾向于"有候选就选候选"，但物理上不合理的候选比空帧更有害。**

## What Changes

### 1. BallTrackState 状态机

在 `BallTracker` 中引入四状态轨迹锁定：

- **SEARCHING**：无稳定轨迹时，主要依赖 detector confidence
- **TENTATIVE**：短轨迹形成但未稳定，同时参考 confidence 和 motion consistency
- **LOCKED**：轨迹稳定后，优先保护当前轨迹，候选必须通过动态物理门控
- **LOST**：短时丢球后保留预测位置，在 extended gate 内尝试恢复

### 2. 状态感知候选评分

不同状态下候选评分权重动态切换。LOCKED 状态下预测位置权重和物理连续性权重显著提升，detector confidence 权重下降。

### 3. 动态物理门控

取代当前固定的 `max_jump_pixels=220` / `prediction_gate_pixels=260` 阈值。门控距离根据近期球速、缺失帧数、帧率、画面球场区域自动调整。

### 4. Missing-over-false-positive 策略

在 LOCKED / LOST 状态下，如果候选未通过动态物理门控，系统必须输出 missing + predicted_position，而不是接受远处高置信候选。缺球优于错球。

### 5. 球员运动感知静止误检抑制

现有静止黑名单（`_stationary_blacklist`）结合球员运动上下文增强：静止候选仅在球员持续运动且非暂停/非比赛时间时判定为静止误检。

### 6. 结构化调试输出

每一帧输出 per-candidate debug metadata，包含 raw_confidence、final_score、distance_to_prediction、gate_decision、rejection_reason。

## Capabilities

### New Capabilities

- `ball-track-state-machine`: 球轨迹锁定状态机（SEARCHING / TENTATIVE / LOCKED / LOST），状态转移逻辑，以及状态感知的候选评分权重体系
- `ball-physics-gating`: 动态物理门控计算（距离、速度、加速度、尺寸一致性），missing-over-false-positive 策略，以及 per-candidate debug metadata 输出

### Modified Capabilities

- `ball-tracking`: 更新静止误报抑制需求，增加球员运动上下文和非比赛时间判断，补充 LOCKED 状态下 missing-over-false-positive 策略

## Impact

- **修改文件**：`ball_tracker.py`（核心改造）、`schemas.py`（新增 debug 字段和状态枚举）、`analysis_pipeline.py`（仅在 `_process_ball_frame()` 调用点传入可选 `player_motion_pixels`，不改变 pipeline 编排或 artifact 写入逻辑）
- **新增文件**：无（所有改动均在现有模块内完成）
- **测试文件**：`test_ball_game_analysis.py` 新增用例、新增 `test_ball_tracker_lock_gating.py`
- **不改变**：`trajectory_cleaner.py`、`bounce_detector.py`、`court_adapter.py`、`detector_protocol.py` 的现有逻辑。`analysis_pipeline.py` 的任务编排、artifact 写入路径和阶段结构保持不变
