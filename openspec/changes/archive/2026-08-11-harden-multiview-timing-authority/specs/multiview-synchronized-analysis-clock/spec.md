# multiview-synchronized-analysis-clock Delta Specification

## MODIFIED Requirements

### Requirement: 分析帧时钟独立于检测

系统 SHALL 提供 `CanonicalAnalysisClock`，以 reference 视频的 analysis-frame 为 tick，为每个 tick 为各 view 解析源帧并输出 `SynchronizedFrameBundle`。该时钟 SHALL 与球员检测无关；无论某视角是否检测到球员，tick 均存在。每个 view SHALL 使用自己的 timing authority、sync mapping 和 frame status，不得用 reference view 的 FPS、尺寸或 timing metadata 代替另一 view 的事实。

#### Scenario: 无检测也有 tick

- **WHEN** reference 视频某分析帧没有任何球员检测
- **THEN** 该帧 SHALL 仍产生一个 `SynchronizedFrameBundle` tick
- **AND** 各 view 的帧状态 SHALL 与检测结果无关

#### Scenario: 单视角缺源帧

- **WHEN** 某 tick 内 cam_2 无同步 source frame
- **THEN** bundle 中 cam_2 SHALL 标记具体不可用状态
- **AND** `Cam1 P3 unavailable / Cam2 P3 observed` 的组合 SHALL 是合法系统状态

#### Scenario: 双路使用独立 timing metadata

- **WHEN** cam_1 与 cam_2 的 source FPS、PTS authority 或媒体尺寸不同
- **THEN** clock SHALL 保留各 view 自己的 timing 和 frame metadata
- **AND** SHALL NOT 通过 reference view 的默认值覆盖 secondary view

### Requirement: FrameSample 契约

`SynchronizedFrameBundle` SHALL 包含 `take_timestamp_ms`、`views`、`frame_status` 与 `mapping_diagnostics`。每个 `FrameSample` SHALL 包含 `source_frame_index`、`source_timestamp_ms`、`mapped_take_timestamp_ms`、`selection_error_ms`、`timing_authority`、`sync_quality` 和 `frame`。cam_1/cam_2 配对 SHALL 复用既有 sync mapping；超出有效区间、媒体范围或误差容差时 SHALL 输出细分 status 而不是伪造可用帧。

#### Scenario: 帧映射诊断

- **WHEN** clock 为某 tick 解析 cam_2 源帧
- **THEN** bundle SHALL 记录 source timestamp、mapped take timestamp、selection error、timing authority 和 sync quality
- **AND** 超出有效区间或 `max_pairing_error_ms` 时 cam_2 SHALL 标记对应不可用状态

#### Scenario: Timing provenance 传递

- **WHEN** 下游 runtime 消费一个 available `FrameSample`
- **THEN** source timing 字段 SHALL 随该样本传入 observation adapter
- **AND** 下游 SHALL 能区分 source PTS、nominal fallback 和不可用 timing

