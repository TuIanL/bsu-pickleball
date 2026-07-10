# player-lock-state-machine Specification

## Purpose
TBD - created by archiving change add-player-lock-and-court-aware-identity. Update Purpose after archive.
## Requirements
### Requirement: PlayerLockState 枚举

系统 SHALL 为每名主球员维护显式的锁定状态机，包含五个状态：SEARCHING、TENTATIVE、LOCKED、LOST、INACTIVE。

#### Scenario: 新 slot 从 SEARCHING 开始

- **WHEN** 创建新的 `PlayerLockManager`
- **OR** 表示创建新的 player slot
- **THEN** 初始状态 SHALL 为 SEARCHING

#### Scenario: SEARCHING 过渡到 TENTATIVE

- **WHEN** bootstrap 阶段内同一候选连续出现至少 `plausible_min_hits`（默认 3）帧
- **AND** 候选位于 inside_court 或 near_court_area
- **AND** 候选置信度 >= `bootstrap_min_conf`（默认 0.15）
- **THEN** 状态 SHALL 从 SEARCHING 过渡到 TENTATIVE

#### Scenario: TENTATIVE 过渡到 LOCKED

- **WHEN** TENTATIVE 状态下同一候选连续出现至少 `lock_min_hits`（默认 5）帧
- **AND** 候选持续在空间门控范围内
- **AND** 候选置信度均值 >= `tentative_min_mean_conf`（默认 0.12）
- **THEN** 状态 SHALL 从 TENTATIVE 过渡到 LOCKED
- **AND** `locked_since_frame` SHALL 记录锁定时的帧号
- **AND** 诊断事件 SHALL 包含 `event: "player_locked"`

#### Scenario: LOCKED 过渡到 LOST

- **WHEN** LOCKED 状态下当前 track 在 `lost_grace_frames`（默认 3）帧内无可匹配观测
- **AND** 没有重连候选通过 reconnect_score 阈值
- **THEN** 状态 SHALL 从 LOCKED 过渡到 LOST
- **AND** `lost_frames` 计数器 SHALL 开始递增

#### Scenario: LOST 恢复回 LOCKED

- **WHEN** LOST 状态下出现候选
- **AND** reconnect_score >= `reconnect_threshold`（默认 0.45）
- **OR** 候选通过扩展空间门控（`reconnect_court_margin_ft`，默认 20ft）且与上次已知位置距离在 `max_reconnect_distance_ft`（默认 15ft）内
- **THEN** 状态 SHALL 从 LOST 恢复回 LOCKED
- **AND** 诊断事件 SHALL 包含 `event: "player_reconnected_from_lost"`

#### Scenario: LOST 过渡到 SEARCHING（长时间丢失）

- **WHEN** LOST 状态下 `lost_frames` 超过 `lost_max_frames_locked`（默认 300）
- **THEN** 状态 SHALL 从 LOST 过渡到 SEARCHING
- **AND** 所有已缓存的位置/外观/bbox 信息 SHALL 被清除
- **AND** 诊断事件 SHALL 包含 `event: "player_reset_after_prolonged_loss"`

#### Scenario: 手动释放将状态设为 INACTIVE

- **WHEN** 通过 API 或配置主动释放某 player slot
- **THEN** 状态 SHALL 设为 INACTIVE
- **AND** slot 不再参与任何自动匹配

### Requirement: 状态依赖置信度阈值

每个状态 SHALL 使用不同的最低置信度阈值来接纳候选观测。

#### Scenario: SEARCHING 使用严格阈值

- **WHEN** 球员 slot 处于 SEARCHING
- **THEN** 候选 `confidence >= lock_searching_conf（默认 0.20）` SHALL 才被接纳

#### Scenario: LOCKED 使用宽松阈值

- **WHEN** 球员 slot 处于 LOCKED
- **THEN** 候选 `confidence >= lock_locked_conf（默认 0.06）` SHALL 即可被接纳
- **AND** 即使候选置信度低于 `PrimaryPlayerSelector.min_confidence（0.65）`，仍不被丢弃

#### Scenario: 未锁定低置信度候选不被接纳

- **WHEN** 球员 slot 处于 SEARCHING
- **AND** 候选 confidence 为 0.08
- **THEN** 候选 SHALL 被拒绝
- **AND** 拒绝原因 SHALL 记录为 `rejected_low_conf_unlocked`

### Requirement: PlayerSlot 数据结构

每个主球员身份 SHALL 对应一个 `PlayerSlot` 数据类：

```python
@dataclass
class PlayerSlot:
    identity_id: str                       # "player_1" / "player_2" / "player_3" / "player_4"
    state: PlayerLockState                 # SEARCHING / TENTATIVE / LOCKED / LOST / INACTIVE
    current_track_id: int | None           # 当前关联的 MultiObjectTracker track_id
    track_id_history: list[int]            # 历史关联过的所有 track_id

    last_seen_frame: int                   # 最后一次观测到的帧号
    last_confirmed_position_m: list[float] | None  # 米坐标
    last_bbox: list[float] | None          # [x1, y1, x2, y2]
    last_image_footpoint: list[float] | None

    side_hint: str | None                  # "near_left" / "near_right" / "far_left" / "far_right"
    confidence_ema: float                  # 指数平滑置信度
    appearance_descriptor: list[float] | None  # [hue_upper, hue_lower, aspect_ratio, height_ratio]

    lost_frames: int                       # LOST 状态下累计丢失帧数
    locked_since_frame: int | None         # 锁定时的帧号
    observed_frames: int                   # 总观测帧数
```

#### Scenario: identity_id 是稳定的

- **WHEN** Player_3 换了 5 个 track_id
- **THEN** `identity_id` SHALL 始终为 "player_3"
- **AND** `track_id_history` SHALL 包含所有 5 个 track_id

### Requirement: 锁定阈值可配置

所有锁定相关阈值 SHALL 通过配置项暴露。

#### Scenario: 默认值合理

- **WHEN** 使用默认 `PlayerLockConfig`
- **THEN** `bootstrap_min_frames` SHALL 为 60
- **AND** `bootstrap_max_frames` SHALL 为 180
- **AND** `target_player_count` SHALL 为 4
- **AND** `lock_min_hits` SHALL 为 5
- **AND** `plausible_min_hits` SHALL 为 3
- **AND** `lost_max_frames_locked` SHALL 为 300
- **AND** `lock_locked_conf` SHALL 为 0.06
- **AND** `lock_searching_conf` SHALL 为 0.20

#### Scenario: 可通过配置覆盖

- **WHEN** 创建 `PlayerLockConfig(bootstrap_min_frames=30, lock_locked_conf=0.08)`
- **THEN** 自定义值 SHALL 覆盖默认值
- **AND** `PlayerLockManager` SHALL 使用自定义值进行状态过渡

### Requirement: 身份释放与 slot 管理

系统 SHALL 根据 `target_player_count` 管理可用的 player slot 总数，并在球员长时间丢失后正确释放 slot。

#### Scenario: slot 数量由 target_player_count 决定

- **WHEN** `target_player_count = 2`（单打）
- **THEN** 系统 SHALL 最多管理 `player_1` 和 `player_2` 两个 slot
- **AND** SHALL NOT 尝试填充 `player_3` 或 `player_4`

#### Scenario: LOST 状态下只允许 reconnect 不允许占坑

- **WHEN** slot `player_3` 状态为 LOST
- **AND** `lost_frames < lost_max_frames_locked`
- **THEN** 只允许通过 reconnect_score 将新 track 回连到 `player_3`
- **AND** 其他候选即使满足 LOCKED 条件，也不能填入 `player_3` 的 slot

#### Scenario: LOST 超时后 slot 回退 SEARCHING

- **WHEN** slot `player_3` 状态为 LOST
- **AND** `lost_frames >= lost_max_frames_locked`
- **THEN** 状态 SHALL 回退为 SEARCHING
- **AND** identity_id SHALL 保留（不释放 "player_3"）
- **AND** 新候选满足 lock_min_hits 后可填入此 slot

#### Scenario: side_hint 不是永久身份定义

- **WHEN** `player_3` 在 bootstrap 时被标记为 `side_hint="far_left"`
- **AND** 后续球员换位到 `near_right` 区域
- **THEN** `identity_id` SHALL 仍为 "player_3"
- **AND** `side_hint` SHALL 允许更新为 "near_right"
- **AND** side_hint SHALL 仅用于初始分配和 reconnect 辅助匹配
