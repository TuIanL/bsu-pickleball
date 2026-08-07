## Why

当前重建链已经能输出第三套 `reconstructed_ball_trajectory` 产物，但击球检测只依据球本身的运动突变，无法回答"这一拍是哪名球员打的"。前端因此只能看到一条无主球路，无法支持每名球员的击球数、球路方向、落点分布等后续统计。系统已经具备稳定球员身份（canonical `Player_1—Player_4`、render trajectory、上肢姿态证据），接入条件成熟，现在是补上"球员归属"这一层的最佳时机。

## What Changes

- **新增 `BallHitPlayerAttributor`**：对通过粗门的事件候选，综合球—手腕距离、球—人体框距离、上肢运动峰值、时间接近度等证据评分，输出 `confirmed / ambiguous / unassigned` 归属。
- **新增 `BallShotAssembler`**：引入 `shot_id`（一次击球产生的完整球路），管理 Shot 生命周期：confirmed/ambiguous hit 与 serve 开启新 Shot；bounce 只切飞行段、不改变 `shot_id` 与 owner；long loss 与流终止关闭 Shot。
- **弹地抑制收敛为单一权威**：把 `BallContactEventDetector` 内的对称 ±8 帧弹地抑制移除，改为 `BallEventResolver.prefilter()` 统一使用有符号非对称时间窗口（bounce 前 0.07s / 后 0.10s）；suppressed/rejected 候选不再进入正式事件列表。**BREAKING**：`detect()` 签名不再接收 `bounce_events`。
- **事件与产物协议升级为 v2**：`TrajectoryEvent` 增加 `event_status`、`hitter_player_id`、`ownership_status`、`attribution`；重建产物增加 `player_roster`、Shot 级 `shot_id` 与归属字段。`ownership_status` 支持 `confirmed / ambiguous / unassigned / not_applicable` 四态。
- **共享上肢证据模块**：从 `ServeStartDetector` 提取关键点索引与运动平滑逻辑为共享模块，保留 wrist/elbow 位置与 `arm_motion` 标量，Serve 检测迁移至共享索引（行为回归不变）。
- **身份胶水层**：`PlayerTrajectoryArtifact` 作为算法侧 canonical 身份主源，`track_id` 统一规范化为字符串作为证据关联键，Pose / overlay_frames 通过该键映射到 `Player_N`。
- **前端升级为 Shot 级交互**：按产物 `player_roster` 动态渲染 P1—P4 筛选与"未归属"，点选任意飞行段高亮整个 Shot，列表与统计按 `shot_id` 聚合；旧 v1 产物不伪造归属并隐藏球员筛选。

## Capabilities

### New Capabilities

- `player-hit-attribution`: 击球球员归属。共享上肢证据索引（wrist/elbow 位置与运动强度）、球—球员时空匹配评分、confirmed/ambiguous/unassigned 判定、尺度归一化与非对称接触时间窗。
- `ball-shot-assembly`: Shot 生命周期与归属传播。`shot_id` 建立、bounce 继承 owner、suppressed/rejected 无影响、long loss 关闭、serve player_id 播种、半场交替序列合理性校验。

### Modified Capabilities

- `ball-contact-event-detector`: 弹地抑制职责移出，只保留球运动突变检测（方向/速度/残差/refractory），不再读取 `bounce_events`。
- `event-anchored-trajectory-reconstruction`: 重建链接入球员上下文（`PlayerAttributionContext`），输出 v2 产物；resolver 拆分为 `prefilter / finalize` 两阶段。
- `reconstructed-trajectory-artifact`: 产物协议升级为 v2，新增 `player_roster`、`event_status`、`hitter_player_id`、`shot_id`、`ownership_status/confidence`、`attributed_frame_index`。
- `ball-trajectory-visualization`: 前端从"按 segment 展示"升级为"按 Shot 筛选、选中、统计"，动态球员筛选、未归属分组（击球者不明 / 无 Shot 上下文）、旧任务兼容。

## Impact

- **后端**：`ball_contact_event_detector.py`、`ball_event_resolver.py`、`reconstruction_engine.py`、`reconstruction_schemas.py`、`ball_flight_segmenter.py`、`analysis_pipeline.py`、`serve_start_detector.py`（提取共享模块）、`storage_service.py`（产物路径），新增 `ball_hit_player_attributor.py`、`ball_shot_assembler.py` 与共享上肢证据模块。
- **前端**：`BallTrajectoryPage.tsx`、`ballTrajectoryVisualization.ts`、`BallTrajectoryScene`、轨迹类型定义。
- **产物**：`reconstructed_ball_trajectory.v2`（v1 保留不回写，旧任务兼容展示）。
- **测试**：后端 `test_ball_trajectory_reconstruction.py`、`test_serve_start_detection.py`（回归）及新增归属/Shot 测试；前端轨迹可视化测试。
