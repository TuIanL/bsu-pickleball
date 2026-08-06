# trajectory-quality-evaluator Specification

## Purpose
定义多维轨迹质量评分（观测覆盖率、图像拟合残差、锚点置信度、推算比例、事件置信度、物理合理性）、展示阈值与过网物理合理性软诊断。
## Requirements
### Requirement: 多维质量评分
系统 SHALL 为每个飞行段计算多维质量评分，不能只使用单一平均置信度。

#### Scenario: 评分维度完整
- **WHEN** 系统评估一个飞行段
- **THEN** 质量评分 SHALL 至少包含：观测覆盖率、图像拟合残差（RMSE px）、锚点置信度、推算比例、事件置信度、物理合理性
- **AND** 评分 SHALL 汇总为单一 `overall` 分数用于展示筛选

#### Scenario: 高度可信度单独评估
- **WHEN** 系统评估使用接触高度先验的段
- **THEN** 高度可信度 SHALL 独立于检测可信度评估
- **AND** 高度可信度 SHALL 因使用全局低可信先验而受限

#### Scenario: 单锚点段质量上限
- **WHEN** 段为 `single_anchor_warp` 模式
- **THEN** 该段的总体质量 SHALL 受限于配置的上限，不能达到双锚点段的最高可信等级

### Requirement: 展示阈值
系统 SHALL 根据总体质量分数决定重建段的展示方式，宁可少显示也不伪装高可信。

#### Scenario: 高可信段正常显示
- **WHEN** 段 `overall` 分数达到高可信阈值
- **THEN** 该段 SHALL 以正常实线显示在默认球场视图

#### Scenario: 中可信段部分虚线
- **WHEN** 段 `overall` 分数处于中可信区间
- **THEN** 该段 SHALL 以估算样式（部分虚线）显示

#### Scenario: 低可信段仅调试显示
- **WHEN** 段 `overall` 分数低于低可信阈值但仍有观测
- **THEN** 该段 SHALL 仅在调试模式或原始检测模式显示，不进入默认球场视图

#### Scenario: 无锚点段不生成球场空间
- **WHEN** 段为 `image_only` 模式或缺少足够空间锚点
- **THEN** 该段 SHALL NOT 出现在默认球场空间视图

### Requirement: 物理合理性软诊断
系统 SHALL 对过网与弹地做物理合理性软诊断，作为质量评分与 diagnostics 的一部分，不作为硬门控。

#### Scenario: 过网状态分级
- **WHEN** 系统评估一个跨越球网平面的段
- **THEN** 过网状态 SHALL 记录为 `net_crossing_status`，取值为 `not_expected / expected / estimated / implausible / unknown`
- **AND** 状态 SHALL 进入 `physical_plausibility_score` 与 `diagnostics`

#### Scenario: 过网不硬门控
- **WHEN** 估算过网高度不足或无法确认高于网带
- **THEN** 系统 MUST NOT 因此删除轨迹或强行抬高轨迹
- **AND** 系统 SHALL NOT 输出"真实过网高度"或"擦网"结论

#### Scenario: 弹地物理一致性
- **WHEN** 段以弹地为边界
- **THEN** 系统 SHALL 校验弹地点高度为 0 且弹地后不凭空加速
- **AND** 一致性结果 SHALL 计入 `physical_plausibility_score`

### Requirement: 质量评分确定性
系统 SHALL 对相同输入产生确定性的质量评分。

#### Scenario: 重复运行结果一致
- **WHEN** 对同一输入重复运行质量评估
- **THEN** 各维度分数、`overall` 分数与展示阈值判定 SHALL 完全一致

