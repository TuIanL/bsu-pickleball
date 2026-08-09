# multiview-synchronized-analysis-clock Specification

## Purpose
CanonicalAnalysisClock:reference 视频的 analysis-frame clock,与检测无关,输出 `SynchronizedFrameBundle`,且保证 source-frame 单调不重复消费。

## Requirements
### Requirement: 分析帧时钟独立于检测

系统 SHALL 提供 `CanonicalAnalysisClock`,以 reference 视频的 analysis-frame 为 tick,为每个 tick 为各 view 解析源帧(`cam_1` / `cam_2`),输出 `SynchronizedFrameBundle`。该时钟 SHALL 与球员检测无关:无论某视角是否检测到球员,tick 均存在,缺源帧的视角标记为 `unavailable` / `no_new_frame`。

#### Scenario: 无检测也有 tick

- **WHEN** reference 视频某分析帧没有任何球员检测
- **THEN** 该帧 SHALL 仍产生一个 `SynchronizedFrameBundle` tick
- **AND** 各 view 的帧状态 SHALL 与检测结果无关

#### Scenario: 单视角缺源帧

- **WHEN** 某 tick 内 cam_2 无同步 source frame
- **THEN** bundle 中 cam_2 SHALL 标记为 `unavailable`
- **AND** `Cam1 P3 unavailable / Cam2 P3 observed` 的组合 SHALL 是合法系统状态

### Requirement: FrameSample 契约

`SynchronizedFrameBundle` SHALL 包含 `take_timestamp_ms`、`views { cam_1, cam_2 }`(每个为 `FrameSample` 或 `None`)、`frame_status` 与 `mapping_diagnostics`。`FrameSample` SHALL 包含 `source_frame_index` / `source_timestamp_ms` / `mapped_take_timestamp_ms` / `selection_error_ms` / `frame`。cam_1/cam_2 配对 SHALL 复用既有 sync mapping,误差超过容差时对应 view SHALL 为 `unavailable`。

#### Scenario: 帧映射诊断

- **WHEN** clock 为某 tick 解析 cam_2 源帧
- **THEN** bundle SHALL 记录该配对的 selection error / 映射质量
- **AND** 超过 `max_pairing_error_ms` 时 cam_2 SHALL 为 `unavailable`

### Requirement: source-frame 单调不重复消费

CanonicalAnalysisClock SHALL 保证同一 `ViewTrackingSession` 的 `source_frame_index` 严格单调、不重复消费。若某 tick 映射到的 secondary source frame 已被前一 tick 消费,则该 tick 该 view SHALL 为 `no_new_frame`(不调用 `session.step`),SHALL NOT 再次喂给有状态 tracker。

#### Scenario: 同帧不二次消费

- **WHEN** 两个 canonical tick 映射到同一 Cam2 source frame
- **THEN** 第二个 tick 的 cam_2 SHALL 标记为 `no_new_frame`
- **AND** cam_2 的 `session.step()` SHALL 只被调用一次(不重复更新 tracker)

#### Scenario: 已消费帧记录

- **WHEN** clock 为某 view 解析下一帧
- **THEN** 系统 SHALL 记录该 view 的 `last_consumed_source_frame_index`
- **AND** 后续 tick SHALL 以此判断是否存在新帧
