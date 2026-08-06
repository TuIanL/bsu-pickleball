## ADDED Requirements

### Requirement: 重复重叠 track 抑制

后端 SHALL 对球员多目标跟踪输出应用重复 track 抑制：当两个 track 的 bbox 重叠度（IoU）超过阈值并持续达到连续帧数时，SHALL 只输出其中较可信/较旧的一个 track，抑制同一目标的重复跟踪，且不得影响球路径跟踪。

#### Scenario: 同目标分身被抑制

- **WHEN** 两个球员 track 的 bbox IoU ≥ 0.6 且持续 ≥ 3 帧（含单帧缺席容错）
- **THEN** 其中较新的 track（或置信度显著更低者）SHALL 从输出中剔除
- **AND** 置信度较高的 track SHALL 保留

#### Scenario: 短时或低度重叠不抑制

- **WHEN** 两个 track 的重叠低于阈值或未达到连续帧数
- **THEN** 两个 track SHALL 均保留输出

#### Scenario: 抑制对分离后恢复

- **WHEN** 曾被视为重复的 track 对后续 IoU 下降（目标分离）
- **THEN** 被抑制的 track SHALL 在分离持续数帧（重叠计数衰减到阈值以下）后可重新出现在输出中
