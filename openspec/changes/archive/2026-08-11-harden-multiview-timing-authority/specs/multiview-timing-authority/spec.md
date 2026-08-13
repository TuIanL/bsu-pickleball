# multiview-timing-authority Specification

## Purpose

定义多视角分析中 timing authority、sync quality、authoritative joint eligibility、PTS provenance 和 fallback mode 的统一契约。

## ADDED Requirements

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
