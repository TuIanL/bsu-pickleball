# multiview-player-identity-stability Specification

## Purpose
为多视角球员身份在展示层（team/label 语义）与时间维度（bootstrap 接纳、reconnect 同侧约束、身份互换防护）的稳定性提供统一约束与回归防护。本能力作为 `player-identity-display`、`player-lock-state-machine`、`player-display-diagnostics` 三者的横向护栏，确保"P1-P4 按场地分侧、同一球员身份不漂移、诊断产物不 404"成为可测试、可回归的契约。

## ADDED Requirements

### Requirement: team 语义与槽位语义单一事实源

系统中所有按球员分侧的展示（`playerMarkers.team`、minimap、结构化可视化）SHALL 与 `player-lock-state-machine` 的槽位位置语义共享同一份"Player_N → side"映射实现（双打：1/2=near, 3/4=far；单打：1=near, 2=far）。前端 adapter 与后端 mock 不得各自内联一份映射逻辑，MUST 复用/对齐同一语义。

#### Scenario: 双打侧映射一致

- **WHEN** 双打模式下查询任意 `Player_N` 的 side
- **THEN** `Player_1`/`Player_2` SHALL 为 near，`Player_3`/`Player_4` SHALL 为 far
- **AND** 前端 adapter 与后端 mock 产出的结果 SHALL 一致

#### Scenario: 单打侧映射一致

- **WHEN** 单打模式下查询任意 `Player_N` 的 side
- **THEN** `Player_1` SHALL 为 near，`Player_2` SHALL 为 far
- **AND** 前端 adapter 与后端 mock 产出的结果 SHALL 一致

### Requirement: 身份稳定性回归测试

针对本次修复的身份相关缺陷，仓库 SHALL 保留可自动运行的回归测试：① display diagnostics 产物兜底（构建失败仍产出占位 artifact）；② playerMarkers team 语义（乱序输入仍按编号分侧）；③ bootstrap 近端大尺寸候选接纳（近端右路可锁定）；④ reconnect 同侧约束（跨侧候选不完成重连）。这些测试 MUST 在 CI 或本地测试命令中可执行。

#### Scenario: 乱序输入下的 markers 排序与 team

- **WHEN** 运行 `pipelineReportAdapter` 单测，输入 tracks 顺序为 `Player_2, Player_4, Player_1, Player_3`
- **THEN** 输出 markers SHALL 按 `Player_1..Player_4` 排序
- **AND** team 依次为 near/near/far/far，label 依次为 A/B/C/D

#### Scenario: 产物兜底单测

- **WHEN** 运行 display diagnostics composer 单测，joint_output 缺失 payload
- **THEN** 断言占位 artifact 文件已写盘且 `status=unavailable`
- **AND** 查询 API 返回结构化 unavailable（非 404）

### Requirement: 身份互换观测

系统 SHALL 提供身份互换的观测途径：`identity_swap_suspected` 事件 SHALL 写入可检索的位置（日志 / job debug 产物 / observability 汇总），使"P1↔P2 互换"可被复现与归因，而不是只能靠肉眼截图发现。

#### Scenario: 互换事件可检索

- **WHEN** 一次分析中出现跨侧 reconnection 或强证据身份互换
- **THEN** 该事件 SHALL 出现在 job 的可观测产物中（日志行或 debug JSON）
- **AND** 事件 SHALL 包含槽位 identity、前后 track_id、home_quadrant 信息

### Requirement: 修复不得破坏既有契约

所有修复 SHALL 保持既有对外契约兼容：display diagnostics 产物 schema（`player-display-diagnostics.v1`）字段不删除；`playerMarkers` 字段结构（id/label/team/x/y/color）不改变；查询 API 的 URL 与参数不改变。行为变化仅在语义层面（team 正确、404→unavailable）。

#### Scenario: 产物 schema 兼容

- **WHEN** 修复后生成 display diagnostics 产物
- **THEN** 产物 schema_version SHALL 仍为 `player-display-diagnostics.v1`
- **AND** 既有字段（canonical_tick/player_id/view_id 等）SHALL 仍在

#### Scenario: playerMarkers 结构兼容

- **WHEN** 修复后生成 playerMarkers
- **THEN** 每个 marker SHALL 仍包含 id/label/team/x/y/color 字段
- **AND** 前端既有渲染逻辑无需改动即可消费
