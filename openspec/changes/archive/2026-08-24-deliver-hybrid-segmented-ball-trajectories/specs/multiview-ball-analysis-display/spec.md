## MODIFIED Requirements

### Requirement: 双摄球分析产出分级可用状态
系统 SHALL 根据三维覆盖、重投影误差、几何质量与落点信息生成 3D overall status，并根据所有合格 3D/2.5D segment 另行生成 `display_trajectory_status`。质量门 SHALL 按段和指标生效，MUST NOT 因 3D 不可用而隐藏合格的估算球路。

#### Scenario: 三维覆盖与几何质量达标
- **WHEN** 轨迹具有足够双摄覆盖且质量阈值达标
- **THEN** 3D overall status SHALL 为 `FULL_ESTIMATED_3D`
- **AND** SHALL 发布三维轨迹、合格落点、速度与质量指标

#### Scenario: 仅部分片段满足三维重建
- **WHEN** 只有部分飞行段具备足够双摄观测
- **THEN** 3D overall status SHALL 为 `PARTIAL_3D`
- **AND** 无效区间 SHALL 断开或由明确标注的 2.5D 段替代，MUST NOT 无标记地连接

#### Scenario: 三维不足但落点可用
- **WHEN** 可靠三维段不足但落点满足权威条件
- **THEN** 3D overall status SHALL 为 `LANDING_ONLY`
- **AND** 页面 SHALL 显示权威落点，并可同时显示独立通过可视化门的估算 2.5D 段

#### Scenario: 三维和权威落点均不可用但估算段可用
- **WHEN** 3D overall status 为 `UNAVAILABLE` 且存在合格 visualization-only 段
- **THEN** `display_trajectory_status` SHALL 为 `degraded`
- **AND** 页面 SHALL 展示估算球路及限制说明，而不是整页空态

