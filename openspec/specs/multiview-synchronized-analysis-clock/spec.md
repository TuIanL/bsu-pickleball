# multiview-synchronized-analysis-clock Specification

## Purpose
CanonicalAnalysisClock:reference 视频的 analysis-frame clock,与检测无关,输出 `SynchronizedFrameBundle`,且保证 source-frame 单调不重复消费。
## Requirements
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

### Requirement: 多视角配对决策可复用

同步时钟或等价的 frame pairing service SHALL 支持生成可复用的 `FramePairingPlan`。任何消费同一 reference timeline 的 association 或 fusion 阶段 SHALL 使用相同的 source frame decision。

#### Scenario: 多消费者共享 decision

- **WHEN** 同一个 reference tick 同时需要 association 和 fusion
- **THEN** 两个消费者 SHALL 读取同一个 secondary source frame decision
- **AND** 不得因消费者不同而重新选出另一张 secondary frame

### Requirement: Frame pairing 以视频帧为单位

系统 SHALL 先为 canonical tick 选择一张 secondary source frame，再读取该帧上的所有球员观测；系统 SHALL NOT 为同一 tick 内的不同球员分别选择不同 source frame。

#### Scenario: 多球员共享副摄帧

- **WHEN** secondary 容差窗口包含多张帧且每张帧包含多个球员
- **THEN** 同一 tick 的所有 secondary players SHALL 来自同一个 source frame index
- **AND** 该 frame index SHALL 写入关联和融合诊断

### Requirement: 分析帧解帧使用帧号语义

joint 执行体（`JointViewRuntime`）解析源帧 SHALL 使用帧号语义（`cv2.CAP_PROP_POS_FRAMES`）定位视频位置，MUST NOT 把帧号当作毫秒（`CAP_PROP_POS_MSEC`）消费。每次解帧的帧位置 SHALL 精确对应 bundle 给出的 `source_frame_index`，保证检测/跟踪运行在正确的源帧上。

#### Scenario: 解帧位置与帧号一致

- **WHEN** runtime 收到 `source_frame_index=400`
- **THEN** 解出的帧 SHALL 为视频第 400 帧（帧号语义）
- **AND** SHALL NOT 落在第 25 帧（400ms 位置）等错误位置

#### Scenario: 逐 tick 帧号严格前进

- **WHEN** 相邻 tick 的 `source_frame_index` 相差 2
- **THEN** 实际解出的帧 SHALL 逐 tick 前进 2 帧
- **AND** 检测框 SHALL 随每个 tick 更新，不得每 ~5-8 tick 才变化一次

### Requirement: 窗口开头副摄帧选择回退

当分析窗口起点（如 `clipStart=0`）早于 sync 有效映射起点（`valid_start_seconds`）时，clock SHALL 为 secondary view 提供显式回退策略：使用最近有效映射外推或最近可用帧，或保持细分不可用状态并携带结构化解释。任何回退 SHALL 在 `FrameSample` 上标注 fallback status 与 reason，MUST NOT 伪装为正常映射。

#### Scenario: 窗口开头副摄有回退帧

- **WHEN** canonical tick 时间戳早于 cam_2 的 `valid_start_seconds`（实测 3.4s）
- **THEN** cam_2 SHALL 使用回退帧选择并标记 `fallback` status 与 reason
- **AND** debug replay 前段 SHALL 显示回退帧画面而非 UNAVAILABLE 黑屏

#### Scenario: 无可用回退时细分不可用

- **WHEN** 回退无法产生有效帧（如媒体范围外）
- **THEN** cam_2 SHALL 保持细分不可用状态（如 `unavailable_outside_valid_interval`）
- **AND** SHALL 携带 `selection_error_ms` 等诊断字段供渲染器呈现

