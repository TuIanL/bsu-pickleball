# player-lock-state-machine Delta Spec

## MODIFIED Requirements

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

#### Scenario: LOST 是持久状态，长时间丢失不重置

- **WHEN** LOST 状态下 `lost_frames` 超过 `lost_max_frames_locked`（默认 300）
- **THEN** 状态 SHALL **保持 LOST**，SHALL NOT 过渡到 SEARCHING
- **AND** 槽位身份（`identity_id`）与锁定关系 SHALL 永久保留
- **AND** SHALL NOT 允许其他候选填入该 slot
- **AND** SHALL NOT 产生 `event: "player_reset_after_prolonged_loss"`

#### Scenario: 手动释放将状态设为 INACTIVE

- **WHEN** 通过 API 或配置主动释放某 player slot
- **THEN** 状态 SHALL 设为 INACTIVE
- **AND** slot 不再参与任何自动匹配

### Requirement: 身份释放与 slot 管理

系统 SHALL 根据 `target_player_count` 管理可用的 player slot 总数，并在球员长时间丢失后保留 slot 身份（硬锁到底），不得把已锁定 slot 释放给其他候选。

#### Scenario: slot 数量由 target_player_count 决定

- **WHEN** `target_player_count = 2`（单打）
- **THEN** 系统 SHALL 最多管理 `Player_1` 和 `Player_2` 两个 slot
- **AND** SHALL NOT 尝试填充 `Player_3` 或 `Player_4`

#### Scenario: LOST 状态下只允许 reconnect 不允许占坑

- **WHEN** slot `Player_3` 状态为 LOST
- **THEN** 只允许通过 reconnect_score 将新 track 回连到 `Player_3`
- **AND** 其他候选即使满足 LOCKED 条件，也不能填入 `Player_3` 的 slot

#### Scenario: LOST 超时后槽位保持身份（硬锁到底）

- **WHEN** slot `Player_3` 状态为 LOST
- **AND** `lost_frames >= lost_max_frames_locked`
- **THEN** 状态 SHALL 保持 LOST（不再回退 SEARCHING）
- **AND** `identity_id` SHALL 保留
- **AND** 其他候选 SHALL NOT 被允许填入此 slot
- **AND** 仅当重连评分达标时，新 track 才可绑回该 slot

#### Scenario: side_hint 不是永久身份定义

- **WHEN** `Player_3` 在 bootstrap 时被标记为 `side_hint="far_left"`
- **AND** 后续球员换位到 `near_right` 区域
- **THEN** `identity_id` SHALL 仍为 "Player_3"
- **AND** `side_hint` SHALL 允许更新为 "near_right"
- **AND** side_hint SHALL 仅用于初始分配和 reconnect 辅助匹配

### Requirement: PlayerSlot 数据结构

每个主球员身份 SHALL 对应一个 `PlayerSlot` 数据类：

```python
@dataclass
class PlayerSlot:
    identity_id: str                       # "Player_1" / "Player_2" / "Player_3" / "Player_4"
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
- **THEN** `identity_id` SHALL 始终为 "Player_3"
- **AND** `track_id_history` SHALL 包含所有 5 个 track_id

#### Scenario: identity_id 命名与身份层一致

- **WHEN** 创建 `PlayerLockManager`
- **THEN** 槽位 `identity_id` SHALL 使用大写驼峰命名 `"Player_1"`..`"Player_4"`
- **AND** SHALL 与 `PlayerIdentityManager` 的 player_id 键格式一致，使 `track_identity_hints` 可被身份层直接消费

### Requirement: 锁定阈值可配置

所有锁定相关阈值 SHALL 通过配置项暴露。

#### Scenario: 默认值合理

- **WHEN** 使用默认 `PlayerLockConfig`
- **THEN** `bootstrap_min_frames` SHALL 为 60
- **AND** `bootstrap_max_frames` SHALL 为 180
- **AND** `target_player_count` SHALL 为 4
- **AND** `lock_min_hits` SHALL 为 5
- **AND** `plausible_min_hits` SHALL 为 3
- **AND** `lock_locked_conf` SHALL 为 0.06
- **AND** `lock_searching_conf` SHALL 为 0.20

#### Scenario: 可通过配置覆盖

- **WHEN** 创建 `PlayerLockConfig(bootstrap_min_frames=30, lock_locked_conf=0.08)`
- **THEN** 自定义值 SHALL 覆盖默认值
- **AND** `PlayerLockManager` SHALL 使用自定义值进行状态过渡

#### Scenario: lost_max_frames_locked 已弃用

- **WHEN** 配置 `lost_max_frames_locked`
- **THEN** 该配置 SHALL 不再触发状态回退（硬锁到底语义下无意义）
- **AND** 该配置 SHALL 保留字段兼容性但标记为 deprecated

## ADDED Requirements

### Requirement: 槽位位置语义

双打模式下，槽位 SHALL 按球场象限固定编号：`Player_1`=近左、`Player_2`=近右、`Player_3`=远左、`Player_4`=远右；单打模式下 `Player_1`=近、`Player_2`=远。

#### Scenario: 双打槽位对应四个象限

- **WHEN** `target_player_count = 4`
- **THEN** `Player_1` SHALL 关联近左象限、`Player_2` 近右、`Player_3` 远左、`Player_4` 远右
- **AND** 每个象限至多锁定一个槽位

#### Scenario: 单打槽位对应近远

- **WHEN** `target_player_count = 2`
- **THEN** `Player_1` SHALL 关联近侧、`Player_2` SHALL 关联远侧

### Requirement: Bootstrap 中心优先锁定

Bootstrap 阶段锁定候选 SHALL 从画面中央向外扩散，且每个球场象限只锁定一个槽位。

#### Scenario: 象限内按中心距离排序

- **WHEN** bootstrap 阶段某象限内存在多个候选
- **THEN** 该象限槽位 SHALL 优先锁定"bbox 中心距画面中心最近"的候选
- **AND** 置信度与出现帧数 SHALL 作为次级排序依据

#### Scenario: 每个象限只取一个

- **WHEN** bootstrap 阶段 `Player_1`（近左）已锁定某候选
- **THEN** 近左象限的其他候选 SHALL 不再分配到 `Player_1`
- **AND** 不满足象限归属的候选 SHALL NOT 被分配到该象限槽位

#### Scenario: 脚点门控优先于中心距离

- **WHEN** 某候选球场脚点落在对应象限之外（如站在画面中央的裁判）
- **THEN** 该候选 SHALL 被脚点门控过滤，不因"距画面中心近"而被锁定

### Requirement: 锁定槽位不可替换

一旦槽位达到 LOCKED 状态，系统 SHALL 禁止任何形式的替换，包括降级候选替换。

#### Scenario: 降级候选不能替换已锁定槽位

- **WHEN** `Player_1` 已 LOCKED 于 track A
- **AND** 出现置信度更高的 track B
- **THEN** `Player_1` SHALL 仍保持 track A 的绑定
- **AND** SHALL NOT 产生 `event: "side_quota_fallback_replaced"`

#### Scenario: 未锁定槽位可被更优候选填充

- **WHEN** 槽位仍处于 searching/tentative/fallback_tentative（未达到 LOCKED）
- **THEN** 更高置信度的候选 SHALL 可以填充该槽位
- **AND** 一旦达到 `lock_min_hits` 达成 LOCKED，替换路径 SHALL 关闭
