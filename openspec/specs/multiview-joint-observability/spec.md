# multiview-joint-observability Specification

## Purpose
TBD - created by archiving change surface-multiview-joint-observability. Update Purpose after archive.
## Requirements
### Requirement: 后端权威可观测投影

系统 SHALL 通过后端 `MultiviewObservabilityProjector` 将已发布的 timing、fusion、online recovery、offline refinement 和可选 debug artifacts 投影为 `multiview_observability_summary.v1`。该 summary SHALL 是可重建的产品 DTO，不得成为独立算法真值；前端 MUST NOT 重算 authoritative eligibility、sync quality、Safety Gate 或 `final_source`。

#### Scenario: Authoritative joint 直接投影
- **WHEN** 已有权威产物记录 `execution_mode=joint_authoritative` 且 `authoritative_joint_eligible=true`
- **THEN** summary SHALL 投影该结论及每路 timing authority
- **AND** projector SHALL NOT 使用前端或新增阈值重新评估该结论

#### Scenario: Safety Gate 结论不被二次推导
- **WHEN** refinement manifest 记录 `status=rejected_by_safety_gate` 和 `final_source=first_pass_f0`
- **THEN** summary SHALL 直接返回发布被拒绝、结构化 reason 和最终 F0
- **AND** projector 和前端 MUST NOT 通过 conflict delta 或其他 metrics 重新决定发布结果

### Requirement: 独立状态域与可用性

Summary SHALL 将 `SYNC`、`FUSION`、`RECOVERY`、`REFINEMENT` 和 `DEBUG` 表达为独立 section，每个 section SHALL 包含 `availability`、`status` 和可选结构化 `reason_code`。`availability` SHALL 区分 `available`、`partial`、`unavailable` 和 `not_applicable`；某一诊断证据缺失 MUST NOT 自动将其他 section 标记为失败或不可用。

#### Scenario: Debug 缺失不影响正式诊断
- **WHEN** joint 任务未开启 `debugTraceEnabled` 但已产出 timing、fusion、recovery 和 refinement 正式诊断
- **THEN** `DEBUG` SHALL 显示 `unavailable` 及未开启详细诊断的 reason
- **AND** 其他四个 section SHALL 独立正常返回

#### Scenario: 历史诊断只部分存在
- **WHEN** 历史 multiview 任务只具有某个 section 的部分字段
- **THEN** 该 section SHALL 返回 `partial` 和缺失证据 reason
- **AND** 系统 MUST NOT 用零值伪装缺失计数

### Requirement: 执行模式适用性

可观测 API 和页面 SHALL 明确区分非 multiview、`late_fusion_v1`、degraded joint 和 authoritative joint，不得将“不适用”或“可运行但非权威”表达为算法执行失败。

#### Scenario: 非 multiview 任务
- **WHEN** 客户端请求 single-view job 的 multiview observability 资源
- **THEN** API SHALL 返回 `404` 和结构化 `not_applicable`
- **AND** 页面 SHALL 显示不适用状态与返回任务页入口

#### Scenario: Late fusion 任务
- **WHEN** multiview job 的 requested/effective mode 为 `late_fusion_v1`
- **THEN** 页面 SHALL 保留并显示可用的 sync/fusion 事实
- **AND** online recovery 和 offline F1 SHALL 明确标记为 `not_applicable`

#### Scenario: Degraded joint 任务
- **WHEN** joint execution 已发生但 `authoritative_joint_eligible=false`
- **THEN** 页面 SHALL 显示 joint execution 存在、非权威状态及后端 reason
- **AND** MUST NOT 简化为“同步失败”或“未联合分析”

#### Scenario: Authoritative joint 任务
- **WHEN** 后端投影 `joint_authoritative`、`authoritative_joint_eligible=true` 且两路 authority 为 `source_pts`
- **THEN** 页面 SHALL 明确显示 GOOD、`source_pts` 和权威联合分析

### Requirement: 同步与融合事实展示

Summary SHALL 分别投影 timing authority/sync mapping 和 fusion participation/quality，不得将“融合完成”等同于“权威同步”。Sync section SHALL 在事实可用时包含 reference view、per-view authority、sync quality、execution mode、authoritative eligibility、selection error 摘要和 frame selection status；Fusion section SHALL 在事实可用时包含 fusion status counts、metric eligibility 和视角差异摘要。

#### Scenario: 同步好但融合覆盖有限
- **WHEN** timing authority 为 authoritative good，但 fusion diagnostics 显示大量 single-view fallback
- **THEN** Sync section SHALL 保持权威同步结论
- **AND** Fusion section SHALL 独立显示双路共同观测覆盖有限

### Requirement: Recovery funnel 和 episode 投影

系统 SHALL 将正式 recovery diagnostics 投影为漏斗，并将同一 `recovery_episode_id` 的多个 runtime ticks 聚合为一个产品级 episode。漏斗 SHALL 区分 opportunity、guidance、ROI/candidate/gates、formal local identity、expected-global preservation、guided success 与 base recovery，且 SHALL NOT 将 guidance count 表达为 recovery success count。

#### Scenario: Guided success 被正确计数
- **WHEN** 真实 P1-A run 包含经 target-view 真实像素证据、formal local identity 与 expected-global preservation 确认的 guided recovery
- **THEN** Recovery UI SHALL 在漏斗中计入 guided success
- **AND** SHALL 提供对应 episode 列表项

#### Scenario: 多 tick 恢复过程聚合为 episode
- **WHEN** 同一 player/target 的一个 recovery episode 内包含多次 guidance、pre-gate reject、lock reject 并最终成功
- **THEN** 默认列表 SHALL 返回一个 outcome 为 `guided_recovery_success` 的 episode
- **AND** episode SHALL 保留 guidance attempts、pre-gate rejections 和 lock rejections 计数

#### Scenario: 未成功 episode 保留失败结果
- **WHEN** recovery episode 在 guidance、pre-gate、lock 或 global assignment 阶段终止且没有 formal success
- **THEN** episode SHALL 使用 `guidance_failed`、`pre_gate_rejected`、`lock_rejected` 或 `global_mismatch` 等结构化 outcome
- **AND** SHALL NOT 生成一系列默认可见的逐 tick 日志项

#### Scenario: Base 自恢复不计为 guided success
- **WHEN** episode 以 same-tick base observation 恢复
- **THEN** episode outcome SHALL 为 `base_recovered`
- **AND** guided recovery success count SHALL NOT 增加

### Requirement: Recovery episode 分页与筛选 API

`GET /api/analysis/jobs/{job_id}/multiview/recovery-events` SHALL 使用 opaque cursor 返回 episode 分页，响应 SHALL 包含 `items`、`next_cursor` 和 `total_estimate`，并 SHALL 支持 `limit`、`outcome`、`global_player_id`、`donor_view`、`target_view`、`from_ms` 和 `to_ms` 筛选。

#### Scenario: 组合筛选 recovery episodes
- **WHEN** 客户端指定 outcome、target view 和时间范围
- **THEN** API SHALL 只返回同时满足这些条件的 episodes
- **AND** `next_cursor` SHALL 可用于继续同一筛选集合

#### Scenario: 只有漏斗而无 episode 证据
- **WHEN** 正式诊断可以提供 recovery funnel，但历史任务不具备可投影 episode 证据
- **THEN** Recovery section SHALL 保留漏斗并标记 episode availability 为 `partial` 或 `unavailable`
- **AND** episode API SHALL 返回空 `items` 和结构化 reason，不得加载 raw trace 填充结果

### Requirement: Opt-in canonical debug 回放

Debug MP4 SHALL 保持 `debugTraceEnabled` opt-in 产物，不得成为正常 `joint_tracking_v2` 任务完成或 observability summary 可用的前置条件。视频存在时，系统 SHALL 通过 `/multiview/debug-video` 提供可 seek 的 canonical MP4；浏览器 MUST NOT 请求 `joint_debug_trace.v1.json`。

#### Scenario: Episode 定位到 debug video
- **WHEN** episode 与 canonical debug MP4 都可用
- **THEN** 后端 SHALL 在 episode 中返回 `debug_video_seek_ms`
- **AND** 用户选择该 episode 时页面 SHALL 定位单个 debug video 播放器到该时间

#### Scenario: Debug video 未生成
- **WHEN** 任务未生成 debug MP4
- **THEN** debug video endpoint SHALL 返回结构化 `404`
- **AND** Debug Replay 区域 SHALL 说明本任务未开启详细诊断回放
- **AND** Sync、Fusion、Recovery 和 Refinement 区域 SHALL 仍可使用

#### Scenario: 浏览器不加载 raw trace
- **WHEN** 用户打开双摄协同分析页并查看 recovery episodes 或 debug video
- **THEN** 浏览器请求中 MUST NOT 包含 `joint_debug_trace.v1.json` 或等价 raw trace 资源

### Requirement: Offline refinement 发布语义

Refinement section SHALL 分别表达离线精修执行状态、Candidate F1 生成状态、Safety Gate 发布决策和最终产品数据源。`rejected_by_safety_gate` SHALL NOT 被表达为离线精修执行失败；`failed_fallback` SHALL 与安全门拒绝明确区分。

#### Scenario: Candidate F1 生成但发布被拒绝
- **WHEN** refinement 已完成并生成 Candidate F1，Safety Gate 记录 `rejected_by_safety_gate` 且 `final_source=first_pass_f0`
- **THEN** UI SHALL 同时显示精修完成、Candidate F1 已生成、发布被拒绝、拒绝原因和最终 F0
- **AND** UI MUST NOT 显示“离线精修失败”

#### Scenario: F1 执行异常回退
- **WHEN** refinement manifest 记录 `failed_fallback`
- **THEN** UI SHALL 显示精修执行异常与最终稳定回退 F0
- **AND** MUST NOT 将该状态标记为 Safety Gate rejection

#### Scenario: F1 通过并发布
- **WHEN** refinement manifest 记录 `status=completed` 和 `final_source=refined_f1`
- **THEN** UI SHALL 明确显示 Safety Gate 通过且最终产品消费 F1

### Requirement: 独立双摄协同分析页

前端 SHALL 在 `/analysis/{jobId}/multiview` 提供独立双摄协同分析页，MVP SHALL 包含 Joint Status Header、Sync Authority、Fusion Quality、Recovery funnel/episode list、Debug Replay 和 Refinement Safety 六个区域，技术运行细节 SHALL 默认折叠。`AnalysisJobPage` SHALL 只保留轻量双摄摘要和详情入口。

#### Scenario: 从完成的双摄任务进入详情
- **WHEN** 用户在已完成 multiview job 的任务页选择“查看双摄协同详情”
- **THEN** 系统 SHALL 导航至该 job 的 `/multiview` 页面
- **AND** 页面 SHALL 从后端 observability API 而非多个原始 artifacts 获取状态语义

#### Scenario: 页面不成为配置或科研工具
- **WHEN** 用户查看双摄协同分析页
- **THEN** 页面 MUST NOT 提供 sync calibration、recovery 或 F1 参数修改控件
- **AND** MVP MUST NOT 包含 GT A/B evaluation、双原视频同步播放、交互式 canonical court 或证据时间线

### Requirement: Debug replay 帧选择与 clock 回退一致

Debug replay 渲染 SHALL 以 trace 中每 tick 的 `source_frame_index` 与 `frame_status` 为准。若 clock 回退策略生效，trace 前段 view SHALL 为回退帧且 status 标记 fallback；渲染器 SHALL 显示回退帧画面并叠加对应状态标记，SHALL NOT 显示 UNAVAILABLE 面板。

#### Scenario: 回退帧正常渲染

- **WHEN** trace 前段 cam_2 status 为 fallback 且含 `source_frame_index`
- **THEN** debug replay SHALL 显示该回退帧画面
- **AND** 画面叠加 SHALL 标注 fallback 状态

#### Scenario: 细分不可用仍清晰呈现

- **WHEN** cam_2 仍为不可用状态（无回退可用）
- **THEN** debug replay SHALL 显示 UNAVAILABLE 面板与结构化原因
- **AND** SHALL 包含 `selection_error_ms` 等诊断信息

### Requirement: 双摄协同分析页 per-player 显示诊断入口

双摄协同分析页 SHALL 提供 per-player 显示诊断展开面板（默认折叠），用户可对单个球员在单个时间点查询显示漏斗证据链；页面 MUST 通过显示诊断 API 获取数据，MUST NOT 直接加载 raw trace。MVP SHALL 仅支持单球员单时刻窗口查询，不提供整场拉取、GT A/B 或交互式时间线。面板内窗口返回的每个 tick 诊断行 SHALL 默认折叠为标题行（视角 · tick · 时间戳 · 帧状态徽标），点击标题 SHALL 展开该行的完整漏斗字段；窗口内多行 MUST NOT 全部默认展开导致页面无限向下延伸。

#### Scenario: 查看单球员显示诊断

- **WHEN** 用户在双摄协同分析页展开某球员的显示诊断
- **THEN** 页面 SHALL 显示该球员在参考视角与辅助视角的逐 stage 漏斗（候选 / 投影 / formal observation / association / guidance / overlay）
- **AND** 面板默认折叠，展开后按时间窗口请求

#### Scenario: 诊断行默认折叠

- **WHEN** 查询窗口返回多个 tick 的诊断行
- **THEN** 每行 SHALL 默认只展示标题信息（视角 · tick · 时间戳 · 帧状态）
- **AND** 点击某行标题 SHALL 展开该行的完整漏斗字段

#### Scenario: 诊断行展开互不影响

- **WHEN** 用户展开窗口中的某一行诊断
- **THEN** 其他行的折叠状态 SHALL 保持独立
- **AND** 页面高度 SHALL 受控，不因行数增长无限延伸

#### Scenario: 诊断不可用时页面语义

- **WHEN** 该 job 无显示漏斗产物或 `debugTraceEnabled=false`
- **THEN** 页面 SHALL 显示结构化不可用原因
- **AND** 其他区域（Sync / Fusion / Recovery / Refinement）SHALL 不受影响

### Requirement: Debug Replay 自动加载与按需卸载

双摄协同详情页的 Debug Replay 面板在 canonical debug MP4 可用（section `availability=available` 且 `video_available=true`）时 SHALL 自动加载并渲染视频，无需用户手动点击；同时 SHALL 提供"卸载/重新加载"控制，并在面板内说明大体积回放文件按需加载的设计权衡（避免每次打开详情页无条件下载大文件）。资源不可用时 SHALL 保持现有不可用提示。

#### Scenario: 资源可用时自动加载

- **WHEN** Debug section 标记 `available` 且 `video_available=true`
- **THEN** 面板 SHALL 直接渲染视频播放器，不再要求点击"加载 canonical MP4"
- **AND** 面板 SHALL 展示一段说明文案解释大体积回放按需加载的带宽权衡

#### Scenario: 可卸载与重新加载

- **WHEN** 视频已自动加载
- **THEN** 面板 SHALL 提供"卸载"控制
- **AND** 卸载后 SHALL 提供"重新加载"控制恢复播放器

#### Scenario: 资源不可用保持提示

- **WHEN** Debug section 为 `unavailable` 或 `video_available=false`
- **THEN** 面板 SHALL 保持既有不可用提示（如"未开启详细诊断回放"或"canonical debug MP4 尚未生成"）
- **AND** MUST NOT 渲染空视频播放器
