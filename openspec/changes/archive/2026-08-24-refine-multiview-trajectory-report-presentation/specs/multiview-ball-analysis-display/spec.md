## MODIFIED Requirements

### Requirement: 双摄球分析产出分级可用状态

系统 SHALL 根据三维覆盖、重投影误差、几何质量与落点信息生成 3D overall status，并根据所有合格 3D/2.5D segment 另行生成 `display_trajectory_status`。质量门 SHALL 按段和指标生效，MUST NOT 因 3D 不可用而隐藏合格的估算球路。对于存在可展示轨迹的 `available` 或 `degraded` 结果，普通数据分析页和球路报告 SHALL 通过视图导航和 3D 轨迹直接呈现结果，不得重复渲染状态提示卡、估算资格说明或诊断详情。状态、质量和诊断字段 SHALL 继续通过 artifact API 保持可查询。

#### Scenario: 三维覆盖与几何质量达标

- **WHEN** 轨迹具有足够双摄覆盖且质量阈值达标
- **THEN** 3D overall status SHALL 为 `FULL_ESTIMATED_3D`
- **AND** SHALL 发布三维轨迹、合格落点、速度与质量指标
- **AND** 普通球路视图 SHALL 直接展示轨迹，不额外显示双摄状态说明卡

#### Scenario: 仅部分片段满足三维重建

- **WHEN** 只有部分飞行段具备足够双摄观测
- **THEN** 3D overall status SHALL 为 `PARTIAL_3D`
- **AND** 无效区间 SHALL 断开或由明确标注的 2.5D 段替代，MUST NOT 无标记地连接
- **AND** 可展示段 SHALL 通过统一 3D 视图呈现，质量资格 SHALL 由指标字段控制而不是通过整块说明卡表达

#### Scenario: 三维不足但落点可用

- **WHEN** 可靠三维段不足但落点满足权威条件
- **THEN** 3D overall status SHALL 为 `LANDING_ONLY`
- **AND** 页面 SHALL 保留权威落点数据供轨迹和技术详情使用，并可同时显示独立通过可视化门的估算 2.5D 段
- **AND** 普通报告 SHALL 不重复显示落点资格、2.5D 说明或逐段诊断文案

#### Scenario: 三维和权威落点均不可用但估算段可用

- **WHEN** 3D overall status 为 `UNAVAILABLE` 且存在合格 visualization-only 段
- **THEN** `display_trajectory_status` SHALL 为 `degraded`
- **AND** 页面 SHALL 展示估算球路及其可视轨迹
- **AND** SHALL 隐藏无资格的速度、最高点和权威落点
- **AND** SHALL 不在普通球路卡片中显示“估算 2.5D”限制说明或环境离群诊断
