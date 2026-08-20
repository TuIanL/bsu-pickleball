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

当 canonical tick 落在人工锚点覆盖区间（`valid_start_seconds` / `valid_end_seconds`，本规范正式定义为 anchor evidence span——人工锚点覆盖的 reference 时间区间，不表示"在此之前 Cam-2 无对应画面"）之外时，clock 不再把"区间外"等价于"无真实画面"。clock 对区间外 tick 直接用原始 canonical 时间计算 `local = map_reference_time(calibration, t)`（MUST NOT clamp 到锚点边界），并将 `local` 与 secondary view 的媒体 PTS 范围比较：落在范围内且最近帧距离 `<= max_selection_error_seconds` → 选中最近真实帧并标记 `available_extrapolated`（带 `mapping_mode` / `extrapolation_distance_ms` / `selection_error_ms` 诊断）；落在范围内但最近帧距离 `> max_selection_error_seconds` → 标记 `unavailable_selection_error`（复用 authoritative frame-selection 质量门，外推不放松该门）；越出媒体 PTS 范围 → 标记 `unavailable_out_of_media_range`。该外推 SHALL 对称覆盖 pre-anchor（`t < anchor_start`）与 post-anchor（`t > anchor_end`）两端；低侧不再冻结于第一锚点帧，高侧只要真实媒体仍存在就不再黑屏。外推帧 MUST NOT 伪装为 authoritative `available`（status 显式区分，`build_frame_map()` 的权威 `available` 契约不变）。

#### Scenario: pre-anchor 帧正常递增

- **WHEN** canonical tick 早于 `anchor_start`（如 3.4s）但 affine 映射后的 cam_2 时间在媒体内
- **THEN** cam_2 的 `source_frame_index` SHALL 随 canonical tick 正常推进（而非固定第一锚点帧）
- **AND** status SHALL 为 `available_extrapolated`，`mapping_mode=pre_anchor_extrapolation`

#### Scenario: post-anchor 仍有真实画面

- **WHEN** canonical tick 晚于 `anchor_end`（如 58s）但 affine 映射后的 cam_2 时间仍落在媒体内
- **THEN** cam_2 SHALL 持续提供真实画面，status 为 `available_extrapolated`，`mapping_mode=post_anchor_extrapolation`
- **AND** MUST NOT 显示 UNAVAILABLE 黑屏

#### Scenario: 外推越出媒体才不可用

- **WHEN** affine 映射后的 cam_2 时间越出 secondary 媒体 PTS 范围
- **THEN** cam_2 SHALL 标记 `unavailable_out_of_media_range`
- **AND** SHALL 携带 `selection_error_ms` 等诊断字段供渲染器呈现

#### Scenario: 不 clamp 到锚点边界

- **WHEN** canonical tick 在锚点区间外
- **THEN** clock SHALL NOT 使用 `max(t, valid_start)` 之类把外推目标钳制到锚点边界
- **AND** 外推目标 SHALL 为 `map_reference_time(calibration, t)` 的真实值

#### Scenario: 无可用外推时细分不可用

- **WHEN** 外推无法产生有效帧（如映射越出媒体范围）
- **THEN** cam_2 SHALL 保持细分不可用状态（`unavailable_out_of_media_range`）
- **AND** SHALL 携带 `selection_error_ms` 等诊断字段供渲染器呈现

#### Scenario: selection error 超限不标 available_extrapolated

- **WHEN** affine 映射后的 cam_2 时间落在媒体 PTS 内，但最近真实帧距离 `abs(selection_error_seconds) > max_selection_error_seconds`
- **THEN** cam_2 SHALL 标记 `unavailable_selection_error`（复用 authoritative frame-selection 质量门）
- **AND** SHALL NOT 标记 `available_extrapolated`（外推只放宽 anchor-span authority gate，不放松 frame-selection 质量门）

### Requirement: 外推帧不污染 tracker 消费游标

`available_extrapolated` 帧 SHALL 携带 `source_frame_index` 并进入 trace / Debug Replay，但 SHALL NOT 推进 `last_consumed_source_frame_index`（该游标仅由 authoritative `available` 路径维护，语义是"已喂给有状态 tracker"，是 source-frame 单调不重复守卫的依据）。`MultiViewJointRun` 的 perception 主链（detector / tracker / association / fusion / recovery）因 `status != "available"` 自动跳过外推帧。即使连续两个 canonical tick 映射到同一 cam_2 源帧，外推路径 SHALL NOT 触发 `no_new_frame`（那是 `available` 路径的单调守卫），renderer 的 `cached_frame.copy()` 同帧拷贝优化仍正确工作。

#### Scenario: 外推帧不更新消费游标

- **WHEN** 某 tick secondary 为 `available_extrapolated`
- **THEN** `last_consumed_source_frame_index[secondary_view]` SHALL NOT 被更新
- **AND** 该帧 SHALL NOT 被送入 `tracker.step` / `prepare`

#### Scenario: 感知主链跳过外推帧

- **WHEN** `bundle.frame_status[view] == "available_extrapolated"`
- **THEN** `MultiViewJointRun` 的 prepare/step 与 recovery 的 `target_available` 判定 SHALL 按 `status != "available"` 跳过
- **AND** 锚点区间外 cam_2 的 `tracking_session.step/prepare` 调用次数 SHALL 为 0

