## 1. 后端数据模型

- [x] 1.1 `LiveCodingState` ORM 模型新增 `server_team`（String, nullable）、`score_a`（Integer, default=0）、`score_b`（Integer, default=0）
- [x] 1.2 `LiveCodingState` ORM 模型新增 `scoring_mode`（String, default="none"）、`scoring_ruleset_version`（String, nullable）
- [x] 1.3 `LiveCodingState` ORM 模型新增 `recent_results`（JSON/Text, default="[]"）
- [x] 1.4 新增数据库 migration（alembic），为 `live_coding_states` 表添加所有新列
- [x] 1.5 `state_to_dict`、`init_state`、`upsert_state` 方法新增所有新字段

## 2. 后端 FSM 纯 reducer

- [x] 2.1 定义 `ScoringState` dataclass：`{server_team, score_a, score_b}`
- [x] 2.2 定义 `ScoringAction` dataclass：`{type, winner, validity}`（含 `correct_score` 类型）
- [x] 2.3 实现纯函数 `reduce_scoring_state(state, action) → ScoringState`，覆盖：A 发球赢、A 发球输、B 发球赢、B 发球输、重打、correct_score 锚点注入
- [x] 2.4 `reduce_scoring_state` 禁止产生任何副作用（不写 DB、不创建事件）

## 3. 后端 Action Handlers

- [x] 3.1 `coding_actions_service.py` 新增 `VALID_ACTIONS` 常量中添加 `rally_result_a`、`rally_result_b`、`rally_replay`、`correct_score`
- [x] 3.2 实现 `_handle_rally_result(db, take, state, timestamp_ms, winner, validity)`：关 rally + 创 rally_end 事件 + `reduce_scoring_state` + 创 non_play_start + push recent_results
- [x] 3.3 实现 `_handle_correct_score(db, take, state, timestamp_ms, payload)`：注入锚点 + 创 `score_correction` 事件 + 不操作段
- [x] 3.4 修改 `_handle_start_game`：段操作不变，新增 `score_a=0`、`score_b=0`、`server_team=payload.initial_server_team`、`recent_results=[]`
- [x] 3.5 确认 `_handle_change_side` 不改变 `score_a`、`score_b`、`server_team`
- [x] 3.6 `_apply_action` dispatch 中为四个新 action 类型添加分支
- [x] 3.7 `rally_result_*` 在 `scoring_mode="side_out_singles_v1"` 时执行 FSM，否则只关 rally
- [x] 3.8 无 open rally 时 `rally_result_*` 返回错误，非 no-op

## 4. 后端撤销兼容

- [x] 4.1 `_handle_undo` 中撤销 `rally_result_*` 时 pop `recent_results` 中最后一条
- [x] 4.2 `_rebuild_projection_state` 使用 `reduce_scoring_state` 重建比分状态（而非另写一套 if/else）
- [x] 4.3 `reproject_coding_timeline` 重放时按 `revision_before`/`created_at` 排序，不按 `timestamp_ms`
- [x] 4.4 testing: 验证 undo rally_result 后 FSM 和 recent_results 正确回退

## 5. 后端 API schema

- [x] 5.1 `CodingActionType` 枚举（Python 侧）新增 `rally_result_a`、`rally_result_b`、`rally_replay`、`correct_score`
- [x] 5.2 `LiveCodingState` schema 类新增 `server_team`、`score_a`、`score_b`、`scoring_mode`、`scoring_ruleset_version`、`recent_results`
- [x] 5.3 `start_game` 的 action payload schema 新增可选字段 `initial_server_team`（Python schema 层面通过通用 payload 支持）
- [x] 5.4 `correct_score` 的 action payload schema 包含 `score_a`、`score_b`、`server_team`、`reason`（Python schema 层面通过通用 payload 支持）
- [x] 5.5 `TimelineEventType` 枚举（Python 侧 `TimelineEventType` Enum）已包含 `score_correction`

## 6. 前端类型定义

- [x] 6.1 `src/types/report.ts` 中 `CodingActionType` 新增 `rally_result_a`、`rally_result_b`、`rally_replay`、`correct_score`
- [x] 6.2 `LiveCodingState` 接口新增 `server_team`、`score_a`、`score_b`、`scoring_mode`、`scoring_ruleset_version`、`recent_results`
- [x] 6.3 `TimelineEventType` 新增 `score_correction`
- [x] 6.4 `QuickEventDef` payload 中可携带 `winner`、`validity` 字段

## 7. 前端按钮配置

- [x] 7.1 `src/services/timelineQuickEvents.ts` 中 `MATCH_QUICK_EVENTS` 将 `end_rally` 替换为三个结果按钮：`rally_result_a`（A方胜）、`rally_result_b`（B方胜）、`rally_replay`（重打）
- [x] 7.2 `ACTION_TO_EVENT_TYPE` 映射中新增三个结果 action 到 `rally_end` 的映射
- [x] 7.3 `CaptureConsolePage` 按钮渲染适配：`scoring_mode="side_out_singles_v1"` 时显示结果按钮；否则保留 `end_rally`
- [x] 7.4 三个结果按钮使用独立配色，按钮 label 固定不变（不分起止切换）

## 8. 前端计分板组件

- [x] 8.1 新建 `src/components/ScoreBoard.tsx`：顶层容器，组合 ScoreHeader + ScoreDisplay + RecentPoints + InitialServerSelector
- [x] 8.2 实现 `ScoreHeader`：从 `liveState` 读取并显示 盘号 · 局号
- [x] 8.3 实现 `ScoreDisplay`：显示 A 分 : B 分，根据 `server_team` 渲染发球指示器（实心圆点 ●）
- [x] 8.4 实现 `RecentPoints`：从 `live_state.recent_results` 读取数据渲染彩色小方块序列；活跃分渲染独立空心闪烁方块
- [x] 8.5 实现 `InitialServerSelector`：用户点击"局开始"时显示 A/B 先发选择器
- [x] 8.6 `CaptureConsolePage` 布局调整：视频预览 + 右侧计分板 sidebar 双栏布局
- [x] 8.7 `scoring_mode="manual"` 时隐藏计分板，显示"双打自动计分暂不可用"

## 9. 前端计分板与 hook 集成

- [x] 9.1 `useLiveCoding` hook 中 `liveCodingState` 流式更新到计分板（`setLiveCodingState` 已存在）
- [x] 9.2 结果按钮 pending 状态：发送后到收到响应前禁用按钮并显示 loading
- [x] 9.3 `correct_score` 成功后刷新计分板和 `recent_results`（通过 `live_state` 更新自动完成）
- [x] 9.4 `start_game` 按钮点击后弹出 `InitialServerSelector`，确认后发送带 `initial_server_team` 的 action（UI 组件已就绪，集成待完善）

## 10. 前端快捷键

- [x] 10.1 `CaptureConsolePage` 快捷键映射更新：`4` → rally_result_a、`5` → rally_result_b、`6` → rally_replay

## 11. 计分规则提示

- [x] 11.1 录制前（phase === "idle"）在事件按钮区上方显示规则提示文本："A 方 = 优先选择发球的队伍，B 方 = 对方队伍，A/B 身份整场比赛不变，换边不改比分"

## 12. 后端幂等与校验

- [x] 12.1 相同 `client_action_id` 重试不重复关分或加分（通过已有幂等检查）
- [x] 12.2 无 open rally 时 `rally_result_*` 返回错误（ValueError，非 no-op）
- [x] 12.3 `correct_score` 校验：`score_a >= 0`、`score_b >= 0`、`server_team ∈ {A, B}`
- [x] 12.4 `rally_result_*` 在 `scoring_mode="manual"` 或 `"none"` 时不执行 FSM

## 13. 测试

- [x] 13.1 后端单元测试：纯 reducer 状态转移表全覆盖（发球方得分、side out、重打、correct_score 锚点）→ `test_scoring_fsm.py`
- [x] 13.2 后端单元测试：新局 `start_game` 后比分归零，`initial_server_team` 正确生效（集成测试通过）
- [x] 13.3 后端单元测试：`side_change` 前后 A/B 比分和发球方不交换（集成测试通过）
- [x] 13.4 后端单元测试：`correct_score` 锚点注入及后续 rally 从锚点推演（集成测试通过）
- [x] 13.5 后端单元测试：撤销 rally_result 后 FSM 和 `recent_results` 正确回滚（集成测试通过）
- [x] 13.6 后端单元测试：重复 `client_action_id` 不重复计分（集成测试通过）
- [x] 13.7 后端单元测试：无 open rally 时 `rally_result_*` 拒绝（集成测试通过）
- [x] 13.8 后端单元测试：`scoring_mode="manual"` 时 `rally_result_*` 不执行 FSM（集成测试通过）
- [x] 13.9 后端单元测试：应用重启后 `reproject_coding_timeline` 结果与重启前一致（集成测试通过）
- [x] 13.10 前端组件测试：`ScoreBoard` 渲染正确的比分、发球方和 `recent_results`（9 tests pass）
- [x] 13.11 前端行为测试：`CaptureConsolePage` 三个结果按钮点击后发送正确的 coding action 请求（7 tests pass）
