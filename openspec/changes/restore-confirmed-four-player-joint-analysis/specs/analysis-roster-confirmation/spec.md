## ADDED Requirements

### Requirement: 冻结名册约束 joint 跟踪与独立身份审计

`joint_tracking_v2` SHALL 在运行前读取与 Job 的 `rosterSnapshotHash` 一致的冻结 `AnalysisRosterSnapshot`，并将每个条目的 P 槽位、Team、初始端位、锚点时间、机位及可用几何/外观证据传给正式球员跟踪。锚点 SHALL 只在其时间窗口内用于观测匹配；系统 MUST NOT 把锚点框当作其他时间的检测。跟踪完成后 SHALL 独立于 Rally/Shot 组合生成并持久化每槽位的 `bootstrap-binding-audit`；没有唯一绑定时 SHALL 保留明确原因，不得用 global 槽序或同名 `Player_N` 确认身份。

#### Scenario: 四人手动名册进入 joint 运行

- **WHEN** Job 冻结了四个互异 P 槽位且 hash 与运行输入一致
- **THEN** joint run SHALL 按该名册建立四个待确认身份约束
- **AND** 审计产物 SHALL 保留四个槽位各自的锚点来源与绑定结论

#### Scenario: Rally/Shot 组合失败

- **WHEN** 球员跟踪完成但 Rally/Shot 组合失败
- **THEN** `bootstrap-binding-audit` SHALL 仍可读取
- **AND** 球员身份确认状态 SHALL 不依赖 Rally/Shot 的成功状态

#### Scenario: 锚点不在当前观测时间窗

- **WHEN** 某 P 槽位只有赛中锚点，而开场轨迹与锚点之间没有可核验的连续性
- **THEN** 开场对应观测 SHALL 保持未确认
- **AND** SHALL NOT 由赛中锚点反向伪造开场身份或画框

#### Scenario: 同时刻锚点命中尚未投影的候选框

- **WHEN** 锚点机位的受跟踪候选框在锚点时间窗内与冻结 bbox 唯一重合，但该帧没有可用球场投影
- **THEN** 系统 SHALL 保存 `(view, raw track id)` 到 P 槽位的待确认联系
- **AND** 该 bbox-only 证据 SHALL NOT 进入 global 位置更新或单独确认身份
- **AND** 同一 raw track 后续成为正式位置观测并取得 global ID 时，系统 SHALL 才尝试确认冻结槽

#### Scenario: Rally/Shot 不得替换联合跟踪身份审计

- **WHEN** joint run 已发布含来源轨迹证据的 `bootstrap-binding-audit`
- **AND** Rally/Shot 后处理成功生成自己的名册投影审计
- **THEN** Rally/Shot SHALL 保留现有 joint-run 审计文件
- **AND** 只有审计文件缺失时才可写入后处理的兼容审计

#### Scenario: 名册缺失或 hash 不匹配

- **WHEN** Job 无可用冻结名册或名册 hash 与 Job 不一致
- **THEN** 系统 SHALL 给出可检索的 identity-unavailable 原因
- **AND** SHALL NOT 把自动 global 槽位宣称为用户确认的 P 身份

### Requirement: 身份审计为单一权威来源

`bootstrap-binding-audit` SHALL 是冻结槽位确认结论的唯一权威来源。`roster.json` 的 `mapping_confirmed`、质量产物的 `mapping_confirmed_by_player` 与 `identity_slots`、页面状态卡 SHALL 全部读同一份审计结论，MUST NOT 各自独立求值。

当不同产物对同一 P 槽位给出互斥的确认结论时，系统 SHALL 以审计为准，并 SHALL 将该 Job 的身份状态标记为不可用而非任选其一继续发布。

#### Scenario: roster 与审计对同一槽位结论冲突

- **WHEN** `roster.json` 报告某槽位 `mapping_confirmed=true`，而 `frozen_roster.anchor_binding_audit` 对同一槽位给出未确认及原因
- **THEN** 该槽位 SHALL 以审计结论为准，视为未确认
- **AND** 质量产物 SHALL 记录该冲突并使相关门槛判定为 fail
- **AND** 页面状态卡、overlay、热力图与 Team 指标 SHALL 一致显示为未确认

#### Scenario: Rally/Shot 补写审计与联合跟踪审计冲突

- **WHEN** 独立的 joint-run 审计文件已存在，且 Rally/Shot 后处理生成的兼容审计对同一槽位给出不同结论
- **THEN** 系统 SHALL 保留 joint-run 审计文件
- **AND** SHALL 显式标记审计不可用并保留双方结论
- **AND** MUST NOT 静默以补写内容覆盖或补全权威审计

### Requirement: 锚点竞争按证据强度裁决

同一 raw track 或 tracklet 同时被两个及以上冻结槽位的锚点命中时，系统 SHALL 保留证据最强的一方作为该 tracklet 的槽位归属，MUST NOT 按到达顺序先到先得。证据强度 SHALL 依次按 canonical 球场距离、bbox IoU 与时间差比较。

落败槽位 SHALL 进入待裁决状态并记录竞争证据（各候选的 IoU、court 距离、时间差与落败原因），SHALL 继续尝试其余候选 tracklet；无剩余候选时保持明确失败原因，MUST NOT 降级为顺序补位或复用已被占用槽位的 tracklet 标签。

#### Scenario: 两个槽位的锚点命中同一 tracklet

- **WHEN** 两个冻结槽位的锚点在同一机位同一时刻命中同一 raw track
- **THEN** 系统 SHALL 保留 court 距离更小、其次 IoU 更高的一方作为该 tracklet 归属
- **AND** 落败槽位 SHALL 记录 `bootstrap_binding_tracklet_competes_for_slots` 及双方对比证据
- **AND** 证据明显更强的一方 MUST NOT 因到达顺序较晚而失去槽位

#### Scenario: 胜者确认后落败方另有候选

- **WHEN** 落败槽位存在未被占用的其他候选 tracklet
- **THEN** 系统 SHALL 用该候选重新执行锚点匹配
- **AND** 重新匹配成功时落败槽位 SHALL 正常确认，并保留首次竞争的审计痕迹
