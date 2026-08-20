# player-identity-display Delta

## ADDED Requirements

### Requirement: playerMarkers 的 team 字段按 canonical 槽位语义赋值

球场 minimap 与报告的 `playerMarkers[].team` 字段 SHALL 按 canonical `Player_N` 槽位语义赋值，MUST NOT 按遍历顺序或 `latest.entries()` 的插入顺序赋值。双打模式：`Player_1`/`Player_2` SHALL 为 `near`，`Player_3`/`Player_4` SHALL 为 `far`；单打模式：`Player_1` SHALL 为 `near`，`Player_2` SHALL 为 `far`。该语义 SHALL 与 `player-lock-state-machine` 的槽位位置语义一致。

#### Scenario: 双打 markers 按编号分侧

- **WHEN** 双打分析产出 `Player_1`、`Player_2`、`Player_3`、`Player_4` 四条轨迹
- **THEN** `playerMarkers` 中 `Player_1`/`Player_2` 的 `team` SHALL 为 `near`
- **AND** `Player_3`/`Player_4` 的 `team` SHALL 为 `far`
- **AND** 任何遍历顺序变化都 SHALL NOT 改变该赋值

#### Scenario: 单打 markers 按编号分侧

- **WHEN** 单打分析产出 `Player_1`、`Player_2` 两条轨迹
- **THEN** `Player_1` 的 `team` SHALL 为 `near`
- **AND** `Player_2` 的 `team` SHALL 为 `far`

#### Scenario: 非 canonical track_id 不猜侧

- **WHEN** `playerMarkers` 输入中存在无法解析为 `Player_N` 的 track_id（如 `global_player_1` 或 `candidate_3`）
- **THEN** 该 marker 的 `team` SHALL 回退为按 `court_point.y`（近半场 `y < 22ft` → near）推断或 `unknown`
- **AND** SHALL NOT 抛出异常或产出错误的 near/far

### Requirement: playerMarkers 与 A-D 标签按数字序稳定

`playerMarkers` 数组 SHALL 按 canonical `Player_N` 数字升序排列，使 label A-D 稳定对应 P1-P4（A=Player_1, B=Player_2, C=Player_3, D=Player_4）。该排序 SHALL 在前后端（`src/services/pipelineReportAdapter.ts` 与 `backend/app/services/mock_analysis.py`）一致实现。

#### Scenario: 后端 tracks 顺序变化不影响 markers 顺序

- **WHEN** 后端 `tracks` 数组顺序为 `Player_2, Player_4, Player_1, Player_3`
- **THEN** 生成的 `playerMarkers` SHALL 仍按 `Player_1, Player_2, Player_3, Player_4` 排序
- **AND** label SHALL 依次为 A、B、C、D
