# stabilize-joint-global-player-roster — Tasks

## 1. Registry roster 化（GlobalPlayerRegistry）

- [x]1.1 `backend/app/vision/multiview/global_state.py`：`GlobalPlayerRegistry.__init__` 增加 `expected_player_count: int`（默认 4），内部维护固定 slot 集合（`global_player_1..N`），`new_global_id()` 收归为私有 `_allocate_roster_slot()`（roster 满返回 None），删除/废弃对外 `new_global_id()` 调用路径
- [x]1.2 registry 增加三级生命周期：`candidate → provisional roster occupant → roster confirmed`，roster 状态 `BOOTSTRAPPING / ROSTER_ACTIVE`；`predict_all()` 仅返回 roster 内且具备普通关联资格的 global 预测（不含候选池、不含 stale 玩家）
- [x]1.3 roster 确认逻辑：仅当全部 slot 有 occupant 且每个 occupant 稳定 K tick（配置）或至少一次可靠 cross-view anchoring 后进入 `ROSTER_ACTIVE`；确认窗口内 occupant 可被替换
- [x]1.4 `backend/app/services/multiview_joint_executor.py`：创建 registry 时传入 `match_ctx.expected_player_count`
- [x]1.5 单测：roster 满后 `_allocate_roster_slot()` 返回 None；candidate 不进入 `predict_all()`；占满未确认不 ACTIVE；confirmed roster 玩家出画不删除

## 2. GlobalRosterCandidate 候选池（含自身归属规则）

- [x]2.1 定义 `GlobalRosterCandidate` dataclass（candidate_id / first_tick / last_tick / hit_count / dual_view_hit_count / canonical 位置 / local_bindings / association_eligibility）
- [x]2.2 **candidate 归属规则**：下一 tick unmatched 观测判定——①同 `(view_id, view_player_id, epoch)` 复用同 candidate；②跨 epoch 的 `(view_id, view_player_id)` 仅弱 prior；③canonical geometry 邻域；④否则新建 `candidate_N`；同 tick 同 candidate 每 view 至多一个 observation（继承 tentative bootstrap view uniqueness）
- [x]2.3 晋升规则：双视角一致 ≥2 有效 tick 或单视角 formal identity 稳定 ≥5 tick（阈值配置化，保守默认）；晋升为 provisional roster occupant；过期窗口（配置）清理未晋升候选
- [x]2.4 单测：瞬时观测只产生 `candidate_N` 不产生 `global_player_N`；同 local 身份累积到同一候选（不扩散成几百个 candidate）；epoch 变化弱 prior 复用；同 view 双人（canonical 近距）不合并；晋升后占 slot；过期清理不影响 roster

## 3. GlobalPlayerAssociator 改造（unmatched 分流 + gate + 迟滞）

- [x]3.1 `backend/app/vision/multiview/association_global.py` `process_tick`：unmatched 观测分流——roster 未满（BOOTSTRAPPING）→ 候选池（按 2.2 归属）；roster 已满（ROSTER_ACTIVE）→ unresolved / recovery / reject，**禁止调用 new_global_id 路径**
- [x]3.2 uncertainty-aware gate：`gate_ft = min(max_reacquire_gate_ft, base_gate_ft + uncertainty_scale × prediction_uncertainty_ft)`，替换固定 `max_association_distance_ft=3.0` 的可行性门；按状态分档（稳定连续 / 历史重连 / 跨 epoch reacquire / 换人尝试更严）；参数走配置
- [x]3.3 PendingReassociation：一帧强证据须同时满足 challenger geometry 可行 + cost 优于 incumbent 超过 `switch_margin`（默认 0.15）+ challenger global 连续一致；连续 `reassociation_frames`（默认 5）帧才切换；challenger 变化/证据中断计数清零；切换记 diagnostics
- [x]3.4 单测：roster 关闭后 unmatched 不创建新 global（硬断言 `registry.players ≤ expected_player_count`）；epoch reset 后弱绑定重新证明回原 global；**N-1 帧不切换、连续 N 帧强证据才切换**；微弱优势（< switch_margin）不累积换人；challenger 每帧变化计数清零

## 4. 两级 identity continuity + roster 重建边界

- [x]4.1 `association_global.py`：保留强绑定 `(view_id, view_player_id, local_identity_epoch) → global`（epoch reset 失效，现状不变）
- [x]4.2 新增弱历史绑定 `(view_id, view_player_id) → global`：epoch reset 后保留为先验，观测经 geometry / donor / prediction 重新证明通过后复用原 global（更新 epoch），证明不足 → unresolved / 候选池，不自动继承、不新建
- [x]4.3 明确 identity epoch reset 是局部事件：SHALL NOT 触发 roster 重建；roster 重建仅由 new_match / roster_reset / participant-change 触发（registry 提供 `reset_roster()` 入口）
- [x]4.4 单测：epoch 0→1 reset 后同 local 身份在几何允许下重回同一 global 且 registry 不重建；换边/局盘切换不触发重建；显式 roster_reset 后进入新 BOOTSTRAPPING

## 5. Stale 关联资格 + Guided recovery 强约束

- [x]5.1 `global_state.py` / `association_global.py`：GlobalPlayerState 增加 association eligibility——`uncertainty > threshold` 或 `last_seen_age > threshold`（配置）时退出普通紧门匹配；仅 historical continuity / guided recovery / strong reacquire 路径回归；恢复成功后重新获得普通资格
- [x]5.2 `association_global.py` / `multiview_joint_run.py`：confirmed + cross_view_anchored + guidance `expected_global_player_id=G3` + guided candidate（`detection_origin=guided_roi`）通过 target-view pre-gate → 优先绑定 G3；G3 几何不可行 / pre-gate 拒绝 → reject / unresolved，不转投其他 global（移除/降级 `guidance_global_mismatch_penalty` 软惩罚路径）
- [x]5.3 base 优先：同 tick base formal observation 正常走普通关联，stale guidance 不得覆盖 base evidence；恢复 episode 按 base_recovered / guided_recovery_success 区分（与现有语义一致）
- [x]5.4 单测：guidance 期望 G3 但 G2 代价更低时仍绑定 G3；G3 不可行时 reject 而非转投 G2；同 tick base 证据存在时 guidance 不覆盖；stale 玩家不吸附其他观测、经强恢复路径回归后恢复资格

## 6. Composer：roster.v1 + canonical 映射（reference anchor）+ structured data + 计数

- [x]6.1 `backend/app/services/multiview_result_composer.py`：joint compose 产出 `global-player-roster.v1`（schema_version / expected_player_count / roster_occupied_count / confirmed_player_count / status / players[global_player_id ↔ Player_N ↔ Pn ↔ view bindings]）并发布 `*_json_path` / `*_url`；该产物定位为诊断 / 映射 contract
- [x]6.2 **canonical display anchor**：`Player_N` 由 reference view 的 formal local identity 决定（稳定绑定 `cam_1/Player_3` → 公开 `Player_3`）；仅有 non-reference evidence 时暂缓分配；整场 reference 缺失用 deterministic fallback（slot 顺序）并在产物标注
- [x]6.3 `fused_to_projected_tracks`：以 roster 映射把 `global_player_id` 转为 canonical `Player_N` 作为 `track_id`；球员计数区分 expected / roster_occupied / confirmed / observed，报告摘要如实报告（不硬写赛制人数）
- [x]6.4 joint compose 生成与单摄同契约的 `position_visualizations/structured/data.json`（22×10 visual grid、每球员独立 grid、`Player_N / Pn` 标签），复用 `PositionVisualizationDataBuilder`；保留旧 PNG heatmap 作为降级但不作为主路径
- [x]6.5 单测：用户可见产物无 `global_player_` 字符串；roster.v1 与内部 diagnostics 可含 internal id；`heatmaps.players[].id ∈ {Player_1..4}`；tracks 身份为 canonical 且重跑一致；遮挡场景 confirmed=3 时摘要如实报告 3

## 7. F1 冻结 roster 映射

- [x]7.1 `backend/app/vision/multiview/offline_refinement.py`：F1 消费 F0 冻结的 roster snapshot，SHALL NOT 修改 `global → Player_N` 映射、SHALL NOT 分配新 roster slot
- [x]7.2 单测：F1 运行后 roster 映射与 F0 一致；F1 不新增 slot；F1 仅改善 fused position / 补 observation

## 8. 真实视频验收（硬断言，不只跑单测）

- [x]8.1 用 job-f473d041a6 同源双摄素材（take_sync_20260720_122645_317228）重跑 joint 任务，断言：整场 `registry.players <= 4`；roster 确认前不 ACTIVE；确认后不创建 G5；epoch reset 重回同一 global 且不重建 roster；网前交叉 N-1 帧不换色
- [x]8.2 断言公开产物：report 摘要"检测到 N 条球员轨迹"中 N 为实际确认/观测人数（不再 47）；`position_visualizations/structured/data.json` 存在且 players 为 P1-P4；用户可见产物无 `global_player_`；前端 VisionPage 热力图走 SVG（非旧 PNG 图库）
- [x]8.3 跑通 `backend/tests/` 相关 multiview / joint / composer / recovery / offline_refinement 测试套件，确认无回归（含 late_fusion_v1 P0 associator 语义不变）
- [x] 8.4 更新 `docs/` 或 `structure picture.md` 中 joint_tracking_v2 的 global roster、身份链路与计数语义说明
