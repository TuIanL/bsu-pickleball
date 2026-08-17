## Why

双摄协同分析在**数据层**已经完整工作：Global P1-P4 轨迹融合、跨摄 guidance ROI 重检测、F1 offline refinement 均正常产出。但分析页的视频预览仍只显示 **reference camera 自己的检测结果**（`debug_trace → views[reference_view_id].detections`），融合后的全局球员状态从未被重新投影回参考画面。结果是：远端球员在参考机位 YOLO 漏检的帧上"凭空消失"，与"系统明明知道场上有 P3"的产品语义直接矛盾。

更根本的问题是：当前正式视频叠加层的数据源是 **opt-in 的 `joint_debug_trace.v1` 诊断产物**（默认关闭），即默认配置下 joint 模式连检测框都不生成。同时该 overlay 直接透传 `global_player_<id>` 标签，违反 `player-identity-display` 的 canonical `Player_N` 硬要求。

## What Changes

- **新增 `multiview-fused-player-overlay` 能力**：把已存在的 F0/F1 evidence、Global Roster、final fused trajectory 以只读方式消费，经 canonical→target-image 投影重新生成参考画面的正式球员叠加层。
- **正式 fused overlay MUST NOT 依赖 `joint_debug_trace`**：debug trace 继续只做诊断；`debugTraceEnabled=false` 时 fused overlay 仍必须正常生成。
- **Evidence 分支决策链（非机械排序）**：每个 Global Player 每 tick 按 `F0 strong observation → accepted F1 recovered（final_source=refined_f1）→ F0 weak observation → cross_view_projected → predicted_only → hidden` 顺序判定。`refined_observed` 可优先于 weak F0（与 F1 现有"original strong 保留、recovered 补充 weak/missing"语义一致），但绝不覆盖 strong F0；证据不足时明确降级（不强行画四个框）。
- **新增 `multiview-fused-player-overlay.v1` contract**：`evidence_type` 字段标识展示证据来源，`bbox` 允许为 `null`，`cross_view_projected` 必须说明 `donor_view`；**confidence 语义拆分**为 `source_confidence`（真实检测/恢复证据原始置信）/ `overlay_confidence`（展示值得程度）/ `donor_quality`，避免单一 confidence 混淆；`uncertainty_ft` 可空（V1 无 covariance，用 donor_quality + fusion_status + geometry_valid + recency 做 gate，不制造 uncertainty）。
- **TargetViewBBoxMemory / 纯平移 reanchor**：仅合格真实观测刷新 memory；以"最近合格 bbox 尺寸 + 新投影脚点"纯平移重建虚线预测框（V1 不做透视缩放）；目标视角从无真实 bbox 历史时只显示 footpoint + identity badge + uncertainty halo，不伪造人体框。
- **F0 origin provenance mapper**：`classify_f0_origin()` 统一映射 `base / guided_roi / offline_refinement`（系统实际命名 `guided_roi`，`joint_types.py:12`），禁止 builder 内字符串直判 `"guided"`。
- **前端播放解析按 canonical `player_id` 稳定化**：新增 `resolveFusedPlayerOverlayFrame()`，支持 gap 插值、`max_overlay_gap` 禁止跨 gap 插值、`predicted_only` TTL 超限隐藏。
- **joint 模式 overlay 标签统一为 canonical `Player_N`**：废弃 `global_player_<id>` 展示标签。
- **修 OpenSpec 历史遗留冲突**：`multiview-analysis-result-composer` 中 joint overlay 使用 `GlobalPlayer_<id>` 的旧要求改为 canonical `Player_N`（以本 Change 的 MODIFIED delta 表达，archive 时合并，不直接改 base spec）。
- **scope 边界（明确不做）**：不修改 Global Player Roster、不修改 guidance 算法语义、不做 same-tick cooperative perception（另行 Change）。

## Capabilities

### New Capabilities

- `multiview-fused-player-overlay`: post-fusion 球员叠加层的正式产物契约与构建——消费 F0/F1 evidence + Roster + target-view geometry，按分支决策链生成融合预览叠加层（含 bbox 记忆/纯平移 reanchor、脚点光圈降级、身份只读 canonical Player_N）。

### Modified Capabilities

- `multiview-analysis-result-composer`: joint 模式正式视频叠加层的数据源从 `joint_debug_trace` 改为 fused evidence；overlay 球员标签从 `GlobalPlayer_<id>` 改为 canonical `Player_N`（删除旧要求）；发布 `fused_player_overlay_*` 产物契约。
- `analysis-artifacts`: 分析产物 contract 新增 `fused_player_overlay_json_path / _url / _status / _detail` 四字段，扩展 Parent 命名空间产物集。
- `video-overlay-hud`: 新增按 `evidence_type` 区分的叠加样式语义（真实观测实线 / 协同补全虚线 / 预测光圈），颜色继续表示身份、线型表示证据。
- `multiview-visual-acceptance`: joint 验收新增 `reference_observed_coverage`（baseline）与 `fused_overlay_coverage`（measured）双指标（要求 fused > reference + 硬 invariant，不预设数字 gate）；`debugTraceEnabled=false` 时 fused overlay 仍必须可生成。

## Impact

- **后端**：`backend/app/services/multiview_result_composer.py`（`_publish_joint_visual_artifacts` / `compose_joint_result`）、`backend/app/services/joint_visual_artifacts.py`、`backend/app/schemas/pipeline.py`（`AnalysisArtifacts` 加 4 字段）、`backend/app/services/storage_service.py`（新增 `fused_player_overlay_json_path()`）、`backend/app/api/routes_analysis.py`（artifact route Literal + 分支）、`backend/app/vision/multiview/offline_refinement.py`（F0 snapshot 只读消费）、`guidance.py`（复用 canonical→image 投影链，不修改语义）、新增 overlay builder 与 contract schema。
- **前端**：`src/components/platform/VideoAnalysisCard.tsx`（evidence 样式）、`src/components/platform/videoOverlayPlayback.ts`（新增 fused 解析）、`src/pages/VisionPage.tsx`（joint 模式加载优先级：fused overlay → trackingOverlay fallback）、`src/services/pipelineReportAdapter.ts`（`fused_player_overlay_*` 解析）。
- **契约**：新增 `multiview-fused-player-overlay.v1` artifact contract（含 `source_confidence` / `overlay_confidence` / `donor_quality` / 可空 `uncertainty_ft`）；`tracking_overlay` 在 joint 模式下降级为 debug-only。
- **OpenSpec**：`multiview-analysis-result-composer` 的 `GlobalPlayer_<id>` 旧要求以本 Change MODIFIED delta 表达（archive 时合并，不直接改 base spec）。
