## 1. 后端产物契约与构建

- [x] 1.1 新增 `backend/app/vision/multiview/player_display_diagnostics.py`：定义 `player-display-diagnostics.v1` contract（flat 行结构，`player_id` 直接为 canonical `Player_N`）与 validator；**v1 漏斗边界冻结为 post-lock eligible detection**，spec/validator 中 MUST 明确 `eligible_detections_in_expected_gate` 不得被描述为 raw YOLO hit（raw detector / ROI / lock rejection 归因不在本 Change）
- [x] 1.2 实现分层断裂状态构建器：输入 `(view_results, associator.last_tick_decisions, roster, frame_status, pre-tick predictions)`，对每个 `roster confirmed player × available view` 生成一行，独立记录 `eligible_detection_present / position_present / court_position_present / projection_status / projection_confidence / formal_observation_emitted`（`eligible_detection_present=true, position_present=false` 与 `court_position_present=false` 必须可区分）
- [x] 1.3 抽取共享纯函数 `build_expected_player_region(predicted_position, uncertainty, target_geometry, policy)`（复用 `base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，cap `max_roi_margin_px`），guidance 与 diagnostics 共用；expected region 只来自 pre-tick prediction，`expected_region_status` 非 `available` 时 `eligible_detections_in_expected_gate=null`（MUST NOT 写 0）
- [x] 1.4 接入 `multiview_joint_run.py`：在 `process_tick`（L400）之后构建该 tick 的漏斗行，run 完成后随 joint 产物写盘；**诊断构建失败 MUST NOT 影响核心 joint result**（core 保持成功，`player_display_diagnostics_status=failed` + reason）；确认 `debugTraceEnabled=false` 路径仍生成

## 2. 只读决策可观测性

- [x] 2.1 `backend/app/vision/multiview/association_global.py`：新增只读 `last_tick_decisions: list[AssociationDecision]`（`view_id / observation_key / result / global_id / reason`），在既有决策分支（continuity / historical / guided_expected / reassoc / unresolved / candidate_admitted）处附加记录；**不改变 `process_tick()` 算法结果与门限**，既有测试应保持通过
- [x] 2.2 `backend/app/vision/multiview/guidance.py`：新增 side-effect-free `last_decisions: list[GuidanceDecision]`（`status=generated|not_eligible` + `reason`），在 `generate()` 各 return None 分支记录原因；**不改变触发语义与返回**；将 ROI 计算迁移到共享 `build_expected_player_region`
- [x] 2.3 测试：断言 observability 附加后 `process_tick()` / `generate()` 的输出与门限行为不变（核心语义回归保护）

## 3. 后端存储与 API

- [x] 3.1 `backend/app/services/storage_service.py`：新增 `player_display_diagnostics_json_path()` accessor（仿 `fused_player_overlay_json_path()` 模式）
- [x] 3.2 `backend/app/schemas/pipeline.py`：AnalysisArtifacts 扩展 `player_display_diagnostics_json_path / _url / _status / _detail` 四字段（可选扩展，缺省为空）
- [x] 3.3 `backend/app/api/routes_analysis.py`：新增 `GET /analysis/jobs/{job_id}/multiview/players/{player_id}/display-diagnostics?timestamp_ms=&window_ms=`；**直接按 `player_id == "Player_N"` 过滤产物行，不做 global id 反查**；产物不存在返回结构化 `unavailable` + reason，未知球员返回 `player_not_found`；响应合并 fused overlay 展示层 evidence_type（若存在）

## 4. 前端展示

- [x] 4.1 `src/services/analysisClient.ts`：新增 `getPlayerDisplayDiagnostics(jobId, playerId, timestampMs, windowMs)` 封装
- [x] 4.2 `src/types/report.ts`：新增 `PlayerDisplayDiagnostics` 产物类型
- [x] 4.3 双摄协同分析页：新增 per-player 显示诊断展开面板（默认折叠），展示该球员两路 view 的逐 stage 漏斗（eligible detection / position / court projection / formal observation / association / guidance / overlay），复用既有 `resolveFusedPlayerOverlayFrame` 语义合并 overlay 层；面板不声称展示 raw detector / lock rejection 归因

## 5. 测试与验收

- [x] 5.1 后端单测：分层断裂状态（`eligible_detection_present=true, position_present=false → formal_observation_emitted=false, break_stage=position_join`；`position_present=true, court_position_present=false → break_stage=projection`；JointObservation 存在但无 AssociationUpdate → `break_stage=association`）；`expected_region_status` 非 available 时 `eligible_detections_in_expected_gate=null`（非 0）；validator 边界
- [x] 5.2 后端集成测试：`debugTraceEnabled=false` 时产物仍生成；API 窗口查询（两路升序、未知球员、产物缺失三种响应）；诊断构建失败时核心 joint result 保持成功
- [x] 5.3 前端测试：诊断面板渲染与 API 封装
- [x] 5.4 用 `mvr_35ac365aec96` / job-95132a7a53 真实素材验收：00:07 P1 漏斗行应显示 `eligible_detections_in_expected_gate>=1`、`position_present` 与 `court_position_present` 真实分层状态、两路 `formal_observation_emitted=false`（复现 Phase 0 结论），产物体积 < debug trace 一个数量级
