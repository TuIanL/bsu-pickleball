## Context

当前真实分析 pipeline 已经覆盖上传视频、球员检测/跟踪、场地投影、pose、发球候选和若干运动指标；同时仓库已经具备球轨迹与弹跳点引擎、球相关 artifact schema、配置开关和 artifact API 预留。但多个 spec 与 README 仍保留早期 MVP 边界：球检测、球轨迹、弹跳、球 overlay 和更完整的比赛语义被描述为 out of scope 或 inactive。

本 change 的核心不是一次性完成全部比赛智能，而是把这些“锁死”的边界改成可配置能力：默认不破坏现有流程，启用后尽可能输出可验证的事实 artifact，并在缺模型、缺输入或算法失败时给出明确状态。

## Goals / Non-Goals

**Goals:**

- 让真实 `AnalysisPipeline` 可以在配置启用时调用球候选检测适配器、球轨迹引擎、轨迹清洗器和弹跳检测器。
- 生成并引用 `detections.jsonl`、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`，并为后续 `ball_overlay.json` 与 `analysis_overlay.mp4` 保留兼容入口。
- 将 `ball` 纳入 multi-target 感知合同，使 player 与 ball 可以共享检测记录和 artifact 状态。
- 让前端和报告消费真实 artifact 的可用/不可用状态，展示球轨迹与弹跳候选事实，但不伪造完整战术语义。
- 清理文档中的永久性禁用措辞，改为配置、依赖和降级说明。

**Non-Goals:**

- 不实现完整 rally segmentation、比分推断、击球类型分类、落点统计、战术推荐或训练处方闭环。
- 不强制引入特定球检测模型权重；检测器通过 adapter/protocol 接入。
- 不要求默认环境启用重模型推理，也不要求测试环境具备 CUDA 或外部模型资产。
- 不把弹跳候选等同于确定的得分、落点或犯规判断。

## Decisions

1. 使用配置门控激活球分析阶段。
   - 决策：`PICKLEBALL_ENABLE_BALL_DETECTION` 控制球检测与 raw trajectory；`PICKLEBALL_ENABLE_BOUNCE_DETECTION` 在清洗轨迹可用后控制弹跳候选；缺少模型路径或 adapter 时记录 `skipped`/`unavailable`。
   - 理由：保留当前轻量默认行为，同时允许比赛分析能力逐步打开。
   - 备选：默认强制启用球检测。放弃原因是会让没有模型资产的本地开发、CI 和演示环境变脆。

2. 以事实 artifact 为第一层产出。
   - 决策：pipeline 先落地逐帧检测、原始轨迹、清洗轨迹和弹跳候选，再由 UI/report 基于 artifact 状态展示。
   - 理由：事实数据可复盘、可测试，也能为后续击球/回合/战术能力提供稳定输入。
   - 备选：直接在报告中生成球路或战术总结。放弃原因是会把尚未验证的语义结论混入产品体验。

3. 保持球引擎 detector-agnostic。
   - 决策：pipeline 只依赖球候选 protocol/adapter，不直接耦合 YOLO、TrackNet、HSV 或特定权重路径。
   - 理由：后续可替换模型或多检测器融合，同时单元测试可用合成候选运行。
   - 备选：在 pipeline 中直接加载某个模型。放弃原因是会提高依赖复杂度并限制后续实验。

4. 用阶段状态和 artifact 状态表达降级。
   - 决策：每个新增阶段写入清晰的 status、detail、counters 和 artifact 引用；失败或缺依赖不阻断已有 player/pose/serve 结果。
   - 理由：用户能知道“没打开、没模型、没检测到、部分可用、已生成”的区别，开发者也能复盘。
   - 备选：缺失时只返回 null。放弃原因是 null 无法区分配置关闭、算法失败和真实无检测。

5. 前端消费真实状态，不回退为模拟球数据。
   - 决策：真实 job 页面仅在 artifact 存在且可解析时显示球层；没有真实 artifact 时显示 unavailable/skipped/failed，而不是套用 demo 球路。
   - 理由：保持真实分析可信度，避免把示例内容误认为上传视频结果。
   - 备选：用 demo 数据填空。放弃原因是会削弱后续算法验证和用户信任。

## Risks / Trade-offs

- [Risk] 球检测模型质量不足导致轨迹噪声高 → 通过 confidence、reject_reason、candidate_count、cleaning metadata 和 stage counters 暴露诊断，UI 标记为候选而非确定结论。
- [Risk] 额外逐帧处理增加任务耗时 → 通过配置默认关闭、采样策略和阶段耗时记录控制影响。
- [Risk] artifact schema 扩展影响旧前端 → 所有新增字段保持可选，旧 artifact name 行为不变，缺失新增 artifact 返回 404 而不是 422。
- [Risk] 弹跳候选被误解为完整比赛事件 → spec 和 UI copy 均限定为 candidate/fact，不输出比分、犯规、落点统计或 rally 结论。
- [Risk] 多个并行 change 同时修改 pipeline → 实施时优先保留已有 player/pose/serve 合同，并在任务中安排回归测试。

## Migration Plan

1. 保持默认配置不启用球分析，确认现有真实分析 job 行为和测试不变。
2. 接入 adapter/protocol 与 pipeline 阶段记录，使启用但缺依赖时返回明确 skipped/unavailable。
3. 在可用球候选输入下写入新增 artifact，并将 URL/status/detail 注入 `AnalysisPipelineResult.artifacts`。
4. 更新 artifact API、前端 layer 状态和报告可用性判断。
5. 更新 README 与环境变量说明，将“禁用/out of scope”改为“可配置启用/依赖未满足时降级”。
6. 若上线后需要回滚，关闭环境变量即可回到原 player/pose/serve 主流程。

## Open Questions

- 首个真实球检测 adapter 采用现有 YOLO 多类别模型、独立球模型，还是先提供轻量占位 adapter 以便接入外部实验？
- `ball_overlay.json` 是否在本 change 同步生成，还是只生成轨迹/弹跳 artifact 并由前端直接消费轨迹渲染？
- 弹跳候选在报告中的中文命名采用“弹跳候选”“疑似弹跳点”还是更保守的“轨迹转折候选”？
