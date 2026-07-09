## 1. BallTrackState enum 与轨迹上下文

- [ ] 1.1 `schemas.py`: 新增 `BallTrackState` 枚举（SEARCHING、TENTATIVE、LOCKED、LOST）
- [ ] 1.2 `ball_tracker.py`: 新增 `BallTrackContext` dataclass（track_state、轨迹点历史、平滑速度、缺失帧数、lock_hits 计数）
- [ ] 1.3 `ball_tracker.py`: 在 `BallTracker.__init__()` 中初始化 `BallTrackContext`
- [ ] 1.4 `ball_tracker.py`: 在 `BallTrackerConfig` 中新增 `tentative_min_hits=2`、`lock_min_hits=4`、`max_missing_frames_locked=10`

## 2. 平滑速度预测

- [ ] 2.1 `ball_tracker.py`: 重构 `_predict_next_position()`，从仅用最后 2 点改为最近 N 点平滑速度外推（`min_prediction_points=3`，不足时回退 2 点）
- [ ] 2.2 确保平滑速度在轨迹长度不足时正确退化

## 3. 动态物理门控

- [ ] 3.1 `BallTrackerConfig`: 新增 `base_gate_pixels=60`、`speed_factor=1.5`、`missing_factor=30`、`min_gate_pixels=50`、`max_gate_pixels=600`
- [ ] 3.2 `ball_tracker.py`: 新增 `_compute_dynamic_gate()`，根据近期球速、缺失帧数、帧率计算原始门控值，然后 `clamp(raw, min_gate_pixels, max_gate_pixels)`
- [ ] 3.3 `ball_tracker.py`: `_compute_dynamic_gate()` 中的 `perspective_adjustment` 使用简单上下半区段：近端×1.2-1.5、远端×0.8-1.0、unknown×1.0（退化为无 perspective 调整）
- [ ] 3.4 `ball_tracker.py`: 将 `_continuity_reject_reason()` 中的固定 `max_jump_pixels`/`prediction_gate_pixels` 替换为动态门控调用

## 4. 状态转移逻辑

- [ ] 4.1 `ball_tracker.py`: 新增 `_update_track_state()`，根据最近的 accepted 连续性和缺失状态驱动 SEARCHING → TENTATIVE → LOCKED → LOST 转移
- [ ] 4.2 TENTATIVE → LOCKED：连续 `lock_min_hits` 个 accepted 候选后升级
- [ ] 4.3 LOCKED → LOST：当前帧无候选通过门控时转移
- [ ] 4.4 LOST → LOCKED：候选出现在 extended gate 内且恢复时转移
- [ ] 4.5 LOST → SEARCHING：`missing_frames > max_missing_frames_locked` 时重置

## 5. 状态感知候选评分 + Missing-over-false-positive

- [ ] 5.1 `BallTrackerConfig`: 新增状态权重字典 `state_weights`，包含 SEARCHING/TENTATIVE/LOCKED/LOST 各自的 `detector_confidence_weight`、`prediction_weight`、`motion_consistency_weight`、`size_consistency_weight`、`jump_penalty_weight`
- [ ] 5.2 `ball_tracker.py`: 重构 `_select_candidate()` 为内部决策函数，根据 `track_state` 使用对应的权重组合打分和门控
- [ ] 5.3 `_select_candidate()` 返回 `(selected, overall_decision, reason)` 三元组，直接输出最终决策，避免"评分说 accepted 但外层推翻"的不一致
- [ ] 5.4 LOCKED/LOST 分支：对候选按分数排序，依次检查动态门控，第一个通过门控的为 accepted；若无人通过则返回 `(None, "missing_predicted_only", "no_candidate_passed_physics_gate")`
- [ ] 5.5 SEARCHING 分支：按 detector confidence 排序直接取最高者，返回 `(best, "accepted", None)`，不执行 missing-over-false-positive
- [ ] 5.6 TENTATIVE 分支：按综合评分取最高者，返回 `(best, "accepted", None)`，不使用强制门控审查

## 7. 锁定期缺失恢复增强

- [ ] 7.1 `ball_tracker.py`: 修改 `_record_missing_detection()`，LOCKED/LOST 状态下使用 `max_missing_frames_locked` 而非统一的 `max_missing_frames`
- [ ] 7.2 LOST 状态使用 extended gate（动态门控 × 1.5× 乘子）进行恢复
- [ ] 7.3 missing 帧输出 `predicted_position`（来自 `_predict_next_position()`）

## 8. 球员运动感知静止误检抑制

- [ ] 8.1 `ball_tracker.py`: `update()` 新增可选参数 `player_motion_pixels: float | None = None`
- [ ] 8.2 `ball_tracker.py`: 新增 `_player_motion_static_reject_reason()`，结合候选静止判断和球员运动上下文
- [ ] 8.3 球员运动阈值 `player_motion_min_pixels=15` 加入 `BallTrackerConfig`
- [ ] 8.4 `player_motion_pixels=None` 时完全回退现有黑名单行为，不报错

## 9. Debug metadata 数据结构

- [ ] 9.1 `schemas.py`: 新增 `BallTrackState` 枚举（SEARCHING、TENTATIVE、LOCKED、LOST）
- [ ] 9.2 `schemas.py`: 新增 `BallCandidateDebug` dataclass（candidate_id、bbox、raw_confidence、final_score、distance_to_prediction、passed_physics_gate、rejection_reason）
- [ ] 9.3 `schemas.py`: 新增 `BallFrameDebug` dataclass（track_state、predicted_position、candidates、accepted_candidate_id、overall_decision）
- [ ] 9.4 `BallFrameSample`: 顶层新增可选字段 `track_state: str | None`、`predicted_position: Point2D | None`、`overall_decision: str | None`
- [ ] 9.5 `BallFrameSample.diagnostics` 内部存储完整的 `BallFrameDebug` 结构，per-candidate 细节不进顶层
- [ ] 9.6 `BallTracker.update()` 每帧填充精简字段到顶层、完整 debug 数据到 `diagnostics`

## 10. 管线集成

- [ ] 10.1 `analysis_pipeline.py`: 在 `_process_ball_frame()` 调用 `tracker.update()` 时传入 `player_motion_pixels`（从球员重心帧间位移计算）
- [ ] 10.2 若球员检测数据不可用，`player_motion_pixels` 传入 None

## 11. 单元测试

- [ ] 11.1 测试 SEARCHING → TENTATIVE → LOCKED 状态转移
- [ ] 11.2 测试 LOCKED → LOST → 恢复 → LOCKED 状态转移
- [ ] 11.3 测试 LOST → SEARCHING（超过 `max_missing_frames_locked` 后重置）
- [ ] 11.4 测试 LOCKED 状态下远处高置信假球被拒绝（missing-over-false-positive）
- [ ] 11.5 测试 LOCKED 状态下无真球候选但有远处假球时输出 `predicted_position`
- [ ] 11.6 测试短时缺失恢复（LOCKED 状态 8 帧缺失后恢复）
- [ ] 11.7 测试快速球不被动态门控误杀
- [ ] 11.8 测试球员运动感知静止误检抑制
- [ ] 11.9 测试 `player_motion_pixels=None` 时回退现有行为
- [ ] 11.10 测试 debug metadata 输出格式正确
