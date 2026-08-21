## ADDED Requirements

### Requirement: 产物新增 v3 多视角估算三维语义
系统 SHALL 在既有 `reconstructed_ball_trajectory.v2`（2.5D）之上新增 `reconstructed_ball_trajectory.v3`，用于多视角估算三维球路；v1/v2 保留以兼容旧任务与单摄。

#### Scenario: v3 顶层语义
- **WHEN** 系统输出 v3 产物
- **THEN** 顶层 SHALL 声明 `schema_version = reconstructed_ball_trajectory.v3`
- **AND** `reconstruction_mode` SHALL 为 `multiview_estimated_3d`
- **AND** `coordinate_semantics` SHALL 包含 `xy = canonical_court_ft`、`z = estimated_multiview_height_ft` 与 `validity = approximate_multiview`

#### Scenario: v3 与 v1/v2 兼容语义
- **WHEN** 系统决定某 job 输出球轨迹的 schema 版本
- **THEN** 历史任务或单摄任务 SHALL 输出 v1/v2（2.5D），且不予回写或覆盖历史文件
- **AND** 新合格双摄任务 SHALL 在同一语义 slug（`reconstructed_ball_trajectory.json`）输出 v3（`multiview_estimated_3d`）
- **AND** 系统 SHALL NOT 新增 `legacy_2_5d_baseline` 平行产物（产品已不以假 2.5D 为默认回退）

### Requirement: 指标级 validity 分级
系统 SHALL 在产物中为每个指标声明独立的有效性，占用的可信度不同。

#### Scenario: 按指标分级
- **WHEN** 产物包含各类指标
- **THEN** 落点 SHALL 含 `landing_source ∈ {dual_view_ground_fused, single_view_ground}` 与 `landing_validity = high`
- **AND** `flight_z_validity`、`flight_xy_validity` SHALL 为 `dual_view_estimated`
- **AND** `average_speed_validity` SHALL 为 `conditional`（不满足资格时 `unavailable`）
- **AND** `instantaneous_speed_validity` SHALL 为 `not_output_v1`

#### Scenario: 段级覆盖率诊断
- **WHEN** v3 含飞行段
- **THEN** 每段 SHALL 声明 `stereo_coverage` 与 `prediction_ratio`
- **AND** 二者 SHALL 用于 speed eligibility 与前端渲染判断

### Requirement: 前端按版本降级读取
系统 SHALL 使前端沿用统一 `reconstructed-ball-trajectory` 概念读取 v1/v2/v3，并按 schema_version 降级，避免维护两条平行正式球路 artifact。

#### Scenario: 统一 slug 分版本降级
- **WHEN** 前端请求重建球路产物
- **THEN** 前端 SHALL 通过统一 `reconstructed-ball-trajectory` slug 读取
- **AND** 依据 `schema_version` 区分 v3（多视角估算 3D）与 v1/v2（2.5D）
- **AND** 无 v3 时专项能力（多视角 3D / 落点权威 / 平均球速）SHALL 显示明确不可用状态，而非静默失败

### Requirement: 分层可用状态写入产物
系统 SHALL 在产物中记录整体可用状态，供前端呈现分级降级，而非仅存在/缺失两态。

#### Scenario: 状态枚举
- **WHEN** 写入产物整体状态
- **THEN** 状态 SHALL 为 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE` 之一
- **AND** 该状态 SHALL 与段级/落点/球速有效性一致