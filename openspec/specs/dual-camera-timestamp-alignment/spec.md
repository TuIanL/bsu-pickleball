## ADDED Requirements

### Requirement: Preserve source frame timing

双摄录制 SHALL 保留每个源视频帧的可复现时间信息（PTS、time base、源帧序号或等价索引），并 SHALL 将其与对应原始 TS 关联保存。

#### Scenario: Source PTS is available

- **WHEN** 两路 RTSP 均提供单调可读取的源 PTS
- **THEN** 系统 SHALL 记录每路帧级 PTS 索引
- **AND** SHALL NOT 用新的主机到包时间戳静默覆盖唯一的源时间依据

#### Scenario: Source PTS is unavailable

- **WHEN** 任一路源 PTS 缺失、不单调或无法跨路比较
- **THEN** 系统 SHALL 保留原始 TS
- **AND** SHALL 将同步质量标记为 `unknown` 或 `degraded`
- **AND** SHALL 在清单中记录降级原因

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

对齐后的派生视频或帧索引 SHALL 使用共同时间网格生成，且 SHALL 保留每个目标帧对应的源帧索引和选择误差。

#### Scenario: Aligned derivative is generated

- **WHEN** 两路时间映射通过质量阈值
- **THEN** 系统 SHALL 生成共同时间轴的派生媒体或帧索引
- **AND** SHALL NOT 修改或覆盖原始 TS

#### Scenario: Alignment cannot be trusted

- **WHEN** 映射质量不通过阈值
- **THEN** 系统 SHALL NOT 将输出标记为 fully aligned
- **AND** SHALL 保留原始素材并暴露诊断状态

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
