## 1. A. 锁层重连空间门控（player_lock_manager.py + player_lock_types.py）

- [x] 1.1 `player_lock_types.py`：`PlayerLockConfig` 新增 `reconnect_lateral_mismatch_score: float = 0.2` 与 `reconnect_gate_enabled: bool = True`；保留 `max_reconnect_distance_ft=15.0`（语义修正为英尺）
- [x] 1.2 `player_lock_manager.py`：`_compute_reconnect_score` 内计算 `elapsed_s = max(0, candidate.frame_index - slot.last_seen_frame) / fps`、`speed_ft_s = meters_to_feet(hypot(last_velocity_mps)) if set else 0`、`allowed_dist_ft = max_reconnect_distance_ft + speed_ft_s * elapsed_s`；`dist > allowed_dist_ft` 时返回 -1.0（硬拒绝）
- [x] 1.3 `_compute_reconnect_score` 的 position_score 改用 `1 - dist/allowed_dist_ft`（门内归一）；导入 `meters_to_feet`
- [x] 1.4 `_reconnect_side_score`：同侧但不同横向返回 `reconnect_lateral_mismatch_score`（默认 0.2），与错侧同级

## 2. B. 重复重叠 track 抑制（multi_object_tracker.py + analysis_pipeline.py）

- [x] 2.1 `multi_object_tracker.py`：新增 `DuplicateTrackSuppressor`（配置 `iou_threshold=0.6`、`sustain_frames=3`；维护 `dict[frozenset[int], int]` 持续重叠计数，缺席/分离帧衰减 -1 而非清零；`filter(tracks)` 两两算 IoU，≥ 阈值且计数 ≥ sustain_frames 时抑制对中较新的 track，新 track 置信度显著更高时反过来；只过滤输出不改内部状态）
- [x] 2.2 `analysis_pipeline.py`：run 内实例化一个 `DuplicateTrackSuppressor`，在 `tracks = tracker.update(detections)` 后插入 `tracks = duplicate_suppressor.filter(tracks)`（仅球员路径；球路径不动）

## 3. 测试

- [x] 3.1 `test_player_lock_manager.py` 新增：远距离候选被拒绝保持 LOST；门内候选正常重连；横向错配候选单独不足以达阈值
- [x] 3.2 新增/扩展 `test_multi_object_tracker.py`：持续高 IoU 分身被抑制；低度/短时重叠不抑制；分离后恢复
- [x] 3.3 后端 `pytest` 全量通过

## 4. 验证

- [x] 4.1 `openspec validate --changes` 通过
- [x] 4.2 用 job-6c0cc96f86 真实数据重放验证（A：fr=1300 距离 18.6ft 被距离门拒绝、fr=1350 横向错配使总分 0.516→0.406 被拒；B：track 50 从 fr=1308 起被抑制、与 track 41 共存帧数由 5 降到 3；完整任务重跑核对待用户执行）
