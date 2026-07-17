## Why

实时录制模式下，目前只能标注盘/局/分的起止和换边/暂停等非比赛状态，但无法记录每一分的胜负结果。没有回合结果，就无法统计比分、连续得分、关键分和回合效率等核心比赛数据。要在不增加录制前设置负担的前提下，让比分系统随标注自动核算。

## What Changes

- **新增三个结果按钮替换 `end_rally`**: `rally_result_a`、`rally_result_b`、`rally_replay`，每个按钮在关闭当前分的同时记录胜负或无效重打
- **新增比分修正动作**: `correct_score`，允许用户在 FSM 推演出错时注入修正锚点，系统以修正值为准重新推演后续比分
- **LiveCodingState 增加比分和发球状态**: `server_team`、`score_a`、`score_b`
- **计分 FSM**: 基于 rally result 自动核算单打比分和发球权切换；段（segment）的边界仍由用户手动控制；使用纯 reducer 函数，确保在线执行与重放结果一致
- **前端计分板**: 视频预览右侧固定区域显示当前盘/局号、比分、发球方和最近 N 分序列
- **每局首发选择**: `start_game` action 新增 `initial_server_team` payload 字段，每局开始时由用户选择首轮发球方（默认上一局选择），取代首分自动推断
- **A/B 为稳定参赛方**: A 方和 B 方是整场比赛中不变的队伍标识，不受换边影响；`side_change` 仅改变画面近端/远端归属，不改变比分和发球方
- **端到端纯 reducer**: FSM 实现为一个纯函数 `reduce_scoring_state(state, action) → state`，同时用于在线实时执行和 undo/rebuild 重放
- **计分规则版本化**: LiveCodingState 新增 `scoring_mode`、`scoring_ruleset_version` 字段，双打模式显式禁用单打 FSM

## Capabilities

### New Capabilities
- `rally-scoring-fsm`: 比分状态机 — 定义计分规则、发球权交换逻辑和修正锚点重放机制
- `live-score-display`: 前端计分板 — 实时比分、发球指示器、最近 N 分序列的 UI 组件
- `score-correction`: 比分修正锚点 — 用户修正比分的交互逻辑和后端修正锚点插入机制

### Modified Capabilities
- `live-coding-console`: 新增三种 coding action 类型（`rally_result_a`、`rally_result_b`、`rally_replay`），新增 `correct_score` action 类型；`LiveCodingState` 新增 score/server 字段；`start_game` 新增 `initial_server_team` payload；match 模式下的快捷键映射变更；`end_rally` 作为后端合法 action 保留但 match 模式前端隐藏
- `session-timeline-events`: `rally_end` 事件的 `payload_json` 新增 `winner`、`validity` 字段 schema；新增 `score_correction` 事件类型

## Impact

- **后端**: `LiveCodingState` ORM 模型新增字段；`coding_actions_service.py` 新增 handler 和纯 reducer 函数；`CaptureSegment` 和 TimelineEvent 逻辑不变；`start_game` handler 新增比分重置
- **前端**: `CaptureConsolePage` 布局调整（右侧计分板）；`timelineQuickEvents.ts` match 模式按钮配置变更；`useLiveCoding` hook 适配新 action 类型；新增 `ScoreBoard`、`RecentPoints`、`InitialServerSelector` 组件
- **API**: `POST /api/capture-takes/{id}/coding-actions` 新增合法 action 类型，`start_game` payload 新增 `initial_server_team`
- **数据**: `LiveCodingState` 表新增 `server_team`、`score_a`、`score_b`、`scoring_mode`、`scoring_ruleset_version`、`recent_results` 列；`CaptureTake` 或 `FieldSession` 可选预留 `target_score`、`win_by`
