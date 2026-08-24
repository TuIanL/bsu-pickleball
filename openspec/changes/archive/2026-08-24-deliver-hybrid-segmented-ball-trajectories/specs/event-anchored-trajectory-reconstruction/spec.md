## MODIFIED Requirements

### Requirement: 锚点数量降级策略
系统 SHALL 根据可用空间锚点数量选择重建模式，锚点不足时不得伪装高可信球场空间重建；单锚点模式 MUST 识别锚点位于段起点还是段终点，并严格对齐对应端。

#### Scenario: 双锚点模式
- **WHEN** 起止均为空间锚点（bounce→hit、hit→bounce、hit→hit、bounce→bounce）
- **THEN** 系统 SHALL 执行 `dual_anchor_warp` 完整双端锚定重建
- **AND** 重建模式 SHALL 记录为 `dual_anchor_warp`

#### Scenario: 起点单锚点模式
- **WHEN** 仅起点有空间锚点（bounce→loss、hit→loss）
- **THEN** 系统 SHALL 将第一个可用重建采样严格对齐起点锚点
- **AND** 另一端 SHALL 使用 pseudo path 相对位移并渐隐，不生成精确终点
- **AND** 该段总体质量上限 SHALL 受限

#### Scenario: 终点单锚点模式
- **WHEN** 仅终点有空间锚点（unknown→bounce、loss→hit）
- **THEN** 系统 SHALL 将最后一个可用重建采样严格对齐终点锚点
- **AND** 未知起点 SHALL 使用反向相对位移并渐隐
- **AND** MUST NOT 把第一个采样错误地对齐终点锚点

#### Scenario: 无锚点模式
- **WHEN** 段两端均无空间锚点（loss→loss、unknown→unknown）
- **THEN** 系统 SHALL 标记 `reconstruction_mode = image_only` 或 `single_view_visual_arc`
- **AND** `single_view_visual_arc` MUST 标记 `metric_validity = visualization_only` 且默认使用低可信视觉编码
- **AND** 原始图像拟合 SHALL 保留用于视频轨迹或调试

#### Scenario: 锚点距离过小
- **WHEN** 两端锚点距离小于 `minimum_anchor_distance`
- **THEN** 系统 SHALL 降级为 `local_visual_arc` 或不输出该重建段
- **AND** MUST NOT 以极小距离为分母计算主轴

## ADDED Requirements

### Requirement: 场外球点的证据分类
系统 SHALL 将标准场地边线和可配置比赛环境边界分开处理；坐标越过标准边线 SHALL 只产生位置事实，MUST NOT 单独作为误检拒绝条件或自动界外判罚。

#### Scenario: 真实界外落点候选
- **WHEN** bounce 位于标准场地边线外但仍处于比赛环境边界内，且同段轨迹连续、端点时间与图像证据一致
- **THEN** 系统 SHALL 保留该 bounce 并标记 `legal_out_candidate`
- **AND** SHALL 明确该分类不是自动判罚结论

#### Scenario: 标定不确定可解释的场外坐标
- **WHEN** 点略超比赛环境边界但偏差落在标定/投影不确定范围内
- **THEN** 系统 SHALL 标记 `calibration_uncertain` 并降低质量
- **AND** SHALL NOT 仅凭该坐标删除原始观测

#### Scenario: 环境离群误检
- **WHEN** 点严重超出比赛环境边界且同时出现轨迹跳变、静止模式、高回投残差或另一视角不支持
- **THEN** 系统 SHALL 标记 `environment_outlier` 并从正式重建段排除
- **AND** SHALL 保存所有触发证据用于审计

