## 1. 结构化区域数据接入报告证据层

- [x] 1.1 将 `PlayerReportEvidenceSources.visualization` 从弱类型占位改为可消费的 `StructuredVisualizationData | null`，并为 `courtCoverage` 增加 selected canonical player 的区域统计证据类型。
- [x] 1.2 在 `usePlayerReportEvidence` 的真实 job 加载流程中并行读取 `getStructuredVizData(jobId)`，保留 404、请求失败和旧任务缺失 artifact 的显式状态，不阻断其他证据加载。
- [x] 1.3 在 `buildPlayerReportEvidence` 中从 `zone_stats.players` 按 canonical player ID 提取区域统计，生成带 `structured_visualization` provenance 的 `EvidenceValue`，禁止从位置网格推断区域占用。
- [x] 1.4 为结构化数据缺失、球员无法匹配、区域统计为空和数据充分性不足补充 unavailable/insufficient reason 文案与状态转换测试。

## 2. 报告页真实区域空间热力图

- [x] 2.1 修改 `PbCourtCoverage`，使用证据层的真实 `zone_stats` 渲染 `StructuredZoneHeatmap`，移除将 `HeatmapPlayerGrid` 误包装成区域统计的路径。
- [x] 2.2 让报告页的区域热力图与当前 selected canonical player 同步，展示三区占用、NVZ 占用率、站位距离、反馈和有效帧不足提示。
- [x] 2.3 真实 job 缺少区域 artifact 时显示 `PbEvidenceUnavailable` 及原因；禁止显示静态演示球场或伪造区域结果，并保持显式 demo 路由兼容。
- [x] 2.4 增加报告页组件测试，覆盖真实 `zone_stats` 渲染、canonical player 切换、artifact 404/失败和 `data_sufficiency=insufficient`。

## 3. 统一报告有效性判断

- [x] 3.1 新增纯函数报告 capability 判定，基于 completed Job、可读取 result manifest、有效 canonical 轨迹点/运动指标/available structured visualization artifact 判定 `loading`、`available` 或 `unavailable`。
- [x] 3.2 为空数组、非有限坐标、仅 skipped/failed artifact、无球员证据和有效移动证据但缺区域统计等边界补充单元测试。
- [x] 3.3 更新 `computeLibraryViewCapabilities`，报告 Tab 不再仅凭 Job ID 或 manifest 存在判定可用；再次分析期间继续使用旧 completed 结果的 capability。

## 4. 所有报告入口统一门控

- [x] 4.1 更新 `LibraryItemWorkspace` 顶部“报告”Tab，在 loading/unavailable 时使用原生 `disabled`、灰色样式和可解释原因，并阻止程序化 `goView("report")` 绕过门控。
- [x] 4.2 更新 `VisionPage` 的 status rail、嵌入式下级报告动作和 `onSelectView("report")`，与共享 capability 保持一致。
- [x] 4.3 更新 `AnalysisJobPage` 完成态报告按钮，区分“任务完成但报告无有效数据”和“报告可用”，避免静态 reportActions 绕过门控。
- [x] 4.4 更新 `ReportContent`/独立报告路由，在 direct URL 没有有效报告证据时显示稳定空态和返回路径，不回退到 demo 或其他 Job 产物。

## 5. 回归测试与验收

- [x] 5.1 增加 workspace capability 测试，覆盖未分析、分析完成无有效证据、分析完成有运动证据但无区域数据、分析完成有完整区域数据和再次分析期间旧结果保持可用。
- [x] 5.2 增加视频分析页/任务完成页/嵌入式 workspace 的报告入口一致性测试，验证所有入口在 unavailable 时不可点击且不发生导航。
- [x] 5.3 使用真实 job fixture 验证 `/visualization-data` 的 canonical `Player_N`、三区统计、provenance 和报告渲染结果；验证历史无 structured JSON 的任务安全降级。
- [x] 5.4 运行相关 Vitest、TypeScript 检查和 OpenSpec 变更校验，确认没有 demo 数据泄漏、旧 PNG fallback 与现有多摄 canonical 语义回归。
