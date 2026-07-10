## MODIFIED Requirements

### Requirement: PrimaryPlayerSelector 降级为建议器

`PrimaryPlayerSelector.select()` SHALL 保持不变，继续作为候选排序器运行，但下游 SHALL 不再将其输出作为硬门控。调用方 SHALL 将其输出视为建议集合而非授权集合。

#### Scenario: select() 仍然返回 top 4 建议

- **WHEN** `PrimaryPlayerSelector.select()` 被调用
- **THEN** 返回结果 SHALL 为 `list[PrimaryPlayerSelection]`，长度为 0 到 4
- **AND** 结果按 `(score, rolling_confidence, confidence)` 降序排列

#### Scenario: select() 不负责身份持久性

- **WHEN** 已锁定球员 `Player_3` 的当前 track 本帧未进入 top 4
- **THEN** `select()` SHALL 不将 `Player_3` 的 track 包含在结果中
- **AND** 这 SHALL 不导致 `Player_3` 身份被释放（由 `PlayerLockManager` 负责）

### Requirement: PlayerLockUpdate 驱动的 eligible_track_ids

`_run_tracking()` 构建 `eligible_track_ids` 时 SHALL 消费 `PlayerLockManager.update()` 返回的 `PlayerLockUpdate` 结构，而非仅使用 `PrimaryPlayerSelector` 的 top 4 结果。`PlayerLockUpdate` 提供 `eligible_track_ids` 并集以及 `track_identity_hints` 映射。

#### Scenario: PlayerLockUpdate 包含建议 + 锁定 + 重连候选

- **WHEN** `PrimaryPlayerSelector` 建议 track_ids = {3, 7, 12, 15}
- **AND** `PlayerLockManager` 已锁定 slot 包含 track_ids = {3, 4, 8}（4 为 LOST 恢复窗口中的 track）
- **THEN** `PlayerLockUpdate.eligible_track_ids` SHALL = {3, 4, 7, 8, 12, 15}

#### Scenario: track_identity_hints 告知身份管理器绑定关系

- **WHEN** `PlayerLockManager` 确定 track_id=4 是 player_3 的 LOST 恢复候选
- **THEN** `PlayerLockUpdate.track_identity_hints` SHALL 包含 `{4: "player_3"}`
- **AND** `PlayerIdentityManager` 在 `_assign_player()` 中 SHALL 优先尝试绑定到 player_3

#### Scenario: 已锁定 track 即使未进 top 4 也被保留

- **WHEN** 远端球员 track_id=5 是已锁定的 `Player_4`，但本帧置信度低未进入 select() top 4
- **AND** `PlayerLockManager` 的 LOCKED slot 中 `current_track_id=5`
- **THEN** track_id=5 SHALL 仍在 `PlayerLockUpdate.eligible_track_ids` 中
- **AND** `PlayerIdentityManager` SHALL 接收到该 track 的观测

#### Scenario: 无锁定球员时不引入额外候选

- **WHEN** `PlayerLockManager` 无任何 LOCKED/LOST slot（如 bootstrap 尚未完成）
- **AND** `PrimaryPlayerSelector` 建议 track_ids = {1, 2, 3}
- **THEN** `PlayerLockUpdate.eligible_track_ids` SHALL = {1, 2, 3}

---

## ADDED Requirements

### Requirement: 空间门控三层区域

系统 SHALL 基于已有 `PickleballCourtGeometry.court_bounds` 和 `PickleballCourtGeometry.tracking_bounds`，叠加自定义外扩，构建三层空间门控。

```python
# 所有值单位为英尺
inside_court:
  x: [0, 20], y: [0, 44]           # court_bounds（已有）

near_court_area（新增）：
  x: [-court_margin_x, 20+court_margin_x]
  y: [-court_margin_y, 44+court_margin_y]
  默认 court_margin_x=12, court_margin_y=12

tracking_area：
  x: [-4, 24], y: [-8, 52]         # tracking_bounds（已有）
```

#### Scenario: 新候选只能在 near_court_area 内初始化

- **WHEN** 候选投影坐标在 near_court_area 之外（即 court_margin_ft 外）
- **AND** 候选尚未被任何 player slot 锁定
- **THEN** 候选 SHALL NOT 被用于初始化新的 player slot
- **AND** 拒绝原因 SHALL 记录为 `rejected_outside_near_court_area`

#### Scenario: 已锁定球员的候选使用 tracking_area

- **WHEN** 候选已被某 LOCKED slot 关联
- **AND** 候选投影坐标在 tracking_area 内
- **THEN** 候选 SHALL 被接纳
- **AND** 即使候选在 near_court_area 外但 tracking_area 内，仍被接纳

#### Scenario: tracking_area 外的所有候选被拒绝

- **WHEN** 候选投影坐标在 tracking_area 外
- **THEN** 候选 SHALL 被拒绝
- **AND** 拒绝原因 SHALL 记录为 `rejected_outside_tracking_area`

### Requirement: Bootstrap 阶段（动态窗口）

bootstrap 使用动态窗口：有最短帧数和最长帧数，任意候选满足条件即提前锁定，不必等窗口完全结束。

#### Scenario: bootstrap 阶段收集候选（最短窗口内）

- **WHEN** `frame_index < bootstrap_min_frames`（默认 60）
- **THEN** 系统 SHALL 收集所有在 near_court_area 内的 tracklet 统计信息
- **AND** SHALL NOT 立即分配 player_1~player_4

#### Scenario: 候选满足条件即提前锁定，不等窗口结束

- **WHEN** `frame_index >= bootstrap_min_frames` 且未达 `bootstrap_max_frames`
- **AND** 某候选连续 `lock_min_hits` 帧在 near_court_area 内且置信度 ≥ `bootstrap_min_conf`
- **THEN** 该候选 SHALL 立即锁定（transition to LOCKED）
- **AND** 未锁定 slot SHALL 继续 SEARCHING 直到 `bootstrap_max_frames`

#### Scenario: bootstrap 最大窗口后强制选出主球员

- **WHEN** `frame_index == bootstrap_max_frames`（默认 180）
- **THEN** 系统 SHALL 从所有收集的候选 tracklet 中选出最多 `target_player_count` 个
- **AND** 未满额空 slot SHALL 保持 SEARCHING
- **AND** 后续帧中出现新候选时 SHALL 尝试填入空位

#### Scenario: bootstrap 不足 target_player_count 人

- **WHEN** bootstrap 结束后收集到 2 个符合资格的候选（target=4）
- **THEN** 系统 SHALL 将 2 个候选分配为 Player_1、Player_2 并设为 LOCKED
- **AND** Player_3、Player_4 SHALL 保持 SEARCHING
- **AND** 后续帧中出现新候选时 SHALL 尝试填入空位

#### Scenario: bootstrap 期间 candidate 必须靠近球场

- **WHEN** bootstrap 期间候选投影坐标不在 near_court_area 内
- **THEN** 候选 SHALL NOT 被纳入 bootstrap 统计

#### Scenario: side_hint 仅作提示不绑死身份

- **WHEN** bootstrap 结束分配 identity_id
- **THEN** `side_hint` SHALL 基于预期球场位置设置（near_left / near_right / far_left / far_right）
- **AND** 后续球员换位/走位时 `identity_id` SHALL 保持不变，`side_hint` SHALL 允许更新

### Requirement: track 重连评分

当已锁定球员的 track 断开后出现新 track，系统 SHALL 计算 reconnect_score 判断是否回连。首版 SHALL NOT 依赖外观特征。

#### Scenario: 位置匹配贡献最高权重

- **WHEN** 新候选的球场坐标距 Player_x 上次已知位置距离为 d
- **THEN** position_score SHALL = max(0, 1 - d / max_reconnect_distance_ft)
- **AND** position_score 在综合分中 SHALL 权重为 0.40

#### Scenario: 运动预测权重

- **WHEN** Player_x 有最近速度估计
- **THEN** motion_prediction_score SHALL 基于预测位置与实际候选位置的匹配度计算
- **AND** motion_prediction_score SHALL 权重为 0.30

#### Scenario: 外观特征首版禁用

- **WHEN** `player_lock_enable_appearance_score = False`（默认）
- **THEN** 重连评分 SHALL 仅包含 position（0.40）+ motion（0.30）+ side（0.20）+ bbox_shape（0.10）
- **AND** appearance_score 权重 SHALL 为 0.0

#### Scenario: 总重连分达到阈值时回连

- **WHEN** reconnect_score >= reconnect_threshold（默认 0.45）
- **THEN** 系统 SHALL 将新 track 绑定到已有的 player identity
- **AND** 状态 SHALL 从 LOST 恢复为 LOCKED
- **AND** 诊断事件 SHALL 包含 `event: "player_reconnected_from_lost"` 及各分项 score

### Requirement: 诊断事件扩展

`PlayerIdentityDiagnostic` 的 `event` 字段 SHALL 扩展以支持锁定相关事件。

#### Scenario: 新事件类型

- **WHEN** `PlayerLockManager` 产生状态相关事件
- **THEN** `event` 有效值 SHALL 包含：
  - `"player_locked"` — 球员首次锁定
  - `"player_reconnected_from_lost"` — 从 LOST 恢复
  - `"player_reset_after_prolonged_loss"` — 长时间丢失后重置
  - `"player_slot_filled"` — 空位被填充
  - `"rejected_low_conf_unlocked"` — 未锁定低置信度拒绝
  - `"rejected_outside_near_court"` — 超出近场区域拒绝
  - `"rejected_outside_tracking"` — 超出跟踪区域拒绝
  - `"rejected_bbox_size"` — bbox 尺寸不合规
  - `"retained_by_lock"` — 因锁定状态而保留

#### Scenario: reason 字段包含子项分

- **WHEN** 产生 `"player_reconnected_from_lost"` 事件
- **THEN** `reason` 字段 SHALL 包含各分项分数，格式如 `"position=0.82 motion=0.65 appearance=0.43 side=0.90 bbox=0.70"`
