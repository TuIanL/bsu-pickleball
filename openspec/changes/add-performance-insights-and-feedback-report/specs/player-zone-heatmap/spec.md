## MODIFIED Requirements

### Requirement: 系统暴露球员空间热力图（区域占用）数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点返回 `zone_stats` 对象，包含每名球员在三个球场区域（kitchen/transition/backcourt）的占用统计、NVZ occupancy rate（canonical 字段 `nvz_occupancy_rate`）、平均站位距厨房线距离、数据充分性与描述性反馈文案。每名球员的 `id` SHALL 为 canonical player ID（`Player_1`..`Player_4`），`label` SHALL 为 `P1`..`P4`（与视频叠加 HUD 对齐）。

#### Scenario: 分析完成后返回区域统计

- **WHEN** 分析任务状态为 `completed`，且球员轨迹 artifact 存在
- **THEN** `zone_stats.players` 数组包含每名球员，每项含 `id`（canonical `Player_N`）、`label`（`P1`..`P4`）、`color`、`denominator_seconds`、`tracked_seconds`、`data_sufficiency`、`nvz_occupancy_rate`、`avg_distance_to_kitchen_line_m` 及 `zones: [{zone, label, seconds, occupancy}]`

#### Scenario: kitchen_control_rate 作为 deprecated alias 输出

- **WHEN** 后端返回 `zone_stats` 且包含 `nvz_occupancy_rate`
- **THEN** 响应 SHALL 同时输出 `kitchen_control_rate`，数值与 `nvz_occupancy_rate` 完全一致，语义标注为 deprecated（兼容迁移期）
- **AND** `nvz_occupancy_rate` 与 `kitchen_control_rate` SHALL 使用同一分子（NVZ 内停留时间）与同一有效时间分母

#### Scenario: 无坐标点时返回空数组

- **WHEN** 球员轨迹数据中无有效坐标点
- **THEN** `zone_stats.players` 为空数组

#### Scenario: 三分区占用率之和归一

- **WHEN** 计算某球员的区域占用率
- **THEN** kitchen/transition/backcourt 三区的 `seconds` 之和不超过 `denominator_seconds`，且各 `occupancy` 在 [0,1] 区间

### Requirement: 输出平均站位距厨房线距离与网前控制反馈

后端 SHALL 计算每名球员时间加权平均站位距厨房线距离（英尺转米，量球员所属半场的厨房线），并基于基准常数 `kitchen_line_reference_distance_m` 生成描述性反馈档位与文案；反馈 SHALL 只描述站位与 NVZ 占用事实，MUST NOT 表达网前控制能力评价（评价性判断由 Performance Insights Engine 综合多项 evidence 推导）。

#### Scenario: 平均站位距离时间加权且量所属半场

- **WHEN** 计算某球员平均站位距厨房线距离
- **THEN** 结果 SHALL 为该球员在有效时间内各点距其所属半场厨房线距离的时间加权平均，单位米，保留一位小数
- **AND** 球员出现在对方半场时 MUST NOT 量到对方厨房线；无法判定所属半场时 SHALL 回退最近厨房线并在反馈中标注口径受限

#### Scenario: 距离档位为描述性反馈

- **WHEN** 球员平均站位距厨房线距离 ≤ `kitchen_line_reference_distance_m`
- **THEN** 反馈档位为贴近线一档（如 `near_line`），文案描述为"平均站位较接近厨房线，NVZ 占用率 X%"等事实陈述
- **WHEN** 距离 > 1.5 × `kitchen_line_reference_distance_m`
- **THEN** 反馈档位为距线较远一档（如 `deep`），文案包含实际距离与参考基准差值的事实陈述
- **AND** 反馈文案 MUST NOT 使用"网前控制优秀/良好/不足"等能力评价措辞

#### Scenario: 有效帧不足时标记数据不充分

- **WHEN** 球员在有效窗口内 `tracked_seconds / denominator_seconds` 低于阈值（默认 0.3）
- **THEN** `data_sufficiency` 为 `insufficient`，且仍返回基于现有帧计算的指标，供前端显示警示而非硬给结论
