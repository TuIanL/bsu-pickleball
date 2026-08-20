# fix-multiview-cam1-bootstrap-4player Design

## Context

job-f83ec9c3f9（60s 窗口验收）实证：cam_1 整场只有 3 个 track 被 PlayerLockManager 锁定，Player_2 槽位全程 searching。用该 job 的真实 homography 对 YOLO 4 个检测做脚点投影：

| 球员 | YOLO conf | bbox | court 投影 | 状态 | 归属 |
|---|---|---|---|---|---|
| 近端左 | 0.87 | [642,445,820,787] | (6.8, 45.3) | outside_court_visible | far_left → Player_3 ✓ |
| 近端右 | 0.83 | [1224,492,1348,905] | (14.9, 47.6) | outside_court_visible | far_right → Player_4 ✓ |
| 远端中 | 0.76 | [788,87,870,208] | (4.5, 9.8) | inside_court | near_left → Player_1 ✓ |
| **远端右** | **0.50** | [1520,104,1579,227] | **(31.3, 12.4)** | **x 超 tracking 上界 24** | **near_right → Player_2 ✗ 被拒** |

根因链：`PlayerProjector` 正常产出该 position（drop_outside_tracking=False，build_view_tracking_session 默认），但 `PlayerLockManager._is_identity_candidate` 的 `is_inside_tracking_area` 硬门（x 超界 → false）在 bootstrap 收集阶段（`_collect_bootstrap_observations` line 269）拒绝该候选 → `_BootstrapTracklet` 无该 track → `_bootstrap_candidate_entries` 无 near_right 象限候选 → Player_2 永远 searching → cam_1 只有 3 个 binding → 4 个 global 抢 3 槽位 → gid_3 几何错配绑定 Player_1（duplicate）+ gid_4 无 cam_1 binding → roster 身份冲突。

上一 change（fix-multiview-player-identity）已修复展示层（playerMarkers team、A-D 排序、产物兜底、去重、API 200）与 reconnect 同侧约束，但 bootstrap 漏锁第 4 人未触及——本 change 解决该根因。

## Goals / Non-Goals

**Goals:**
- bootstrap 候选接纳改为"纵向可判"（x 出界不单独拒绝），远端右第 4 人进入候选池。
- 象限分配支持图像位置松弛映射（x 出界时用 bbox 中心 x 推断 left/right），Player_2 槽位可被锁定。
- bootstrap 四槽位完整性可观测（slot_unfilled 事件）。
- joint association reference 槽位唯一性（gid_3 不直接覆盖 gid_1 的 Player_1，走 reassoc）。
- display diagnostics 显式呈现身份冲突（roster_conflict 字段）。

**Non-Goals:**
- 不改 YOLO 检测器与 tracker 层（漏检/合并问题不在本 change）。
- 不改 court 标定 homography 与 tracking bounds 几何定义（x 超界是"接纳策略"问题，不是几何错误）。
- 不改 PendingReassociation 的 `reassociation_frames` 迟滞语义与 association 算法门限。
- 不改锁定槽位不可替换语义。
- 不做 orientation 相关改动（已验证 rotate_180 正确）。

## Decisions

### D1: 候选接纳判据——"纵向可判"替代"tracking area 硬门"

**方案**：新增纯函数 `is_court_side_decidable(court_position, court) -> bool`（court y 不在 SIDE_DEAD_ZONE 且非 None），`_is_identity_candidate` 的 bootstrap 分支从 `is_inside_tracking_area` 硬门改为：`court_position is not None AND is_court_side_decidable(...) AND (bbox 非空) AND conf ≥ state 门控`。x 超界不再单独导致拒绝。

**备选对比**：
- A（选）：纵向可判即接纳，x 不参与硬门。最贴合根因（x 出界≠非球员），改动集中在 `_is_identity_candidate`。
- B：放宽 `tracking_x_margin`（4→8ft）。治标不治本——x=31.3 仍超 8ft margin，且影响 tracking_bounds 全局语义（reconnect 距离门也用它）。
- C：bootstrap 收集跳过 `_is_identity_candidate` 直接收所有 tracklet，用下游排序过滤。风险大（裁判/观众进候选池），且偏离"清晰度门控"语义。
选 A：最小侵入、最贴合根因，且可复用 reconnect 阶段的同侧约束兜底。

### D2: 象限松弛映射——"投影为主、图像位置兜底"

**方案**：`_infer_quadrant(tracklet)` 增加 x 出界分支：court 投影 y 可判 near/far，但 x 出界（或 court 投影整体不可信）时，用 tracklet 平均 bbox 中心 x 与画面宽度比较（`> 50% → right, else left`）推断横向，组合成 `near_left/near_right/far_left/far_right`。正常投影路径不变。

**备选对比**：
- A（选）：图像 x 位置兜底，仅 x 出界分支启用。简单、可解释（画面横向与球场横向大致对齐）。
- B：单应矩阵外推 court x（用 homography 反投影图像 x 到 court 全域）。复杂，且 court 全域外推精度差。
- C：该候选归 unknown 象限，走 fallback 填充。与"每个象限只锁一个"冲突，可能把第 4 人填到错误槽位。
选 A：够用且不引入几何外推误差。

### D2.5: bootstrap 候选排序——"持续性优先于中心距离"（真实素材验收发现）

**方案**：`_bootstrap_candidate_entries` 排序键从 `(near_large, center_distance, -conf, -frames)` 改为 `(near_large, -frames, center_distance, -conf)`——出现帧数（持续性）提升到中心距离之前。

**动机（job-cf202280f2 验收实测）**：cam_1 的 near_right 槽位被一个 12 帧的短暂 track（track 16，bbox 更靠画面中心）抢占，而真正的第 4 人（track 4，90 帧稳定、court (31.3,12.7) 超界）因"中心距离远"排在后面被跳过；track 16 随后消失 → Player_2 lost → 空槽。旧排序的"中心优先向外扩散"在**短暂 track 与稳定球员同象限竞争**时会把槽位给错对象。持续性优先保证稳定球员先锁定，短暂 track（观众/检测抖动）只能填剩余槽或 fallback。

**备选对比**：
- A（选）：`-frames` 提到 center_distance 前。最小改动，直接修复"短 track 抢槽"。
- B：加置信度门槛（如 conf 0.4 以上才进象限匹配）。会误伤 conf 0.3-0.4 的真实远端球员（本素材第 4 人 conf 0.43-0.50 勉强过）。
- C：象限内先按持续性、跨象限再按中心距离。逻辑更复杂，收益不明确。
选 A：一行排序键调整即修复根因，且单测（test_bootstrap_persistence_beats_center_distance_for_same_quadrant）锁定行为。

### D3: 槽位唯一性——"reassoc 不覆盖"

**方案**：`GlobalPlayerAssociator` 对 reference view 的 `(view_id, view_player_id) → global` mapping 增加占用检查：新 global 尝试绑定已占用槽位时，不直接写 mapping，而是进入 `PendingReassociation`（沿用既有 challenger 强证据帧数机制，达 `reassociation_frames` 才切换）。同时记录 `reference_slot_conflict` 事件（只读观测，不改算法门限）。

**备选对比**：
- A（选）：复用既有 PendingReassociation 机制 + 唯一性检查。与既有"关联迟滞"spec 一致，最小改动。
- B：在 composer/roster 层去重（保留一个 global 的 binding）。治标——association 层 mapping 本身已错，下游掩盖无意义。
- C：允许同槽位双 global（mapping 变多对多）。破坏 `Player_N` 唯一语义，牵涉 display/overlay/指标全链路。
选 A：在根因层（association mapping 写入点）加约束，且复用成熟迟滞机制。

### D4: 冲突可观测——roster_conflict 字段

**方案**：`GlobalPlayerAssociator` 维护只读 `reference_slot_conflicts: dict[(view_id, view_player_id), int]`（tick 计数，有冲突即递增）；display diagnostics builder 读该计数生成 `roster_conflict` 漏斗行字段。字段缺省 false，旧产物兼容。

### D5: 诊断事件——slot_unfilled

**方案**：`PlayerLockManager` 在 bootstrap 窗口结束（`_finalize_bootstrap` 或 `update` 中 `frame_index >= bootstrap_max_frames`）时，对仍 searching 的槽位输出 `event: "slot_unfilled"`（含 identity_id/home_quadrant）。使四槽位完整性可观测、可回归。

## Risks / Trade-offs

- [接纳 x 超界候选引入场外人员误锁] → 三重约束兜底：纵向可判 + bbox 清晰度（conf 门控）+ 象限归属唯一；D1 仅放宽 x 硬门，y 死区/bbox 缺失仍拒绝；单测覆盖"裁判不被锁"。
- [图像位置松弛映射与球场横向错位（相机斜视角）] → 仅用于 x 出界分支，正常投影路径不变；斜视角偏差只在出界候选上体现，且锁定后由 reconnect 同侧约束修正。
- [强制四槽位可能把非球员填入空槽] → "宁可空槽不误锁"为硬约束：slot_unfilled 事件只观测不伪造；填充仅在纵向可判 + 清晰的候选上发生。
- [reassoc 迟滞可能短暂保留错误 mapping（gid_3 抢槽期间）] → 5 帧迟滞窗口内 display 仍显示 gid_1 → Player_1，属可接受（强证据才切换）；roster_conflict 字段让该窗口可观测。
- [上游 change 的 reconnect 同侧约束与 x 出界接纳并存] → 同侧约束针对 reconnect 阶段（LOST/LOCKED），D1 针对 bootstrap 收集，两者阶段不同不冲突；bootstrap 锁定后的 reconnect 仍受同侧约束保护。

## Migration Plan

1. 后端：D1 + D2（`_is_identity_candidate` / `_infer_quadrant` / `_collect_bootstrap_observations`）+ D5（slot_unfilled），跑 `test_player_lock_manager.py` 全绿（含新增）。
2. 后端：D3（association 槽位唯一性）+ D4（roster_conflict），跑 association 相关测试全绿。
3. 回归：后端全套 pytest；前端 `npm test`（display diagnostics 类型不变，仅新增可选字段）。
4. 验收：用 job-f83ec9c3f9 同源素材重跑 60s 窗口 joint job，人工核验：① cam_1 4 个 track 全锁定（display diagnostics 有 Player_2 行）② roster 无 duplicate（4 个 global 4 个不同 Player_N）③ display diagnostics `roster_conflict=false` ④ overlay/minimap 标签 P1-P4 各归其位。
5. 回滚：D1/D2 独立提交（lock 层），D3 独立提交（association 层），可分别回滚。

## Open Questions

- x 出界候选的 court 纵向阈值：y 判 near/far 的边界直接用 `court.length_ft / 2`（22ft）还是需要 x 出界时更保守的 margin？（当前方案：沿用 SIDE_DEAD_ZONE，不做额外收紧；有真实数据再调。）
- `roster_conflict` 是否需要按 `(player_id, view_id)` 聚合为每行 bool，还是保留 tick 级计数？（当前方案：行级 bool，计数留给 association 观测产物。）
