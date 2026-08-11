## Why

当前双摄分析的 late-fusion 主路径已经具备同步校准、跨视角关联、canonical 坐标归一化和降级融合能力，但关联阶段与最终融合阶段可能选择不同的副摄 source frame，导致球员跨视角身份错误。与此同时，同步 artifact 的校验不足、零副摄证据仍可能被标记为正常双摄融合，以及 canonical frame 未接入运行实体，使结果的正确性和可解释性无法完成验收。

现在需要完成一轮 P1 Closure / Multiview Reliability Hardening，先关闭当前产品实际使用的 late-fusion 路径的 authority、wiring 和 truthfulness 缺口，再进行 joint_tracking_v2 的产品切换和时间基准升级。

## What Changes

- 新增权威 `FramePairingPlan`，以 reference 时间轴一次性确定每个 canonical tick 的副摄 source frame；association 和 fusion 必须消费同一计划，不得分别重新选帧。
- 新增严格的同步 authority 校验，验证 schema、reference camera、当前副摄 mapping、mapping 身份、数值范围、quality 和有效时间范围。
- 增加运行后真实模式判定和诊断统计：区分 dual evidence、single-view fallback、predicted 和副摄有效覆盖率；没有任何副摄有效证据时不得标记为正常 `multiview_fused`。
- 将持久化的 canonical court frame 绑定到同一 take 的 Parent 和具体运行实体；同一 take 的重复分析必须复用同一个 canonical frame。
- 统一执行模式字段的协议命名，解决 OpenSpec 使用 `multiviewExecutionMode`、当前后端使用 `executionMode` 的不一致；保留 `late_fusion_v1` 默认行为，避免历史任务迁移风险。
- 补充多视角可靠性测试，包括窗口内多帧配对、缺失副摄 mapping、零副摄证据、重复分析 canonical frame 复用和 A/B 执行模式签名隔离。

本 Change 不包含完整的 PTS 时间基准重构。`frame_index / fps` 与 source PTS 的统一应作为独立 Change，避免同时影响单摄轨迹、球、姿态、事件、clip 和 overlay 链路。

## Capabilities

### New Capabilities

- `multiview-analysis-reliability`: 定义权威帧配对计划、同步 authority 校验、有效模式判定和多视角可靠性诊断。

### Modified Capabilities

- `multiview-analysis-input-contract`: 增加 canonical frame 绑定和同步 mapping 的真实 camera identity 校验要求。
- `multiview-analysis-orchestration`: 增加可靠性 preflight、运行后 effective mode 和降级状态的编排契约。
- `multiview-analysis-result-composer`: 结果 manifest 必须反映真实的双摄证据和降级模式，禁止零副摄证据标记为正常融合。
- `multiview-fusion-run`: late-fusion 运行必须持有并消费唯一的 FramePairingPlan 和 canonical frame reference。
- `multiview-synchronized-analysis-clock`: 明确 late-fusion 的关联与融合必须共享同一帧配对结果。
- `multiview-execution-mode`: 统一执行模式字段命名，并保持 late-fusion 与 joint-tracking 的 A/B 隔离语义。
- `multiview-court-frame-normalization`: 同一 CaptureTake 的 canonical frame definition 必须跨 Parent、FusionRun 和 JointRun 复用。

## Impact

- 后端：`multiview_coordinator.py`、`analysis_executor_dispatch.py`、`multiview_result_composer.py`、`vision/multiview/pipeline.py`、`canonical_timeline.py`、`sync.py`、`fusion_run.py` 及 joint run wiring。
- API：双摄创建请求的执行模式字段需要统一；结果 manifest、diagnostics 和 Parent summary 需要暴露 effective mode 及覆盖统计。
- 产物：新增或扩展 FramePairingPlan、sync validation diagnostics、effective mode 和 canonical frame reference 字段；现有 fused trajectory schema 保持兼容。
- 测试：补充后端多视角单元、编排、Composer、前端请求协议和真实视频 smoke test；保留 `late_fusion_v1` 作为 A/B baseline。
- 依赖：不改变录制流程；PTS authority 作为后续独立 Change 处理。
