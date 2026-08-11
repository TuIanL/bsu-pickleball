## ADDED Requirements

### Requirement: 双摄分析窗口传播与同步映射

双摄 Parent 的分析窗口 MUST 以 reference view 的公共 take 时间轴表示。`late_fusion_v1` 创建的每个 child MUST 持久化其实际媒体时间轴窗口；secondary child 的窗口 MUST 由权威 sync mapping 换算。`joint_tracking_v2` Parent MUST 保留公共窗口并在执行时交给 CanonicalAnalysisClock/JointRun，不得因没有 child 而丢失窗口。

#### Scenario: late fusion reference child

- **WHEN** 用户创建带 `[start_ms, end_ms)` 窗口的 `late_fusion_v1` 双摄任务
- **THEN** Parent SHALL 持久化该公共窗口
- **AND** reference child SHALL 使用相同的 reference 时间轴范围

#### Scenario: late fusion secondary child

- **WHEN** secondary view 存在有效 sync mapping
- **THEN** secondary child SHALL 持久化映射到自身媒体时间轴的起止范围
- **AND** 两路 child SHALL 表示同一个物理时间窗口

#### Scenario: joint Parent 窗口保留

- **WHEN** 用户创建带窗口的 `joint_tracking_v2` 双摄任务
- **THEN** Parent SHALL 持久化 `clipStartMs` 与 `clipEndMs`
- **AND** joint executor SHALL 使用该窗口建立有限的 reference canonical ticks

#### Scenario: 同步不可用时不伪造窗口映射

- **WHEN** secondary view 缺少有效 sync mapping
- **THEN** 系统 SHALL 保留 reference 窗口
- **AND** secondary SHALL 按既有同步不可用语义标记为 unavailable 或走既有降级路径
- **AND** SHALL NOT 以新的窗口映射逻辑伪造同步配对

### Requirement: 双摄窗口范围可追溯

双摄 Parent、child、fusion/joint run 和派生可视化结果 MUST 能追溯请求窗口、实际解码范围、实际处理帧数和源视频总帧数。`analysisScope` MUST NOT 被解释为时间范围的替代字段。

#### Scenario: 窗口结果诊断

- **WHEN** 带窗口的双摄任务完成
- **THEN** Parent 结果 SHALL 暴露 requested clip 与实际处理范围
- **AND** A/B view diagnostics SHALL 能区分源视频总帧数和窗口内处理帧数

#### Scenario: 任务进度使用窗口分母

- **WHEN** 带窗口的双摄任务正在运行
- **THEN** child 或 joint view progress SHALL 以窗口内计划处理帧/tick 为分母
- **AND** SHALL 仍保留源视频总帧数作为诊断信息

