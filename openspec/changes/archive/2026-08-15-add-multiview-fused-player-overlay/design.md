## Context

双摄协同分析（`joint_tracking_v2`）在**数据层**已完整工作：`MultiViewJointRun` 产出 Global P1-P4 轨迹、`GuidanceGenerator` 跨摄 guidance ROI 重检测、`F1OfflineRefinement` 离线找回。但用户可见的视频预览层仍是一个被割裂的通道：

```text
joint_output.debug_trace
    ↓ views[reference_view_id].detections
    ↓ build_joint_tracking_overlay()          # joint_visual_artifacts.py:37
    ↓ TrackingOverlayArtifact
    ↓ VideoAnalysisCard（前端）
```

三个已被代码确认的结构性问题：

1. **正式视觉层依赖 opt-in 诊断产物**：`joint_debug_trace.v1` 是 `debugTraceEnabled` 默认关闭的 diagnostic artifact（`debug_trace.py:1` "Versioned, opt-in"）。`multiview_result_composer.py:512` 只有 trace 有 ticks 才生成 overlay → 默认配置下 joint 模式连检测框都不生成。
2. **没有 post-fusion 补全**：overlay 只包装 reference view 当帧已存在的 detections，远端球员在 YOLO 漏检帧上消失，融合结果（`F0RefinementSnapshot`、final fused trajectory、accepted F1 recovered observations）从未回流到视觉层。
3. **身份标签违规**：overlay 透传 `global_player_<id>`，违反 `player-identity-display` 的 canonical `Player_N` 硬要求；且 `multiview-analysis-result-composer/spec.md:131/142` 仍写着旧要求，是历史遗留冲突。

数据基础已经齐备，不需要重做 tracking：`F0RefinementSnapshot`（`offline_refinement.py:72`）每个 canonical tick 已保存每 view 的 `observed / bbox / canonical_position / detector_confidence / source_frame_index / tracking_status`；`GuidanceGenerator`（`guidance.py:120-121`）已有完整的 `canonical_to_local → court_to_image_single` 投影链。

## Goals / Non-Goals

**Goals:**

- 新增正式产物 `multiview-fused-player-overlay.v1`：以 F0/F1 evidence + Global Roster + target-view geometry 为只读输入，生成 reference 画面的融合球员叠加层。
- 五级 Evidence 决策：`base_observed > guided_observed > refined_observed > cross_view_projected > predicted_only`，证据不足明确降级，不强行画四个框。
- 正式 fused overlay MUST NOT 依赖 `joint_debug_trace`；`debugTraceEnabled=false` 时仍必须正常生成。
- overlay 用户可见身份统一为 canonical `Player_N`（P1-P4）。
- 前端 joint 模式优先消费 fused overlay，按 canonical `player_id` 做时间解析 + gap/TTL。
- 清理 OpenSpec 历史遗留冲突（composer spec 的 `GlobalPlayer_<id>` 旧要求）。

**Non-Goals:**

- 不修改 Global Player Roster / 关联 / 身份逻辑。
- 不修改 `cross-view-player-guidance` / `guided-player-redetection` 算法语义（仅作为 overlay provenance 来源）。
- **不做 same-tick cooperative perception**（Cam2 本帧新发现即时帮 Cam1 本帧重检测）——这是独立的 Change B，需拆分 `ViewTrackingSession.step()` 事务边界。
- 不做多视角融合视频文件的编码（继续沿用"原视频 + SVG/DOM overlay"实时组合）。
- 不做透视 bbox 尺寸自适应（perspective profile）——列为 V1.1 增强。

## Decisions

### D1: 数据源 = JointOverlayEvidenceBundle（只读消费，绝不反写）

```text
F0RefinementSnapshot（每 tick 每 view 观测证据）
+ accepted F1 RecoveredViewObservation（离线找回）
+ final fused trajectory（global_player_id → canonical 位置）
+ roster_map（global_player_id → Player_N，复用 _build_roster_map）
+ view geometry（orientation / inverse_homography / frame size）
        ↓
JointOverlayEvidenceBundle（immutable）
        ↓
FusedPlayerOverlayBuilder
```

**备选**：继续用 debug trace。**否决理由**：debug trace 是 opt-in 诊断产物，承载正式视觉层是架构错位；且 trace 的 detections 只有 reference view 本地证据，没有跨摄信息。

**硬不变量**：Overlay 只消费分析结果，绝不把展示推断写回 tracker / association / metrics——保持 guidance spec 的"guidance 不能制造 measurement"精神。

### D2: 分支决策链（EvidenceType = 最终选中的展示证据类型，非机械排序）

`EvidenceType` 不是五个优先级的机械排序，而是按证据语义逐级判定的**分支决策链**。关键点：F1 的既有语义是"original strong evidence 保留、recovered evidence 补充 weak/missing view"（`multiview-offline-refinement/spec.md`），因此 **accepted recovered observation 可以优先于 F0 weak observation**，但绝不覆盖 F0 strong observation。

每个 `(Player_N, canonical_tick)` 在参考画面上的判定顺序：

```text
reference view 有 F0 strong observation（origin=base/guided_roi）
    → base_observed / guided_observed（用 F0 真实 bbox）

否则 final_source == refined_f1
且 reference view/tick 有 accepted recovered observation
    → refined_observed（用 recovered bbox，provenance=offline_refinement）

否则 reference view 有弱 F0 observation
    → base_observed / guided_observed（用 F0 bbox，接受较低质量）

否则 其他 view 当前有真实 observation
且 final fused sample 非 predicted/conflict
且 geometry 有效
    → cross_view_projected（投影 footpoint + reanchor bbox）

否则 存在短时 predicted sample 且 TTL 未过
    → predicted_only（淡化光圈）

否则
    → 不渲染（hidden）
```

| 判定结果 | 视觉呈现 |
|---|---|
| `base_observed` | 真实 bbox，实线 |
| `guided_observed` | 真实 bbox，实线 + 协同恢复标识 |
| `refined_observed` | 真实 bbox，实线，provenance=offline_refinement |
| `cross_view_projected` | 投影 footpoint + reanchor bbox，虚线/半透明 + donor_view |
| `predicted_only` | 淡化 footpoint + identity badge + uncertainty halo |

**F0 strong vs weak 判定**：strong = 该 view observation 通过质量门（detector_confidence / projection_confidence 达标，门限可配）；weak = observed 但未达 strong 门。F1 只针对 weak/missing/lost 生成 recovery window，因此 recovered 与 strong F0 不会同 tick 竞争（若发生，遵循 F1 的 original-strong 优先规则，recovered 标记 suppressed）。

**备选**：固定五级排序。**否决理由**：机械排序会把"F1 找回的更可信 bbox"压在弱 F0 之下，与现有 F1 spec 语义（recovered 补充 weak view）直接矛盾，也会让用户看到明明 refined 过却仍显示模糊弱框的怪象。

### D3: bbox 补全 = TargetViewBBoxMemory + 纯平移 reanchor，禁止把 ROI 当 bbox

`GuidanceGenerator` 的 ROI 是"搜索区域"（如 200×200 像素），不是人体框，**不得直接当 bbox**。

为每个 `(global_player_id, target_view_id)` 维护：

```text
last_good_bbox / last_good_footpoint / bbox_width / bbox_height / last_real_observed_at
```

**memory 只允许合格观测刷新**：仅当 base/guided/refined observation 满足 `bbox 几何合法 + confidence/quality 过门 + width/height 在合理范围` 时才更新 `last_good_bbox`，防止单个错误框污染后续 2 秒的 cross-view bbox。

`cross_view_projected` 时使用**纯平移 reanchor**：以新投影 footpoint 为锚点，把最近合格真实 bbox 的 width/height 原样平移过去（`bbox_source = last_good_bbox_reanchored`）。**V1 不做任何透视缩放/高度微调**（与 Non-Goals 一致，避免演化为需要调参的视觉模型）。目标视角**从无真实 bbox 历史**时，只画 `footpoint + Pn badge + uncertainty halo`，不伪造人体框——此规则为 spec invariant。

### D4: 新 contract `multiview-fused-player-overlay.v1`

```json
{
  "schema_version": "multiview-fused-player-overlay.v1",
  "reference_view_id": "cam_1",
  "frames": [{
    "frame_index": 420,
    "timestamp_seconds": 14.0,
    "players": [{
      "player_id": "Player_3",
      "label": "P3",
      "bbox": [812, 233, 851, 319],
      "footpoint": [831.5, 319],
      "evidence_type": "cross_view_projected",
      "source_confidence": 0.83,
      "overlay_confidence": 0.76,
      "donor_quality": 0.81,
      "donor_view": "cam_2",
      "uncertainty_ft": null,
      "bbox_source": "last_good_bbox_reanchored"
    }]
  }]
}
```

- `evidence_type` ∈ 五级枚举；`bbox` 允许 `null`；`cross_view_projected` 必须携带 `donor_view`。
- **confidence 语义拆开，不复用单一 `confidence`**：
  - `source_confidence`：真实 detector / recovered evidence 的原始置信（`cross_view_projected` 时来自 donor，绝不伪装成 reference-view detection confidence）；
  - `overlay_confidence`：该 presentation entity 值得展示的程度（builder 决策输出）；
  - `donor_quality`：仅 cross_view_projected 使用；
  - `uncertainty_ft`：**V1 可空**——当前 `F0RefinementSnapshot` 未持久化完整 prediction covariance，不强行制造 uncertainty；V1 用 `donor_quality + fusion_status + geometry_valid + recency` 做 gate，待 GlobalPlayerState covariance 正式进入 snapshot 后再升级为真实 uncertainty gate。
- 不复用 `FrameDetection`（其语义是"一条 YOLO 检测"），避免 detection confidence 与 presentation confidence 混淆。
- 复用 `F0TickSnapshot.reference_frame_index` 作为 `frame_index`，时间轴与 fused trajectory 对齐。

### D5: 投影链抽纯 helper（复用 guidance 实现，不复制逻辑）

把 `guidance.py` 中已有的 `canonical_to_local(orientation) + court_to_image_single(inverse_homography)` 抽为 overlay builder 直接消费的纯函数模块，输入 global canonical 位置 + target view geometry，输出：

```text
canonical_to_target_image(...)
→ image_footpoint
→ projection_valid
→ failure_reason
```

**不返回数值误差边界**（当前没有 calibration covariance 支撑该承诺）；`projection_valid=false`（如目标点超出 court / homography 奇异）时禁止生成 projected overlay。**不修改 `guidance.py` 现有语义**，只做只读复用。

### D5.1: F0 origin provenance mapper（必须，防字符串漂移）

系统实际使用的 detection origin 命名是 `Literal["base", "guided_roi", "offline_refinement"]`（`joint_types.py:12`），**不是** `guided`。Builder 内必须统一走 provenance mapper：

```python
classify_f0_origin(origin) -> base_observed | guided_observed
```

`base → base_observed`、`guided_roi → guided_observed`、未知 origin 按 base 兜底并记录 warning。禁止在 builder 内直接 `origin == "guided"` 字符串判断，否则所有 guided recovery 会被错误分类为 base。

### D6: Composer 发布 + 前端消费

- `_publish_joint_visual_artifacts()` 新增 fused overlay 发布：写 Parent namespace（`fused-player-overlay.json`）、补 `fused_player_overlay_url/status/detail` 契约，并加入 `fused_manifest.json` artifacts 区。
- `tracking_overlay` 在 joint 模式下不再作为正式视觉层发布（降级 debug-only），前端 fallback 链避免分叉。
- 前端加载优先级：`fusedPlayerOverlay` → `trackingOverlay`（fallback）→ 单摄原逻辑（完全不动）。
- `VideoAnalysisCard` 按 `evidence_type` 切换线型：实线（1/2/3）、虚线+半透明（4）、淡化光圈（5）。**颜色永远表示身份**（P3 不会因 Cam2 辅助而变色）。
- 新增 `resolveFusedPlayerOverlayFrame()`：按 `player_id`（而非本地 track_id）做前后帧解析；gap 语义对齐 pose 已有实现（`MAX_POSE_GAP_SECONDS=0.5s`），`predicted_only` 超 TTL 立即隐藏。

### D7: tracking_overlay 的 joint 模式处置

joint 模式下 `build_joint_tracking_overlay` 不再承担正式产物职责，改为仅当 `debugTraceEnabled` 时发布（或完全不发布）；单摄模式 `tracking_overlay` 行为不变。前端通过"加载优先级"自然收敛，无需后端双写。

## Risks / Trade-offs

- **投影脚点误差**（人体非地面点、homography 平面假设、镜头畸变）→ `cross_view_projected` 只用于定位补全，虚线 + uncertainty halo 可视化误差；V1 不做数值 uncertainty 承诺，改用 **`donor_quality + fusion_status（非 predicted/conflict）+ geometry_valid + recency`** 四元 gate（donor_quality 门限默认 0.5、recency 门限默认 0.5s，可配）过滤不可信投影。
- **reanchor bbox 失真**（球员快速变向/横向移动时形状可能偏离）→ V1 纯平移保持最近合格真实 bbox 尺寸、接受短暂失真；`last_real_observed_at` 距今过远（bbox 记忆 TTL，V1 默认 2.0s）时降级为 footpoint 光圈。
- **错误框污染 bbox 记忆** → memory 仅由 `bbox 合法 + quality 过门 + 尺寸合理` 的 base/guided/refined 观测刷新（D3），错误检测不会扩散到后续 cross-view 补全。
- **展示证据被误读为检测真值** → `evidence_type` 显式区分 + 线型区分 + `source_confidence` / `overlay_confidence` 拆分（D4），且 overlay 永不反写 metrics。
- **F1 recovered observation 时间对齐** → 全部通过 `canonical_tick` 索引对齐 F0 snapshot / fused trajectory，recovered observation 本身携带 source frame。
- **性能** → 每 tick 4 players × 2 views 的纯矩阵投影，量级可忽略；builder 只读不改 tracker 热路径。

## Migration Plan

1. 新增 builder 与 contract，与现有链路**并行**开发（不动 `compose_joint_result` 主路径，先独立可测）。
2. composer 切到 fused overlay 发布，`tracking_overlay` 降级；前端同步切加载优先级（旧数据仍可被 fallback 兜底）。
3. 清理 `multiview-analysis-result-composer/spec.md` 的 `GlobalPlayer_<id>` 旧要求（第 131/142 行），避免按旧 spec 改回。
4. 用真实双摄素材做 visual acceptance（不只看"文件生成成功"）：
   - `reference_observed_coverage`（baseline：reference view 自身真实观测覆盖率）
   - `fused_overlay_coverage`（measured：最终可靠 overlay 覆盖率）
   - 验收要求：`fused_overlay_coverage > reference_observed_coverage`，并报告提升百分点；同时满足硬 invariant（见下）。**不预设 82% / 96% 之类数字 gate**——等第一批真实录像跑完再决定是否固化具体门槛，避免为过拍脑袋的 96% 放宽预测 TTL 制造假连续。
   - 硬 invariant：`invalid_projection_count = 0`、`unknown_public_player_id_count = 0`、`overlay_player_count_per_tick <= expected_player_count`、`cross_view_projected_without_donor = 0`、`prediction_over_ttl_rendered = 0`。
5. 回滚策略：composer 发布开关（env flag）可一键退回旧 tracking_overlay 路径；前端 fallback 天然兼容。

## Open Questions

- `cross_view_projected` 的 donor_quality / recency 门限与 `predicted_only` 的 TTL 最终取值（V1 给默认值，visual acceptance 后校准）。
- `predicted_only` 的 gate 基准确认：V1 用 `prediction TTL + last real observation age`（F0 snapshot predictions 的 canonical position + 该 Player 最近真实观测时间），不依赖 covariance。
- 是否需要"仅显示真实检测"的评审模式开关（评审/论文场景可能想关闭协同补全）——可在实现中作为可选字段。
- `bbox_source` 枚举值（`last_good_bbox_reanchored` / `none`）是否需要扩展（如 `guided_roi`）——随实现收敛。
