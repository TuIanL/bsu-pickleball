# player-zone-heatmap Specification

## Purpose

定义球员空间热力图（区域占用）数据的后端输出、Kitchen Control Rate 计算口径、比赛有效时间分母分层解析、网前控制反馈文案生成，以及前端渲染与交互契约。
## Requirements
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

### Requirement: Kitchen Control Rate 使用比赛有效时间作为分母

后端 SHALL 按可用性分层解析"比赛有效时间"作为 KCR 分母：① job 携带 clip 区间（来自 rally 片段分析）→ 单一窗口；② job 关联的录制会话存在时间线事件 → 取 `rally_start`/`rally_end` 窗口并集（排除 non-play、暂停、换边区间）；③ 两者皆无 → 回退为球员轨迹首帧至末帧的总时长。

#### Scenario: rally 片段 job 使用 clip 区间

- **WHEN** job 携带 `clip_start_ms` 与 `clip_end_ms`
- **THEN** 分母 SHALL 等于 clip 区间时长，且仅 clip 区间内的轨迹点计入区域占用

#### Scenario: 双摄视频使用时间线 rally 净时间

- **WHEN** job 关联的录制会话存在 `rally_start`/`rally_end` 时间线事件且无 clip 区间
- **THEN** 分母 SHALL 等于各 rally 窗口时长之和，`non_play`、暂停、换边区间不计入分母也不计入分子

#### Scenario: 无比赛数据时回退总时长

- **WHEN** job 既无 clip 区间也无时间线 rally 事件
- **THEN** 分母 SHALL 等于该球员轨迹首帧至末帧的总时长，全部轨迹点计入区域占用

#### Scenario: 时间线事件缺失成对事件

- **WHEN** rally 窗口缺少对应的 `rally_end` 或时间戳异常
- **THEN** 该窗口被钳制到有效范围或丢弃，不使分母为负或无限

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

### Requirement: 前端从结构化数据渲染区域空间热力图

前端 SHALL 使用 `StructuredVisualizationData.zone_stats` 渲染区域空间热力图。视频分析页与真实 Player Report SHALL 消费同一份 job-scoped structured visualization artifact；报告组件 SHALL 通过 `PlayerReportEvidence` 获取当前 canonical player 的区域统计，不得使用位置网格或静态占位数据代替 `zone_stats`。

#### Scenario: 视频分析页正常渲染区域热力图

- **WHEN** 前端收到有效 `zone_stats` 数据
- **THEN** 渲染三段球场底图（Kitchen/Transition/Backcourt），顶部提供球员单选 chip，选中球员的三区占用率、NVZ 占用率、平均站位距离与反馈文案可见

#### Scenario: 真实报告页渲染区域热力图

- **WHEN** completed real job 的 `/visualization-data` 返回与 selected canonical player 匹配的 `zone_stats.players` 条目
- **THEN** Player Report 的“场地覆盖”卡 SHALL 使用该条目渲染区域空间热力图、三区占用条、NVZ 占用率、平均站位距厨房线和反馈
- **AND** 该卡 SHALL 标记或保留 structured visualization provenance，不得显示 demo 标记或静态演示区域

#### Scenario: 报告页缺少区域统计但仍有其他真实证据

- **WHEN** real job 报告存在有效运动证据，但 structured artifact 缺失、请求失败或没有 selected player 的 `zone_stats`
- **THEN** 报告整体 SHALL 继续渲染可用模块
- **AND** “场地覆盖”卡 SHALL 显示明确 unavailable 原因，不得渲染空白球场或从位置热力图猜测区域占用

#### Scenario: 有效帧不足时显示警示

- **WHEN** 选中球员的 `data_sufficiency` 为 `insufficient`
- **THEN** 卡片显示“有效帧不足”警示，不将占用百分比呈现为确定结论

#### Scenario: 无区域统计数据时降级

- **WHEN** `zone_stats` 缺失或 `players` 为空
- **THEN** 组件显示“暂无区域统计”或等价 unavailable 状态，不渲染空白球场

### Requirement: 热力图消费身份可信样本
zone heatmap、position heatmap 与 scatter plot SHALL 只消费正式 canonical trajectory 中 `confirmed_observed`、`confirmed_recovered`、`interpolated` 样本，并按球员返回 accepted/quarantined sample count、coverage 与 data sufficiency。下游 MUST NOT 从 raw track ID 或隔离样本重新推断 P 编号。

#### Scenario: P2 轨迹包含跨侧污染样本
- **WHEN** P2 quarantine diagnostics 含落在 P3/P4 side 的 cross-side samples
- **THEN** 这些样本 SHALL NOT 出现在 P2 热力图或散点图
- **AND** P2 统计 SHALL 显示 quarantined count 与覆盖不足提示

#### Scenario: 隔离后数据不足
- **WHEN** P2 accepted coverage 低于 sufficiency threshold
- **THEN** 前端 SHALL 显示“身份可信样本不足”
- **AND** SHALL NOT 把稀疏点计算结果呈现为确定表现结论

