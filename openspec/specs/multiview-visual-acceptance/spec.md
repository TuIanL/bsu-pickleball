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

