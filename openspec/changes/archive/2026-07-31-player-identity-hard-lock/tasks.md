## 1. 身份层接线修复（D1：锁定层唯一权威）

- [x] 1.1 统一命名：`PlayerLockManager` 槽位 `identity_id` 从 `player_{idx+1}` 改为 `Player_{idx+1}`，与身份层 `player_id` 键格式一致
- [x] 1.2 修复 `PlayerIdentityManager._assign_player`：删除"槽位未满即新建身份"与 `_best_candidate` 独立匹配，改为按 ①hints ②track_to_player ③无果则记录 `unmatched` 的顺序转发
- [x] 1.3 身份层对 LOST 槽位的新 track：即使槽位处于 LOST，也把新 track 绑回同一 `player_id`（随锁定层 hint 走）
- [x] 1.4 更新 `player_lock_types.py` 注释与 `analysis_pipeline.py` 注释，删除命名不一致的误导说明

## 2. 对外身份契约与输出清洗（D4）

- [x] 2.1 删除 `analysis_pipeline.py:1863` 检测标签中的 ` / T{track_id}`，仅保留 `P{1-4}`
- [x] 2.2 校验 `PlayerTrajectoryArtifact` / projection 轨迹产物：`player_id` 只含 canonical ID，数量 ≤ `effective_player_count`
- [x] 2.3 确认原始 `track_id` 仅存在于调试产物（projection debug）与诊断字段（`history_track_ids`），不进入用户可见身份字段

## 3. 前端 canonical ID 展示

- [x] 3.1 新增 `formatPlayerId(playerId)` 工具（`Player_N` → 整数 `N`），集中映射
- [x] 3.2 `CourtMinimap`：按 `player_id`（canonical）分组绘制，标签显示 `P{1-4}`，不再用 `ID{track_id}`
- [x] 3.3 `VideoAnalysisCard`：检测框标签改用 `detection.player_id` 渲染 `P{1-4}`，不再显示 `ID {track_id}`
- [x] 3.4 `AnalysisDetailsPage`：轨迹摘要与点位检查改为 canonical ID，移除"原始 ID：{trackId}"

## 4. Bootstrap 中心优先 + 象限唯一（D2）

- [x] 4.1 实现槽位象限归属判定：`Player_1`=近左、`Player_2`=近右、`Player_3`=远左、`Player_4`=远右（单打退化近/远）
- [x] 4.2 bootstrap 候选按"bbox 中心距画面中心距离"升序为主排序，置信度/出现帧数为次级
- [x] 4.3 每象限只锁定一个槽位；球场脚点门控优先于中心距离（排除画面中央的裁判/路人）

## 5. 硬锁到底（D3）

- [x] 5.1 移除 `player_reset_after_prolonged_loss`：LOST 超时后保持 LOST，槽位身份永久保留，不再回退 SEARCHING
- [x] 5.2 移除已锁定（LOCKED）槽位的降级替换（`side_quota_fallback_replaced`）；仅未锁定槽位（searching/tentative/fallback_tentative）可被更优候选填充
- [x] 5.3 保留 LOST 重连路径（`_find_best_reconnect` + reconnect_score），重连命中后状态恢复 LOCKED
- [x] 5.4 更新 `PlayerIdentityDiagnostic.event` 枚举：移除 `player_reset_after_prolonged_loss`，保留/补齐 `unmatched`
- [x] 5.5 标记 `lost_max_frames_locked` 配置为 deprecated（保留字段，不再触发状态回退）

## 6. 测试

- [x] 6.1 单元测试：命名统一后 `track_identity_hints` 被身份层正确消费（覆盖命名不匹配回归）
- [x] 6.2 单元测试：身份层对无 hint 的新 track 记录 `unmatched`，不新建身份、不 best-candidate 匹配
- [x] 6.3 单元测试：bootstrap 中心优先排序与象限唯一（同象限多候选取中心最近；跨象限不互抢）
- [x] 6.4 单元测试：硬锁到底——球员长时间丢失后槽位身份不变、不重置，重连后绑回原身份
- [x] 6.5 单元测试：输出清洗——trajectory/overlay 产物 `player_id` 仅含 canonical ID，无原始 `track_id`
- [x] 6.6 前端组件测试：`CourtMinimap` / `VideoAnalysisCard` / `AnalysisDetailsPage` 渲染 canonical ID，无 `ID {track_id}` 文案
- [ ] 6.7 集成回归：跑一段真实双打视频分析，断言最终输出球员身份 ∈ {1..4}，且单球员漏检后重见身份不变
