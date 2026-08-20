# Tasks: multiview-observability-visualization

## 1. 基础与可视化层

- [x] 1.1 安装 `echarts` 依赖并加入 `package.json`
- [x] 1.2 新建 `src/components/platform/viz/EChart.tsx` 封装组件：按需从 `echarts/core` 注册（Bar/Pie/Line/Heatmap/Funnel/Gauge + Grid/Tooltip/DataZoom），统一语义色与容器 resize
- [x] 1.3 新增 `src/lib/observabilityViz.ts`：健康度评分推导（availability 加权 + effective_multiview_ratio + 恢复成功率）与一句话结论生成，标注"前端汇总"
- [x] 1.4 为评分与图表组件补单元测试（最小数据 fixture，覆盖 available/partial/unavailable/not_applicable 四态）

## 2. L1 概览层

- [x] 2.1 重构 `MultiviewObservabilityPage` 顶部：新增 L1 概览条（一句话结论 + 健康度评分 + "前端汇总"标注）
- [x] 2.2 实现 SYNC → FUSION → RECOVERY → REFINEMENT 流水线状态灯（纯 HTML/CSS）：availability 映射绿/黄/红/灰，每阶段显示一个关键数字
- [x] 2.3 流水线阶段点击 → 滚动定位至对应 L2 图表卡并高亮

## 3. L2 图形层（四大域图表）

- [x] 3.1 同步权威：per-view authority 双视角对比柱（参考机位高亮），替换 SyncAuthorityPanel 内 MetricRow 网格
- [x] 3.2 融合质量：effective_multiview_ratio 环形图 + status_counts 堆叠条 + 样本量注释，替换 FusionQualityPanel 内 MetricRow 网格
- [x] 3.3 恢复漏斗：funnel 六段漏斗图（宽=计数/机会，标注各级转化率与流失原因），替换 RecoveryPanel 顶部 MetricRow 网格
- [x] 3.4 精修门控：execution / publication 决策门控流程可视化（F0 → 精修 → 安全门 → F1/F0，当前状态高亮），替换 RefinementSafetyPanel 内 MetricRow 网格
- [x] 3.5 每个图表悬停 tooltip 输出原始值 + reason 原文（authority_reason / reason_code / safety_gate.reason / outcome 标签）

## 4. L3 明细层与热力图

- [x] 4.1 球员显示诊断热力图：按窗口分段调用 `getPlayerDisplayDiagnostics(jobId, playerId, timestampMs, windowMs=2000)` 并拼接为 (9 stage × tick) 矩阵
- [x] 4.2 热力图渲染：通过 / 卡住 / 未触发三色编码，缺失段以"未触发"占位不伪造；球员切换重新拉取
- [x] 4.3 热力图格点击 → 复用 `onSeek` 定位 Debug Replay 视频（debug 不可用时仅高亮）
- [x] 4.4 L3 明细层默认折叠：MetricRow 明细、Recovery Episodes 表格、技术运行详情统一折叠管理，展开后与改造前等价

## 5. 交互与时间筛选

- [x] 5.1 恢复卡片时间范围筛选控件（起止 ms slider），驱动漏斗过滤与 episodes 请求 `from_ms`/`to_ms`
- [x] 5.2 恢复时间线可视化：episodes 按 start/end_ms 绘制事件时间线（outcome 着色），点击事件定位 Debug Replay
- [x] 5.3 空数据/降级分域占位：所有图表对 partial/unavailable 显示占位说明，不渲染空坐标系

## 6. 收尾与验证

- [x] 6.1 适配 `MultiviewObservabilityPage.test.tsx` 至新 DOM 结构，补充流水线状态灯与折叠行为测试
- [x] 6.2 `npm run build` 通过，验证 echarts 按需引入后产物增量（目标 < 150KB gzip）
- [x] 6.3 全页面走查：late_fusion_v1 任务（recovery/refinement 不适用）、degraded joint 任务、debug 视频缺失三种场景降级展示正确
- [x] 6.4 更新 docs 中与联合运行状态页面相关的说明（如有）
