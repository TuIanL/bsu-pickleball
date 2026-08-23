## ADDED Requirements

### Requirement: 跨视角关联消费时序连续性
跨视角 associator SHALL 消费基础视觉过滤后的共享候选集合、两个本地 tracker 的 pre-tick 预测快照、上一可信 3D 路径连续性与当前飞行段上下文，MUST NOT 将连续性参数长期保留为默认零值。

#### Scenario: 原始候选包含真球和静态误检
- **WHEN** 一个视角同时包含真球与静态高置信候选，另一视角只有真球候选
- **THEN** associator SHALL 结合 tracker 预测、尺度/运动一致性和几何残差选择真球配对
- **AND** 选择结果及各评分分量 SHALL 写入 evidence

#### Scenario: 高残差配对仍通过宽松空间门
- **WHEN** 候选配对虽位于比赛环境范围内但回投或 epipolar 残差超过高可信阈值
- **THEN** evidence SHALL 保留该配对用于审计并标记低质量
- **AND** 该配对 MUST NOT 成为高可信 stereo anchor、速度或最高点依据

### Requirement: stereo evidence 按飞行段组织
系统 SHALL 将配对观测、单视角观测与 stereo measurement 关联到具体 `segment_id`，使三维增强只在同一飞行段内发生。

#### Scenario: 分析窗口包含多拍
- **WHEN** canonical evidence 跨越多个 hit/bounce 边界
- **THEN** 每个 observation 和 measurement SHALL 关联一个 segment 或明确标记为待分配
- **AND** 后置重建 MUST NOT 把不同 segment 的观测送入同一曲线优化

#### Scenario: 仅有稀疏双摄重叠
- **WHEN** 同段只在少数时刻具有合格的 stereo measurement
- **THEN** 合格 measurement SHALL 作为稀疏 anchor 参与该段重建
- **AND** 同段连续单视角观测 SHALL 保留为图像回投约束

