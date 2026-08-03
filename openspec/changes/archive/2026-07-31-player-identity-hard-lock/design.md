## Context

匹克球分析管线中球员身份由三层组成：`MultiObjectTracker`（IOU 跟踪器，分配无限递增的内部 `track_id`）、`PlayerLockManager`（维护 4 个身份槽位）、`PlayerIdentityManager`（把 `track_id` 映射到 `Player_1`..`Player_4`）。当前存在四个根因导致身份不稳定：

1. **命名分裂**：锁定层发 `player_1`（小写）作为提示，身份层只认 `Player_1`（大写），提示永远匹配不上 → 锁定层实际上不参与身份决策。
2. **先新建后匹配**：身份层 `_assign_player` 在"新建身份"（槽位未满时）之前不尝试匹配已丢失球员 → 同一球员重见时被拆成两个身份。
3. **可重置/可替换**：锁定槽位丢失约 10 秒后重置回 SEARCHING，可被其他框接管；降级候选可被替换 → 身份翻转。
4. **track_id 泄漏**：`VideoAnalysisCard`、`CourtMinimap`、`AnalysisDetailsPage` 及后端 label（`P1 / T164`）直接展示原始 `track_id`（如 `ID164`、`ID172`）。

目标是将球员身份收敛为**任务级契约**：对外只存在 1–4 四个身份，锁定后不可变，原始 `track_id` 仅作内部调试。

## Goals / Non-Goals

**Goals:**
- 一场比赛/一个分析任务内，对外 `player_id` 固定为 `1`–`4`（单打为 `1`–`2`）。
- 任务启动时自动锁定四名球员（bootstrap 中心优先 + 象限唯一）。
- 锁定后硬锁到底：不重置、不替换、不新建身份；漏检时保留身份并用预测+插值维持轨迹。
- 锁定层成为身份唯一权威，身份层只做转发与轨迹维护。
- 所有用户可见输出只呈现 canonical player ID，杜绝原始 `track_id`。

**Non-Goals:**
- 不做跨任务/跨比赛的球员长期身份绑定（如换边后跨局识别为同一人）。
- 不做外观特征（ReID embedding）重识别（`enable_appearance_score` 保持关闭）。
- 不做手动登记/人工修正入口（用户已选纯自动锁定）。
- 不改动球检测、姿态估计、计分等其他子系统。

## Decisions

### D1：锁定层作为身份唯一权威，身份层降为纯转发

**现状**：`PlayerLockManager` 与 `PlayerIdentityManager` 各自维护身份映射，且因命名分裂而脱节。

**决策**：`PlayerLockManager` 的槽位 `identity_id` 从 `player_{idx+1}` 改为 `Player_{idx+1}`（大写），与身份层字典键完全一致，使 `track_identity_hints` 真正生效。`PlayerIdentityManager._assign_player` 改为仅按以下顺序：
1. `track_identity_hints` 命中 → 直接使用该槽位身份（即使该槽位处于 LOST，也把新 track 绑回同一身份）；
2. `track_to_player` 已有映射 → 复用；
3. 均未命中 → **不新建身份**，记录 `unmatched` 诊断，等待锁定层在下一帧给出提示。

同时**删除**身份层的独立 `_best_candidate` 匹配与"槽位未满即新建"逻辑——重识别统一由锁定层的重连评分负责。

- **理由**：单一权威避免两份映射发散；锁定层已具备 side/quota/bootstrap/重连的全部上下文。
- **备选**：保留身份层最佳候选匹配。**否决**：与锁定层职责重叠，是身份分裂的直接来源。
- **影响**：`player_lock_manager.py:37`、`player_identity.py:214-258`。

### D2：Bootstrap 中心优先 + 象限唯一锁定

**决策**：槽位按位置语义固定编号：`Player_1`=近左、`Player_2`=近右、`Player_3`=远左、`Player_4`=远右。Bootstrap 阶段对每个槽位（象限）：

1. 只接受球场脚点在对应象限内的候选（沿用 `bootstrap_court_margin_ft` 门控，排除裁判/路人）；
2. 在象限内，按"bbox 中心到画面中心距离"升序（即中心优先、向外扩散）为主排序，置信度与出现帧数作为次级排序；
3. 每象限只取一个，一旦某槽位达到 LOCKED，该槽位永久占用，不再参与后续分配。

- **理由**：贴合用户"从画面中央向四周扩散 4 个人为止"的直觉；象限唯一保证四人两两分开、不会同侧抢位。
- **备选**：仅按置信度排序。**否决**：远端球员置信度天然偏低，会被近端重复锁定。
- **影响**：`player_lock_manager.py` 的 `_try_early_lock` / `_finalize_bootstrap` / `_assign_candidate_to_slot`；需要从 `PlayerFramePosition.bbox` 计算画面中心距离。

### D3：硬锁到底——移除重置与降级替换路径

**决策**：
- **移除** LOST 超时重置：`player_reset_after_prolonged_loss`（`lost_max_frames_locked` 后回 SEARCHING）路径删除。LOST 是持久状态，槽位身份永久保留；重连继续按 `_find_best_reconnect`（位置预测 + 运动 + side + bbox）尝试把新 track 绑回同一槽位。
- **移除** 已锁定槽位的降级替换：`side_quota_fallback_replaced` 只允许在槽位未达到 LOCKED（仍为 searching/tentative/fallback_tentative）时发生；一旦 `lock_min_hits` 达成 LOCKED，任何替换路径都被禁止。
- 轨迹维持：漏检期在插值缓冲内的帧用线性插值补齐（沿用现有 `_interpolate`）；超出缓冲的缺口保留为空白，不伪造样本。

- **理由**：这是"锁死"语义的直接落地，杜绝同一个人在画面上 ID 翻转。
- **备选**：保留超时抢救。**否决**：用户已明确选择硬锁到底，抢救路径正是身份翻转的来源。
- **影响**：`player_lock_manager.py:454-493`、`player_lock_types.py`（`lost_max_frames_locked` 变为无意义，标记为 deprecated）。

### D4：对外身份契约——`player_id ∈ {1..4}`，track_id 只进调试

**决策**：
- canonical player ID 统一为 `Player_1`..`Player_4`（内部字符串），对外展示映射为整数 `1`–`4`。
- 后端所有用户可见产物（`PlayerTrajectorySample.player_id`、`FrameDetection.player_id`、投影轨迹点、渲染槽位）只使用 canonical ID。
- `analysis_pipeline.py:1863` 的检测标签去掉 ` / T{track_id}`，仅保留 `P{1-4}`。
- 原始 `track_id` 仅保留在 `history_track_ids`（诊断用）与调试产物（projection debug）中；`FrameDetection.track_id` 保留但标记为内部字段，前端不得展示。
- 前端统一提供 `formatPlayerId(playerId)`，所有展示点（minimap、视频叠加、详情页、报告）改用 canonical ID。

- **理由**：把"只允许 1–4"从口号变成 schema/展示层的硬约束。
- **备选**：彻底删除 `FrameDetection.track_id` 字段。**否决**：部分调试/定位场景仍需要，保留但隔离。
- **影响**：`backend/app/schemas/tracking.py`、`backend/app/services/analysis_pipeline.py:1863`、`src/components/platform/CourtMinimap.tsx`、`src/components/platform/VideoAnalysisCard.tsx`、`src/pages/AnalysisDetailsPage.tsx`。

### D5：单打/双打适配

**决策**：槽位数 = `effective_player_count`（单打 2 / 双打 4）。单打时槽位退化为 `Player_1`=近、`Player_2`=远，中心优先逻辑不变。对外契约同样保证只出现 `1`–`2`。

- **影响**：`analysis_pipeline.py:1579-1582` 已计算 `effective_player_count`，直接透传给锁定层/身份层即可。

## Risks / Trade-offs

- [Bootstrap 锁错人（如裁判/路人）且无人工修正] → 脚点门控（`bootstrap_court_margin_ft`）+ 置信度下限 + 象限唯一三重过滤；对演示场景，兜底方案是重跑分析。硬锁语义下锁错即整场错，属可接受的演示权衡。
- [中心优先启发式不稳（画面中央恰有非球员）] → 以"球场脚点是否落在对应象限"为硬门控，中心距离仅是象限内的排序键，不绕过脚点过滤。
- [移除重置后，若某球员中途离场，槽位永久空置，第 5 人无法被跟踪] → 演示场景固定 4 人比赛，可接受；文档中说明。
- [重连时两名球员交叉，可能短暂把错误 track 绑到槽位（身份 ID 不变，但轨迹片段短暂错位）] → 重连评分含位置+运动+side+bbox 四项，且命中后逐帧纠偏；演示精度可接受。
- [`lost_max_frames_locked` 配置失效，可能影响依赖它的脚本/测试] → 保留配置字段但标记 deprecated，相关测试改为断言"不重置"。

## Migration Plan

1. 纯算法与展示改动，无数据库/存储迁移。
2. 分三步合入，每步保持可运行：
   - 步骤 A：统一命名 + 身份层改为纯转发（D1），修 `P1 / T164` 标签与前端展示（D4）。
   - 步骤 B：Bootstrap 中心优先 + 象限唯一（D2）。
   - 步骤 C：移除重置与降级替换，硬锁到底（D3）。
3. 回滚：配置项 `PICKLEBALL_PLAYER_LOCK_*` 保留；若需退回旧行为，git revert 即可，无需数据迁移。

## Open Questions

- `FrameDetection.track_id` 前端在调试/自定义叠加中是否仍需要？当前决策保留字段但不展示；如后续确认无使用方，可彻底移除。
- 中心优先的"画面中心"定义：固定取帧几何中心，还是取标定球场投影在画面上的中心？演示阶段固定取帧几何中心，后续可用标定中心替换。
