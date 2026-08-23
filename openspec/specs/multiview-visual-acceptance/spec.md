# multiview-visual-acceptance Specification

## Purpose
TBD - created by archiving change prepare-authoritative-multiview-acceptance-run. Update Purpose after archive.
## Requirements
### Requirement: Authoritative visual acceptance gate

系统 SHALL 为 Visual Acceptance Run 提供明确的 authoritative gate。只有两路实际 timing authority 均为 `source_pts`、sync quality 为 `good`、结构校验通过且 resolver 返回 `execution_mode=joint_authoritative` 与 `authoritative_joint_eligible=true` 时，运行结果才 SHALL 被标记为 authoritative acceptance。

#### Scenario: 输入满足 authoritative gate
- **WHEN** 两路 registered video sidecar 均通过校验，sync calibration identity/schema/数值合法且 quality 为 `good`
- **THEN** 系统 SHALL 允许创建或运行 `joint_tracking_v2` Visual Acceptance Run
- **AND** SHALL 在 job/run diagnostics 中记录 `joint_authoritative`、`good` 和 `true`

#### Scenario: 输入未达到 authoritative gate
- **WHEN** 任一路 sidecar 缺失、timing authority 不是 `source_pts`、sync quality 不是 `good` 或 mapping 结构非法
- **THEN** 系统 SHALL 停止 authoritative acceptance
- **AND** SHALL 输出结构化 reason、sidecar/sync diagnostics
- **AND** SHALL NOT 通过修改 JSON 字段伪装为 authoritative

### Requirement: Opt-in joint debug trace

`joint_tracking_v2` SHALL 支持 `debug_trace_enabled` 配置。默认值 SHALL 为 `false`；开启时系统 SHALL 在同一 canonical tick 上下文生成 `joint_debug_trace.v1.json`，不得重新运行 tracker、重新选择 source frame 或改变 tracking/recovery/fusion 语义。该配置 SHALL 进入 input/config signature。

#### Scenario: 默认运行不写 trace
- **WHEN** `debug_trace_enabled` 未提供或为 `false`
- **THEN** joint run SHALL 保持现有 artifact 和 diagnostics 行为
- **AND** SHALL NOT 写入逐 tick debug trace

#### Scenario: Visual Acceptance Run 开启 trace
- **WHEN** authoritative Visual Acceptance Run 显式设置 `debug_trace_enabled=true`
- **THEN** 系统 SHALL 写入 `joint_debug_trace.v1.json`
- **AND** trace SHALL 使用该 tick 已决定的 source frame、timing context、guidance snapshot、runtime result、association update 和 fused state

### Requirement: Debug trace evidence completeness

每个 trace tick SHALL 保存 canonical tick/timestamp、每路 source frame/timestamp/selection error/status、bbox/image footpoint、local player id/identity epoch/track id、binding visibility、global prediction、guidance ROI/id/donor、detection origin、pre-gate residual、lock/tracking status、canonical observations、fused position 和 recovery event。缺失字段 SHALL 显式使用 unavailable/missing 状态，而不是省略造成歧义。

#### Scenario: target view 没有 observation
- **WHEN** target source frame available 但该 view 没有 formal player observation
- **THEN** trace SHALL 保留该 view 的 source frame/timing/status
- **AND** SHALL 记录 binding、guidance/recovery attempt 和 missing observation 状态

#### Scenario: target source frame unavailable
- **WHEN** canonical tick 无法为 target 选择有效 source frame
- **THEN** trace SHALL 记录具体 availability status 和 mapping reason
- **AND** SHALL NOT 将该 tick 记录为视觉漏检或 recovery opportunity

### Requirement: Debug artifacts are separate from business truth

系统 SHALL 将 debug trace、debug MP4 和 summary report 作为 JointRun 的 diagnostic artifacts，与 `fused_player_trajectory.v2` 和现有业务报告分离。renderer SHALL 只消费已有 trace、trajectory、diagnostics、canonical frame、timing mapping 和原视频，且 SHALL 按 trace 的 source frame decision 对齐两路媒体。

#### Scenario: 生成 debug MP4
- **WHEN** trace、两路原视频和 v2 trajectory 均可读取
- **THEN** renderer SHALL 输出双路视频、canonical court panel、timeline/status panel 和 summary JSON
- **AND** SHALL 不重新运行 tracker 或按相同 frame number 拼接两路视频

#### Scenario: renderer 输入不完整
- **WHEN** trace、timing mapping、视频或必要 artifact 缺失
- **THEN** renderer SHALL 失败并指出具体缺口
- **AND** SHALL NOT 自动重跑 joint analysis

### Requirement: Natural recovery is reported without manufacturing opportunities

Visual Acceptance Run SHALL 首先运行真实自然视频，并 SHALL 原样报告 `recovery_opportunity`、`guidance_generated`、`guided_roi_invocation`、`guided_recovery_success`、`base_recovered` 和失败 reason。没有自然 recovery opportunity 时，系统 SHALL 报告零机会，不得修改算法或默认注入 controlled dropout。

#### Scenario: 自然视频发生 guided recovery
- **WHEN** 真实 run 中 target frame available、donor 合格、guidance ROI 被调用且 guided evidence 通过既有 P1-A recovery chain
- **THEN** report SHALL 展示 opportunity 到 global identity preservation 的完整漏斗

#### Scenario: 自然视频没有 recovery opportunity
- **WHEN** 真实 run 的 recovery opportunity count 为零
- **THEN** report SHALL 明确记录零 opportunity
- **AND** SHALL NOT 将该结果解释为 recovery failure 或自动启用 controlled dropout

### Requirement: Manual anchor workbench is input-only

系统 SHALL 提供一个开发/验收用的双路逐帧工作台，使用 registered `video_id` 播放两路视频，并使用与 registered video 绑定的 source PTS timing 映射展示 frame index 与 camera-local PTS。工作台 SHALL 支持逐路前后逐帧、记录/删除共同事件锚点和导出 `calibrate_dual_camera_sync.py` 的原始 JSON 输入。

#### Scenario: 记录共同事件锚点
- **WHEN** 操作者在两路视频上选定同一可见事件并记录锚点
- **THEN** 导出 JSON SHALL 保存 reference camera、camera identities 以及每路当前 source PTS
- **AND** SHALL 同时保留 frame index 作为人工复核 provenance

#### Scenario: 工作台不得伪造 authority
- **WHEN** 操作者下载锚点 JSON
- **THEN** 工作台 SHALL NOT 直接写入 `sync_calibration.json` 或修改 calibration quality
- **AND** calibration quality SHALL 继续由现有 CLI 的 residual、anchor count 和 authority resolver 判定

#### Scenario: timing API 输入不完整
- **WHEN** registered video 缺少或无法验证绑定的 PTS sidecar
- **THEN** 工作台 SHALL 显示 source timing unavailable
- **AND** SHALL NOT 使用 `frame_index / fps` 生成导出 PTS

### Requirement: fused overlay 覆盖率验收

joint 模式 visual acceptance SHALL 同时度量两个覆盖率指标：`reference_observed_coverage`（baseline：reference view 自身真实观测的帧覆盖率）与 `fused_overlay_coverage`（measured：最终可靠 overlay 的帧覆盖率，含 base/guided/refined 真实图像证据与 cross_view 可信双摄补全）。验收 SHALL 要求 `fused_overlay_coverage` 高于 `reference_observed_coverage` 并报告提升百分点，SHALL NOT 预设固定数值 gate（待真实素材跑完后再决定是否固化门槛）。验收过程 SHALL 使用真实双摄素材逐帧检查，而非仅检查"文件生成成功"。

#### Scenario: 双覆盖率度量

- **WHEN** joint visual acceptance 运行
- **THEN** 报告 SHALL 同时输出 `reference_observed_coverage`（baseline）与 `fused_overlay_coverage`（measured）
- **AND** 验收结论 SHALL 基于真实素材的逐帧检查

#### Scenario: 融合覆盖率提升

- **WHEN** fused overlay 覆盖率达到目标
- **THEN** `fused_overlay_coverage` SHALL 高于 `reference_observed_coverage`
- **AND** 缺失帧 SHALL 为证据不足的合理降级，而非单摄漏检造成的随机闪烁

### Requirement: fused overlay 硬不变量

joint visual acceptance SHALL 同时检查以下硬不变量，任一违反 SHALL 判为不通过：`invalid_projection_count = 0`（geometry 无效仍渲染投影）、`unknown_public_player_id_count = 0`（非 canonical Player_N 身份出现）、`overlay_player_count_per_tick <= expected_player_count`（单 tick 可见球员超限）、`cross_view_projected_without_donor = 0`（cross_view 缺 donor_view）、`prediction_over_ttl_rendered = 0`（超 TTL 仍渲染预测）。

#### Scenario: 投影无效即失败

- **WHEN** 任一 `cross_view_projected` 的投影 geometry 无效仍被渲染
- **THEN** `invalid_projection_count` 递增
- **AND** acceptance SHALL 判为不通过

#### Scenario: 身份与上限不变量

- **WHEN** acceptance 统计完成
- **THEN** `unknown_public_player_id_count` / `overlay_player_count_per_tick` 超限 SHALL 判为不通过
- **AND** `cross_view_projected_without_donor` / `prediction_over_ttl_rendered` 非零 SHALL 判为不通过

### Requirement: debug 产物与正式叠加层分离

`joint_debug_trace` 与正式 fused overlay SHALL 相互独立：debug trace 关闭时 fused overlay 仍可生成；debug trace 内容 SHALL 不进入正式 overlay 数据源。

#### Scenario: debug 关闭不影响正式产物

- **WHEN** `debugTraceEnabled=false` 运行 joint 分析
- **THEN** 正式 fused overlay SHALL 仍正常生成并可验收

#### Scenario: debug 内容不污染正式产物

- **WHEN** debug trace 开启时生成正式 fused overlay
- **THEN** overlay 数据源 SHALL 仍为 F0/F1 evidence，SHALL NOT 混入 debug trace 内容

### Requirement: Debug trace 可选候选检测层

`joint_debug_trace.v1` 的每个 view SHALL 支持可选 debug-only 字段 `candidate_detections`。当且仅当该 tick 该 view 状态为 `available`（即 perception 实际执行）且 tracker 存在"存活但未满足 `lock_only` formal eligibility"的 track 时，生产端 SHALL 可将这些 provisional 候选写入 `candidate_detections`（每项至少含 `bbox`、`track_id`、`confidence`）。formal `detections` 的定义、来源与过滤规则 SHALL 保持不变；`candidate_detections` SHALL NOT 进入 `frame_detections`、identity、association、fusion 或任何正式分析产物。trace validator SHALL 将 `candidate_detections` 作为可选字段校验：字段缺失时 trace 仍 SHALL 通过加载；字段存在时其值 SHALL 为 list。display-only tick（未执行 perception 的 view）SHALL NOT 写入 `candidate_detections`。

#### Scenario: bootstrap 期候选被记录且与 formal 隔离

- **WHEN** 某 `available` tick 中 tracker 存活 track 包含 track A（已满足 lock eligibility）与 track B（尚未锁定）
- **THEN** trace 该 view 的 `detections` SHALL 仅含 track A
- **AND** `candidate_detections` SHALL 含 track B 的 bbox/track_id/confidence，且不含 player_id

#### Scenario: 旧 trace 无字段仍可加载

- **WHEN** 加载不含 `candidate_detections` 字段的历史 `joint_debug_trace.v1`
- **THEN** validator SHALL 通过校验
- **AND** renderer SHALL 以空候选列表渲染，行为等同现状

#### Scenario: display-only tick 不写候选

- **WHEN** 某 tick 该 view 状态为 `available_extrapolated` 或 `fallback_valid_start`（perception 未执行）
- **THEN** 该 view SHALL NOT 出现 `candidate_detections` 内容
- **AND** 该 view 的 `detections` SHALL 保持为空

#### Scenario: 候选不污染正式产物

- **WHEN** debug trace 开启且 `candidate_detections` 非空
- **THEN** 正式 `frame_detections`、`fused_player_trajectory.v2` 与 fused overlay 数据源 SHALL 不包含任何候选 track
- **AND** `eligibility_policy` SHALL 保持 `lock_only` 语义不变

### Requirement: Debug renderer 候选框与正式框区分绘制

Debug MP4 renderer SHALL 对 `candidate_detections` 与 formal `detections` 使用视觉强区分的双层绘制：候选框 SHALL 使用细线（线宽小于正式框）与弱色，标签 SHALL 统一包含 `tracker candidate` 字样（可附 track id），SHALL NOT 显示 `Player_N` 或任何 formal 身份；正式框 SHALL 保持既有高亮实线与 `Player_N` 标注不变。生产端 SHALL 按 `candidate_track_ids = live_track_ids - eligible_track_ids` 计算候选集合，同一 tick 内 `formal_track_ids ∩ candidate_track_ids` SHALL 为空（同一 track SHALL NOT 同时以候选框和正式框出现）。同一 track 在后续 tick 完成正式锁定后，其候选框 SHALL 被正式框取代。renderer SHALL 使用 `view.get("candidate_detections", [])` 容错读取，字段缺失时 SHALL 不绘制候选框。

#### Scenario: bootstrap 期看到弱候选框

- **WHEN** 某 `available` tick 的 view 中 formal `detections` 为空、`candidate_detections` 含存活 track
- **THEN** 该 view 画面 SHALL 为每个候选绘制细线弱色框并标注 `tracker candidate`
- **AND** SHALL NOT 出现 `Player_N` 标注

#### Scenario: 同一 tick 内候选与正式集合互斥

- **WHEN** 某 `available` tick 的 view 同时产生 formal `detections` 与 `candidate_detections`
- **THEN** 两个集合的 track_id SHALL 互不相交
- **AND** 生产端 SHALL 按 `live_track_ids - eligible_track_ids` 计算候选集合

#### Scenario: 正式锁定后候选被取代

- **WHEN** track 在 tick N 为候选、在 tick M（M>N）完成 lock 进入 formal `detections`
- **THEN** tick M 画面 SHALL 仅以正式框样式绘制该 track
- **AND** 该 track SHALL NOT 再出现在候选框中

### Requirement: Debug MP4 court panel 等比绘制

Debug MP4 的 canonical court panel SHALL 使用单一 px/ft 比例绘制球场，SHALL NOT 对 20 ft 与 44 ft 两个方向使用不同比例。球场 SHALL 横置显示（44 ft 为横轴、20 ft 为纵轴），保持真实 `44:20 = 2.2:1` 外观，并 SHALL 绘制外边界、网（距底线 22 ft）、两侧 NVZ line（各距网 7 ft）与两段 service centerline（NVZ 至底线区间）。canonical `(x_ft, y_ft)` 数据 SHALL 保持不变，轴交换 SHALL 仅发生在显示层。Debug MP4 整体 SHALL 保持既有四联布局与 `1280×620` 输出尺寸契约。

#### Scenario: 球场无均匀拉伸

- **WHEN** renderer 绘制 court panel
- **THEN** 横向与纵向 SHALL 使用同一 px/ft scale
- **AND** 球场外观比例 SHALL 为 2.2:1（44 ft 边显著长于 20 ft 边）

#### Scenario: 标准球场线齐全

- **WHEN** court panel 渲染完成
- **THEN** 画面 SHALL 包含外边界、网、两条 NVZ line 和两段发球中线
- **AND** 球员位置点 SHALL 按显示层轴交换映射落在新坐标系中

#### Scenario: MP4 输出尺寸不变

- **WHEN** renderer 输出 debug MP4
- **THEN** 视频 SHALL 保持 `1280×620` 四联布局
- **AND** 既有输出尺寸契约 SHALL 不因 court panel 重绘而改变

### Requirement: 四人身份视觉验收指标
joint tracking 的视觉验收 SHALL 读取 `four-player-identification-quality.v1`，至少报告 confirmed roster、逐人 canonical coverage、最长缺口、identity switch、duplicate binding、cross-side contamination 与 ROI recovery contribution。硬不变量失败时整体 SHALL 不通过，即使平均覆盖率较高。

#### Scenario: 平均覆盖高但 P2 被错绑
- **WHEN** 四人平均 coverage 达标但存在 P2→P1 duplicate binding 或正式 cross-side contamination
- **THEN** 验收 SHALL 失败
- **AND** SHALL 指向具体 tick、view、source track、slot/global/canonical binding

### Requirement: Baseline 与定点片段对照
验收 runner SHALL 对同一素材的 baseline Job 与新 Job 做结构化对照，并支持人工标注定点 fixture。约第 2 秒 P2 应产生正确 P2 evidence；约第 4 秒 P2 projected/recovered evidence MUST NOT 使用 P1 bbox owner；P2 accepted trajectory MUST NOT 污染 P3/P4 side。

#### Scenario: 新 Job 定点验收通过
- **WHEN** runner 检查配置的 P2 可见与误绑片段
- **THEN** 每个 fixture SHALL 输出 expected/actual identity、bbox overlap、provenance 与 verdict
- **AND** 所有硬不变量 fixture SHALL 通过

### Requirement: Appearance enabled/disabled 消融验收
视觉验收 SHALL 对同一输入和固定配置比较 appearance disabled/enabled 结果，报告交叉片段 ID switch、reconnect 正确率、P2 coverage、duplicate/cross-side、descriptor availability 与额外耗时。appearance enabled MUST NOT 使任何硬不变量退化。

#### Scenario: 衣服颜色辅助交叉恢复
- **WHEN** P1/P2 在标注交叉片段内几何/运动代价接近，且衣服 descriptor 具有可靠区分度
- **THEN** enabled 运行 SHALL 保持或改善正确 identity continuity
- **AND** disabled/enabled 的结构化差异 SHALL 写入验收摘要
