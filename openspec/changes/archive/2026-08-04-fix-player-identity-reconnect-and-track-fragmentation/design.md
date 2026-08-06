# Design — 身份锁重连空间门控 + 重复重叠 track 抑制

## Context

job-6c0cc96f86 诊断数据（`player-trajectories` 的 lock/identity diagnostics）证实两条缺陷链：

```
fr=1300  P1 重连 → trk=50  score=0.522  position=0.00 motion=1.00 side=0.75 bbox=0.73
fr=1350  P1 重连 → trk=50  score=0.516  position=0.03 motion=0.96 side=0.75 bbox=0.66
```

- **A 缺陷（锁层）**：`_compute_reconnect_score`（`player_lock_manager.py:671`）把距离当**软分数**。位置与 `max_reconnect_distance_ft` 单位一致（`PlayerFramePosition.court_position` 为英尺，`image_to_court` 输出英尺），但距离只是加权项之一：fr=1300 候选距离 19.2 英尺、fr=1350 距离 15.0 英尺，position_score 归零/近零后，motion(1.00/0.96)/side(0.75)/bbox(0.73/0.66) 仍把总分补到 0.52 > `reconnect_threshold` 0.45，导致错误的 track 50 被当成 P1 重连。
- **B 缺陷（跟踪器层）**：`MultiObjectTracker` 把 P2 分身成 track 41（正）与 track 50（幻影），两 track bbox IoU 0.64-0.68 持续 5+ 帧。track 50 作为"幻影候选"源源不断提供给身份层。

## Goals / Non-Goals

**Goals:**
- A：重连候选超过"允许距离"硬性拒绝，保持 LOST（蓝点冻结在最后可信位置），不再瞬移到其他球员。
- A：修复单位错用，距离门按流逝时间缩放（允许 `基础距离 + 估计速度 × 流逝时间`），避免遮挡期间长距离跑动被误拒。
- B：球员跟踪输出抑制同一目标的重复重叠 track，从源头消灭"幻影候选"。
- 前端无需改动（上一 change 的位移断线已就位，配合本次后端修复，蓝点与连线都正确）。

**Non-Goals:**
- 不修检测器（R1）：P1 离画面远未被检测到属模型/参数层面，超出本 change。
- 不改 `BallTracker` / 球路径（球用独立跟踪器，重复抑制只作用于球员）。
- 不改变 `MultiObjectTracker` 的 IOU 匹配算法本身（只在其输出上加抑制层，降低回归风险）。

## Decisions

### Decision A: 锁层重连空间门控

`player_lock_types.py` 新增配置：
- `max_reconnect_distance_ft: float = 15.0`（保留，语义修正为英尺）
- `reconnect_lateral_mismatch_score: float = 0.2`（同侧横错配惩罚，替代硬编码 0.75）
- `reconnect_gate_enabled: bool = True`（防御性开关）

`player_lock_manager.py`：
1. **硬距离门**（单位：英尺；`last_confirmed_position_m` 实为英尺，`_m` 为历史命名误解）：
   ```
   elapsed_s = max(0, candidate.frame_index - slot.last_seen_frame) / config.fps
   speed_ft_s = meters_to_feet(hypot(last_velocity_mps)) if set else 0   # last_velocity_mps 为 m/s
   allowed_dist_ft = max_reconnect_distance_ft + speed_ft_s * elapsed_s
   ```
   `_compute_reconnect_score` 内 `dist > allowed_dist_ft` 时返回 `-1.0`（`_assign_recovery_candidates` 与 `_find_best_reconnect` 均按 `score >= reconnect_threshold` 判断，负数即拒绝）。
2. **position_score 语义**：门内 `max(0, 1 - dist/max(1, allowed_dist_ft))`。
3. **横向错配惩罚**：`_reconnect_side_score` 同侧但不同横向由 0.75 → `reconnect_lateral_mismatch_score`(0.2)，与错侧同级。

**备选**：只压阈值/只调权重。否决——软分数永远有漏网之鱼（本次即 position=0 仍重连），必须硬门。

### Decision B: 重复重叠 track 抑制

新增 `DuplicateTrackSuppressor`（置于 `multi_object_tracker.py`，与 IOU 工具同文件）：
- 配置：`iou_threshold: float = 0.6`，`sustain_frames: int = 3`。
- 状态：`dict[frozenset[int], int]` 记录每个 track 对的持续重叠帧数；缺席/分离帧**衰减 -1 而非清零**（容错真实分身常见的 1 帧缺席，如 fr=1302 只有 track 50）。
- `filter(tracks)`：两两算 bbox IoU；`IoU ≥ threshold` 时计数器 +1，否则 -1；计数 ≥ `sustain_frames` 时抑制该对中**较新的 track**（track_id 较大者，分身通常为新 track；仅当新 track 置信度显著更高时反过来），从输出中剔除。
- **只过滤输出，不改内部 `_tracks`**：若两目标后续分离（IoU 下降），计数衰减到阈值以下后，被抑制 track 自然重新出现——避免误杀两个真·近距离球员。

接入点：pipeline 球员路径 `tracks = tracker.update(detections)`（`analysis_pipeline.py:1756`）后加一行 `tracks = duplicate_suppressor.filter(tracks)`；每次 run 实例化一个 suppressor。球路径（`BallTracker`）不受影响。

**备选**：改 `MultiObjectTracker` 匹配逻辑阻止分身。否决——贪心 IOU 匹配改动风险高（可能影响所有正常跟踪），输出层抑制更外科手术、可独立开关与测试。

## Risks / Trade-offs

- [距离门过严 → 遮挡期间合法长跑被误拒，球员冻结] → 用 `速度 × 流逝时间` 缩放允许距离；冻结优先于错认（与"硬锁到底"哲学一致）。
- [重复 track 抑制误杀真·近距离双人] → IoU 阈值 0.6 + 持续 3 帧 + 缺席衰减 + 输出层抑制（内部保留，分离数帧即恢复），多重缓解。
- [行为变化需重跑任务验证] → 用 job-6c0cc96f86 或同视频重建任务，重点核对 21-23 秒 P1 蓝点不再瞬移、不再出现幻影 track。
