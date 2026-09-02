## MODIFIED Requirements

### Requirement: 四人识别硬不变量

双打正式结果 SHALL 满足同 tick track↔local slot↔global↔canonical 双射，并在连续有效窗口内保持 local slot lineage 的可解释连续性；duplicate binding、一个 source track 同时对应多个 P 槽位、一个 P 槽位同时对应多个 active track、未经受控 reassociation 的 local slot↔global 换绑、正式 cross-side contamination 均 SHALL 为零。无法裁决的样本 SHALL 进入 `ambiguous`/`unresolved` 隔离，不得写入正式 canonical trajectory、heatmap 或 report。

#### Scenario: 同一检测竞争 P1 和 P2

- **WHEN** 同一 tick 的 source track 同时成为 P1 与 P2 候选
- **THEN** 系统 SHALL 至多接受一个绑定
- **AND** 另一项 SHALL 标记 ambiguous/duplicate 并进入隔离诊断

#### Scenario: P2/P4 local slot 发生未确认换绑

- **WHEN** 7–13 秒回归窗口内同一 view 的 local slot 在 P2 与 P4 global 之间切换，但未满足连续 reassociation 和唯一性条件
- **THEN** 该观测 SHALL 不得进入正式 canonical trajectory
- **AND** 质量产物 SHALL 计为 local-slot reassociation violation 或 ambiguous sample

### Requirement: 新 Job 真实回归

真实回归 SHALL 创建新 analysis Job 并保存 baseline/new 的结构化对照；刷新旧 artifact SHALL NOT 视为算法回归。固定验收片段 SHALL 覆盖约第 2 秒 P2 可见性、第 4 秒 P2 不误投到 P1、第 7–13 秒 P2/P4 身份与 overlay 稳定性，以及 P2 正式轨迹不进入 P3/P4 对侧区域。

#### Scenario: 新任务改善 P2

- **WHEN** 对同一素材运行变更前 baseline 与变更后新 Job
- **THEN** 新 Job SHALL 满足全部硬不变量
- **AND** minimum per-player coverage、P2 coverage 与 P2 longest gap SHALL 不劣于 baseline

#### Scenario: 7–13 秒 P2/P4 身份稳定

- **WHEN** 检查新 Job 的 `fused-trajectory`、`player-display-diagnostics` 和 `fused-player-overlay`
- **THEN** P2/P4 的 canonical `player_id` SHALL 不发生未经确认的交换
- **AND** 同一 local slot 的 reassociation violation SHALL 为零，ambiguous/unresolved 样本不得进入正式轨迹

#### Scenario: 7–13 秒 overlay 不频闪

- **WHEN** 检查 reference `cam_1` 的 P2/P4 overlay frame 序列
- **THEN** 投影碰撞或几何跳变 SHALL 不发布误导性 synthetic bbox
- **AND** bbox/footpoint SHALL 保持在配置 residual 内，display topology 的短窗 transition count SHALL 不超过配置门限
