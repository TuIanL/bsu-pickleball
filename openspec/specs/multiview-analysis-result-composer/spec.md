# multiview-analysis-result-composer Specification

## Purpose
TBD - created by archiving change 2026-08-07-integrate-multiview-analysis-orchestration. Update Purpose after archive.
## Requirements
### Requirement: 位置类指标基于 fused 重算

Composer MUST 使用 fused trajectory + `metric_eligible` 重新计算位置类指标（movement distance / speed / heatmap / zone stats），复用单摄 metrics 阶段同一套数学但输入换为 fused 轨迹。MUST NOT 复制 child 在 local frame 计算好的位置指标。

#### Scenario: fused 可用时指标来自 fused

- **WHEN** 两个 child 完成且融合产出 fused trajectory
- **THEN** Parent 报告的 movement / speed / heatmap / zone stats SHALL 由 fused 轨迹重算
- **AND** SHALL NOT 复制任一 child 的 local-frame 位置指标

#### Scenario: metric eligibility 生效

- **WHEN** fused 轨迹含 `dual_observed / single_view_fallback / conflict / predicted / unavailable` 样本
- **THEN** `predicted` 与 `unavailable` 样本 SHALL 不计入 movement / heatmap（`metric_eligibility_policy`）
- **AND** `predicted` 样本仍可用于可视化

### Requirement: 继承 reference-view 结果

Composer MUST 从 reference view 继承非位置类结果：pose / ball / action classification / overlay video / serve 等，并如实标注其来源是 reference view（不伪装成融合结果）。继承 MUST 补齐产物契约：除复制文件与填写 `*_json_path` 外，SHALL 设置 `*_url`（指向 Parent 命名空间）与 `*_status`/`*_detail`（继承自 reference child 的落盘结果）。GB 级叠加视频 SHALL NOT 复制到 Parent 命名空间，改为引用 child 的 URL。

#### Scenario: 数据来源如实标注

- **WHEN** Parent 报告同时包含 fused 位置指标与 reference-view 的非位置结果
- **THEN** 报告 SHALL 明确区分哪些数据来自多视角融合、哪些来自 reference view
- **AND** 不得将 reference-view 结果标注为融合结果

#### Scenario: 产物契约完整

- **WHEN** Composer 继承 reference child 的产物
- **THEN** 每个继承产物的 `*_url` SHALL 指向 Parent 命名空间（`/api/analysis/jobs/{parent_id}/artifacts/{route}`）
- **AND** 对应 `*_status` / `*_detail` SHALL 继承自 child 落盘结果，使前端视觉层状态正确

#### Scenario: 大视频引用 child 而非复制

- **WHEN** reference child 存在叠加视频（`analysis_overlay.mp4`）
- **THEN** Parent 的 `analysis_overlay_video_url` SHALL 引用 child 的 URL
- **AND** SHALL NOT 复制该视频文件到 Parent 命名空间

### Requirement: 归一化到 Parent namespace

Composer MUST 把 P0 fused artifacts 与 diagnostics 发布到 Parent artifact namespace（`/jobs/{parent_id}/artifacts/...`），并生成 Parent-owned `report.json` 与 artifact manifest。报告内 `job_id`、artifact URL、`report_id` 均 MUST 指向 Parent，MUST NOT 指向 internal child。

#### Scenario: 产物归 Parent

- **WHEN** Composer 完成组装
- **THEN** `fused_player_trajectory.v1` 与 `fused_diagnostics.json` SHALL 经 Parent artifact 端点可访问
- **AND** Parent 报告内的所有引用 SHALL 解析到 Parent 自身

#### Scenario: 内部 child 不泄漏

- **WHEN** Parent 报告已生成
- **THEN** 报告 SHALL NOT 包含 child 的 `job_id`、child `report_id` 或指向 child 的 artifact URL
- **AND** child 标识只出现在 provenance / 技术详情中

### Requirement: artifact manifest 作为 Parent 唯一产品出口

Parent 报告 MUST 内嵌 `artifacts` 清单作为产品层唯一出口（`playerTrajectory / fusionDiagnostics / referenceOverlay`，各带 `source` 与 `url`）。P0 的 `MultiViewFusionRun` 产物目录（`multiview/run/<run_id>/`）MUST 视为中间产物，Composer MUST 把 fused artifacts 与 diagnostics **复制/改写 URL 到 Parent artifact 命名空间**，产品层 MUST NOT 引用 fusion run 目录。

#### Scenario: manifest 列出产品产物

- **WHEN** 双摄融合完成
- **THEN** Parent 报告 SHALL 内嵌 `artifacts` 清单，列出 `playerTrajectory`（`source: fused`）、`fusionDiagnostics`、`referenceOverlay`（`source: cam_1`）及各自 Parent 命名空间 URL
- **AND** 清单内所有 URL SHALL 解析到 Parent 自身

#### Scenario: 前端只消费 Parent 命名空间

- **WHEN** 前端渲染双摄结果
- **THEN** 所有数据来源 SHALL 经 Parent artifact 命名空间 / manifest 取得
- **AND** SHALL NOT 出现指向 `multiview/run/<run_id>/` 的引用

### Requirement: fallback 同样 compose Parent 报告

当执行确定性单视角降级（sync 不可用或单路失败）时，Composer MUST 仍重新生成 Parent-owned 报告：内容可继承成功 child 的结果，但所有权必须归 Parent，并携带 `analysis_source` provenance（`mode / source_job_id / source_view / reason`）。

#### Scenario: B 机位失败降级

- **WHEN** cam_2 失败、Parent 以 cam_1 单视角降级
- **THEN** Parent 报告 SHALL 包含 cam_1 的结果但所有权归 Parent
- **AND** provenance SHALL 记录 `{mode: "single_view_fallback", source_job_id: <child-a>, source_view: "cam_1", reason: "cam_2_failed"}`

#### Scenario: sync 不可用降级

- **WHEN** 两路均完成但 sync 不可用、未执行融合
- **THEN** Parent 报告 SHALL 使用确定性单视角结果（reference view 优先）
- **AND** 展示「未执行多视角融合」的明确提示
- **AND** provenance SHALL 记录 `mode: "single_view_fallback"` 及原因

### Requirement: 修复 getter 名不匹配产物继承

对 storage 访问器名与 `*_json_path` 后缀不一致的产物（`detections` / `analysis_overlay_video` / `serve_debug_overlay` / `player_render_trajectory`），Composer MUST 使用显式访问器名继承，不得再因 getter 名不匹配被静默跳过。

#### Scenario: 四类产物被正确继承

- **WHEN** reference child 生成了 `detections`、`analysis_overlay_video`、`serve_debug_overlay`、`player_render_trajectory`
- **THEN** 这些产物 SHALL 通过显式访问器名复制到 Parent 命名空间（或引用 child URL）
- **AND** 对应 `*_url` / `*_status` SHALL 在 Parent 结果中可用

### Requirement: Parent 结果补全视频源与球员数

Composer 生成的 Parent `AnalysisPipelineResult` SHALL 提供 `source_video_url`（基于 Parent 的 `videoId`）与 `observed_player_count`（fused 轨迹中的去重球员数），使前端能展示视频源与球员统计。

#### Scenario: 补全字段

- **WHEN** Composer 生成 Parent 结果
- **THEN** `artifacts.source_video_url` SHALL 基于 Parent 的 `videoId` 生成
- **AND** `observed_player_count` SHALL 等于 fused 轨迹中不同 `global_player_id` 的数量

### Requirement: v1/v2 独立 writer + 公共 version-aware reader

系统 SHALL 提供独立 artifact writer:`late_fusion_v1 → writer_v1 → fused_player_trajectory.v1`(P0 writer 永远保留);`joint_tracking_v2 → writer_v2 → fused_player_trajectory.v2`。系统 SHALL 提供公共 `load_fused_trajectory(path)` reader:按 schema_version 归一化(`normalize_v1` / `normalize_v2`)为 Composer 消费的 internal model。

#### Scenario: version-aware 读取

- **WHEN** Composer 需要消费 fused trajectory
- **THEN** 系统 SHALL 按 schema_version 选择 v1/v2 归一化
- **AND** SHALL NOT 依赖"v1 reader 能读 v2 未知字段"的假设

#### Scenario: late_fusion 保留 v1

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** 产物 SHALL 为 `fused_player_trajectory.v1`(writer_v1 不升级)
- **AND** 与 joint 的 v2 独立,A/B 为两个稳定版本

### Requirement: joint_tracking_v2 compose 来源

当 Parent 的 `multiviewExecutionMode=joint_tracking_v2` 时,Composer SHALL 从 Parent-owned `JointViewRuntime` A/B 与 `MultiViewJointRun` 获取产物,而非从 reference child 继承。正式视频叠加层（fused player overlay）SHALL 来自 `multiview-fused-player-overlay.v1` 构建产物;overlay 球员标签 SHALL 使用 canonical `Player_1/2...`(展示为 P1-P4),不使用 `GlobalPlayer_<id>` 或 child 局部的 `Player_<id>`。

#### Scenario: joint compose 来源

- **WHEN** joint Parent 完成 joint run
- **THEN** Composer SHALL 从 JointRun 获取 cam_1 / cam_2 view artifact 与 fused trajectory
- **AND** SHALL NOT 依赖 reference child 继承路径

#### Scenario: 正式叠加层使用 fused overlay

- **WHEN** joint 模式渲染视频 overlay
- **THEN** 数据源 SHALL 为 `multiview-fused-player-overlay.v1` 构建产物（F0/F1 evidence + roster + geometry）
- **AND** SHALL NOT 从 `joint_debug_trace` 聚合正式检测框

#### Scenario: 全局身份标签

- **WHEN** joint 模式渲染视频 overlay
- **THEN** 球员标签 SHALL 来自 canonical `Player_N`（P1-P4）
- **AND** 同一真实球员在双摄下 SHALL 显示同一 canonical 标签
- **AND** `global_player_<id>` SHALL NOT 出现在面向用户的 overlay 字段

### Requirement: fused overlay 产物发布

joint 模式 Composer SHALL 把 `multiview-fused-player-overlay.v1` 发布到 Parent artifact 命名空间,补齐 `fused_player_overlay_url` / `fused_player_overlay_status` / `fused_player_overlay_detail` 契约,并将 overlay 入口加入 `fused_manifest.json` 的 artifacts 区。`tracking_overlay` 在 joint 模式 SHALL 不再作为正式视觉层发布(降级 debug-only),单摄模式行为不变。

#### Scenario: joint 模式发布 fused overlay

- **WHEN** joint Parent 完成 compose
- **THEN** Parent artifacts SHALL 包含 `fused_player_overlay_url`
- **AND** `fused_manifest.json` artifacts 区 SHALL 包含 fused overlay 入口

#### Scenario: joint 模式 tracking_overlay 降级

- **WHEN** joint 模式生成视觉产物
- **THEN** `tracking_overlay` SHALL 不作为正式视觉层发布
- **AND** 单摄(非 joint)模式 `tracking_overlay` SHALL 保持既有行为

### Requirement: late_fusion_v1 compose 不变

`executionMode=late_fusion_v1` 的 Composer 行为 SHALL 完全保持 P0 现状:位置类指标基于 fused 重算、非位置类产物从 reference child 继承、`fused_manifest.json` 作为 Parent 唯一出口。

#### Scenario: late_fusion child inheritance 保持

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** Composer SHALL 从 reference child 继承 pose/ball/overlay/serve 等
- **AND** 位置类指标基于 fused trajectory 重算(与 P0 一致)

### Requirement: refinement manifest 生命周期

`joint_tracking_v2` 的 fused manifest SHALL 记录 F1 offline refinement 的完整生命周期。Parent `canonicalStatus` 在 F1 recovery、re-fusion、safety gate 和 artifact publication 完成前 SHALL 保持 `running`；F0 是中间态，不得在 F1 尚未判定时被宣称为最终结果。

manifest 的 `refinement` 字段 SHALL 包含：

```text
status: skipped_no_windows | completed | rejected_by_safety_gate | failed_fallback
firstPassArtifact: fused_player_trajectory.f0.v2.json
recoveredObservations: recovered_view_observations.v1.json | null
refinedArtifact: fused_player_trajectory.f1.v2.json | null
final_source: refined_f1 | first_pass_f0
metrics: F0/F1 acceptance metrics and thresholds
```

产物 SHALL 独立写入 JointRun 目录，F1 SHALL 由 formal re-fusion 和完整 temporal filtering 生成，SHALL NOT 由 append recovered fused samples 生成。Composer 的最终产品引用 SHALL 按 `final_source` 选择 F1 或 F0；Candidate F1 即使被 safety gate 拒绝，也 SHALL 保留供 A/B 和诊断。

#### Scenario: F1 完成并采用

- **WHEN** joint run 完成 recovery、formal re-fusion 且通过 `RefinementAcceptanceGate`
- **THEN** manifest SHALL 记录 `refinement.status=completed`、`final_source=refined_f1`
- **AND** `refinedArtifact` SHALL 指向 `fused_player_trajectory.f1.v2.json`
- **AND** Parent 产品轨迹 SHALL 消费 F1

#### Scenario: 门拒绝回退

- **WHEN** F1 正常执行但被 `RefinementAcceptanceGate` 拒绝
- **THEN** manifest SHALL 记录 `refinement.status=rejected_by_safety_gate`、`final_source=first_pass_f0`
- **AND** Parent 产品 SHALL 消费 F0
- **AND** Candidate F1、recovered evidence 和 F0/F1 metrics SHALL 保留供 A/B

#### Scenario: 无窗口跳过

- **WHEN** F0 没有任何符合 donor、target availability 和 target weak/missing/lost 条件的窗口
- **THEN** manifest SHALL 记录 `refinement.status=skipped_no_windows`、`final_source=first_pass_f0`
- **AND** SHALL 明确区分“无 eligible window”与“F1 执行失败”

#### Scenario: 异常回退

- **WHEN** F1 在第二遍解码、检测、re-fusion、metrics 或 artifact publication 阶段抛出异常
- **THEN** manifest SHALL 记录 `refinement.status=failed_fallback`、`final_source=first_pass_f0`
- **AND** Parent SHALL 保持可消费的 F0 结果

#### Scenario: F0 不可变与原子发布

- **WHEN** F1 生成、被采用或被拒绝
- **THEN** `fused_player_trajectory.f0.v2.json` SHALL 保持原样且可通过 hash/内容比较验证
- **AND** 系统 SHALL 在 F0、recovered、Candidate F1 和 diagnostics 写出完成后最后更新 Parent manifest
- **AND** manifest coherent 之前 Parent SHALL NOT 标记为 completed

#### Scenario: 历史产物兼容

- **WHEN** Composer 消费没有 `refinement` 字段的历史 joint v2 产物
- **THEN** 系统 SHALL 将其视为 F0-only
- **AND** 默认 `final_source=first_pass_f0`，不得假设 F1 artifact 存在

### Requirement: Manifest 反映真实多视角证据

`MultiViewResultComposer` SHALL 根据 diagnostics 的有效证据计算并写入 effective mode。manifest 的 `analysis_source`、fused diagnostics 和 Parent result message SHALL 使用一致的模式语义。

#### Scenario: 零双摄证据不标正常融合

- **WHEN** fused artifact 只有 reference single-view fallback samples
- **THEN** manifest 的 mode SHALL 为 `single_view_fallback`
- **AND** manifest SHALL 保留 fallback reason 与 evidence counters

#### Scenario: 部分覆盖标 degraded

- **WHEN** 运行包含双摄证据但 secondary 覆盖低于正常融合阈值
- **THEN** manifest SHALL 为 `multiview_degraded`
- **AND** diagnostics SHALL 暴露 effective ratio

### Requirement: joint compose 视觉层产物契约
joint_tracking_v2 模式的 `compose_joint_result` SHALL 产出或继承前端视觉层产物（tracking_overlay / pose_overlay / heatmaps / player_render_trajectory 等），并补齐 `*_url` / `*_status` / `*_detail` 契约，使前端框架、骨架、热力图与小地图可用。热力图 / scatter / structured data SHALL 使用 canonical `Player_N / Pn` 标签（经 roster 映射），MUST NOT 直接使用 `global_player_N` 作为用户可见标签。joint 路径 SHALL 生成与单摄同契约的 `structured/data.json`（22×10 visual grid、每球员独立 grid、`heatmaps.players[].id ∈ {Player_1..4}`），复用 `PositionVisualizationDataBuilder`，使前端 `StructuredHeatmap` 走 SVG 渲染而非旧 PNG 降级。

#### Scenario: joint 结果含视觉层产物

- **WHEN** joint Parent 完成分析
- **THEN** Parent artifacts SHALL 包含 `tracking_overlay_url`、`pose_overlay_url`、`heatmaps_url` 等
- **AND** 前端视觉层 SHALL 可加载（非 unavailable）

#### Scenario: 产物来源如实标注

- **WHEN** joint 模式产出视觉层产物
- **THEN** 产物 SHALL 标注来源（joint run / canonical player 标签）
- **AND** SHALL NOT 伪装为 child 单摄产物

#### Scenario: joint 产出 structured data

- **WHEN** joint 分析完成且 roster confirmed
- **THEN** 系统 SHALL 生成 `position_visualizations/structured/data.json`
- **AND** `heatmaps.players[].id` SHALL 仅含 `Player_1..Player_4`
- **AND** `heatmaps.players[].label` SHALL 为 `P1..P4`

#### Scenario: 公开产物无 global id

- **WHEN** joint 分析完成
- **THEN** 用户可见的轨迹身份 / 热力图标签 / report SHALL NOT 包含 `global_player_`
- **AND** 全部使用 canonical `Player_N / Pn`

### Requirement: global-player-roster.v1 产物（诊断 / 映射 contract）
joint compose SHALL 产出 `global-player-roster.v1` 产物（JSON，定位为**内部诊断 / 映射 contract**，非用户展示 identity）：包含 `schema_version`、`expected_player_count`、`roster_occupied_count`、`confirmed_player_count`、`status`（`bootstrap` / `confirmed`）与每个 roster 玩家的 `global_player_id`、canonical `player_id`（`Player_N`）、`label`（`Pn`）及 `bindings`（各 view 的 `view_player_id` 与 track provenance）。该产物与内部 diagnostics 可保留 internal `global_player_N`；用户可见的 trajectory / metrics / structured visualization / report 中 SHALL NOT 出现 `global_player_`。Composer 将 fused 样本转 tracks 时 SHALL 以 roster 映射将 `global_player_id` 转换为 canonical `Player_N`。**canonical `Player_N` 由 reference view 的 formal local identity 决定（display anchor）**：稳定绑定 reference view 的 `Player_N` 则公开身份为该 `Player_N`；仅有 non-reference evidence 时暂缓分配，reference binding 出现后再确定；整场 reference 缺失使用 deterministic fallback（如 slot 顺序）并在产物中标注。

#### Scenario: roster 产物可发布

- **WHEN** joint 分析完成
- **THEN** Parent artifacts SHALL 包含 roster.v1 的 `*_json_path` / `*_url`
- **AND** 每个 roster 玩家 SHALL 有 `global_player_id ↔ Player_N ↔ Pn` 完整映射

#### Scenario: 轨迹身份为 canonical

- **WHEN** Composer 由 fused 样本生成 `ProjectedTrackPoint`
- **THEN** `track_id` SHALL 为 canonical `Player_N`（经 roster 映射，reference binding 决定）
- **AND** 同一物理球员在不同重跑中的公开身份 SHALL 保持一致（非 slot 顺序编号）

#### Scenario: 诊断产物保留 internal id

- **WHEN** 检查 `global-player-roster.v1` 或内部 diagnostics
- **THEN** 其中 SHALL 可包含 internal `global_player_N`
- **AND** 用户可见产物 SHALL NOT 包含该字符串

### Requirement: 球员计数语义
Composer / report 的球员统计 SHALL 区分并明确语义：`expected_player_count`（赛制人数）、`roster_occupied_count`（已占 slot 数）、`confirmed_player_count`（已确认玩家数）、`observed_player_count`（实际有观测的玩家数）。报告摘要 SHALL 按实际确认 / 观测人数如实呈现，MUST NOT 为避免大量碎片轨迹而硬写 `expected_player_count`。

#### Scenario: 遮挡致只确认 3 人

- **WHEN** 双打任务因遮挡最终只确认 3 名玩家
- **THEN** 摘要 SHALL 如实报告确认 / 观测人数（如 3）
- **AND** 不得为凑数报告"检测到 4 条球员轨迹"

#### Scenario: 碎片轨迹不计入

- **WHEN** 分析产生大量 transient candidate（从未晋升）
- **THEN** 球员计数 SHALL 基于 roster / confirmed / observed 玩家
- **AND** candidate 数 SHALL NOT 计入公开球员计数

### Requirement: F1 offline refinement 冻结 roster 映射
F1 offline refinement SHALL NOT 改变 roster 身份映射：不得修改 `global → Player_N` 对应关系，SHALL NOT 在 F1 阶段分配新 roster slot。roster snapshot SHALL 与 F0 snapshot 一起冻结；F1 仅可补充 observation、改善 fused position。

#### Scenario: F1 不改身份

- **WHEN** F1 运行于已确认 roster 之上
- **THEN** F1 输出 SHALL 保持 F0 的 global→canonical 映射
- **AND** SHALL NOT 新增或重分配 roster slot

### Requirement: joint 模式发布球立体产物
系统 SHALL 使 `multiview_analysis_result_composer` 在 joint 模式下正式发布球相关产物：不可变 `multiview_ball_stereo_evidence.v1` 与用户轨迹 `reconstructed_ball_trajectory.v3`。

#### Scenario: 发布 stereo evidence
- **WHEN** joint 任务已生成球立体证据
- **THEN** composer SHALL 发布 `multiview_ball_stereo_evidence.json`
- **AND** 该 evidence SHALL 为不可变原始证据，供审计与后续重建引用

#### Scenario: 发布 v3 用户轨迹
- **WHEN** joint 任务已生成多视角估算三维球路
- **THEN** composer SHALL 在同一语义 slug 发布 `reconstructed_ball_trajectory.json`（schema `.v3`）
- **AND** 输出整体可用状态 `FULL_ESTIMATED_3D / PARTIAL_3D / LANDING_ONLY / UNAVAILABLE` 与指标级 validity 分级

#### Scenario: 产物可用性降级
- **WHEN** 双摄 3D 证据不足但落点权威可用
- **THEN** composer SHALL 发布 `LANDING_ONLY` 状态与可用落点
- **AND** 不得回退为假 2.5D 默认产物

