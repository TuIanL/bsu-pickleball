## ADDED Requirements

### Requirement: local slot 重绑定与显示振荡可审计

`player-display-diagnostics.v1` SHALL 对每个发生 local slot reassociation、reassociation pending、ambiguous、projection collision、bbox-footpoint inconsistency 或 display topology transition 的 canonical tick 提供可追溯信息。诊断 SHALL 至少能够区分 view、local slot、tracklet/identity epoch、incumbent global、challenger global、decision reason、projection rejection reason 和当前/前一 display state；新增字段为 additive，旧产物缺失时 SHALL 使用兼容默认值。

#### Scenario: local slot 重绑定记录旧新归属

- **WHEN** 同一 view 的 local `Player_N` 从一个 global candidate 进入 pending 或完成 reassociation
- **THEN** 诊断 SHALL 记录 view、local slot、identity epoch、旧 global、候选 global、连续证据计数和 decision reason
- **AND** 查询结果 SHALL 能按 canonical `Player_N` 与时间窗口定位该事件

#### Scenario: 投影拒绝与显示降级可区分

- **WHEN** projected bbox 因 collision、geometry jump 或 bbox-footpoint inconsistency 被拒绝
- **THEN** 诊断 SHALL 分别记录 rejection reason、fallback display state 和是否复用了 presentation geometry
- **AND** SHALL NOT 将该事件只记为普通的 detection miss

#### Scenario: 短窗状态振荡可量化

- **WHEN** 同一 canonical player 在配置窗口内多次切换 `REAL_BOX`、`PROJECTED_BOX`、`PROJECTED_POINT` 或 `HIDDEN`
- **THEN** 诊断 SHALL 输出窗口起止时间、transition count、state sequence 和触发原因
- **AND** 质量验收 SHALL 能使用该字段判断是否发生高频振荡

#### Scenario: 旧诊断产物兼容

- **WHEN** 查询历史 `player-display-diagnostics.v1` 产物且缺少新增字段
- **THEN** API SHALL 正常返回
- **AND** 调用方 SHALL 将新增诊断解释为 unavailable/empty，而不是伪造无冲突或无振荡结论
