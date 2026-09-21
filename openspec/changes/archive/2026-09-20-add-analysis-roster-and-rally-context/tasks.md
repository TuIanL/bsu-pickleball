## 1. 数据契约与迁移

- [x] 1.1 定义 `RallyScoringSnapshot`、`CourtEndProjection`、`AnalysisRosterSnapshot`、`bootstrap_binding_audit` 和 `AnalysisRallyContextSnapshot` 的后端/前端 schema 与 provenance 字段。
- [x] 1.2 添加 CaptureTake、AnalysisJob、timeline projection 与 artifact 的持久化迁移；保证历史记录缺字段时兼容读取。
- [x] 1.3 实现 scoring/roster/court-end/context hash 与 Job input signature，验证相同媒体但不同名册或上下文不会复用结果。

## 2. 录制事实与端位投影

- [x] 2.1 在 `start_next_rally` 同一事务中从当前 reducer 创建仅含计分事实的 `RallyScoringSnapshot` 并关联来源 action/event/revision。
- [x] 2.2 实现基于有效 action ledger 的 scoring snapshot replay、undo、score correction 与 supersede 链测试。
- [x] 2.3 实现独立 `CourtEndProjection`，从确认初始端位和有效 `side_change` 回放 A/B near/far；不得修改 ScoringState schema。
- [x] 2.4 覆盖换边、撤销换边、缺少初始端位及历史 timeline 的服务层测试。

## 3. 分析预检、名册与身份连续性

- [x] 3.1 实现受限范围 player bootstrap API，返回参考帧、P1–P4 候选、锚点和质量诊断，不启动完整 Pipeline。
- [x] 3.2 在上传和录制分析入口提供 P1–P4、Team A/B 与初始端位确认；允许跳过且不阻塞普通分析。
- [x] 3.3 在 Job 提交时冻结完整 `AnalysisRosterSnapshot`，并确保后续可编辑来源名册不影响旧 Job。
- [x] 3.4 在 formal tracking 输出 bootstrap-to-canonical `bootstrap_binding_audit`；身份不能确认时给出 stable unavailable reason。
- [x] 3.5 覆盖成功、候选不足、跳过、再次确认和 identity binding 失败的 API/组件/集成测试。

## 4. Job-bound context 与 formal binding

- [x] 4.1 实现 context composer，组合 scoring snapshot、Job roster 和 court-end projection，写入不可变 `AnalysisRallyContextSnapshot` 与 context-set hash。
- [x] 4.2 让 AnalysisJob 执行记录、重试和幂等逻辑只消费该 Job 的 context；后续修正产生新版本而不改写旧 Job。
- [x] 4.3 实现 `direct_segment_link`、`direct_start_event_link`、`unique_temporal_match`、unavailable 的优先级绑定器与结构化诊断。
- [x] 4.4 扩展 immutable `AnalysisWindowPlan`、canonical Rally/Shot 和 artifact 路由以引用冻结 context；禁止以 `initial_side` 推导 Team A/B。
- [x] 4.5 覆盖直接绑定、时间降级、歧义降级、计分修正、名册编辑、换边和历史 Job 的端到端契约测试。

## 5. 发布验收

- [x] 5.1 执行迁移、计分重放、projection、bootstrap/audit、context composer、formal binding 和 canonical artifact 回归测试。
- [x] 5.2 用代表性双打 CaptureTake 验收：发球继承、比分冻结、换边、撤销、重新确认名册、identity 断裂及历史任务兼容。
  - 已在临时 SQLite 上运行代表性双打 CaptureTake 验收：`rally_start` 固定发球队/比分，`change_side` 与 `undo` 正确回放，重新确认产生不同 roster hash 且旧 Job 上下文不变，identity 断裂输出 unavailable，历史 payload 可继续读取。
  - 真实拍摄素材的目视核查仍建议在发布前由产品/算法负责人执行；本项自动验收不替代该目视核查。
- [x] 5.3 发布时默认启用 context consumer；分析入口默认提交新流程，并提供任务级 legacy 兼容按钮。部署仍可用 `PICKLEBALL_RALLY_CONTEXT_ENABLED=false` 全局回滚，确认未影响普通视频分析、同步小地图与既有报告。
