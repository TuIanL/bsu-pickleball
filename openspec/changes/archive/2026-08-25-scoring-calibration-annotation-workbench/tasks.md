## 1. 标注包契约与持久化模型

- [x] 1.1 定义 `scoring-calibration-annotation.v1` 的枚举、标注条目、候选决定、质量摘要和 Gold Set artifact schema。
- [x] 1.2 新增标注包 revision、标注条目和算法候选决定的后端模型，保存 CaptureTake、视频/机位、片段版本和候选产物 provenance。
- [x] 1.3 创建数据库迁移和索引，支持按 CaptureTake、revision、状态和证据时间排序查询，并保持对现有表的兼容。
- [x] 1.4 为 draft、reviewed、locked 生命周期和 locked revision 不可原地修改规则补充模型层测试。

## 2. 后端标注服务与 API

- [x] 2.1 实现按 CaptureTake 创建、查询和列出标注包 revision 的 service/API，并在没有可用视频时返回结构化阻塞原因。
- [x] 2.2 实现标注条目的创建、更新、删除/撤销和单条查询，支持证据时间窗、机会状态、结果、落点、置信度和备注。
- [x] 2.3 实现算法候选加载与人工决定保存，支持 `accepted`、`corrected`、`rejected`、`unreviewed`，且不修改 canonical shot/rally artifact。
- [x] 2.4 实现锁定前结构和语义校验，覆盖时间窗、必需字段、机会状态/结果、落点状态/区域和同回合重复发球检查。
- [x] 2.5 实现 reviewed/locked 流程，在锁定事务中生成规范化 Gold Set artifact、质量摘要和 revision provenance；失败时保留 draft。
- [x] 2.6 增加 Gold Set 查询/导出 API，只允许 locked revision 作为下游指标校准输入，并明确返回 schema version、revision 和质量摘要。

## 3. 前端入口与数据访问

- [x] 3.1 增加标注包、标注条目、候选决定、校验错误和质量摘要的 TypeScript 类型及 `analysisClient` API 封装。
- [x] 3.2 为 CaptureTake 增加进入评分校准工作台的入口和路由，不改变现有片段管理、实时编码和 Vidat 导入入口。
- [x] 3.3 创建工作台页面骨架，加载 CaptureTake 视频、机位选项、回合片段、算法候选和当前 draft，并实现独立的加载、空数据、失败和保存状态。

## 4. 标注交互工作台

- [x] 4.1 复用 `SegmentVideoPlayer` 实现视频播放、暂停、拖动、逐帧控制和证据窗口定位；支持标注回看时跳转到对应时间窗。
- [x] 4.2 实现候选/人工事件时间轴与标注队列，展示回合上下文、未标注、未复核、不确定和 warning 筛选状态。
- [x] 4.3 实现标注表单，覆盖阶段、击球人、机会状态、结果、落点可观察性、落点区域、置信度和备注，并阻止明显不一致的组合提交。
- [x] 4.4 实现候选接受、修正、拒绝和人工新建事件，清楚区分候选来源与最终人工事实。
- [x] 4.5 实现保存后进入下一条、证据窗口回看和必要的快捷操作，保证快捷操作不绕过保存、校验和 revision 语义。
- [x] 4.6 实现 draft/reviewed/locked 状态展示、锁定前质量摘要、阻塞错误和锁定确认；locked revision 只读并提供创建新 revision 的入口。

## 5. Gold Set 质量与后续指标衔接

- [x] 5.1 实现质量摘要计算，至少包含总条目数、已确认条目数、未知/不可观察条目数、未匹配候选数、冲突数和证据完整率。
- [x] 5.2 将 locked Gold Set 的人工事实接入指标校验所需的读取边界，但不在本 change 中生成六维分数、Overall 分数或 PB Vision quality 分数。
- [x] 5.3 为没有 locked Gold Set 的情况保持现有指标/报告行为，并返回明确的“尚无可用校准真值”状态。

## 6. 测试与验收

- [x] 6.1 为 schema、机会状态/结果/落点语义和锁定校验增加后端单元测试。
- [x] 6.2 为 draft 保存、候选接受/修正/拒绝、revision 锁定、locked revision 修正和 Gold Set 导出增加 API 集成测试。
- [x] 6.3 为工作台加载、逐帧证据定位、表单校验、队列筛选、保存下一条和 locked 只读状态增加前端测试。
- [x] 6.4 使用一个已注册的本地 CaptureTake 完成端到端验收：人工创建发球/接发、标记不可观察情况、锁定 Gold Set，并确认既有片段管理和分析流程不受影响。
- [x] 6.5 补充工作台使用说明，明确本 change 依赖用户自己的原始视频，不要求继续导出 PB Vision 数据，也不等同于机器学习训练工具。
