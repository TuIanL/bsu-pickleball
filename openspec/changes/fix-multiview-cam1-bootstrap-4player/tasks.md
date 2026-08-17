# Tasks: fix-multiview-cam1-bootstrap-4player

## 1. 候选接纳放宽：纵向可判即接纳（D1，核心）

- [x] 1.1 新增共享纯函数 `is_court_side_decidable(court_position, court) -> bool`（court_position 非 None 且 court y 不在 SIDE_DEAD_ZONE），置于 `player_lock_manager.py` 或 tracking utils
- [x] 1.2 `_is_identity_candidate`：bootstrap 分支从 `is_inside_tracking_area` 硬门改为"court_position 非 None + `is_court_side_decidable` + bbox 非空 + conf ≥ 状态门控"；x 超界不再单独拒绝（reconnect/lost 分支保持同侧约束不变）
- [x] 1.3 确认 `_collect_bootstrap_observations`（line 269）对 x 超界候选开始收集（conf 0.5 + 纵向可判场景）
- [x] 1.4 新增单测：构造 court (31.3, 12.4)、conf 0.5、bbox 非空候选 → `_is_identity_candidate=True` 且被 bootstrap 收集（`test_player_lock_manager.py`）
- [x] 1.5 新增单测：court y 死区 / court_position 缺失 / bbox 缺失候选仍被拒绝（既有语义不破坏）

## 2. 象限松弛映射：图像位置兜底（D2）

- [x] 2.1 `_infer_quadrant(tracklet)`：增加 x 出界分支——court 投影 y 可判 near/far 但 x 出界（或投影 x 不可信）时，用 tracklet 平均 bbox 中心 x 与 `frame_width/2` 比较推断 left/right，组合象限
- [x] 2.2 正常投影路径（x 在界内）保持 court 投影优先，不触发松弛映射
- [x] 2.3 新增单测：court (31.3, 12.4) + bbox 中心 x=1286（frame_width 1920）→ 归 near_right；正常投影 (6.8, 45.3) → far_left 不走映射
- [x] 2.4 **真实素材验收修正（D2.5）**：`_bootstrap_candidate_entries` 排序键改 `(near_large, -frames, center_distance, -conf)`——持续性优先于中心距离，修复"短暂 track 抢稳定球员槽位"（track 16 抢 near_right、track 4 被跳过）；新增单测 `test_bootstrap_persistence_beats_center_distance_for_same_quadrant`

## 3. bootstrap 四槽位完整性 + slot_unfilled 观测（D5）

- [x] 3.1 `_finalize_bootstrap` / `update`：bootstrap 窗口结束（frame_index ≥ bootstrap_max_frames）时，对仍 searching 槽位输出 `event: "slot_unfilled"` 诊断（含 identity_id/home_quadrant）
- [x] 3.2 确认不伪造锁定、不替换已锁定槽位（宁可空槽不误锁）
- [x] 3.3 新增单测：4 名球员（含 x 超界候选）画面 → bootstrap 结束后 Player_1..4 全 locked；仅 3 球员 + 1 裁判 → Player_2 保持 searching 且产出 slot_unfilled

## 4. association 槽位唯一性 + 冲突观测（D3/D4）

- [x] 4.1 `association_global.py`：reference view `(view_id, view_player_id)` mapping 占用检查——新 global 尝试绑定已占用槽位时进入 `PendingReassociation`（复用既有 challenger 强证据机制），不直接覆盖
- [x] 4.2 记录 `reference_slot_conflict` 只读事件（view_id/view_player_id/incumbent_global/challenger_global/epoch），不改 association 算法与门限
- [x] 4.3 维护只读 `reference_slot_conflicts` 计数（tick 级，供 display diagnostics 消费）
- [x] 4.4 新增单测 `test_multiview_association_uniqueness.py`：gid_1 已绑 cam_1 Player_1，gid_3 候选 → 不覆盖、进 reassoc pending、达帧数才切换；冲突事件可检索

## 5. display diagnostics roster_conflict 字段（D4 下游）

- [x] 5.1 `player_display_diagnostics.py`：漏斗行新增 `roster_conflict: bool = False`，数据来源 association `reference_slot_conflicts`（同 tick 有冲突即 true）
- [x] 5.2 前端 `report.ts` 类型 + observability 面板展示（可选字段，旧产物兼容 false）
- [x] 5.3 新增单测：构造冲突计数 → 漏斗行 roster_conflict=true；无冲突 → false；旧产物缺字段不报错

## 6. 回归验证

- [x] 6.1 运行后端相关测试集（lock manager / association / display diagnostics）确认全绿
- [x] 6.2 运行前端 `npm test` + `tsc -b` 确认全绿
- [x] 6.3 用 job-f83ec9c3f9 同源素材重跑 60s 窗口 joint job（clipStartMs=0, clipEndMs=60000, debugTraceEnabled=true），人工核验：① display diagnostics 有 Player_2 行（4 个 player 齐）② roster 无 duplicate ③ roster_conflict=false ④ overlay/minimap P1-P4 各归其位
- [x] 6.4 更新受影响快照/示例数据（若有），确保无遗留硬编码
