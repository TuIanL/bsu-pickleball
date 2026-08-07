# Tasks: 球员归属球路（add-player-attributed-ball-shot-trajectories）

## 1. 共享上肢证据模块

- [x] 1.1 新建 `backend/app/vision/pickleball_game_analysis/upper_limb_evidence.py`：定义 `UpperLimbFrameEvidence`（track_id/frame_index/timestamp_seconds/左右手腕/左右肘坐标/arm_motion_px_per_second）与 `build_upper_limb_evidence_index(pose_frames, *, smooth_window_frames)`，从 `ServeStartDetector._pose_motion_by_track` 提取坐标保留逻辑与滑动平均逻辑
- [x] 1.2 迁移 `ServeStartDetector` 读共享索引（`_pose_motion_by_track` 改为调用共享模块），行为保持逐字节一致
- [x] 1.3 新增共享模块单元测试（wrist/elbow 坐标保留、运动强度平滑、缺帧处理）
- [x] 1.4 回归：跑 `test_serve_start_detection.py` 全量通过，发球结果与迁移前一致

## 2. 身份胶水层

- [x] 2.1 定义 `normalize_track_key(track_id) -> str | None`，新增单测覆盖 int/str/None（如 17 → "17"、"17" → "17"）
- [x] 2.2 实现 `PlayerAttributionContext`：以 `PlayerTrajectoryArtifact` 为 canonical 主源，建立 `track_id(str) → player_id` 映射；pose / overlay_frames 作为证据查询源；render v2 roster 提供 render_slot
- [x] 2.3 契约测试：`PlayerTrajectorySample(track_id=17, player_id="Player_2")` + `PoseSubject(track_id="17")` + `FrameDetection(track_id="17")` → 归属结果 `Player_2`
- [x] 2.4 确认 `analysis_pipeline.py` 中 `_TrackingRunOutput` 已持有所需内存对象（render_trajectory / pose_frames / tracking / ball_run_output），无需文件回读

## 3. 弹地抑制收敛（Detector / Resolver 重构）

- [x] 3.1 `BallContactEventDetector.detect()` 移除 `bounce_events` 参数与内部对称窗口抑制（ball_contact_event_detector.py:144-154），删除 `bounce_suppression_window_frames` 配置项
- [x] 3.2 `ResolverConfig` 改为时间语义：`bounce_suppress_before_sec=0.07`、`bounce_suppress_after_sec=0.10`、`bounce_suppress_confidence=0.60`，实现有符号 `delta_sec` 判定
- [x] 3.3 拆 `BallEventResolver.prefilter()`（纯球侧粗门：bounce 抑制 + refractory + 残差拒绝）与 `finalize()`（结合归属生成最终事件），新增 `PrefilteredHitCandidate` 数据对象
- [x] 3.4 窗口边界测试：-0.05s → suppressed；+0.08s → suppressed；+0.12s / +0.20s → survives prefilter
- [x] 3.5 快速垫击回归用例：frame 100 hit(P1) → frame 130 bounce → frame 136 hit candidate（+0.20s）不被抑制，进入归属
- [x] 3.6 配置快照（before/after/fps/frame_stride）写入产物 diagnostics

## 4. BallHitPlayerAttributor

- [x] 4.1 新建 `ball_hit_player_attributor.py`：`HitPlayerAttributionConfig`（contact_window_before_sec=0.15 / after_sec=0.08、maximum_pose_sample_gap_sec=0.10、maximum_tracking_sample_gap_sec=0.12、权重、attribution_min_score、attribution_min_margin）
- [x] 4.2 证据评分实现：wrist_proximity(0.35，人体尺度归一化 `pixel_dist / max(bbox_diagonal, minimum_scale_px)`)、bbox_proximity(0.25)、arm_motion_peak(0.20，窗口内 max)、court_side(0.15)、temporal_freshness(0.05)；证据缺失时剩余权重归一化
- [x] 4.3 判定：confirmed（分数达标且 margin 达标）/ ambiguous（分数达标但 margin 不足）/ unassigned（证据不足）；输出 `PlayerAttribution`（含 attributed_frame_index 与 candidate_scores）
- [x] 4.4 serve 播种：`_serve_reset_events()` 补传 `player_id`，归属 method = `serve_seeded`
- [x] 4.5 测试：P1 手腕近 + 挥拍峰值 → confirmed Player_1；网前 P1/P2 近但 P2 腕部运动强 → Player_2；证据接近 → ambiguous；无姿态 → bbox 降级归属；无证据 → unassigned

## 5. BallShotAssembler

- [x] 5.1 新建 `ball_shot_assembler.py`：按生命周期表组装 `shot_id`（confirmed/ambiguous hit 与 serve 开启；bounce 继承；suppressed/rejected 无影响；long loss / 流终止关闭）
- [x] 5.2 归属传播：bounce 后 segment 继承 `hitter_player_id` 与 `ownership_status/confidence`，记录 `ownership_source_event_id`
- [x] 5.3 `shot_id=null` 孤立段输出 `ownership_status=not_applicable`
- [x] 5.4 测试：hit(P1) → bounce → next hit(P3) 前后段同属 P1 shot；suppressed hit 不切断 shot；long loss 后残余段为孤立段

## 6. 半场交替序列校验

- [x] 6.1 实现 `hitter_side_at_contact` 推导（contact 时刻球员球场位置所在半场，非 initial_side）
- [x] 6.2 连续同侧校验：证据弱（conf<0.85 或 margin<0.25）降级 ambiguous；证据强保留并记录 `side_alternation_violation`
- [x] 6.3 测试：同侧弱证据降级；同侧强证据保留 + diagnostics

## 7. 重建链与产物 v2

- [x] 7.1 `reconstruction_schemas.py`：`TrajectoryEvent` 增加 `event_status`、`hitter_player_id`、`hitter_render_slot`、`ownership_status`、`ownership_confidence`、`ownership_source_event_id`、`attribution`；`FlightSegment`/`ReconstructedSegment` 增加 shot/owner 字段；`ownership_status` 四态枚举
- [x] 7.2 `reconstruction_engine.py`：接 `PlayerAttributionContext`，编排 prefilter → attribute → finalize → segment → shot assembly，输出 `reconstructed_ball_trajectory.v2`（顶层 `player_roster`，事件含 attribution，段含 shot 归属）
- [x] 7.3 `analysis_pipeline.py` 接线：内存对象直接构造 `PlayerAttributionContext` 传入，写入 v2 产物，不覆盖 v1 路径
- [x] 7.4 v2 序列化与 schema 版本常量更新；`event_to_payload` / `_segment_to_payload` 扩展
- [x] 7.5 无球员上下文降级：仍完成事件切段与重建，归属字段为 null/unassigned，不伪造

## 8. 前端 Shot 级交互

- [x] 8.1 `ballTrajectoryVisualization.ts`：`EstimatedBallTrajectory` 增加 shotId/hitterPlayerId/hitterRenderSlot/ownershipStatus/ownershipConfidence；新增 `EstimatedBallShot` 视图模型与聚合逻辑；轨迹 ID 改用后端 `segment_id`
- [x] 8.2 `BallTrajectoryScene`：选中状态升级为 `selectedShotId`，点击任意 segment 通过 `userData.shotId` 高亮整个 Shot；渲染保持独立 line strip
- [x] 8.3 `BallTrajectoryPage`：动态球员筛选（来自 `player_roster`，单打/双打自适应，v1 隐藏）、"未归属"双分组（击球者不明 / 无 Shot 上下文）、筛选顺序 球员→可信度→数量限制、列表与统计按 Shot 聚合
- [x] 8.4 前端测试：P3 筛选可见球路均为 Player_3；shot 含两 segment 时点选高亮两条；v1 产物无筛选仍正常展示；统计按 shot 去重

## 9. 验收与全量回归

- [x] 9.1 端到端验收用例（含第 3.5 快速垫击场景与 9 个硬验收：手腕归属、网前区分、ambiguous、bbox 降级、serve 播种、跨 bounce 继承、track 切换保持 canonical、前端 P3 筛选、v1 兼容）
- [x] 9.2 后端全量测试通过：`pytest backend/tests`（重点 `test_ball_trajectory_reconstruction.py`、`test_serve_start_detection.py`、新增归属/Shot 测试）
- [x] 9.3 前端全量测试通过：`npm test`（重点轨迹可视化相关）
- [x] 9.4 lint/typecheck 通过（后端 ruff / 前端 eslint + tsc）
