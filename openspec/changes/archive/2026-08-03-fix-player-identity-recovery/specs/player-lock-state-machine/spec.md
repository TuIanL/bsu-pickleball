## MODIFIED Requirements

### Requirement: PlayerLockState 枚举

系统 SHALL 为每名主球员维护显式的锁定状态机，包含五个状态：SEARCHING、TENTATIVE、LOCKED、LOST、INACTIVE。锁定层 SHALL 在同一帧内对 slot 与 track 执行一对一分配。

#### Scenario: 新 slot 从 SEARCHING 开始

- **WHEN** 创建新的 `PlayerLockManager`
- **OR** 表示创建新的 player slot
- **THEN** 初始状态 SHALL 为 SEARCHING

#### Scenario: SEARCHING 过渡到 TENTATIVE

- **WHEN** bootstrap 阶段内同一候选连续出现至少 `plausible_min_hits` 帧
- **AND** 候选位于 inside_court 或 near_court_area
- **AND** 候选置信度达到 searching 门控
- **THEN** 状态 SHALL 从 SEARCHING 过渡到 TENTATIVE

#### Scenario: TENTATIVE 过渡到 LOCKED

- **WHEN** TENTATIVE 状态下同一候选连续出现至少 `lock_min_hits` 帧
- **AND** 候选持续在空间门控范围内
- **THEN** 状态 SHALL 从 TENTATIVE 过渡到 LOCKED
- **AND** `locked_since_frame` SHALL 记录锁定时的帧号
- **AND** 诊断事件 SHALL 包含 `event: "player_locked"`

#### Scenario: LOCKED 在短暂换 track 时优先同槽位恢复

- **WHEN** LOCKED 状态下当前 track 暂时没有可匹配观测
- **AND** 当前帧存在未被其他锁定槽位消费的合格新 track
- **AND** 新 track 的 reconnect score 达到阈值
- **THEN** 该新 track SHALL 绑定回原 LOCKED slot
- **AND** SHALL 输出该 slot 的 `track_identity_hints`
- **AND** SHALL NOT 将该 track 分配给其他 slot

#### Scenario: LOCKED 过渡到 LOST

- **WHEN** LOCKED 状态下当前 track 在 `lost_grace_frames` 帧内无可匹配观测
- **AND** 没有通过一对一恢复分配的候选
- **THEN** 状态 SHALL 从 LOCKED 过渡到 LOST
- **AND** `lost_frames` 计数器 SHALL 开始递增

#### Scenario: LOST 恢复回 LOCKED

- **WHEN** LOST 状态下出现候选
- **AND** reconnect_score 达到 `reconnect_threshold`
- **AND** 该候选尚未被其他 slot 预留
- **THEN** 状态 SHALL 从 LOST 恢复回 LOCKED
- **AND** 当前 track SHALL 绑定回原 identity
- **AND** 诊断事件 SHALL 包含 `event: "player_reconnected_from_lost"`

#### Scenario: LOST 是持久状态，长时间丢失不重置

- **WHEN** LOST 状态下 `lost_frames` 超过 `lost_max_frames_locked`
- **THEN** 状态 SHALL 保持 LOST，SHALL NOT 过渡到 SEARCHING
- **AND** 槽位身份与锁定关系 SHALL 永久保留
- **AND** SHALL NOT 允许其他候选填入该 slot
- **AND** SHALL NOT 产生 `event: "player_reset_after_prolonged_loss"`

#### Scenario: 手动释放将状态设为 INACTIVE

- **WHEN** 通过 API 或配置主动释放某 player slot
- **THEN** 状态 SHALL 设为 INACTIVE
- **AND** slot 不再参与任何自动匹配

### Requirement: PlayerSlot 数据结构

每个主球员身份 SHALL 对应一个 `PlayerSlot` 数据类，并保留当前 track、历史 track、最近位置、当前 side 及 bootstrap home quadrant 等恢复信息：

```python
@dataclass
class PlayerSlot:
    identity_id: str
    state: PlayerLockState
    current_track_id: int | None
    track_id_history: list[int]
    last_seen_frame: int
    last_confirmed_position_m: list[float] | None
    last_bbox: list[float] | None
    last_image_footpoint: list[float] | None
    side_hint: str | None
    assignment_side: str | None
    home_quadrant: str | None
    confidence_ema: float
    appearance_descriptor: list[float] | None
    lost_frames: int
    locked_since_frame: int | None
    observed_frames: int
```

#### Scenario: identity_id 是稳定的

- **WHEN** Player_3 换了 5 个 track_id
- **THEN** `identity_id` SHALL 始终为 `Player_3`
- **AND** `track_id_history` SHALL 包含所有 5 个 track_id

#### Scenario: bootstrap 写入槽位位置元数据

- **WHEN** 一个候选在 bootstrap 被分配到 `near_left`
- **THEN** 对应 slot 的 `home_quadrant` SHALL 为 `near_left`
- **AND** `side_hint` SHALL 至少包含 `near` 侧信息
- **AND** `identity_id` SHALL 不因后续换边或换 track 而改变

#### Scenario: identity_id 命名与身份层一致

- **WHEN** 创建 `PlayerLockManager`
- **THEN** 槽位 `identity_id` SHALL 使用 `Player_1`..`Player_4`
- **AND** SHALL 与 `PlayerIdentityManager` 的 player_id 键格式一致

### Requirement: 身份释放与 slot 管理

系统 SHALL 根据 `target_player_count` 管理 player slot 总数，并在球员丢失后保留 slot 身份；已锁定 slot 只能通过同槽位 reconnect 恢复，不能被其他候选占坑。

#### Scenario: LOST 状态下只允许同槽位 reconnect

- **WHEN** slot `Player_3` 状态为 LOST
- **THEN** 只有通过 reconnect score 且未被其他 slot 预留的 track 才可回连到 `Player_3`
- **AND** 其他候选即使满足 LOCKED 条件，也不能填入 `Player_3`

#### Scenario: 同一候选不能被多个 LOST 槽位认领

- **WHEN** `Player_1` 和 `Player_2` 同时处于 LOST
- **AND** 当前帧只有一个候选 track 满足两个 slot 的重连阈值
- **THEN** 该 track SHALL 最多分配给其中一个 slot
- **AND** 另一个 slot SHALL 保持 LOST
- **AND** `track_identity_hints` SHALL 不得同时包含两个不同 player_id 对应同一 track_id

#### Scenario: LOST 超时后槽位保持身份

- **WHEN** slot `Player_3` 长时间处于 LOST
- **THEN** `identity_id` SHALL 保留
- **AND** 其他候选 SHALL NOT 被允许填入此 slot
- **AND** 仅当同槽位重连评分达标时，新 track 才可绑回该 slot

### Requirement: 槽位位置语义

双打模式下，槽位 SHALL 按球场象限固定编号：`Player_1`=近左、`Player_2`=近右、`Player_3`=远左、`Player_4`=远右；单打模式下 `Player_1`=近、`Player_2`=远。该位置语义用于 bootstrap 初始分配和 reconnect 辅助，不得重新定义 canonical identity。

#### Scenario: bootstrap home quadrant 参与重连辅助

- **WHEN** `Player_1` 在 bootstrap 被分配到近左象限
- **AND** 后续出现两个位置分数相近的 reconnect 候选
- **THEN** 近左/near 相关元数据 SHALL 作为辅助排序信号
- **AND** 不得因为球员后续移动到另一侧而把身份重新编号

#### Scenario: 单打槽位对应近远

- **WHEN** `target_player_count = 2`
- **THEN** `Player_1` SHALL 关联近侧、`Player_2` SHALL 关联远侧

## ADDED Requirements

### Requirement: 同帧 slot-track 一对一约束

`PlayerLockManager.update()` SHALL 对当前帧的 slot 与 track 执行一对一恢复分配。

#### Scenario: 一个 track 只能有一个 canonical hint

- **WHEN** 一帧中多个 LOST 槽位都将同一个 track 作为候选
- **THEN** 只有一个 slot SHALL 获得该 track
- **AND** 该 track 在 `track_identity_hints` 中 SHALL 最多出现一次

#### Scenario: 多个候选分别回连

- **WHEN** 两个 LOST 槽位各有一个不同且通过阈值的候选
- **THEN** 两个候选 SHALL 分别绑定到不同 slot
- **AND** `eligible_track_ids` SHALL 包含两个候选
