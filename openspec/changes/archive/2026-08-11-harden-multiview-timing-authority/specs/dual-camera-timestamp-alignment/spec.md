# dual-camera-timestamp-alignment Delta Specification

## MODIFIED Requirements

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
