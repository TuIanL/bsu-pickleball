# player-display-diagnostics Delta

## ADDED Requirements

### Requirement: 身份冲突显式观测

`player-display-diagnostics.v1` 漏斗行 SHALL 增加 `roster_conflict` 字段（bool，缺省 false），表示该 `(player_id, view_id)` 行对应的 reference 槽位在本 tick 存在多 global 竞争（数据来源：`GlobalPlayerAssociator` 的 `reference_slot_conflict` 事件或等价只读观测）。duplicate 去重（保留首行）SHALL 保留，但身份冲突 SHALL 通过 `roster_conflict=true` 显式呈现，MUST NOT 仅靠"保留首行"掩盖。字段缺省兼容旧产物（前端按 false 显示）。

#### Scenario: 冲突槽位的行标记

- **WHEN** 某 tick cam_1 的 Player_1 槽位存在 gid_1/gid_3 竞争
- **THEN** 该 tick 的 `(Player_1, cam_1)` 漏斗行 SHALL `roster_conflict=true`
- **AND** 去重仍保留首行，但冲突可被观测

#### Scenario: 无冲突行不标记

- **WHEN** 某 tick 无多 global 竞争该槽位
- **THEN** 漏斗行 SHALL `roster_conflict=false`（或缺省）

#### Scenario: 旧产物兼容

- **WHEN** 查询历史任务的显示诊断产物（无 `roster_conflict` 字段）
- **THEN** 前端 SHALL 按 false 展示
- **AND** 查询 API SHALL NOT 因字段缺失报错
