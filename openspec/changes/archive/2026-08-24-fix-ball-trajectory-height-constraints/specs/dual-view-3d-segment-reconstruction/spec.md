## MODIFIED Requirements

### Requirement: 段级空间不变量

系统 SHALL 对优化所得 3D 曲线施加空间与物理不变量。

#### Scenario: 弹地端高度为零
- **WHEN** 飞行段以 bounce 为端点
- **THEN** 端点 `Z` SHALL 为 0（`z=0` 硬锚点）
- **AND** 地面 XY SHALL 对齐双摄 Homography 融合得到的落点权威

#### Scenario: 段内连续且无异常值
- **WHEN** 飞行段内存在测量
- **THEN** 3D 曲线 SHALL 在段内连续
- **AND** 不得产生明显不合理的速度或高度跳变
- **AND** 短缺口允许预测，但 `source = predicted`，不冒充 detection

#### Scenario: 高度不得低于地面
- **WHEN** 3D 段完成优化或准备发布
- **THEN** 所有有效控制点和密集采样点的 `estimated_height_ft` SHALL 为有限值且不小于 0
- **AND** 允许不超过数值容差的浮点误差，但不得出现可见的负高度

#### Scenario: 3D 高度约束失败时降级
- **WHEN** 优化结果出现负高度、非有限高度、bounce 端不为 0 或段内穿过地面
- **THEN** 该段 MUST NOT 以 `stereo_estimated_3d` 或其他可用 3D 状态发布
- **AND** 系统 SHALL 优先交给同段合格的 2.5D 重建，否则标记为 `unavailable`
- **AND** artifact SHALL 保存高度约束失败原因供诊断

### Requirement: 高度由双摄约束而非先验弧线

系统 SHALL 区分双摄约束高度和仅用于可视化的先验弧线；双摄合格段的 `estimated_z(t)` SHALL 由两个视角约束，双摄不合格段可以输出显式标记的 2.5D 估算高度，但 MUST NOT 冒充三维测量。

#### Scenario: 双摄合格段
- **WHEN** 段级重建满足 `stereo_estimated_3d` 资格
- **THEN** `z(t)` SHALL 来自两视角回投约束
- **AND** SHALL 标记为 approximate multiview height
- **AND** SHALL 同时满足高度非负和端点物理不变量

#### Scenario: 双摄不合格但单摄段可显示
- **WHEN** 段具有连续单摄证据与事件端点但不足以重建 3D
- **THEN** 系统 SHALL 允许使用事件边界感知的二次弧生成估算高度
- **AND** SHALL 标记 `metric_validity = visualization_only` 与具体 reconstruction mode
- **AND** MUST NOT 输出真实最高点或三维球速
