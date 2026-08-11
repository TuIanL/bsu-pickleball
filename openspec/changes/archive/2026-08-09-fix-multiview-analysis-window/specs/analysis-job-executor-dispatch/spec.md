## ADDED Requirements

### Requirement: 多视角执行体实际遵守分析窗口

所有 multiview executor MUST 实际消费 Parent 或 child 上的窗口字段。`late_fusion_v1` 的 child Pipeline 和派生叠加视频 MUST 只处理窗口范围；`joint_tracking_v2` MUST 只运行窗口内 canonical ticks，并通过既有同步 clock 取得 secondary source frame。缺少窗口时两种模式 SHALL 保持全场行为。

#### Scenario: late fusion child 执行窗口

- **WHEN** late fusion child 携带 `clipStartMs/clipEndMs` 被 SingleView executor 执行
- **THEN** executor SHALL 将窗口传递给 Pipeline
- **AND** Pipeline SHALL 只在 decode range 内读取帧，正式轨迹和指标 SHALL 只保留请求窗口

#### Scenario: late fusion overlay 执行窗口

- **WHEN** late fusion child 启用分析叠加视频且携带窗口
- **THEN** OverlayVideoWriter SHALL 从窗口对应的源帧开始读取并在窗口结束后停止
- **AND** SHALL NOT 为该 artifact 无条件重新读取完整源视频

#### Scenario: joint tracking 执行窗口

- **WHEN** `joint_tracking_v2` Parent 携带 `[start_ms, end_ms)` 被 claim
- **THEN** MultiViewJointExecutor SHALL 将窗口转换为 reference frame 边界和必要的预热范围
- **AND** MultiViewJointRun SHALL 只生成边界内的 canonical ticks
- **AND** secondary source frame SHALL 继续由 CanonicalAnalysisClock 按 sync mapping 配对

#### Scenario: joint 窗口外样本不进入正式结果

- **WHEN** joint tracking 为初始化读取了预热帧
- **THEN** 预热帧 MAY 更新 tracker 状态
- **BUT** 预热帧 SHALL NOT 进入正式融合 sample、指标分母或用户可见轨迹统计

#### Scenario: 无窗口兼容

- **WHEN** executor 收到未携带完整窗口的历史或新任务
- **THEN** late fusion 和 joint tracking SHALL 分别沿用各自现有的全场执行路径
- **AND** SHALL NOT 因窗口字段缺失而失败

### Requirement: 窗口执行取消与失败诊断

窗口执行 MUST 保持现有 cancellation、retry 和 terminal failure 语义，并在窗口非法、视频边界裁剪或 seek 失败时写入结构化诊断，不得静默退化为全视频执行。

#### Scenario: 非法窗口拒绝

- **WHEN** `clipStartMs < 0`、`clipEndMs <= clipStartMs` 或窗口无法映射为正向 frame range
- **THEN** executor SHALL 返回稳定的参数错误
- **AND** SHALL NOT 启动全视频分析作为回退

#### Scenario: 窗口超出视频边界

- **WHEN** 合法窗口部分超出源视频有效时长
- **THEN** executor SHALL 将实际 decode range 裁剪到视频边界
- **AND** 结果 SHALL 记录请求范围与实际范围的差异

