## ADDED Requirements

### Requirement: Composer 发布 Parent 级双摄球 evidence 与 v3 轨迹
`multiview_analysis_result_composer` SHALL 将球分析阶段的 immutable evidence 与用户轨迹写入 Parent 的公开 artifacts，并保持两者使用同一任务、同一输入窗口和同一 canonical 时间语义。

#### Scenario: joint 生成完整球路
- **WHEN** 球分析生成 evidence 与 v3 轨迹
- **THEN** Composer SHALL 在 Parent artifacts 中发布两个产物的 path/url/status/detail
- **AND** v3 的质量摘要 SHALL 能回溯到 evidence 的统计

#### Scenario: joint 仅生成部分球路
- **WHEN** evidence 存在但只有部分三维轨迹可用
- **THEN** Composer SHALL 发布完整 evidence 与 `PARTIAL_3D` v3 轨迹
- **AND** 不得因部分无效点而删除可用三维段

### Requirement: Composer 映射球分析状态而不篡改原始证据
Composer SHALL 只负责 schema 组装、artifact 发布和状态汇总，不得修改 evidence 中的原始候选、时间戳、帧索引或三角测量结果。球分析失败时，Composer SHALL 发布失败/不可用状态与 detail。

#### Scenario: 证据保持不可变
- **WHEN** Composer 读取球分析 evidence 并生成 Parent result
- **THEN** evidence 的内容 hash 或等价完整性信息 SHALL 保持不变
- **AND** Parent URL SHALL 指向已发布的不可变文件

#### Scenario: 球分析异常
- **WHEN** 球分析没有生成合法 v3
- **THEN** Composer SHALL 写入 `reconstructed_ball_trajectory_status` 与 detail
- **AND** SHALL 保留 player artifacts 及可用的 evidence（若存在）

### Requirement: Composer 的速度与质量字段使用统一语义
Composer SHALL 校验 v3 中的时间单位、距离单位、速度单位和质量状态，发现不一致时 SHALL 拒绝以成功状态发布，并将异常写入 detail。

#### Scenario: 速度单位校验
- **WHEN** 输入轨迹声明 `speed_kmh`
- **THEN** Composer SHALL 校验其数值已经从内部单位正确换算
- **AND** 不得把 `ft/s` 原值直接写入 `speed_kmh`

#### Scenario: 质量字段校验
- **WHEN** 输入 v3 包含覆盖率、重投影误差或三角测量角度
- **THEN** Composer SHALL 将这些指标与 overall status 一并发布
- **AND** 指标缺失或越界时 SHALL 降级或拒绝成功状态
