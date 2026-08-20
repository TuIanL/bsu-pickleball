# multiview-timing-authority Specification

## Purpose
TBD - created by archiving change harden-multiview-timing-authority. Update Purpose after archive.
## Requirements
### Requirement: Timing authority 分层

系统 SHALL 将每路媒体 timing authority 表示为 `source_pts`、`legacy_nominal_fps` 或 `missing`，并 SHALL 将该字段与媒体、CaptureTrack 和分析输入关联保存。`source_pts` 只表示该路具有可复现的本地源 PTS，不得单独解释为跨摄像头已同步。

#### Scenario: 最终注册视频具备 PTS sidecar

- **WHEN** 最终用于分析的 registered video 存在可读取且单调的 PTS sidecar
- **THEN** 该 view 的 timing authority SHALL 为 `source_pts`
- **AND** provider SHALL 暴露 sidecar provenance、frame count、FPS 和首尾 PTS

#### Scenario: PTS sidecar 缺失或损坏

- **WHEN** registered video 缺少 sidecar 或 sidecar 校验失败
- **THEN** 单摄兼容路径 MAY 使用 `legacy_nominal_fps`
- **AND** joint authoritative eligibility SHALL 为 false
- **AND** diagnostics SHALL 记录 `timing_authority_unavailable` 或等价 reason

### Requirement: Structural authority 与 quality gate 分离

多视角执行器 SHALL 先验证 sync authority 的结构合法性，再执行 `good / degraded / unknown / unavailable` quality gate。结构校验通过 SHALL NOT 自动代表 synchronized joint 可用。

#### Scenario: 结构合法且 quality good

- **WHEN** 当前 reference/secondary mapping、schema、camera identity 和数值字段均合法，且 quality 为 `good`
- **THEN** execution mode SHALL 为 `joint_authoritative`
- **AND** authoritative joint eligibility SHALL 为 true

#### Scenario: 结构合法但 quality degraded

- **WHEN** structural validation 通过但 mapping quality 为 `degraded`
- **THEN** execution mode SHALL 为 `joint_degraded`
- **AND** 运行 SHALL 保留双路 timing diagnostics
- **AND** authoritative joint eligibility SHALL 为 false

#### Scenario: quality unknown 或 authority unavailable

- **WHEN** quality 为 `unknown`，或当前 secondary mapping 缺失/结构校验失败
- **THEN** execution mode SHALL 为 `single_view_fallback`
- **AND** 系统 SHALL 禁止 strong cross-view timing claim
- **AND** diagnostics SHALL 保留结构化 reason

### Requirement: Authoritative joint eligibility

一次运行只有在两路 timing authority 均为 `source_pts`、sync quality 为 `good`、当前 tick 位于 calibration valid interval 内且 source frame selection error 未超过 tolerance 时，才 SHALL 将对应 tick 标记为 authoritative joint eligible。该 eligibility SHALL 与“任务能够运行”分离。

#### Scenario: P1 primary eligible tick

- **WHEN** 两路均使用 source PTS，sync quality 为 `good`，tick 在有效校准区间内，且每路 selection error 均在容差内
- **THEN** tick SHALL 可进入 authoritative joint 统计

#### Scenario: 可运行但非 authoritative tick

- **WHEN** 任务因 compatibility 或 degraded policy 仍可执行，但任一路使用 nominal FPS、sync degraded 或 selection error 超限
- **THEN** tick MAY 产出兼容/降级结果
- **AND** tick SHALL NOT 计入 authoritative joint 统计

### Requirement: Timing authority diagnostics

系统 SHALL 在任务和运行 diagnostics 中记录每路 timing authority、sync quality、execution mode、authoritative eligibility、mapping reason、sidecar provenance 和每类 frame selection status 的计数。

#### Scenario: 完成的 joint run 被审查

- **WHEN** 开发者查看一次完成或 fallback 的多视角运行
- **THEN** diagnostics SHALL 能区分 `joint_authoritative`、`joint_degraded`、`compatibility_degraded` 和 `single_view_fallback`
- **AND** SHALL 能定位导致某一路或某个 tick 不可用的 reason

### Requirement: Historical registered video sidecar materialization

系统 SHALL 支持对已完成历史 CaptureTake 的最终 registered video 幂等生成 `<registered_video_path>.pts.jsonl`，并 SHALL 使用现有 PTS sidecar writer 提取 `best_effort_timestamp_time`。生成过程 SHALL 使用临时文件和原子替换，不得修改或覆盖原始 TS、registered video 或已有有效 sidecar。

系统 SHALL 通过多个触发源驱动该补写，使 sidecar 与视频同生命周期：

- **materialize API**：系统 SHALL 提供 `POST /api/videos/{video_id}/timing/materialize` 同步补写接口。接口 SHALL 对 registered video 幂等生成 sidecar；sidecar 已存在且有效 SHALL 直接复用并返回现有 summary；视频不存在或不可用 SHALL 返回结构化 404；生成失败 SHALL 返回结构化 409 且不得影响媒体本身。
- **启动扫描**：系统启动时 SHALL 扫描全部 registered videos（含 sync-recording 会话注册的视频），对缺失 sidecar 的异步补写。扫描与补写 SHALL 并发受限（默认 1），外接盘未挂载、媒体文件缺失或 ffprobe 失败 SHALL 仅记录 warning 并以 `missing`/unavailable 降级，SHALL NOT 阻塞启动。
- **merge 收尾补强**：`request_merge` 对 `merge_status == completed` 且视频已注册的会话 SHALL 仍校验每路 registered video 的 sidecar，缺失 SHALL 补写（幂等快路径），使"merge 完成"与"timing 可用"同生命周期。

同一视频的多个触发源并发补写 SHALL 通过 per-video 锁串行化，避免重复 ffprobe；原子写入保证任一触发源成功即终止其余竞争。

#### Scenario: registered video 可生成 sidecar
- **WHEN** registered video 可读取且 ffprobe 返回非空、有限、单调的 frame PTS
- **THEN** 系统 SHALL 写入对应 sidecar
- **AND** sidecar SHALL 记录 frame index、PTS、可用 DTS 和 keyframe provenance

#### Scenario: sidecar 已存在且有效
- **WHEN** 对应 sidecar 已存在且 frame index/PTS 校验通过
- **THEN** 系统 SHALL 复用该 sidecar
- **AND** SHALL NOT 重复扫描或覆盖它

#### Scenario: 通过 materialize API 修复缺失 sidecar
- **WHEN** 客户端对缺失 sidecar 的 registered video 调用 `POST /api/videos/{video_id}/timing/materialize` 且补写成功
- **THEN** API SHALL 返回 sidecar summary（frame count、FPS、首尾 PTS）
- **AND** 随后的 `GET /api/videos/{video_id}/timing` SHALL 返回 `source_pts` authority

#### Scenario: materialize 补写失败
- **WHEN** 媒体不可读取、ffprobe 超时、PTS 非有限或不单调
- **THEN** API SHALL 返回结构化 409（含 reason）
- **AND** registered video 与既有媒体 SHALL 保持不变
- **AND** timing authority SHALL 保持 `missing`/unavailable

#### Scenario: 启动扫描自愈历史会话
- **WHEN** 后端启动且存在缺失 sidecar 的 registered video（如 8-13 之前完成 merge 的会话）
- **THEN** 系统 SHALL 在后台自动补写缺失 sidecar
- **AND** 补写完成后 `GET /api/videos/{video_id}/timing` SHALL 返回 `source_pts` authority
- **AND** 启动过程 SHALL 不被补写任务阻塞

#### Scenario: 启动扫描遇到外接盘未挂载
- **WHEN** 启动扫描时媒体所在卷不可用或媒体文件缺失
- **THEN** 系统 SHALL 记录 warning 并跳过该视频
- **AND** 其他视频的补写 SHALL 不受影响
- **AND** 后端 SHALL 正常完成启动

### Requirement: Sidecar authority persistence

sidecar 校验成功后，系统 SHALL 将 `source_pts`、sidecar path、frame count、FPS 和首尾 PTS provenance 关联到对应 CaptureTrack/registered video。sidecar 缺失、损坏或与 registered video 不匹配时，系统 SHALL 将 timing authority 保持为 `missing`/unavailable，并 SHALL 阻止 authoritative joint eligibility。

#### Scenario: sidecar 校验成功
- **WHEN** sidecar frame index 严格递增、PTS 单调不递减且至少包含一个有效 frame
- **THEN** CaptureTrack timing authority SHALL 为 `source_pts`
- **AND** provider SHALL 暴露 sidecar provenance

#### Scenario: sidecar 校验失败
- **WHEN** sidecar 为空、JSONL 损坏、PTS 非有限或不单调
- **THEN** 系统 SHALL 保留 media
- **AND** SHALL 记录结构化失败原因
- **AND** joint authoritative eligibility SHALL 为 false

