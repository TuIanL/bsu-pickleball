## ADDED Requirements

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
