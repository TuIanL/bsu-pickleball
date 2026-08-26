## 1. 证据账本与校准配置

- [x] 1.1 定义 `SemanticEvidenceRecord`、evidence provenance、freshness 和 canonical tick 引用模型
- [x] 1.2 将时间线、球员活动、ServeStartDetector、球候选运动性和场地区域证据统一写入 evidence ledger
- [x] 1.3 增加 semantic boundary policy version、`min_confirm_ticks`、`grace_window_sec`、rescue 条件和冲突处理配置
- [x] 1.4 保证 fixture/manual 注入证据与真实 detector/ServeStartDetector 输出在 provenance 中明确区分

## 2. 回合边界仲裁

- [x] 2.1 扩展 `SemanticStateMachine`，支持 `pending_start`、`pending_end`、`confirmed_start`、`confirmed_end` 和 `rescued_active`
- [x] 2.2 实现按 canonical timestamp 的持续窗口、hysteresis、evidence freshness 和 deterministic tie-break
- [x] 2.3 实现矛盾证据处理：有效球运动或比赛活动出现时撤销未确认的 pending end
- [x] 2.4 保持 manual/corrected + Enforced 才能执行 hard boundary action，algorithmic evidence 继续 fail-open/soft
- [x] 2.5 保证 boundary action id、formal segment id 和 replay 结果幂等且可重复

## 3. 单摄与双摄球链路接入

- [x] 3.1 在单摄 `AnalysisPipeline` 中接入 adjudication result、grace window、pending candidate 和 rescue 结果
- [x] 3.2 在 `BallTracker` 中区分 pending、confirmed、rescued、suppressed candidate，并保持 stationary blacklist 不被语义抑制污染
- [x] 3.3 在双摄 canonical runner 中为每个 canonical tick 共享一份 evidence/snapshot/adjudication/action id
- [x] 3.4 覆盖双摄缺帧、`available_extrapolated` 和单视角可用时的单次 boundary 执行语义
- [x] 3.5 扩展语义 diagnostics，记录 evidence ids、pending/confirmed 状态、grace window、formal before/after、segment 和 fallback

## 4. 回放 artifact 与评估

- [x] 4.1 实现 `ball_semantic_boundary_eval.v1` payload、deterministic path、status/detail 和历史 outputs 目录兼容
- [x] 4.2 增加 `ball-semantic-boundary-eval` artifact API 读取与缺失时的 404 行为
- [x] 4.3 实现 canonical tick replay，确保相同 evidence/config/policy version 得到确定性 adjudication
- [x] 4.4 实现 boundary precision、recall、confirmation latency、false suppression 和 cross-segment contamination 指标
- [x] 4.5 建立 2026-07-20 双摄真实窗口与合成边界案例 fixture，覆盖准备、发球、回合、丢球、结束和重捕获

## 5. 测试与真实素材验收

- [x] 5.1 增加 evidence freshness、provenance、pending/hysteresis、冲突和 rescue 的单元测试
- [x] 5.2 增加单摄与双摄 boundary action 幂等、缺帧和 detector-once 集成测试
- [x] 5.3 增加 Shadow-vs-Enforced 对照测试，验证算法证据不会单独 hard reset，权威确认边界仍正确生效
- [x] 5.4 使用 2026-07-20 双摄素材执行 replay，记录各边界时间点、参考标签来源和指标结果
- [x] 5.5 运行相关回归、编译、OpenSpec strict validation 和 `git diff --check`，确认模型文件未被修改
