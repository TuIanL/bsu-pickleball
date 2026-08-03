## Why

当前球员身份在分析任务内不稳定：远端球员因检测缺失/低置信度被取消识别，重新识别时被分配新的 track ID，导致同一球员在画面上显示为不同 ID（如 `ID164`、`ID172`），并可能分裂为多个身份。根本原因是 IOU 跟踪器无限递增的 track_id 泄漏到用户可见输出，且锁定层与身份层之间的接线失效（提示命名不匹配、身份层先新建后匹配、锁定槽位可重置/替换）。

## What Changes

- **球员 ID 固定为 1–4**：一场比赛/一个分析任务内，对外球员身份 `player_id` 只允许 `1`/`2`/`3`/`4`（双打）或按 `expected_player_count` 收缩（单打为 `1`/`2`）。原始 tracker `track_id` 只作为内部调试信息，不再出现在任何用户可见输出中。
- **四名球员先锁死**：任务启动 bootstrap 阶段自动锁定球员槽位，候选优先从画面中央向外扩散，且每个球场象限（近左/近右/远左/远右）只取一个。
- **硬锁到底**：锁定后的槽位身份永久不变。球员长时间漏检时保留身份、用速度预测+插值维持轨迹，人回来时按槽位重接；**删除**长时间丢失后重置（`player_reset_after_prolonged_loss`）与降级替换（`side_quota_fallback_replaced`）两条会翻转身份的路径。
- **锁定层成为身份唯一权威**：修复 `player_1` 与 `Player_1` 命名分裂，身份层不再独立新建身份，只转发锁定层的 track→slot 映射。
- **前端只显示 1–4**：`CourtMinimap`、`VideoAnalysisCard`、`AnalysisDetailsPage` 等处统一显示 canonical player ID，不再渲染原始 track_id。
- **BREAKING**：`PlayerLockState` 状态机的"长时间丢失→SEARCHING 重置"行为移除，改为"长时间丢失仍保持 LOST，身份保留"。

## Capabilities

### New Capabilities
- `player-identity-display`: 用户可见输出（视频叠加、球场 minimap、轨迹详情页、报告）只呈现 canonical player ID（1–4），原始 tracker `track_id` 不得出现在任何面向用户的 API 字段或文案中。

### Modified Capabilities
- `player-lock-state-machine`: 锁定语义改为"硬锁到底"——bootstrap 中心优先+象限唯一锁定，锁定后槽位永不重置/替换；移除长时间丢失重置与降级替换两条状态转换。
- `player-trajectory-identity`: 身份层改为锁定层的纯转发，取消独立新建身份逻辑；`player_id` 固定为 1–4 且与锁定槽位一一对应。

## Impact

- **后端**：
  - `backend/app/vision/player_tracking_engine/player_lock_manager.py` — bootstrap 排序、硬锁路径、移除重置/替换
  - `backend/app/vision/player_tracking_engine/player_identity.py` — 命名统一、身份层转发、ID 契约
  - `backend/app/vision/player_tracking_engine/player_lock_types.py` — 配置项与槽位定义
  - `backend/app/services/analysis_pipeline.py` — 接线（hints 生效）、`P1 / T164` 标签去掉 track_id
  - `backend/app/schemas/tracking.py` — `player_id` 取值约束为 1–4
  - `backend/app/core/config.py` — 新增/调整锁定配置项
- **前端**：
  - `src/components/platform/CourtMinimap.tsx`
  - `src/components/platform/VideoAnalysisCard.tsx`
  - `src/pages/AnalysisDetailsPage.tsx`
- **规格**：修改 `player-lock-state-machine`、`player-trajectory-identity` 两份 spec；新增 `player-identity-display` spec。
- **测试**：锁死/重连/不分裂身份的单元测试与集成测试；前端展示 canonical ID 的组件测试。
