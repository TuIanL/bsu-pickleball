# fix-multiview-player-identity Design

## Context

joint_tracking_v2 双摄分析（job-222b3ca877）暴露四类问题，根源分布在展示层与跟踪层两层：

1. **display diagnostics 404**：`multiview_result_composer._publish_joint_player_display_diagnostics`（composer.py:706-712）在 `joint_output.display_diagnostics_payload` 缺失/非 dict 时直接 return，**不写盘任何 artifact**；`multiview_joint_run.py:834-859` 构建失败时 `display_diagnostics_payload=None`。两处叠加 → 查询 API（routes_analysis.py:367-368）永远 404。
2. **playerMarkers.team 错位**：`pipelineReportAdapter.ts:323-335` 与 `mock_analysis.py:1159-1178` 用 `index < 2 ? "near" : "far"`，依赖 `latest.entries()` 的**插入顺序**（由后端 tracks 顺序决定，非确定性），与 `player-lock-state-machine` 的槽位语义（P1P2=near, P3P4=far）冲突。
3. **近端球员未识别**：bootstrap 候选过滤（`player_lock_manager._bootstrap_candidate_entries` + `primary_player_selector`）对"距画面中心远"的近端大尺寸球员不友好，近端右路（home=near_right → Player_2）可能被远端候选抢占或永远 searching。
4. **P1↔P2 身份互换**：`player_lock_manager._assign_recovery_candidates` 的 reconnect 与 `association_global.process_tick` 的 PendingReassociation 无"同侧优先 + 跨侧拒绝"硬约束，跨侧强证据连续 5 帧即可切换 → 视觉层 P1/P2 标签互换。

约束：本 change 只改语义/兜底/稳定性，不改变对外 schema 与 URL；所有修复需可回归。

## Goals / Non-Goals

**Goals:**
- display diagnostics 产物在任何情况下都存在占位 artifact，查询 API 不再 404。
- `playerMarkers.team` 与 A-D 标签按 canonical `Player_N` 数字语义稳定赋值（前后端一致）。
- bootstrap 接纳画面近端的大尺寸高清晰候选，近端右路球员可锁定。
- reconnect/association 阶段同侧优先、跨侧拒绝，杜绝 P1↔P2 视觉互换。
- 每类修复配套回归测试。

**Non-Goals:**
- 不改 display diagnostics 产物 schema（保持 `player-display-diagnostics.v1` 与既有字段）。
- 不改 `playerMarkers` 字段结构（id/label/team/x/y/color）。
- 不改查询 API 的 URL/参数。
- 不解决 tracker 层的 YOLO 检测召回率问题（那是另一类模型质量问题）。
- 不引入新的外部依赖。

## Decisions

### D1: display diagnostics 兜底策略——"占位 artifact 双保险"

**方案**：`multiview_joint_run.py` 构建结束时若 `display_diagnostics_payload is None`（构建抛错或校验失败），回退为一个最小占位 dict：
```python
display_diagnostics_payload = {
  "schema_version": "player-display-diagnostics.v1",
  "job_id": run_id, "video_id": capture_take_id,
  "reference_view_id": reference_view_id,
  "status": "unavailable",
  "detail": display_diagnostics_error or "rows empty / build skipped",
  "rows": [],
}
```
同时 composer 侧（`_publish_joint_player_display_diagnostics`）对 `payload` 缺失/非 dict 时**构造并写盘**同等占位 artifact，而不是 return。两处任一生效，文件必存在。

**备选方案对比**：
- A（选）：joint run 侧兜底 + composer 侧兜底，双保险，防未来调用路径变化。
- B：只在 composer 侧兜底。更少改动，但 joint run 产物语义（status=unavailable）在 composer 才可见，调试时 joint output 层面缺失。
- C：API 层把 404 改成结构化 unavailable。治标不治本，产物文件仍不存在，且与既有 spec "产物不存在返回结构化 unavailable" 的语义靠 API 硬转，前端拿不到 detail。

选 A：既满足"文件必存在"，也让 joint output 自带兜底语义，API 只需处理"status=unavailable/failed"。

### D2: team 语义单一事实源——共享 side-from-id 函数

**方案**：新增纯函数（前后端各自实现，但语义一致）：
```python
# backend: app/schemas/analysis.py 或 tracking utils
def canonical_player_side(player_id: str, doubles: bool) -> str:
    n = int(player_id.removeprefix("Player_"))
    if not doubles:
        return "near" if n == 1 else "far"
    return "near" if n <= 2 else "far"
```
```typescript
// frontend: src/services/pipelineReportAdapter.ts
function playerSideFromId(id: string, doubles: boolean): "near" | "far"
```
`tracksToPlayerMarkers` 与 `_tracks_to_player_markers` 改为：先按 `Player_N` 数字排序（`sort((a,b)=>num(a)-num(b))`），再依次给 label A-D 与 team（由函数计算）。非 canonical id 用 court_point.y 兜底或 unknown。

**备选对比**：
- A（选）：按编号解析，与 lock_manager 槽位语义强绑定，确定性最高。
- B：按 court_point.y 判断近远。对投影抖动敏感，bootstrap 初期轨迹点少时不稳，且与槽位语义可能冲突（球员会移动）。
- C：后端直接输出 team 字段，前端透传。改动面更大（要改报告 schema），且 demo/mock 路径仍在后端。

选 A：最确定、改动最小、前后端行为一致。

### D3: bootstrap 近端候选接纳——"近端尺寸加权"而非"中心距离排序"

**方案**：`_bootstrap_candidate_entries()` 排序键增加近端尺寸加权：对 bbox 面积大（`bbox_area > near_large_bbox_ratio × frame_area`）且脚点 y 投影处于近端（`court_y < near_side_threshold_ft`，默认 22ft 网线以内）的候选，把"距画面中心距离"这一主排序键替换为"近端大尺寸优先"标记（近端大尺寸候选排在远端候选之前，象限内再按中心距离排）。
同时 `_is_identity_candidate` 对近端大尺寸候选放宽 `is_inside_tracking_area`（允许 `near_court_area` / `outside_court_visible` 投影状态）。

**关键护栏**：放宽只作用于"近端 + 大尺寸 + 高清晰"三重条件同时满足的候选；脚点门控（court_position 投影）仍为硬约束，防止裁判/观众误入槽位。

**备选对比**：
- A（选）：排序键加权 + 条件放宽，改动集中在 `player_lock_manager`，风险可控。
- B：提升 YOLO 置信度阈值或扩大 tracking area 常数。扩大 tracking area 会引入裁判误锁；改阈值会影响全部候选。
- C：bootstrap 后补一轮"近端空缺检测"（若 near 槽位 searching 而画面近端有强候选则强制锁定）。逻辑复杂，且与"锁定槽位不可替换"spec 冲突。

选 A：条件收敛（近端+大+清晰），对非球员干扰最小。

### D4: reconnect 同侧约束——"quadrant 硬约束 + 跨侧拒绝"

**方案**：在 `_assign_recovery_candidates` 的候选评分里加入：
- `side_match`：候选 `side`（来自 `inferred_side` / `assignment_side`）与槽位 `home_quadrant` 的 side 部分（near/far）不符时，直接不可选（score=0）；
- `lateral_match`：同侧但横向（left/right）不符时，得分乘以强惩罚系数（如 0.1，与既有"横向错配惩罚"一致）。
同侧候选不足时，槽位保持 LOST（符合既有 spec "LOST 是持久状态，长时间丢失不重置"）。

**备选对比**：
- A（选）：side 不符直接排除 + 横向惩罚。最硬，杜绝跨侧互换。
- B：仅惩罚不排除。跨侧证据足够强时仍会换，问题依旧。
- C：在 association_global 层加同侧约束。joint 层改动大，且 local tracker 层已能拦截，双重约束成本高。
选 A：在 lock 层拦截跨侧互换（根因层），joint 层保持既有 PendingReassociation 语义（同侧内允许 reassoc）。

### D5: 身份互换观测——诊断事件

**方案**：`PlayerLockManager.update` 在完成一次 `side` 不符的强制重连（理论上被 D4 禁止，若发生说明有 bug 或初始 bootstrap 错位）或检测到 `identity_swap_suspected` 条件时，往 `PlayerIdentityDiagnostic` 列表追加 `event: "identity_swap_suspected"`（含 `identity_id`、`from_track`、`to_track`、`home_quadrant`、`side`）。观测页/日志可直接检索。

## Risks / Trade-offs

- [bootstrap 放宽误锁裁判/观众] → 脚点门控硬约束 + "近端+大尺寸+高清晰"三重条件；新增单测覆盖"站在画面中央的裁判不被锁定"。
- [team 按编号分侧与球员实际站位不符（如球员换边）] → 槽位语义是"身份命名"而非"实时位置"；minimap 仍按 court_point 绘制实际位置，team 仅用于分组语义，两者不冲突。
- [D4 跨侧拒绝降低极端横向跑动的恢复率] → 双打同侧双人短距离互换由"横向错配惩罚+连续帧证据"保留恢复路径；悬挂期阈值（`lost_grace_frames`）可配置，必要时放宽。
- [display diagnostics 占位 artifact 改变 API 响应语义（404→200 unavailable）] → 前端已按既有 spec 支持 `unavailable` 展示路径；需同步检查 observability 页与测试，避免把 200 unavailable 当成功数据渲染。
- [mock_analysis.py 与 adapter 改动后 demo 数据视觉变化] → demo 数据本身就是固定 4 条轨道，按编号分侧后 A-D 仍对应 P1-P4，视觉一致；更新相关快照测试。

## Migration Plan

1. 后端：先落 D1（composer + joint run 兜底），跑 display diagnostics 相关测试。
2. 后端：D3 + D4 + D5（bootstrap/reconnect/观测），跑 lock manager 相关测试。
3. 前端：D2 的 adapter 改动 + 单测；后端 D2 的 mock 改动。
4. 回归：跑 `npm test`（前端 vitest）+ 后端 pytest（含新增回归）。
5. 用 job-222b3ca877 同源视频重跑一个 joint job，人工核验：诊断接口 200、markers 分侧正确、近端右路有框、P1-P4 稳定。
6. 回滚：若展示异常，先回滚前端 adapter（独立提交）；后端兜底/约束独立提交，可分别回滚。

## Open Questions

- 近端"大尺寸"的阈值（bbox 面积比）与"近端"判定阈值（court_y < 22ft？）在 baseline 视角下是否需要对不同 camera 高度做归一化？（默认用面积比 + court_y，先不做相机高度归一化，后续有数据再调。）
- `playerMarkers.team` 是否需要在后端报告 JSON 里直接输出（避免前端每次都要解析）？（当前决定：前后端各实现一次纯函数，保持 schema 不变；若后续多次出现不一致可再议。）
