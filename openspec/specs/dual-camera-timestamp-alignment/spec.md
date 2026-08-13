# dual-camera-timestamp-alignment Specification

## Purpose

定义双摄源帧时间、时间线映射、共同时间基派生视频、多分段录制和训练标注映射规则，并保证时间语义在实现和测试中可追踪验证。
## Requirements
### Requirement: Preserve source frame timing

双摄录制 SHALL 保留每个源视频帧的可复现时间信息（PTS、time base、源帧序号或等价索引），并 SHALL 将其与对应原始 TS 和最终用于分析的 registered video 关联保存。registered video 的 PTS sidecar SHALL 经过生成与单调性校验；sidecar 缺失或损坏时 SHALL 保留媒体并明确标记 timing authority 不可用。

#### Scenario: Source PTS is available

- **WHEN** 两路 RTSP 均提供单调可读取的源 PTS，且最终 registered video 的 sidecar 校验通过
- **THEN** 系统 SHALL 记录每路帧级 PTS 索引并关联到 registered video
- **AND** SHALL NOT 用新的主机到包时间戳静默覆盖唯一的源时间依据

#### Scenario: Registered video sidecar materialization fails

- **WHEN** 任一路 registered video 的 PTS sidecar 生成或校验失败
- **THEN** 系统 SHALL 保留原始 TS、registered video 和 CaptureTake completed 状态
- **AND** 对应 view SHALL 标记 `timing_authority=unavailable`
- **AND** joint authoritative analysis SHALL NOT 使用该 view 声称 fully aligned

#### Scenario: Source PTS is unavailable

- **WHEN** 任一路源 PTS 缺失、不单调或无法作为有效 timing authority
- **THEN** 系统 SHALL 保留原始 TS
- **AND** SHALL 将同步质量标记为 `unknown` 或 `degraded`
- **AND** SHALL 在清单和 analysis diagnostics 中记录降级原因

### Requirement: Estimate and persist timeline mapping

系统 SHALL 为每个机位保存相对于参考机位的固定偏移、速率比例/漂移估计、拟合残差和参考时间轴标识。

#### Scenario: Fixed offset without measurable drift

- **WHEN** 两路时间差在录制期间保持在配置阈值内
- **THEN** 系统 SHALL 保存固定 `offset_ms`
- **AND** SHALL 允许训练导出将事件时间映射到每个机位的本地帧索引

#### Scenario: Drift is measured

- **WHEN** 时间差随录制时长变化
- **THEN** 系统 SHALL 保存 `drift_ppm` 或等价速率参数
- **AND** SHALL 使用该映射构建共同时间轴
- **AND** SHALL 将超过阈值的拟合残差标记为 `degraded`

### Requirement: Generate common-timebase derivatives

对齐后的派生视频或帧索引 SHALL 使用共同时间网格生成，且 SHALL 保留每个目标帧对应的源帧索引、source PTS、mapped take timestamp、选择误差和 selection status。frame selection SHALL 先检查 calibration valid interval，再检查媒体范围和误差容差。

#### Scenario: Target time is outside calibration interval

- **WHEN** reference target time 小于 `valid_start_seconds` 或大于 `valid_end_seconds`
- **THEN** 对应 view SHALL 标记 `unavailable_outside_valid_interval`
- **AND** 系统 SHALL NOT 通过 nearest frame 或 offset=0 生成看似有效的配对

#### Scenario: Aligned derivative is generated

- **WHEN** 两路时间映射通过质量阈值且 target time 在有效区间内
- **THEN** 系统 SHALL 生成共同时间轴的派生媒体或帧索引
- **AND** SHALL 记录 source frame、source PTS、mapped target time 和 selection error
- **AND** SHALL NOT 修改或覆盖原始 TS

#### Scenario: Alignment cannot be trusted

- **WHEN** 映射质量、有效区间或选择误差不通过阈值
- **THEN** 系统 SHALL NOT 将输出标记为 fully aligned
- **AND** SHALL 保留原始素材并暴露细分诊断状态

### Requirement: Support multi-segment recordings

系统 SHALL 对每个重连分段保存独立的 PTS 范围和映射，并 SHALL 按分段映射拼接或导出；不得仅使用第一个分段的时长计算整个 take 的目标帧数。

#### Scenario: Recording reconnects into multiple segments

- **WHEN** 任一路发生重连并生成第二个或后续分段
- **THEN** 系统 SHALL 为每个分段保存 source PTS 范围和映射状态
- **AND** 对齐输出 SHALL 保留所有有效分段内容
- **AND** SHALL 暴露分段之间的 gap、overlap 或无法校正状态

### Requirement: Export training-safe annotation mapping

训练标注导出 SHALL 为每个事件或片段提供共同时间戳以及每个摄像头的本地帧索引/PTS 映射，并 SHALL 明确原始素材与对齐派生物的关系。

#### Scenario: Event maps to both cameras

- **WHEN** 事件时间位于两路共同有效区间
- **THEN** 导出 SHALL 提供两路对应的 `frame_index`、`source_pts` 和映射误差

#### Scenario: Event is outside one camera interval

- **WHEN** 事件落在某一路无有效帧的区间
- **THEN** 该路 SHALL 标记为 unavailable，而不是返回看似有效的帧号

### Requirement: Manual multi-anchor calibration preparation

系统 SHALL 支持在内置工作台使用至少 3 组、推荐 4-6 组跨越分析时间范围的共同事件锚点，通过后端 API 生成 `dual_camera_sync_calibration.v1`。每组锚点 SHALL 使用各 camera 的本地 source time；系统 SHALL 持久化原始锚点和生成结果，结果 SHALL 保存 reference camera、camera identity、offset、rate、drift、anchor count、residual、quality、valid interval 及素材 provenance。CLI SHALL 保留为维护和兼容入口，但用户 SHALL NOT 必须下载文件或运行 CLI 才能完成确认。

#### Scenario: 多锚点拟合质量良好
- **WHEN** 锚点至少 3 组、覆盖视频有效范围且拟合 residual 在配置阈值内
- **THEN** calibration SHALL 标记 `quality=good`
- **AND** SHALL 保存可复现的拟合参数、valid interval、原始锚点和素材 provenance
- **AND** CaptureTake 同步锚点状态 SHALL 可进入 `confirmed`

#### Scenario: 锚点不足或拟合质量不足
- **WHEN** 锚点少于 3 组、没有覆盖有效时间范围或 residual 超过阈值
- **THEN** calibration SHALL 标记为 `unknown` 或 `degraded`，或拒绝确认
- **AND** SHALL 保存结构化 reason
- **AND** SHALL NOT 被宣称为 authoritative good 或人工确认完成

#### Scenario: 通过内置工作台完成拟合
- **WHEN** 用户在系统内提交共同事件锚点
- **THEN** 后端 SHALL 复用与 CLI 相同的 payload 校验和拟合逻辑
- **AND** SHALL 将权威结果写入当前 CaptureTake 的约定时间线资产位置
- **AND** 用户 SHALL NOT 需要手工移动生成文件

### Requirement: Automatic timing derivation remains degraded

从 segment `input_start_time` 自动推导的校准 SHALL 保持 `quality=degraded`，即使两路 media 可读且 offset 看似稳定，也 SHALL NOT 绕过人工锚点的 authoritative calibration gate。

#### Scenario: 使用自动推导脚本
- **WHEN** 用户为缺少 calibration 的历史 take 运行自动推导流程
- **THEN** 系统 SHALL 写入结构合法的 `dual_camera_sync_calibration.v1`
- **AND** quality SHALL 为 `degraded`
- **AND** authoritative acceptance SHALL 继续被阻止

### Requirement: Calibration identity and interval validation

加载 calibration 时，系统 SHALL 验证 schema version、reference camera、secondary camera mapping identity、positive rate、finite residual、anchor count、quality 和 valid interval。camera identity 或 interval 不匹配时 SHALL 以结构化 reason 拒绝该 mapping。

#### Scenario: camera identity 不一致
- **WHEN** mapping 的 `camera_id` 或 `reference_camera` 与 joint input 不一致
- **THEN** sync authority SHALL 判定为 unavailable
- **AND** joint run SHALL NOT 声称两路已对齐

#### Scenario: tick 超出 calibration interval
- **WHEN** canonical tick 映射到某路 valid interval 之外
- **THEN** 该 view SHALL 标记 unavailable
- **AND** SHALL NOT 通过 nearest frame 或 offset=0 外推有效观测

