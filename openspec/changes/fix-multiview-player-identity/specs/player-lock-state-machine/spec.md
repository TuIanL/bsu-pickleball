# player-lock-state-machine Delta

## ADDED Requirements

### Requirement: bootstrap 阶段接纳近端大尺寸高清晰候选

bootstrap 阶段候选过滤 SHALL 将"画面近端、bbox 大、清晰度高"的球员视为高优先级候选，即使其图像中心距离画面中心较远（近端球员在 baseline 视角下天然偏离画面中心）。过滤规则（`is_inside_tracking_area`、中心距离排序、置信度门控）SHALL 对近端大尺寸候选使用更宽松的有效性判定，MUST NOT 因"距画面中心远"或"脚点略超出 tracking area"而过滤掉近端明显球员。

#### Scenario: 近端右路球员在 bootstrap 被接纳

- **WHEN** 双打 baseline 视角下，近端右路球员 bbox 面积大（如 > 画面面积 5%）、清晰（conf >= searching 门控），但 bbox 中心距画面中心较远
- **THEN** bootstrap SHALL 将其作为 `near_right` 象限候选接纳
- **AND** SHALL 锁定到 `Player_2` 槽位（双打槽位语义）
- **AND** SHALL NOT 因中心距离排序靠后而把该象限让给远端候选

#### Scenario: 远端候选不因近端放宽而误占近端槽位

- **WHEN** 近端右路球员在 bootstrap 窗口内可被检测到
- **AND** 同时存在一个远端（画面顶部、小 bbox）候选
- **THEN** 近端右路候选 SHALL 优先匹配 `near_right` 槽位
- **AND** 远端候选 SHALL NOT 占用 `Player_2`（近右）槽位

### Requirement: reconnect 阶段同侧优先与横向错配惩罚

`PlayerLockManager` 的 LOST/LOCKED reconnect 阶段 SHALL 对候选施加"同侧优先 + 横向错配惩罚"：候选的 `home_quadrant` / `side_hint` 与槽位不符时，其重连得分 SHALL 被显著惩罚；跨侧（near↔far）候选 SHALL 需要远高于同侧候选的证据才能重连，防止 P1↔P2 这类身份互换。

#### Scenario: 同侧横向错配候选得分不足

- **WHEN** 槽位 `Player_1`（home=near_left）处于 LOST，候选属于 near_right 象限
- **THEN** 该候选的重连得分 SHALL 受横向错配惩罚，单独不足以达到 `reconnect_threshold`
- **AND** 槽位 SHALL 保持 LOST 或等待真正同侧候选

#### Scenario: 跨侧候选被拒绝

- **WHEN** 槽位 `Player_1`（home=near_left）处于 LOST，唯一候选属于 far 侧
- **THEN** 该候选 SHALL 被拒绝（跨侧），槽位 SHALL 保持 LOST
- **AND** SHALL NOT 产生 `event: "player_reconnected_from_lost"` 到该跨侧 track

### Requirement: 身份互换诊断事件

当发生潜在的身份互换（槽位 track 变化跨越 home quadrant / side）时，系统 SHALL 输出诊断事件（如 `event: "identity_swap_suspected"` + `from_track`/`to_track`/`home_quadrant`/`side`），供 `player-identity-recovery-validation` 与观测页面归因，MUST NOT 静默吞掉。

#### Scenario: 跨侧 reconnection 触发诊断事件

- **WHEN** 一个 LOST 槽位以跨侧候选完成重连（或强证据下被接受）
- **THEN** 系统 SHALL 记录 `event: "identity_swap_suspected"` 及双方 track/quadrant 信息
- **AND** 该事件 SHALL 可被观测页面或日志检索

#### Scenario: 正常同侧重连不产生告警事件

- **WHEN** 一个 LOST 槽位以同侧候选完成重连
- **THEN** 系统 SHALL 仅记录 `event: "player_reconnected_from_lost"`
- **AND** SHALL NOT 记录 `identity_swap_suspected`
