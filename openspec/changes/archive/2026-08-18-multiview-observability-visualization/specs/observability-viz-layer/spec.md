# observability-viz-layer Specification

## Purpose
联合运行状态页面的前端可视化层：ECharts 图表组件封装、三层信息架构（L1 概览 / L2 图形 / L3 明细）、流水线状态灯、健康度推导与悬停/下钻/时间筛选/视频定位交互。本能力只负责展示组织，MUST NOT 重算后端算法结论。

## ADDED Requirements

### Requirement: 三层信息架构

联合运行状态页面 SHALL 按 L1 概览层、L2 图形层、L3 明细层纵向组织。L1 SHALL 位于首屏上部，包含一句话结论、整体健康度与四阶段流水线状态灯；L2 SHALL 以图表卡呈现四大域；L3 SHALL 默认折叠，包含现有 MetricRow 明细、Recovery Episodes 表格与技术运行详情。

#### Scenario: 非专业用户首屏可读

- **WHEN** 页面加载完成且 summary 可用
- **THEN** 首屏（无需滚动）SHALL 呈现一句话结论、健康度与 SYNC / FUSION / RECOVERY / REFINEMENT 四阶段状态灯
- **AND** 每个阶段 SHALL 显示一个关键数字（如有效多视角比例、恢复次数与成功率、精修发布结果）

#### Scenario: 明细默认折叠可展开

- **WHEN** 页面加载完成
- **THEN** L3 明细层 SHALL 默认折叠
- **AND** 用户展开后 SHALL 看到与改造前等价的完整指标明细

### Requirement: 流水线状态灯

L1 流水线 SHALL 以 SYNC → FUSION → RECOVERY → REFINEMENT 顺序展示各阶段状态灯与关键数字。状态灯颜色 SHALL 映射 availability：`available` 为绿、`partial` 为黄、`unavailable` 为红、`not_applicable` 为灰。点击任意阶段 SHALL 滚动定位至对应 L2 图表卡。

#### Scenario: 状态灯映射

- **WHEN** 某分域 availability 为 `available`
- **THEN** 该阶段状态灯 SHALL 显示绿色
- **AND** `not_applicable` 分域（如 late_fusion 的 recovery）SHALL 显示灰色并标注"不适用"，不得显示为失败

#### Scenario: 点击下钻

- **WHEN** 用户点击 L1 流水线某一阶段
- **THEN** 页面 SHALL 平滑滚动至对应的 L2 图表卡并高亮

### Requirement: 健康度评分推导

前端 SHALL 基于后端已发布事实推导 0-100 健康度评分与一句话结论，输入 SHALL 仅限四域 availability、`effective_multiview_ratio` 与恢复漏斗计数。评分展示 SHALL 标注"前端汇总"字样；系统 MUST NOT 以评分替代或重算后端算法结论。

#### Scenario: 评分由既有字段推导

- **WHEN** summary 包含四域 availability 与融合/恢复计数
- **THEN** 前端 SHALL 计算并显示健康度评分与一句话结论
- **AND** `not_applicable` 分域 SHALL 不计入权重

#### Scenario: 部分事实缺失不误报

- **WHEN** 某分域 availability 为 `unavailable` 或 `partial`
- **THEN** 评分 SHALL 按降级权重计算
- **AND** 页面 SHALL 显示对应降级原因文本，MUST NOT 显示为高分或算法失败

### Requirement: ECharts 图表组件封装

系统 SHALL 提供 `components/platform/viz/` 下的 ECharts 封装组件，按需从 `echarts/core` 注册所需图表与组件，MUST NOT 整体引入全量 echarts。封装组件 SHALL 统一处理主题色（沿用项目绿/黄/红语义色）、空数据占位与容器 resize。

#### Scenario: 按需加载

- **WHEN** 页面引入图表组件
- **THEN** 构建产物仅包含注册过的图表与组件模块
- **AND** 未使用模块不得进入产物（以构建体积验证）

#### Scenario: 空数据占位

- **WHEN** 某图表数据为空或分域不可用
- **THEN** 图表区域 SHALL 显示占位说明（沿用 SectionBadge 语义）
- **AND** SHALL NOT 渲染空坐标系或伪造数据

### Requirement: 悬停提示与原因下钻

图表元素悬停 SHALL 显示该数据点的原始值与对应原因文本（`authority_reason` / `reason_code` / `safety_gate.reason` / outcome 标签）。tooltip SHALL 使用后端已发布字段，MUST NOT 现场计算新结论。

#### Scenario: 悬停显示原文

- **WHEN** 用户悬停恢复漏斗某一级或融合环形某一扇区
- **THEN** tooltip SHALL 显示计数、转化率及该级相关 reason 原文（若存在）
- **AND** 悬停不改变页面其他区域状态

### Requirement: 时间范围筛选联动

恢复卡片 SHALL 提供时间范围筛选控件，驱动恢复漏斗过滤与 episodes 查询的 `from_ms`/`to_ms` 参数，并与恢复时间线联动。

#### Scenario: 刷选联动

- **WHEN** 用户调整时间范围
- **THEN** 恢复漏斗计数 SHALL 按窗口内 episodes 重新统计
- **AND** episodes 请求 SHALL 携带 `from_ms`/`to_ms`，时间线 SHALL 缩放至该范围

### Requirement: 视频定位联动

恢复时间线事件与球员显示热力图格点击 SHALL 复用现有 `canSeek` / `debug_video_seek_ms` 机制定位 Debug Replay 视频。

#### Scenario: 点击事件定位视频

- **WHEN** 用户点击恢复时间线上某 episode 事件或热力图某格
- **THEN** Debug Replay 视频 SHALL 定位至该事件 `debug_video_seek_ms`（或对应 tick 时间）
- **AND** 若 debug 视频不可用，点击 SHALL 仅高亮事件，不报错
