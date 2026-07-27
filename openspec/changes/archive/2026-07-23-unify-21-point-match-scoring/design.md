## Context

现有比赛标注链路以 `CaptureTake`、`LiveCodingState`、coding action 日志和 `set/game/rally` segment 构成。计分 reducer 目前实现 `side_out_singles_v1`：只有发球方赢球才得分；单打 take 启用该 FSM，双打 take 使用 `manual` 并隐藏自动计分 UI。前端同时展示层级按钮和结果按钮，并把已开始的 `start_next_rally` 动态替换为无结果的 `end_rally`，导致操作语义与自动计分不一致。

本变更必须兼容已经持久化的旧规则 take，并保证实时执行、离线 outbox、undo/rebuild 与比分修正产生相同结果。比赛仍使用 A/B 稳定身份，换边不得交换比分或胜局归属。

## Goals / Non-Goals

**Goals:**

- 为单打与双打提供同一套可版本化、可重放的五局三胜 21 分混合计分规则。
- 将比分、发球权、计分阶段、发球站位、单局胜负和整场胜负建模为权威后端状态。
- 让局开始选择先发方成为创建新局的前置条件，消除默认 A 方和重复提交。
- 让比赛操作区只暴露当前状态允许的动作，并在单摄和双摄工作台保持一致。
- 保持旧 `side_out_singles_v1` 和 `manual` take 可读取、可重放，不对历史数据进行破坏性重算。

**Non-Goals:**

- 不识别真实视频中的自动得分、犯规或球员身份。
- 不实现球员姓名、阵容轮换、替补或个人发球统计；双打首版只显示“左区队员/右区队员”。
- 不改变 A/B 身份或 `change_side` 的场地交换语义。
- 不重新设计练习模式和工程模式的事件工具栏。

## Decisions

### 1. 使用版本化的统一规则 reducer

新增规则版本 `hybrid_21_best_of_5_v1`，单打和双打的新 match take 均使用该版本。reducer 输入显式包含 `server_team`、`score_a`、`score_b`、计分阶段及比赛累计状态，输出新的不可变状态与派生结果（是否局结束、是否比赛结束）。

选择单一 reducer 而不是在 action service 中分散条件判断，是为了让在线执行、undo/rebuild 和测试共享同一套规则。旧规则版本继续路由到旧 reducer；不原地改变 `side_out_singles_v1` 的语义。

### 2. 计分阶段由比分确定并持久化为权威投影

当进入一次 rally 前比分不是 20:20 时，该 rally 使用每球得分：胜方加 1，并成为下一球发球方。当进入 rally 前比分为 20:20 时，该 rally 及本局剩余 rally 使用发球得分：发球方胜则加 1，接发方胜只交换发球权。由于 21 分封顶，20:20 后一旦发球方得分即结束本局。

`scoring_phase` 作为 `LiveCodingState` 的权威投影返回，重放时仍由有效 action 序列推导。比分修正到 20:20 时进入发球得分阶段；修正到其他未结束比分时回到每球得分阶段，避免额外维护不可解释的隐藏开关。

### 3. 扩展 LiveCodingState 表达比赛级状态

增加或等价提供：`games_won_a`、`games_won_b`、`scoring_phase`、`serving_side`、`match_status`。`serving_side` 由发球方当前得分奇偶派生：奇数为 `left`，偶数（含 0）为 `right`，不单独接受客户端写入。

继续使用既有 `set` segment 作为整场比赛的内部容器，`game` 表示五局三胜中的一局，`rally` 表示一分。前端不再要求用户点击“盘开始”；首次 `start_game` 时后端按现有行为确保内部 set 存在。

### 4. 局开始采用先选择、后提交的单次命令

前端点击“开始第 N 局”只打开先发方选择器，不立即写 action。用户选择 A 或 B 后发送唯一一次带 `initial_server_team` 的 `start_game`。后端对新规则版本强制校验该字段，不再以当前发球方或 A 方兜底。

取消选择不产生 segment、事件或 revision 变化。键盘“开始局”快捷键也只打开选择器。

### 5. 结果 action 原子完成回合、比分和自动收局

`rally_result_a`、`rally_result_b`、`rally_replay` 仍是唯一合法的回合结束路径。有效胜负 action 在同一事务中关闭 rally、运行 reducer、写入 rally 结果；若达到 21 分，还关闭 game、写入含最终比分和胜方的 `game_end`、累计胜局。若任一方取得第三局，则同时标记比赛完成并关闭内部 set。

移除 UI 中直接调用 `end_rally` 的入口，但为历史或非新规则 API 保留 action 兼容。新规则下直接 `end_rally` 应被拒绝，防止创建无结果回合。

### 6. 比赛操作区由权威状态派生

前端建立纯 view-model 映射，而不是在 JSX 中逐个替换按钮：

- 无当前局且比赛未结束：主操作为“开始第 N 局”。
- 当前局存在、无 open rally：主操作为“开始第 N 分”。
- open rally 存在：主操作为等宽的“A 方胜”“B 方胜”，次操作为“重打”。
- 本局自动结束：回到“开始下一局”；比赛完成：显示结果并禁用继续开局。

换边、战术暂停、重点标记和撤销保留为次级操作。单摄使用完整计分板，双摄使用响应式比分栏加同一操作 view-model，不再隐藏双打结果按钮。

### 7. 操作可用性由前后端共同约束

前端根据 `match_status`、当前 game/rally segment 和 pending outbox 禁用非法或重复操作；后端仍是最终校验者。pending 期间不伪造比分，按钮显示提交中并阻止重复点击。键盘快捷键调用同一 view-model，仅触发当前可用动作。

## Risks / Trade-offs

- [旧规则与新规则并存增加分派复杂度] → 以 `scoring_ruleset_version` 明确选择 reducer，并为各版本建立独立回放测试。
- [增加 LiveCodingState 字段需要数据库迁移] → 新字段提供安全默认值，迁移只补结构，不重算历史 take。
- [outbox 中可能已有默认 A 的 `start_game`] → 仅对创建后采用新规则版本的 take 强制新 payload；旧 take 继续按旧契约同步。
- [自动收局改变人工工作流] → 保留 undo，使最后一分撤销后完整重放并恢复为未结束局；比分修正也必须重新计算局/场投影。
- [双打没有球员身份信息] → 首版只展示“左区队员/右区队员”，不虚构具体姓名或编号。
- [20:20 阶段易产生边界错误] → 用进入 rally 前的比分决定该 rally 规则，并覆盖 20:19→20:20、20:20 接发方胜、20:20 发球方胜三类边界测试。

## Migration Plan

1. 增加 LiveCodingState 所需字段和 API schema 默认值，部署兼容新旧客户端的后端。
2. 引入 `hybrid_21_best_of_5_v1` reducer 和版本路由，保留旧 reducer。
3. 更新 coding action 在线执行及 rebuild/undo 路径，并补齐规则与迁移测试。
4. 更新前端类型、计分板和状态化操作 view-model，再启用单打/双打统一规则。
5. 验证旧 take 仍按原 `scoring_ruleset_version` 显示和重放。

回滚时前端可恢复旧操作区；后端保留新增字段和新规则读取能力，避免已经创建的新版本 take 变得不可读取。

## Open Questions

无。规则边界、奇偶站位、局开始选择和 UI 状态流均已由用户确认。
