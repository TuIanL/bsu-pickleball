## 1. 契约与投影基础

- [x] 1.1 定义 `multiview-fused-player-overlay.v1` schema：`EvidenceType` 枚举（base_observed / guided_observed / refined_observed / cross_view_projected / predicted_only）、overlay frame / player entry 结构（`bbox` 允许 null、`footpoint`、`evidence_type`、`source_confidence`、`overlay_confidence`、`donor_quality`、`donor_view`、`uncertainty_ft` 可空、`bbox_source`），并写版本化 validator（对齐 `joint_debug_trace.v1` 的既有模式）
- [x] 1.2 抽取纯投影 helper `canonical_to_target_image(global_pos, orientation, inverse_homography, frame_size) → (image_footpoint, projection_valid, failure_reason)`：复用 `guidance.py` 的 `canonical_to_local` + `court_to_image_single`，不返回数值误差边界（无 covariance 支撑），`projection_valid=false` 时禁止 projected overlay
- [x] 1.3 添加单元测试：schema 校验（bbox=null、evidence_type 枚举、cross_view 必须带 donor_view、uncertainty_ft 可空）、投影 helper 的 valid / invalid（越界 / 奇异 homography）分支

## 2. Evidence Bundle 组装

- [x] 2.1 实现 `JointOverlayEvidenceBundle`：承载 F0RefinementSnapshot、accepted F1 recovered observations（经 `final_source == refined_f1` 判定）、final fused trajectory（`global_player_id → canonical 位置` + `fusion_status`）、roster map（复用 `_build_roster_map`）、view geometry（reference_view_id、orientation、inverse_homography、frame size）
- [x] 2.2 实现 bundle 构造器：从 `MultiViewJointRunOutput`（`f0_snapshot` / `trajectory` / `diagnostics`）与 refinement 结果组装，全部只读，绝不反写 tracker / association / metrics
- [x] 2.3 添加测试：bundle 从 joint output + refinement 组装正确；F1 未运行时（`skipped_no_windows` / `rejected_by_safety_gate`）bundle 仍可基于 F0 构建

## 3. FusedPlayerOverlayBuilder（分支决策链）

- [x] 3.1 实现 `FusedPlayerOverlayBuilder.build()`：遍历 canonical ticks，对每个 `(global_player_id, canonical_tick)` 按**分支决策链**（非机械排序）判定 reference view 的 evidence_type：F0 strong observation（origin=base/guided_roi）→ base/guided_observed；否则 `final_source==refined_f1` 且存在 accepted recovered observation → refined_observed；否则 F0 weak observation → base/guided_observed；否则 donor 真实观测 + fused sample 非 predicted/conflict + geometry valid → cross_view_projected；否则短时 predicted + TTL 未过 → predicted_only；否则不渲染。`frame_index` = `reference_frame_index`，时间轴对齐 fused trajectory
- [x] 3.2 实现 F0 origin provenance mapper `classify_f0_origin(origin) -> base_observed | guided_observed`：`base → base_observed`、`guided_roi → guided_observed`、未知 origin 按 base 兜底并 warning；builder 内禁止直接字符串判断 `origin == "guided"`（系统实际命名是 `guided_roi`，`joint_types.py:12`）
- [x] 3.3 实现 F0 strong / weak 判定与 base/guided 输出：strong 需 detector/projection quality 过门（门限可配），输出真实 bbox；weak 分支在 refined 不存在时才使用
- [x] 3.4 实现 `refined_observed`：按 canonical tick + view 匹配 accepted recovered observation，输出 recovered bbox，provenance=offline_refinement
- [x] 3.5 实现 `cross_view_projected`：gate = `donor_quality（默认 ≥0.5） + fusion_status 非 predicted/conflict + projection_valid + recency（默认 ≤0.5s）`，不制造数值 uncertainty；投影 footpoint + reanchor bbox（见任务组 4）
- [x] 3.6 实现 `predicted_only`：gate = `prediction TTL + last real observation age`（F0 predictions canonical position + 最近真实观测时间），TTL 未过输出淡化光圈，否则该帧不渲染
- [x] 3.7 添加测试：分支决策链优先级（strong F0 > recovered > weak F0 > cross_view > predicted > hidden）；recovered 优先于 weak F0、不覆盖 strong F0；证据不足时该帧该球员不渲染

## 4. TargetViewBBoxMemory / 纯平移 reanchor

- [x] 4.1 实现 `TargetViewBBoxMemory`：按 `(global_player_id, target_view_id)` 维护 `last_good_bbox / last_good_footpoint / bbox_width / bbox_height / last_real_observed_at`；**仅允许合格观测刷新**（bbox 几何合法 + confidence/quality 过门 + width/height 在合理范围），错误框不得污染 memory
- [x] 4.2 实现纯平移 reanchor：`cross_view_projected` 时以新投影 footpoint 为锚点，把最近合格真实 bbox 的 width/height 原样平移（`bbox_source = last_good_bbox_reanchored`）；**V1 不做透视缩放/高度微调**；无历史 bbox 时 `bbox=null` 仅输出 footpoint + identity badge + halo；`last_real_observed_at` 超 bbox 记忆 TTL（V1 默认 2.0s）降级为 footpoint 光圈
- [x] 4.3 添加测试：reanchor 纯平移正确性（尺寸不变）、无历史不伪造、记忆过期降级、低质量观测不刷新 memory

## 5. Composer 发布与产物接线

- [x] 5.1 `AnalysisArtifacts` schema 新增 `fused_player_overlay_json_path / _url / _status / _detail` 四个字段（`backend/app/schemas/pipeline.py:41`）
- [x] 5.2 `StorageService` 新增 `fused_player_overlay_json_path()` accessor（对齐 `tracking_overlay_json_path` 模式，`storage_service.py:216`）
- [x] 5.3 artifact API route 接线：`routes_analysis.py:344` `read_analysis_artifact` 的 Literal 列表 + if/elif 分支新增 `fused-player-overlay` → `fused_player_overlay_json_path()`
- [x] 5.4 `_publish_joint_visual_artifacts()` 新增 fused overlay 发布：调用 builder → 写 Parent namespace → 补齐 `fused_player_overlay_url / status / detail` 契约（对齐 tracking_overlay 的 url/status/detail 补齐模式，确保 result 无本地绝对路径泄漏、URL 用户可访问）
- [x] 5.5 `publish_fused_artifacts()` 把 fused overlay 入口加入 `fused_manifest.json` artifacts 区
- [x] 5.6 joint 模式 `tracking_overlay` 降级为 debug-only（不再作为正式视觉层发布），单摄模式行为不变
- [x] 5.7 后端集成测试：joint compose 后 artifacts 含 `fused_player_overlay_url` 且该 URL 经 API 可访问（非 404）；`debugTraceEnabled=false` 时 fused overlay 仍生成

## 6. 前端消费与样式

- [x] 6.1 类型层新增 `FusedPlayerOverlayArtifact` 类型（对齐 `TrackingOverlayArtifact` 契约风格），pipelineReportAdapter 解析 `fused_player_overlay_*` 字段（`pipelineReportAdapter.ts:56` 附近模式）
- [x] 6.2 确认前端 artifact fetch 层已支持新 route（url 由后端下发、fetch 层按 url 加载，确认无硬编码 route 列表）
- [x] 6.3 VisionPage joint 模式加载优先级：`fusedPlayerOverlay` → `trackingOverlay`（fallback），单摄路径不动；加载状态 / 错误兜底与既有 overlay 一致
- [x] 6.4 VideoAnalysisCard 按 `evidence_type` 切换样式：1/2/3 实线、4 虚线 + 半透明（携带 donor 标识）、5 淡化 footpoint + identity badge + uncertainty halo；球员颜色仅表示身份，不随证据来源变化

## 7. 播放时间解析

- [x] 7.1 新增 `resolveFusedPlayerOverlayFrame()`：按 canonical `player_id` 对前后帧做插值（区别于 `resolveDetectionFrame` 的 track_id 语义）
- [x] 7.2 实现 gap / TTL 语义：短 gap 合法插值、超过 `max_overlay_gap` 禁止跨 gap 插值、`predicted_only` 超 TTL 立即隐藏（常量可配，默认对齐 pose 的 0.5s 风格）
- [x] 7.3 添加前端单元测试：按 player_id 插值连续性、跨 gap 不插值、预测 TTL 隐藏

## 8. 验收与 spec 归档

- [x] 8.1 用真实双摄素材跑 joint 分析，输出 `reference_observed_coverage`（baseline）与 `fused_overlay_coverage`（measured），确认 fused > reference 并报告提升百分点；不预设 82%/96% 数字 gate（第一批录像后再定）
- [x] 8.2 硬 invariant 检查：`invalid_projection_count = 0`、`unknown_public_player_id_count = 0`、`overlay_player_count_per_tick <= expected_player_count`、`cross_view_projected_without_donor = 0`、`prediction_over_ttl_rendered = 0`
- [x] 8.3 保持 delta 规范：**不直接修改 `openspec/specs/` 下的 base spec**，`GlobalPlayer_<id>` 旧要求的清理已通过本 Change 的 `specs/multiview-analysis-result-composer/spec.md` MODIFIED delta 表达，archive 时合并进 base spec
- [x] 8.4 回归：单摄模式 tracking_overlay / 播放解析不受影响；joint 模式 `debugTraceEnabled=false` 全链路（分析 → compose → API 取产物 → 前端预览）可用
