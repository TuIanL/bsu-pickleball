## Context

当前实时录制标注系统只有段（segment）管理——盘、局、分的起止和换边/暂停等非比赛状态，但没有回合结果记录和比分状态。`LiveCodingState` 只跟踪 ordinal 和阶段，`end_rally` action 仅关闭分 segment 并写入 non_play_start 事件，不记录胜负。

用户需要在不断增加录制前设置负担的前提下，让比分系统随标注自动核算。核心约束：段边界仍由用户手动控制，FSM 只推比分。

## Goals / Non-Goals

**Goals:**
- 用三个结果按钮（A胜、B胜、无效重打）替换 `end_rally`（仅在 match + singles UI 中替换，后端保留 `end_rally` 作为合法 action），每次点击同时完成关分、记录胜负、FSM 推比分
- FSM 为单打计分规则：发球方赢则得分+1，接发方赢则 side out
- 纯 reducer 函数 `reduce_scoring_state()` 同时供在线实时执行与撤销/重建使用，保证结果一致
- 每局开始时由用户选择首轮发球方，`start_game` 同时重置比分
- 支持修正锚点：用户手动修正比分后，后续 rally 从修正值重新推演
- A/B 方为整场比赛的稳定参赛方标识，不随换边改变
- 双打模式显式禁用单打 FSM，通过 `scoring_mode` 字段控制
- 前端显示实时比分、发球方、最近 N 分序列

**Non-Goals:**
- 段 segment 的创建关闭逻辑不变，FSM 不干预
- 双打计分规则（第1/第2发球员转换）不在此次实现
- 不实现自动局/盘结束判定（如 11 分判定）
- 不实现赛末点提示
- 不新增独立 endpoint，复用现有 `POST /api/capture-takes/{id}/coding-actions`

## Decisions

### D1: 三个结果按钮替代 `end_rally` — 合并式

每个按钮是一个完整的 coding action，在后端单个事务中完成三段操作：

```
rally_result_a → 1. close_rally(segment + rally_end event)
                  2. record_winner({winner:"A", validity:"valid"})
                  3. FSM: score_a+1, server stays A (if A serving)
                  4. create non_play_start(between_rallies)
```

**不自动开下一分**：用户仍需点击"分开始"开始下一分。这保持了对段边界的完全控制（例如局末点时用户关分后直接点局结束而非开下一分）。

### D2: FSM 只推比分，不动段

FSM 是一个纯计算层，输入是 `{winner, validity}`，输出是 `{score_a, score_b, server_team}` 的增量更新。它与 `LiveCodingState` 的 set/game/rally ordinal 和 segment 创建关闭完全解耦。

```
rally_result handler:
  → 段操作（关 rally segment，与非比分模式完全一致）
  → FSM 操作（更新比分，完全独立于段逻辑）
```

FSM 实现为一个纯函数：

```python
def reduce_scoring_state(
    state: ScoringState,
    action: ScoringAction,
) -> ScoringState:
    ...
```

在线执行时：读取当前 `ScoringState` → `reduce_scoring_state()` → 保存新状态。撤销或重建时：从本局初始状态开始 → 依次 `reduce_scoring_state()` → 得到最终状态。`correct_score` 也是 reducer 能处理的一种 action 类型——当 `action.type == "correct_score"` 时直接返回锚点状态。这保证了实时执行结果、应用重启后的重建结果、撤销后的重新投影结果三者始终一致。

### D3: 单打计分 FSM 状态转移

`server_team` 必须在第一分开始前由 `start_game` 的 `initial_server_team` 设置，不允许为 `None`。

```
State: { server_team: "A"|"B", score_a: int, score_b: int }

前提: server_team ∈ {"A", "B"} (由 start_game 初始化)

server_team = "A":
  winner="A", validity="valid"   → score_a+=1, server_team stays "A"
  winner="B", validity="valid"   → server_team="B" (side out, 不记分)
  validity="replay"              → 不变

server_team = "B": (对称)
  winner="B", validity="valid"   → score_b+=1, server_team stays "B"
  winner="A", validity="valid"   → server_team="A"
  validity="replay"              → 不变
```

### D3a: start_game 比分重置

`start_game` action 新增必要条件：

```json
{
  "action": "start_game",
  "payload": {
    "initial_server_team": "A"
  }
}
```

后端执行 `start_game` 时，在完成现有段操作（关 rally、关游戏、关间歇、创建新 game segment）之后增加：

```
score_a = 0
score_b = 0
server_team = payload.initial_server_team
recent_results = []  (清空)
```

`start_set` 不重置比分（比分属于局），除非 `start_set` 时存在 open game 需要先关闭。`initial_server_team` 默认值：同一场次内记住上一局的选择（前端传递），第一局默认为 A。

### D4: 修正锚点覆盖 FSM

`correct_score` action 携带完整的比分状态锚点：

```json
{
  "action": "correct_score",
  "payload": {
    "score_a": 5, "score_b": 3,
    "server_team": "A",
    "reason": "裁判确认比分"
  }
}
```

重放时，FSM 的 reducer 遇到 `correct_score` action 时直接返回锚点状态。后续的 rally result 从锚点继续推演。多个 correction 之间，以 `revision`（或 `sequence_number`）为准，而不是 `timestamp_ms`——因为现场 action 可能使用相同的 `timestamp_ms` 或赛后补记到更早的位置。`revision` 表示用户命令的权威执行顺序。

`correct_score` 同时创建一条 `score_correction` 类型的 TimelineEvent：

```json
{
  "event_type": "score_correction",
  "payload_json": {
    "score_before": { "a": 4, "b": 3, "server_team": "B" },
    "score_after": { "a": 5, "b": 3, "server_team": "A" },
    "reason": "漏记一分"
  }
}
```

这里 `score_after` 属于人工修正事实，因此可以保存；它和普通 rally 自动推导出的比分性质不同。

### D5: 每局初始发球方选择

取消首分推断逻辑。改为每局开始时由用户明确选择：

```
┌──────────────────────┐
│ 本局先发球方         │
│  ○ A 方  ● B 方     │
│       [确 认]        │
└──────────────────────┘
```

- 默认继承上一局的选择，第一局默认为 A
- 用户可以在 `start_game` 的弹出/内联确认中一键切换
- 该选择通过 `start_game` 的 `payload.initial_server_team` 传递到后端
- 这样首分状态转移完全正常：A 发球 A 胜 → 1:0，A 发球 B 胜 → side out

### D5a: A/B 为稳定参赛方，不受换边影响

A 方和 B 方是整场比赛中的稳定参赛方标识，不随换边改变。换边只改变画面上的近端/远端归属：

```
side_change 时:
  比分 (score_a, score_b) → 不变
  发球方 (server_team)   → 不变
  A/B 身份                → 不变
```

前端计分板的 A 方/B 方标签在换边后保持不变。当前无需在 LiveCodingState 中新增 near/far 字段，只需在 design 层面明确这一约束。

### D6: rally_end 事件 payload schema

`rally_end` 事件（由三个结果按钮自动创建）的 payload 结构：

```json
{
  "payload_json": {
    "winner": "A" | "B" | null,
    "validity": "valid" | "replay",
    "reason": ""
  }
}
```

MVP 只保留 `valid` 和 `replay` 两种状态。`invalid` 不在此轮实现——"误操作、根本不应存在的片段"交给赛后片段管理处理，不混入 replay。

`rally_replay` 的 payload 简化为 `{"validity": "replay"}`（winner 自动为 null）。FSM 行为：replay 不改变计分状态，发球方不变。

事件本身不存 `score_after` 或 `server_after`。比分由 FSM 在重放时重新推演。

### D6a: RecentPoints 从 live_state.recent_results 读取

RecentPoints 不直接从原始 `timelineEvents` 中筛选 `rally_end`，而是读取 `LiveCodingState.recent_results`：

```json
{
  "recent_results": [
    {"winner": "A", "validity": "valid"},
    {"winner": "B", "validity": "valid"},
    {"winner": "A", "validity": "valid"}
  ]
}
```

每次 `rally_result_*` 成功后，后端 push 到列表尾部（最多 10 条）。`correct_score` 不改变它。`start_game` 清空它。`undo` 时 pop 最后一条。

当前活跃分（存在 open rally 但尚无结果）不应出现在 RecentPoints 中。可以在序列末尾渲染一个独立的空心闪烁方块作为 pending indicator。

### D7: 前端组件结构

```
CaptureConsolePage
├── VideoPreview
├── Sidebar (新增固定区域)
│   ├── ScoreBoard
│   │   ├── ScoreHeader (盘号 · 局号)
│   │   ├── ScoreDisplay (A 分 : B 分, 发球指示器)
│   │   ├── RecentPoints (从 live_state.recent_results 渲染)
│   │   └── InitialServerSelector (新局开始时显示)
│   └── ScoreCorrectionPanel (可折叠)
├── QuickEvents
│   └── match + singles 模式:
│       [A方胜] [B方胜] [重打]   ← 取代 [分结束]
│       [分开始] [局结束] [盘结束]
│       [换边] [暂停] [重点] [撤销]
│   └── match + doubles / practice / engineering 模式:
│       [分结束]  ← end_rally 保持不变
└── MiniTimeline
```

## Risks / Trade-offs

- **首分推断可能反直觉**: 用户先点"B方胜"时系统推断 A 是发球方、B 侧 out，比分 0:0。这符合规则但可能让用户困惑。 → 录制前显示规则提示
- **FSM 与段逻辑解耦增加了修正复杂度**: 修正锚点需要影响 FSM 状态但不影响段，需要确保 `correct_score` handler 只操作 score field。 → `correct_score` 在 `_apply_action` 中独立处理，不走段管理分支
- **undo 需要考虑比分回滚**: 撤销一个 rally_result 时需要同时回滚 FSM 状态。当前 undo 机制通过重放剩余 action 重建状态，FSM 重放自然支持回滚。 → 无需额外逻辑

## Scoring Mode 与版本管理

`LiveCodingState` 新增字段：

```python
scoring_mode: str = "side_out_singles_v1"  # 激活的计分模式
scoring_ruleset_version: str = "side_out_singles_v1"  # 历史记录归属的规则版本
```

- `match_format="singles"` 时自动设为 `side_out_singles_v1`
- `match_format="doubles"` 时设为 `"manual"`（无自动计分）
- `practice` / `engineering` 模式设为 `"none"`
- 前端在非 singles 模式下隐藏计分板或显示"当前模式自动计分暂不可用"
- `scoring_ruleset_version` 随 `scoring_mode` 初始化，后续不自动变更。这样未来规则升级时，可以区分历史数据使用的是哪版规则

## end_rally 保留

`end_rally` 作为后端合法 action **保留**，不从 `VALID_ACTIONS` 中移除。前端仅在 `match + singles` 模式中隐藏 `end_rally` 按钮并用三个结果按钮替代。`practice` 和 `engineering` 模式继续使用 `end_rally`。

## Open Questions

- `target_score`（如 11、15、21）和 `win_by`（1 或 2）是否在 FieldSession 或 CaptureTake 中预留？本轮只用于展示提示，不触发自动结束。建议预留到 CaptureTake 元数据 JSON 中，不在 LiveCodingState 加字段。
