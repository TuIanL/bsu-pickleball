# player-lock-state-machine Specification

## Purpose
维护四名主球员的锁定状态机（SEARCHING / TENTATIVE / LOCKED / LOST / INACTIVE），bootstrap 阶段按象限（近左/近右/远左/远右）从画面中央向外扩散锁定候选；锁定后硬锁到底——槽位身份永久保留、不重置、不替换。
## Requirements
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

### Requirement: 重连候选的空间距离门控与横向错配惩罚

系统 SHALL 在 LOCKED/LOST 槽位重连时应用空间距离门控：候选距槽位最后确认位置超过"允许距离"（`max_reconnect_distance_ft` + 估计速度 × 流逝时间）时 SHALL 拒绝重连并保持 LOST；同侧但横向错配的候选 SHALL 受到显著惩罚，不得仅凭运动/外观分数完成重连。

#### Scenario: 超距离候选被拒绝

- **WHEN** LOST 槽位的重连候选距最后确认位置超过允许距离
- **THEN** 该候选 SHALL 被拒绝，槽位 SHALL 保持 LOST
- **AND** 不输出该候选的 `track_identity_hints`

#### Scenario: 距离门按流逝时间缩放

- **WHEN** 槽位自上次确认后流逝时间越长
- **AND** 槽位估计速度非零
- **THEN** 允许距离 SHALL 相应增大（基础距离 + 速度 × 流逝时间）

#### Scenario: 同侧横向错配候选分数不足

- **WHEN** 候选在允许距离内但属于同侧不同横向象限（如近左槽位接近右候选）
- **THEN** 该候选的侧分 SHALL 与错侧同级惩罚，单独不足以达到 `reconnect_threshold`
