## MODIFIED Requirements

### Requirement: team 语义与槽位语义单一事实源

系统中所有按球员分侧的展示（`playerMarkers.team`、minimap、结构化可视化）SHALL 从同一份已确认的冻结名册读取 `Player_N → Team A/B → initial_team_a_end`，并结合 canonical 球场端位及当前视角朝向计算展示侧。双打 P1/P2 SHALL 属于用户确认的 Team A，P3/P4 SHALL 属于 Team B；Team A 可以在 `end_a` 或 `end_b`，不得把 P 编号固定等同于某摄像头的 near/far。前端 adapter 与后端 SHALL 使用同一语义。旧 Job 缺冻结名册时 SHALL 保留历史槽位映射并标注其来源，不得伪称为用户确认。

#### Scenario: 双打确认 A 队位于画面远端

- **WHEN** 用户确认 P1/P2 为 Team A、`initial_team_a_end=end_a`，且当前摄像头的 end_a 在画面远端
- **THEN** P1/P2 SHALL 显示在 Team A 对应的远端，P3/P4 SHALL 显示在 Team B 对应的近端
- **AND** `playerMarkers.team`、minimap 和结构化可视化 SHALL 一致

#### Scenario: 初始端位相反

- **WHEN** 用户确认 `initial_team_a_end=end_b`
- **THEN** P1/P2 SHALL 映射到 end_b，P3/P4 SHALL 映射到 end_a
- **AND** 切换展示机位 SHALL 只改变画面投影，不改变 canonical Team/端位归属

#### Scenario: 单打确认名册

- **WHEN** 单打 Job 冻结了 P1/P2 与各自 Team/端位
- **THEN** 展示 SHALL 依据冻结端位与当前视角计算侧别
- **AND** SHALL 不依赖输入 tracks 的遍历顺序

#### Scenario: 历史任务缺名册

- **WHEN** 旧任务没有冻结的 Team/端位信息
- **THEN** 系统 SHALL 保持旧 `Player_N` 槽位显示兼容
- **AND** SHALL 标明该侧别是历史 fallback，而非用户确认

## ADDED Requirements

### Requirement: 局部身份缺失不得丢弃场内正式观测

joint run SHALL 将有效的场内正式检测交给全局关联，即使该检测暂时没有本地 `Player_N` 身份。没有本地身份的观测 SHALL 使用原始 source track key 保持自身关联，不得借用过期的局部 P 标签。软接管产生的 tentative P 身份 MUST NOT 成为正式观测身份或用户可见标签。

#### Scenario: 正式检测没有本地 P 身份

- **WHEN** 一个正式人体检测有有效的场内位置，但身份管理器没有确认本地 `Player_N`
- **THEN** joint run SHALL 将该匿名观测提交给全局关联
- **AND** 它 SHALL 保留 source track 与未分配原因
- **AND** 它 SHALL NOT 继承其他局部轨迹的 P 身份

#### Scenario: 软接管产生暂定 P 猜测

- **WHEN** 身份管理器为新 raw track 产生 tentative soft-takeover P 候选
- **THEN** joint run SHALL 将该观测标为 tentative 并使用原始 source track key
- **AND** 视频检测框 SHALL NOT 显示该猜测的 P 标签

### Requirement: 双打 Global Roster 保留两端各两人的候选空间

正式双打 joint run SHALL 在 canonical end_a/end_b 各维护两个候选容量。只有端位可判且不与现有独立球员重复的候选才能占用相应容量；端位不明的候选 SHALL 留待裁决。未确认且长期无有效观测的 provisional 占位在同端出现通过唯一性与持续性门槛的真实候选时 SHALL 受控替换并记录证据，已确认身份 MUST NOT 因短时漏检而被替换。满槽时真实观测仍 SHALL 进入可追踪的恢复漏斗，不得静默丢弃。

#### Scenario: 同端四个早期候选

- **WHEN** 开场同一 canonical 端位出现四条可晋升候选轨迹，而另一端尚无可靠候选
- **THEN** 同端最多两个独立候选 SHALL 占用 roster
- **AND** 另一端两个容量 SHALL 保留给该端后续有效球员

#### Scenario: 错误 provisional 占位阻塞真人

- **WHEN** 四个槽位已占用但一个 provisional 长期无观测、同端新候选具有更强持续及锚点证据
- **THEN** 系统 SHALL 在唯一性检查后允许受控替换并记录旧/新候选及原因
- **AND** 同一 tick 不得使一个 source track 对应两个 P 槽位

#### Scenario: 已确认球员暂时漏检

- **WHEN** 已确认球员发生短时检测缺口
- **THEN** 其槽位 SHALL 保留，不得仅按候选出现顺序被其他人抢占

### Requirement: 端位是可修订的观测结论

global 身份的 canonical 端位 SHALL 由持续观测证据决定，并 SHALL 允许在证据充分时被修订。系统 MUST NOT 把锚点时刻之前的端位估计当作不可变约束，从而永久否决后验的多数证据。

端位与冻结锚点期望端位冲突时，系统 SHALL 触发重新裁决而非直接拒绝绑定。重新裁决 SHALL 结合锚点证据强度与该身份后续连续观测的端位一致性决定最终端位与归属，并 SHALL 逐人留痕：`roster_end` 的变更原因、依据样本数与前后取值。

修订 SHALL NOT 降低身份唯一性门槛：修订后同一 tick 仍不得出现同端重复绑定或一个 source track 对应两个 P 槽位。仅为了让锚点匹配通过而改写端位属于禁止行为。

#### Scenario: 端位估计与锚点期望冲突

- **WHEN** 某 global 身份在锚点时刻的 `roster_end` 与该槽位冻结端位不一致，但该身份后续连续观测中多数样本落在冻结端位
- **THEN** 系统 SHALL 触发端位重新裁决，MUST NOT 直接返回端位冲突并永久拒绝
- **AND** 裁决完成后该身份 SHALL 归属到证据支持的端位
- **AND** SHALL 记录变更原因、依据样本数与前后端位取值

#### Scenario: 端位不明观测不消耗配额

- **WHEN** 某身份的位置观测无法判定 canonical 端位
- **THEN** 该观测 SHALL 留在待裁决池，MUST NOT 计入任一端的候选容量
- **AND** 端位不可用 MUST NOT 成为永久拒绝锚点绑定的理由

#### Scenario: 同一 global 身份横跨两端

- **WHEN** 某 global 身份的 metric-eligible 样本同时出现在两个 canonical 端位
- **THEN** 系统 SHALL 保留全部证据并标记该身份疑似合并了多个真实球员
- **AND** 端位裁决 SHALL NOT 仅取锚点前的少数样本而丢弃后验多数证据
- **AND** SHALL 记录横跨比例供拆分判定使用
