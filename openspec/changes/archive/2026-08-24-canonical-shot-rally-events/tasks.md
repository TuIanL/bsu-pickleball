## 1. 建立数据契约与校验模型

- [x] 1.1 定义 `shot-rally-events.v1` 与 `metric-snapshot.v1` 的 TypeScript/Pydantic 数据模型，覆盖状态、详情、单位、质量、来源、计算版本和证据引用
- [x] 1.2 定义 `rally_id`、`shot_id`、`ordinal` 的确定性生成规则及唯一性校验，并统一 `Player_N`、已确认、含糊和未分配的归属状态
- [x] 1.3 建立首批指标字典与 `product_reference_v1` 样本充分性阈值，明确每项指标的单位、分子、分母和适用范围

## 2. 接入分析产物路径与 API

- [x] 2.1 增加 canonical shot/rally events 与 metric snapshot 的产物路径解析，并扩展 `AnalysisPipelineResult.artifacts`，同时覆盖 capture 和 legacy 目录
- [x] 2.2 在分析产物 API 注册 `shot-rally-events`、`metric-snapshot` slug，返回 JSON；对缺失产物返回 404，并增加路径遍历和跨 job 访问保护
- [x] 2.3 增加产物序列化与状态测试，覆盖 available、skipped、insufficient_evidence、unavailable、failed 和空事件数组

## 3. 组合现有识别结果生成规范产物

- [x] 3.1 实现后处理组合器，读取现有 ball-shot-assembly、serve、rally、trajectory 和 roster 结果，不新增第二套击球检测或归属状态机
- [x] 3.2 将现有结果映射为 Rally/Shot 字段，保留确认、含糊、未分配及缺失语义字段，并写入时间、空间、轨迹、质量、来源和证据引用
- [x] 3.3 实现确定性的 Metric Snapshot 聚合，输出 match、team、player 范围及 numerator、denominator、sample_count、status，禁止除零和无证据填值
- [x] 3.4 将产物生成接入完成态 job 流程；不得因指标不足使视觉分析失败，并支持旧 job 重生成或显式标记可选产物状态

## 4. 接入 Player Report Evidence

- [x] 4.1 扩展 Shot Evidence/report evidence adapter，使其读取 canonical events，并通过 `rally_id` 与 ordinal 暴露回合上下文和阶段选择
- [x] 4.2 将 Metric Snapshot 映射为 `EvidenceValue`，保留数值、分子/分母、状态、原因、来源和置信度，移除该路径上的 mock 或第二数据源回退
- [x] 4.3 增加集成测试，覆盖真实 job 与 demo 数据隔离、canonical ID 映射、第三拍筛选、含糊归属和不可用指标

## 5. 固定样例并完成回归验证

- [x] 5.1 增加确认归属、含糊归属、未分配、击球缺失、重复击球、单打、双打和短样本样例
- [x] 5.2 增加重复生成一致性测试，以及 evidence_ids 对 canonical event/metric 的完整性校验
- [x] 5.3 验证产物 API、路径解析、TypeScript/Python 类型检查，并回归现有 report、trajectory 和 shot assembly 测试
- [x] 5.4 编写面向后续 `performance-score.v1` 的交接说明，明确本 change 只提供可追溯事实与描述性指标，继续禁用未经校准的数值技能评分
