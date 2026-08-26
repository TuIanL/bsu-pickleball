# ball-detection-quality-gates Specification

## Purpose
定义球候选、单视角跟踪、轨迹连续性、双摄关联和默认发布之间统一的精度优先质量门与诊断契约，确保误检可解释、长缺口不被错误连接、低质量结果只保留在诊断层。

## Requirements

### Requirement: 球候选必须通过分层质量门

系统 SHALL 对每个 detector 候选执行几何、置信度、尺度/形状和区域约束，并输出明确的接受、拒绝或仅诊断状态。对于有标定的视角，候选 SHALL 通过由球场空间棱柱投影得到的图像包络；对于无可靠标定的视角，系统 SHALL 使用带降级标记的宽松 ROI。任何单一置信度值 MUST NOT 单独决定候选进入正式球路。

#### Scenario: 场边物体落在球场包络外

- **WHEN** 候选框位于投影球场空间棱柱包络之外，且不存在正在进行的合法重捕获解释
- **THEN** 系统 SHALL 拒绝该候选进入正式 tracker observation
- **AND** SHALL 记录 `outside_court_projection` reason code

#### Scenario: 空中球产生合理投影偏移

- **WHEN** 候选框因球的估计高度落在地面边界外但仍落在 3D 球场棱柱投影内
- **THEN** 系统 SHALL 允许候选继续参与时间与运动质量门
- **AND** MUST NOT 仅因其不在地面四边形内而拒绝

#### Scenario: 候选框尺度或形状异常

- **WHEN** 候选框的面积比例、宽高比或尺度变化超过当前图像位置对应的配置范围
- **THEN** 系统 SHALL 拒绝或标记为 `diagnostic_only`
- **AND** SHALL 记录具体尺寸/形状 reason code

### Requirement: 球路锁定与重捕获必须经过时间连续性确认

系统 SHALL 使用至少 `tentative`、`locked` 和 `lost/searching` 的轨迹状态。新候选 MUST 在配置的时间窗口内满足 N-of-M 观测和连续性条件后才能锁定；重捕获 MUST 使用不宽于正常跟踪的门控。`tentative` 和未通过重捕获门控的观测 MUST NOT 进入默认球路或权威重建。

#### Scenario: 单帧误检

- **WHEN** 一个候选只在单个采样时刻出现且前后没有满足连续性的观测
- **THEN** tracker SHALL 保持未锁定状态或转为拒绝
- **AND** 该候选 SHALL 只出现在诊断计数中

#### Scenario: N-of-M 确认

- **WHEN** 候选在配置窗口内满足最小观测数、时间连续性和运动门控
- **THEN** tracker SHALL 将状态置为 `locked`
- **AND** 仅从确认点起向正式球路发布

#### Scenario: 丢失后的错误接管

- **WHEN** 已锁定轨迹进入 `lost/searching` 且新候选与最后可信状态的空间、尺度或速度差异超过重捕获门
- **THEN** 系统 SHALL 不得用该候选接管旧轨迹
- **AND** SHALL 关闭或断开旧段并记录重捕获拒绝原因

### Requirement: 球路运动约束必须使用实际时间

系统 SHALL 基于真实 `timestamp_sec` 计算速度、方向变化、加速度和候选间隔，并 SHALL 根据当前视角/尺度与轨迹状态使用可配置的自适应阈值。出现无法由配置运动范围解释的跳变时，系统 MUST 断开或降级轨迹，而不是仅依靠高 detector confidence 继续连接。

#### Scenario: 不同采样 stride 的相同运动

- **WHEN** 同一段视频以不同 `frame_stride` 生成观测
- **THEN** 运动门控 SHALL 使用观测实际时间差计算
- **AND** 不得把采样点数量当作时间间隔

#### Scenario: 突然跨画面跳变

- **WHEN** 相邻可信观测需要超出速度/加速度/方向变化门限才能连接
- **THEN** 系统 SHALL 标记 `motion_jump` 并结束当前连续段
- **AND** 后续观测 SHALL 重新经过确认或重捕获流程

### Requirement: 长缺口不得被轨迹插值跨越

系统 SHALL 以秒为单位配置和执行最大插值缺口。插值 MUST NOT 跨越最大缺口、`lost/searching`、tracker reset、异常跳变或明确的事件边界；超出条件时 SHALL 产生断点并从新观测重新建立 segment。每个插值样本 SHALL 保留来源和缺口上下文。

#### Scenario: 短缺口

- **WHEN** 相邻有效观测的时间差不超过最大缺口秒数且两端状态连续
- **THEN** 系统 MAY 生成 `interpolated` 样本
- **AND** SHALL 保存插值时长、端点时间和来源标记

#### Scenario: 长缺口

- **WHEN** 相邻有效观测的时间差超过最大缺口秒数
- **THEN** 系统 SHALL 不得在两端之间生成连续球路
- **AND** SHALL 保存 gap boundary reason 供 artifact 和前端断线使用

#### Scenario: 丢失后重新出现

- **WHEN** tracker 在缺口期间进入 `lost/searching` 或发生 reset，随后出现新候选
- **THEN** 新候选 SHALL 从新 segment 或新确认窗口开始
- **AND** MUST NOT 通过插值或平滑跨越旧段与新段

### Requirement: 双摄关联必须通过几何与连续性共识

系统 SHALL 对双摄候选 pair 检查时间匹配、重投影误差、三角测量几何质量、3D 球场棱柱范围、相邻时刻运动连续性和相对次优 pair 的歧义余量。只有通过硬门且满足最小质量 margin 的 pair 才能成为权威双摄观测；未通过的 pair MAY 保留为诊断，但 MUST NOT 驱动权威 anchor、三角测量或默认 overlay。

#### Scenario: 双视角候选唯一且几何一致

- **WHEN** pair 的时间差、重投影残差、3D 范围和运动连续性均通过硬门，且优于次优 pair 达到 margin
- **THEN** 系统 SHALL 将其标记为权威双摄观测
- **AND** SHALL 允许其进入三角测量和重建质量统计

#### Scenario: 候选配对歧义

- **WHEN** 最优 pair 与次优 pair 的分数差低于最小 margin 或几何残差无法区分
- **THEN** 系统 SHALL 标记 `ambiguous_pair`
- **AND** 不得把该 pair 作为权威观测发布

#### Scenario: 双摄重建超出物理范围

- **WHEN** pair 的三角测量结果超出球场空间棱柱、出现非有限坐标或不满足配置的运动范围
- **THEN** 系统 SHALL 拒绝该 pair 的重建资格
- **AND** SHALL 保存几何/物理拒绝原因

### Requirement: 球分析必须输出质量门诊断

系统 SHALL 输出可按任务、视角、tick、候选、track、segment 和双摄 pair 查询的诊断摘要。诊断至少 SHALL 包含候选总数与各拒绝原因、状态转移、确认/丢失/重捕获计数、缺口秒数与断点原因、跨视角 pair 分数/残差/歧义及最终展示资格。诊断 MUST 与发布 artifact 的 provenance 一致。

#### Scenario: 查询单视角误检诊断

- **WHEN** 用户或测试读取某任务球分析诊断
- **THEN** 响应 SHALL 能定位候选被拒绝的阶段和 reason code
- **AND** SHALL 区分 detector 未产生候选与质量门拒绝候选

#### Scenario: 查询轨迹展示资格

- **WHEN** 某 segment 没有进入默认 overlay
- **THEN** 诊断 SHALL 包含其观测覆盖、插值/预测比例、断点、质量门结果和 `display_eligible` 原因
- **AND** 该结果 SHALL 与 reconstructed artifact 的字段一致
