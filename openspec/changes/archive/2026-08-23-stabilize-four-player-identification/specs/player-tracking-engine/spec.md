## ADDED Requirements

### Requirement: 运动与尺度联合的一对一 track association
`MultiObjectTracker` SHALL 对 track×detection 先应用几何/尺度 hard gate，再以 predicted IoU、脚点运动残差、bbox area/aspect 变化、检测置信度和投影可信度进行 maximum-cardinality/min-cost 一对一匹配。单帧最近 bbox 或最高 IoU MUST NOT 绕过一对一约束与 incumbent continuity。

#### Scenario: 两名球员交叉重叠
- **WHEN** P1/P2 bbox 在一帧交叉且下一帧分离
- **THEN** tracker SHALL 结合运动与尺度连续性保持原 source track
- **AND** SHALL NOT 仅因单帧 IoU 更高交换两个 track ID

#### Scenario: 短暂漏检后恢复
- **WHEN** 某 track 在 lost window 内缺失后于预测邻域重新出现
- **THEN** tracker SHALL 优先恢复原 track ID
- **AND** 恢复检测 SHALL 仍受一对一和尺度异常门控

### Requirement: 缺失槽位的受限 ROI 二次检测
真实 doubles 任务在 base detection 未形成某已知/预期槽位的合格观测时 SHALL 支持受预算约束的 target ROI 二次检测。恢复 candidate MUST 含真实 detector bbox，并通过 confidence、scale、footpoint、target-court membership 和 duplicate suppression；投影点本身 MUST NOT 创建 detection 或 source track。

#### Scenario: P2 base detector 漏检但 ROI 命中
- **WHEN** P2 base detection 缺失且 motion/guidance 产生有效 target ROI
- **THEN** ROI detector SHALL 可输出 detector-backed candidate 进入 tracker
- **AND** provenance SHALL 标记为 ROI recovery

#### Scenario: 只有跨视角投影没有像素检测
- **WHEN** donor view 可见 P2 但 target ROI 没有 detector bbox
- **THEN** target view SHALL NOT 创建 P2 source track
- **AND** 仅可输出受 provenance 约束的 projected/predicted 展示状态

### Requirement: Tracker 消费合格 appearance soft cost
tracker SHALL 通过 `PlayerAppearanceDescriptor` protocol 消费可选 appearance distance，并只在 hard gate 后加入 min-cost 排序。descriptor 不可用或 non-discriminative 时 SHALL 等价于 appearance disabled，且 detection-in/track-out 对外接口保持兼容。

#### Scenario: Appearance extractor 不可用
- **WHEN** 当前帧没有合格 descriptor 或 feature flag 关闭
- **THEN** tracker SHALL 仅使用运动/几何/尺度代价继续工作
- **AND** SHALL NOT 因缺少 appearance 丢弃检测
