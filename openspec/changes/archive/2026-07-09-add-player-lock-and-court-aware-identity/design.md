## Context

### 现有架构

```
每帧（analysis_pipeline.py:_run_tracking 约 L1454-1579）：

  1. PersonDetector.detect(frame)                         → raw_detections
  2. filter_detections_to_roi(raw_detections, roi)        → detections
  3. MultiObjectTracker.update(detections)                 → tracks (IOU-based, max_lost=15)
  4. FootpointEstimator.estimate(track)                    → image footpoint
  5. PlayerProjector.project(tracks, homography, ...)      → PlayerFramePosition[] (court ft)
  6. CourtPositionSmoother.update(track_id, x_ft, y_ft, …) → 平滑坐标
  7. PrimaryPlayerSelector.select(tracks, positions, …)    → top 4 track_ids
  8. _tracks_to_frame_detections(..., eligible_track_ids)  → FrameDetection[] (只保留 top4)
  9. identity_manager.update(frame_index, positions,
         eligible_track_ids=primary_player_track_ids)      → Player_x 轨迹样本
```

### 瓶颈点

**(A) PrimaryPlayerSelector 是硬门控**

`_run_tracking` L1486-1511：

```python
primary_player_track_ids = {
    selection.track_id
    for selection in self.primary_player_selector.select(...)
}
# ...
player_samples = identity_manager.update(
    positions=frame_positions,
    eligible_track_ids=primary_player_track_ids,   # ← 远端球员不在此集合
)
```

远端球员因以下原因易掉出 top 4：

- `mean_confidence` 低 → `tracklet_quality_score` 低（`primary_player_selector.py:293-306`）
- bbox 面积小 → 可能低于 `min_box_area_ratio`（默认 0.0005）→ 直接淘汰
- 投影坐标不稳定 → `target_court_occupancy` 低

**(B) PlayerIdentityManager 无法记住被筛掉的球员**

`player_identity.py:110-120`：

```python
if eligible_track_ids is not None:
    excluded = [obs for obs in observations if obs.track_id not in eligible_track_ids]
    observations = [obs for obs in observations if obs.track_id in eligible_track_ids]
```

即使 `PlayerIdentityManager` 有 `lost_buffer_frames=90` 的重连窗口，它也永远不会看到被筛掉的 track。

**(C) MultiObjectTracker 的 track_id 不稳定**

`multi_object_tracker.py:23`：`max_lost=15` 帧后删除 track。球员捡球离场 → track 删除 → 返回时新 track_id。

**(D) CourtPositionSmoother 按 track_id 索引**

`court_position_smoother.py:37-49`：`_states: dict[int, SmoothState]`。track_id 变了 → 平滑状态重置。

---

## Decisions

### Decision 1: 新增 PlayerLockManager 中间层

```
PersonDetector → MultiObjectTracker → PlayerProjector → CourtPositionSmoother
                                                            │
                                                            ▼
                                                     PrimaryPlayerSelector
                                                       （降级为建议器）
                                                            │
                                                       suggestions
                                                            │
                                                            ▼
                                                     PlayerLockManager  ←── 新增
                                                       │
                                                       ├─ bootstrap: 前 N 帧锁定 4 球员
                                                       ├─ maintain: 保留已锁定球员
                                                       ├─ reconnect: lost 球员重连
                                                       └─ reject: 排除路人/观众
                                                       │
                                                       locked_ids + suggestions
                                                            │
                                                            ▼
                                                     PlayerIdentityManager
```

**Why separate from PlayerIdentityManager?**

- PlayerIdentityManager 负责 track ↔ player 的一对一观测绑定
- PlayerLockManager 负责四名主球员集合的稳定性策略
- 职责分离后，identity manager 继续处理观测级别的插值/平滑/状态更新，lock manager 处理策略级别的准入/锁定/释放

### Decision 2: 状态机设计

每个主球员独立维护状态（非全局状态机，而是 per-player）：

```
                  ┌──────────┐
                  │SEARCHING │  ← 初始状态 / 长时间丢失后重置
                  └────┬─────┘
                       │ bootstrap 期间连续 plausible_hits >= 3
                       ▼
                  ┌──────────┐
                  │TENTATIVE │  ← 观察中，未完全信任
                  └────┬─────┘
                       │ 连续 plausible_hits >= lock_min_hits（默认 5）
                       ▼
          ┌───────────────────────┐
          │       LOCKED          │  ← 稳定跟踪，低置信度保留
          └───┬───────────────┬───┘
              │               │
     丢失 < lost_buffer      置信度恢复
              │               │
              ▼               │
          ┌──────┐            │
          │ LOST │────────────┘
          └──┬───┘
             │ 丢失 > lost_max_frames_locked（默认 300）
             ▼
         SEARCHING（重新初始化）
```

**Why not a single 4-player state machine?**

每个球员的丢失/恢复是独立的。Player_1 捡球离场时 Player_2/3/4 可能仍在场上。

### Decision 3: Bootstrap 阶段（动态窗口）

bootstrap 使用动态窗口：有最短帧数和最长帧数，不达到目标人数时可自动延长：

```
bootstrap 参数（可配置）：
  bootstrap_min_frames: int = 60        # 最短收集帧数（60fps 约 1 秒，30fps 约 2 秒）
  bootstrap_max_frames: int = 180       # 最长收集帧数（到达后强制结束）
  min_observed_frames: int = 8          # 候选至少出现 8 帧
  bootstrap_min_conf: float = 0.15      # bootstrap 期间最低置信度
  bootstrap_court_margin_ft: float = 12.0  # 球场外扩候选区域

流程：
  1. 收集前 bootstrap_min_frames 帧内所有 tracklet
  2. 若已锁定人数 < target_player_count，继续收集到 bootstrap_max_frames
  3. 只要某个候选满足 lock_min_hits（连续 5 帧在球场区域），立即锁定该候选
  4. 对每个 tracklet 统计：
     - 出现帧数
     - 平均置信度
     - 平均 bbox 面积
     - 球场归属比例（inside_court + near_court 占比）
     - 四人组分布合理性
  5. 选出最多 target_player_count 个最优候选，按预期位置分配 identity_id
  6. 已选候选状态 → LOCKED，未满额空 slot → 继续 SEARCHING
```

side_hint 不做永久语义绑定。`player_3` 在 bootstrap 时可能被标记为 `side_hint="far_left"`，但当球员换位/走位时，`player_3` 身份不变，`side_hint` 允许更新。side_hint 只是空间提示，不是身份定义。

### Decision 4: 状态依赖阈值

不同状态下对 confidence、court distance、bbox area 有不同要求：

| 参数 | SEARCHING | TENTATIVE | LOCKED | LOST 重连 |
|------|-----------|-----------|--------|-----------|
| conf_threshold | 0.20 | 0.15 | 0.06 | 0.10 |
| max_court_distance_ft | court+8ft | court+12ft | court+20ft | 上次位置+15ft |
| min_box_area_ratio | 0.0005 | 0.0003 | 0.0001 | 0.0002 |
| reconnect_score_threshold | N/A | N/A | N/A | 0.45 |

**Why LOCKED conf_threshold = 0.06?**

远端球员在画面中像素面积小（可能 < 500px²），YOLO 对该尺度的置信度在 0.1-0.3 之间波动。0.06 足够低以避免因短时波动丢失已锁定球员，但又高于典型的背景误检（< 0.05）。

### Decision 5: 空间门控

利用已有 `PickleballCourtGeometry` 的 `is_in_court_bounds()` 和 `is_in_tracking_bounds()`，构建三层空间门控：

```
inside_court          [0, 20] × [0, 44] ft       ← 使用 court_bounds
near_court_area       [-8, 28] × [-8, 52] ft      ← 使用 court_bounds + court_margin
tracking_area         [-4, 24] × [-8, 52] ft       ← 使用 tracking_bounds（已有）
outside_tracking_area  其余区域
```

初始化新球员：只能来自 inside_court 或 near_court_area
维持已锁定球员：可以来自 tracking_area 内（含 near_court_area）
拒绝：outside_tracking_area 的任何候选

**Why not use existing tracking_bounds directly?**

`tracking_bounds`（x: -4~24, y: -8~52）是固定值。near_court_area 需要更大外扩来覆盖捡球区域。同时需要区分"用于初始化的区域"和"用于维持已锁定球员的区域"。

### Decision 6: PlayerLockUpdate 输出结构

使用结构化的 `PlayerLockUpdate` 作为 `PlayerLockManager.update()` 的返回值，而非裸 `set[int]`。这避免 "locked_identity_ids 与 eligible_track_ids 并集" 的类型不一致问题（identity 与 track 不能直接并集）：

```python
@dataclass
class PlayerLockUpdate:
    eligible_track_ids: set[int]                       # 本帧应被身份管理器看到的 track 集合
    track_identity_hints: dict[int, str]               # track_id → identity_id 提示映射
    player_states: dict[str, str]                      # identity_id → status（active/lost/inactive）
    diagnostics: list[PlayerIdentityDiagnostic]        # 锁定相关诊断事件
    newly_locked: list[str]                            # 刚锁定的 identity_id 列表
    newly_lost: list[str]                              # 刚丢失的 identity_id 列表
```

数据流修正后：

```python
# PrimaryPlayerSelector 只提供建议，不再做硬门控
suggestions = self.primary_player_selector.select(...)
suggested_ids = {s.track_id for s in suggestions}

# PlayerLockManager 产出完整的准入策略
lock_update = self.player_lock_manager.update(
    frame_index=frame_index,
    suggestions=suggestions,
    positions=frame_positions,
    frame=frame,  # 用于提取 appearance 特征（可选）
)

# 传给 identity manager
player_samples = identity_manager.update(
    frame_index=frame_index,
    positions=frame_positions,
    eligible_track_ids=lock_update.eligible_track_ids,
    track_identity_hints=lock_update.track_identity_hints,
)
```

**Why structured over raw set union?**
- `track_identity_hints` 告知 identity manager 某 track 可能是已有的 player_x，用于优先绑定
- `newly_locked` / `newly_lost` 允许上层（pipeline）做日志和进度通知
- 单一 `PlayerLockUpdate` 避免 pipeline 中散落多个 lock manager 查询调用

### Decision 7: track_id 重连

当已锁定球员的 track 被 MultiObjectTracker 释放后，新 track_id 需要回连到原身份：

```
重连评分（reconnect_score）：
  position_score         × 0.40   # 距离上次位置的远近
  motion_prediction      × 0.30   # 速度预测位置匹配度
  side_consistency       × 0.20   # 近端/远端一致性
  bbox_shape_score       × 0.10   # 框宽高比变化
  (appearance_score)     × 0.0    # 首版禁用，后续可选开启
```

外观特征首版设置为可选增强（默认禁用），配置项：

```python
enable_player_lock_appearance_score: bool = False
```

原因：
- 远端球员像素面积小 → HSV 直方图样本量不足，颜色统计不稳定
- 场地光照变化（日晒/阴影/灯光）导致同球员的色调漂移
- 同队球员球衣颜色相同，外观无区分力
- 运动模糊时颜色会混合，统计数据失效

首版仅依赖 position + motion + side + bbox_shape（4 项无外观信息的几何特征）。外观特征在基础锁定跑稳后作为可选增强开启。

**When appearance is enabled**（首版不实现，预留接口）：

```python
appearance_descriptor = [
    mean_hue_upper_body,      # 上半身平均色调
    mean_hue_lower_body,      # 下半身平均色调
]
# bbox_aspect_ratio 和 bbox_height_ratio 已在 bbox_shape_score 中使用
```

### Decision 8: smoother 按 identity_id 平滑

`CourtPositionSmoother` 当前内部 `_states: dict[int, SmoothState]` 以 `track_id` 为键。改为支持双键：

```python
def update(self, track_id, identity_id, x_ft, y_ft, ...):
    key = identity_id if identity_id else f"track_{track_id}"
    state = self._states.get(key)
    # ...
```

这样当 identity locked 时，平滑状态绑定到 identity_id，track_id 切换不影响平滑连续性。

**实施顺序**：此改动放在最后阶段（阶段五），因为需要 identity mapping 稳定后才能接得干净。否则 pipeline 中会面临"这一帧 track_id 到底对应哪个 identity"的时序问题。

### Decision 9: target_player_count 支持单打/双打

配置中加入 `target_player_count`，不硬编码 4：

```python
player_lock_target_player_count: int = 4  # singles=2, doubles=4
```

bootstrap 最多锁定 `target_player_count` 个候选人，为锁定 > target_player_count 做准备（单打场景不需要 4 个 slot）。

### Decision 10: 身份释放策略

| 状态 | 行为 |
|------|------|
| SEARCHING | 空 slot，等待候选填充 |
| TENTATIVE | 候选观察中，不占正式 identity |
| LOCKED | 占有 identity，当前 track 不可见 → LOST |
| LOST | < `lost_max_frames_locked`：只允许 reconnect，不允许其他候选填入此 slot |
| LOST | >= `lost_max_frames_locked`：slot 回退 SEARCHING，但保留 identity_id，新候选满足 lock_min_hits 时填入 |
| INACTIVE | 仅当视频结束或 `target_player_count` 减少时出现，首版不使用 |

---

## Risks / Trade-offs

### Risk 1: LOCKED 状态下低置信度误引入非球员

**场景**：球场上出现裁判、球童、急救人员，其检测框与已锁定球员的预测位置接近。

**Mitigation**：
- 必须通过 position/proximity 检验，不与已锁定球员位置重叠
- 帧间 bbox 面积突变（> 3×）触发诊断事件，不自动接受
- 初始 bootstrap 阶段（SEARCHING → LOCKED）只锁定球场区域内候选

### Risk 2: 球员换位导致 identity 分配错乱

**场景**：双打比赛中近端两名球员交换位置（如 left ↔ right）。

**Mitigation**：
- 位置仅为 reconnect 多项评分中的一项（0.35 权重）
- bbox_shape + appearance 权重合计 0.25，提供位置之外的区分能力
- exchange 场景在 < 5 帧内完成时，运动预测可以桥接

### Risk 3: bootstrap 阶段无法锁定足 4 人

**场景**：视频开头只有 3 人在画面中，第 4 人尚未入场。

**Mitigation**：
- bootstrap 结束后，若只锁定 2-3 人，保留空位继续 SEARCHING
- 当新候选满足 LOCKED 条件（连续 N 帧在球场区域且合理分布）时填入空位
- 不强制 4 人满额

### Risk 4: 远距离捡球时球员走出 tracking_area

**场景**：球飞到球场外很远，球员跑出画面边线。

**Mitigation**：
- LOST 状态缓冲 `lost_max_frames_locked=300`（30fps 下约 10 秒）
- LOST 期间持续预测位置，使用扩展门控恢复
- 超出 `lost_max_frames_locked` 后正确重置为 SEARCHING，不产生僵尸 identity
