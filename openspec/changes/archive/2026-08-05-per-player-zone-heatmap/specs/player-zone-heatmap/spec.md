## ADDED Requirements

### Requirement: 系统暴露球员空间热力图（区域占用）数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点返回 `zone_stats` 对象，包含每名球员在三个球场区域（kitchen/transition/backcourt）的占用统计、Kitchen Control Rate、平均站位距厨房线距离、数据充分性与反馈文案。

#### Scenario: 分析完成后返回区域统计

- **WHEN** 分析任务状态为 `completed`，且球员轨迹 artifact 存在
- **THEN** `zone_stats.players` 数组包含每名球员，每项含 `id`、`label`（"球员N"）、`color`、`denominator_seconds`、`tracked_seconds`、`data_sufficiency`、`kitchen_control_rate`、`avg_distance_to_kitchen_line_m` 及 `zones: [{zone, label, seconds, occupancy}]`

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

后端 SHALL 计算每名球员时间加权平均站位距厨房线距离（英尺转米），并使用硬编码基准常数 `kitchen_line_reference_distance_m` 生成反馈等级与文案；反馈文案 SHALL 将常数标注为"参考基准"。

#### Scenario: 平均站位距离时间加权

- **WHEN** 计算某球员平均站位距厨房线距离
- **THEN** 结果 SHALL 为该球员在有效时间内各点距最近厨房线距离的时间加权平均，单位米，保留一位小数

#### Scenario: 距离低于基准判定优秀

- **WHEN** 球员平均站位距厨房线距离 ≤ `kitchen_line_reference_distance_m`
- **THEN** 反馈等级为 `excellent`，文案描述网前控制优秀

#### Scenario: 距离高于基准判定不足

- **WHEN** 球员平均站位距厨房线距离 > 1.5 × `kitchen_line_reference_distance_m`
- **THEN** 反馈等级为 `insufficient`，文案包含实际距离、与"参考基准"的差值以及 Kitchen Control Rate 百分比

#### Scenario: 有效帧不足时标记数据不充分

- **WHEN** 球员在有效窗口内 `tracked_seconds / denominator_seconds` 低于阈值（默认 0.3）
- **THEN** `data_sufficiency` 为 `insufficient`，且仍返回基于现有帧计算的指标，供前端显示警示而非硬给结论

### Requirement: 前端从结构化数据渲染区域空间热力图

前端 SHALL 新增 `StructuredZoneHeatmap` 组件，用 SVG 渲染三段横带球场底图，每段按选中球员占用率着色，并展示区域占用条、KCR、平均站位距离与反馈文案。

#### Scenario: 正常渲染区域热力图

- **WHEN** 前端收到有效 `zone_stats` 数据
- **THEN** 渲染三段球场底图（Kitchen/Transition/Backcourt），顶部提供球员单选 chip，选中球员的三区占用率、KCR、平均站位距离与反馈文案可见

#### Scenario: 有效帧不足时显示警示

- **WHEN** 选中球员的 `data_sufficiency` 为 `insufficient`
- **THEN** 卡片显示"有效帧不足"警示，不将占用百分比呈现为确定结论

#### Scenario: 无区域统计数据时降级

- **WHEN** `zone_stats` 缺失或 `players` 为空
- **THEN** 组件显示"暂无区域统计"占位，不渲染空白球场
