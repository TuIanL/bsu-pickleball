# Tasks: fix-multiview-player-identity

## 1. display diagnostics 产物兜底（P0）

- [x] 1.1 `multiview_joint_run.py:834-859`：构建结束确保 `display_diagnostics_payload` 非 None——当构建抛错/校验失败/rows 为空时回退为最小占位 dict（`status=unavailable/failed` + detail + `rows=[]`，schema_version 保持 `player-display-diagnostics.v1`）
- [x] 1.2 `multiview_result_composer._publish_joint_player_display_diagnostics`（composer.py:706-712）：`payload` 缺失/非 dict 时构造并写盘占位 artifact（`status=unavailable` + detail），不再直接 return
- [x] 1.3 `routes_analysis.py:344-...`：产物存在但 `status=unavailable/failed` 时返回结构化 unavailable 响应（非 404）；产物文件缺失时返回结构化 unavailable（含 reason/job_id），HTTP 状态码不为 404
- [x] 1.4 新增后端单测：joint_output 缺失 payload → composer 写盘占位 + 查询 API 返回 200 unavailable（`backend/tests/test_player_display_diagnostics.py` 扩展或新文件）
- [x] 1.5 检查前端 observability 页/联合分析页对 `status=unavailable` 的展示路径，确保 200 unavailable 不误渲染为成功数据

## 2. playerMarkers team 语义 + 稳定排序（P0）

- [x] 2.1 后端新增纯函数 `canonical_player_side(player_id, doubles) -> "near"|"far"`（双打 1/2=near、3/4=far；单打 1=near、2=far），置于 `app/schemas/analysis.py` 或 tracking utils
- [x] 2.2 `backend/app/services/mock_analysis.py:_tracks_to_player_markers`：markers 按 `Player_N` 数字升序排序；`team` 改用 `canonical_player_side` 计算；非 canonical id 用 court_point.y 兜底（y<22 → near）
- [x] 2.3 前端 `pipelineReportAdapter.ts:tracksToPlayerMarkers`：先按 `Player_N` 数字排序再分配 label A-D；`team` 改用 side-from-id 纯函数（双打/单打由 `job.metadata.matchFormat` 决定）
- [x] 2.4 新增/更新前端单测：乱序输入（Player_2,Player_4,Player_1,Player_3）→ 输出按 P1-P4 排序、team=near/near/far/far、label=A/B/C/D
- [x] 2.5 新增后端单测：`_tracks_to_player_markers` 乱序输入 → team 按编号分侧；单打模式验证

## 3. bootstrap 近端大尺寸候选接纳（P1）

- [x] 3.1 `player_lock_manager._bootstrap_candidate_entries`：排序键加入"近端大尺寸优先"（bbox 面积 > 阈值 且 脚点 court_y < 近端阈值）→ 此类候选在象限内优先于"距画面中心近"的远端候选
- [x] 3.2 `player_lock_manager._is_identity_candidate` / `_classify_candidate`：对"近端 + 大尺寸 + 高清晰"候选放宽 `is_inside_tracking_area` 判定（允许 near_court_area / outside_court_visible）
- [x] 3.3 保持脚点门控硬约束：`court_position` 投影仍为必要条件，裁判/观众（脚点在 quadrants 外）不得入槽
- [x] 3.4 新增后端单测：构造近端右路大 bbox 候选 + 远端小 bbox 候选 → 近端候选锁定到 Player_2；画面中央裁判候选不被锁定

## 4. reconnect 同侧约束 + 身份互换防护（P1）

- [x] 4.1 `player_lock_manager._assign_recovery_candidates`：候选 side 与槽位 home_quadrant 的 side 不符时直接不可选（score=0）
- [x] 4.2 同侧横向错配惩罚：side 相符但 left/right 不符 → 得分乘强惩罚系数（与既有横向错配惩罚语义一致）
- [x] 4.3 `player_lock_manager.update`：检测到 side 不符的强制重连/疑似互换时，向 `PlayerIdentityDiagnostic` 追加 `event: "identity_swap_suspected"`（含 identity_id/from_track/to_track/home_quadrant/side）
- [x] 4.4 新增后端单测：near_left 槽位 LOST + 仅 far 侧候选 → 保持 LOST 且不产生 reconnected 事件；同侧 near_right 候选 → 得分受惩罚不足以达到 reconnect_threshold
- [x] 4.5 确认 `association_global.process_tick` 的 PendingReassociation 语义与 lock 层约束不冲突（同侧内 reassoc 保留）

## 5. 回归验证（P2）

- [x] 5.1 运行后端相关测试集（display diagnostics / lock manager / tracking）确认全绿
- [x] 5.2 运行前端 `npm test` 确认 adapter 单测全绿
- [x] 5.3 用 job-222b3ca877 同源视频重跑一个 joint job，人工核验：① 诊断接口返回 200 非 404 ② minimap markers 分侧正确（P1P2 near / P3P4 far）③ 近端右路球员有检测框 ④ 播放过程中 P1-P4 标签稳定不互换
- [x] 5.4 更新受影响快照/示例数据（如 demo 报告、fixtures），确保无遗留硬编码顺序依赖
