## ADDED Requirements

### Requirement: fused overlay 覆盖率验收

joint 模式 visual acceptance SHALL 同时度量两个覆盖率指标：`reference_observed_coverage`（baseline：reference view 自身真实观测的帧覆盖率）与 `fused_overlay_coverage`（measured：最终可靠 overlay 的帧覆盖率，含 base/guided/refined 真实图像证据与 cross_view 可信双摄补全）。验收 SHALL 要求 `fused_overlay_coverage` 高于 `reference_observed_coverage` 并报告提升百分点，SHALL NOT 预设固定数值 gate（待真实素材跑完后再决定是否固化门槛）。验收过程 SHALL 使用真实双摄素材逐帧检查，而非仅检查"文件生成成功"。

#### Scenario: 双覆盖率度量

- **WHEN** joint visual acceptance 运行
- **THEN** 报告 SHALL 同时输出 `reference_observed_coverage`（baseline）与 `fused_overlay_coverage`（measured）
- **AND** 验收结论 SHALL 基于真实素材的逐帧检查

#### Scenario: 融合覆盖率提升

- **WHEN** fused overlay 覆盖率达到目标
- **THEN** `fused_overlay_coverage` SHALL 高于 `reference_observed_coverage`
- **AND** 缺失帧 SHALL 为证据不足的合理降级，而非单摄漏检造成的随机闪烁

### Requirement: fused overlay 硬不变量

joint visual acceptance SHALL 同时检查以下硬不变量，任一违反 SHALL 判为不通过：`invalid_projection_count = 0`（geometry 无效仍渲染投影）、`unknown_public_player_id_count = 0`（非 canonical Player_N 身份出现）、`overlay_player_count_per_tick <= expected_player_count`（单 tick 可见球员超限）、`cross_view_projected_without_donor = 0`（cross_view 缺 donor_view）、`prediction_over_ttl_rendered = 0`（超 TTL 仍渲染预测）。

#### Scenario: 投影无效即失败

- **WHEN** 任一 `cross_view_projected` 的投影 geometry 无效仍被渲染
- **THEN** `invalid_projection_count` 递增
- **AND** acceptance SHALL 判为不通过

#### Scenario: 身份与上限不变量

- **WHEN** acceptance 统计完成
- **THEN** `unknown_public_player_id_count` / `overlay_player_count_per_tick` 超限 SHALL 判为不通过
- **AND** `cross_view_projected_without_donor` / `prediction_over_ttl_rendered` 非零 SHALL 判为不通过

### Requirement: debug 产物与正式叠加层分离

`joint_debug_trace` 与正式 fused overlay SHALL 相互独立：debug trace 关闭时 fused overlay 仍可生成；debug trace 内容 SHALL 不进入正式 overlay 数据源。

#### Scenario: debug 关闭不影响正式产物

- **WHEN** `debugTraceEnabled=false` 运行 joint 分析
- **THEN** 正式 fused overlay SHALL 仍正常生成并可验收

#### Scenario: debug 内容不污染正式产物

- **WHEN** debug trace 开启时生成正式 fused overlay
- **THEN** overlay 数据源 SHALL 仍为 F0/F1 evidence，SHALL NOT 混入 debug trace 内容
