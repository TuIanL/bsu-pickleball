## Why

回合状态模型已经通过 7 个真实比赛视频的人工复核，能够可靠地产出回合边界；但当前系统仍将它定位为离线候选和人工验收工具。普通双摄分析既不会在 Worker 中运行该模型，也不会将其输出固定为本次分析、指标和报告的时间依据，导致实验成果无法成为产品能力。

现在应将模型升级为双摄正式分析的必经规划阶段：无须赛后逐条确认即可生成可追溯的自动回合，并由同一版本的回合计划驱动后续分析。与此同时，正式片段页应移除研发期复核操作，恢复面向使用者的简洁回放和结果查看体验。

## What Changes

- 新增正式 `MatchStateSegmentationRun` 生命周期：记录对某个 CaptureTake 的模型包、权重与解码器哈希、双摄输入与同步版本、运行状态、artifact 和替代关系。
- 新增生产级双摄回合切分 Runtime：直接从 CaptureTrack 媒体按 CaptureTake 权威时间轴和同步 calibration 采样；不依赖训练期 manifest、JPEG cache、人工标签或评估数据。
- 将成功切分结果以 `source=algorithm`、`status=inferred` 发布为正式 Rally Segment，并通过 `segmentation_run_id` 关联所属运行；人工事件和人工片段永不被覆盖。重新分析成功后才 supersede 旧自动片段，失败时保留旧版。
- 将双摄分析改为先完成 Parent-owned segmentation prerequisite、固定 `AnalysisWindowPlan`，再释放或执行后续视觉分析。`joint_tracking_v2` 与 `late_fusion_v1` 均须保证切分发生在任何依赖该计划的视觉执行之前。
- 后续 V1 分析仍连续解码并保持身份状态；回合窗口先用于有效时间、事件归属、回合级统计与报告，不在本变更中实现跨大量离散窗口的跳跃式 tracking。
- 任务进度增加“回合自动切分”阶段，并将模型/双摄输入不可用、同步不可用、低证据、正常零回合和推理失败区分为可解释状态。正式双摄 `match_default` profile 对不可用或推理失败采取 fail-fast；单摄工程流程不适用该必经阶段。
- `SegmentManagerPage` 收敛为“现场人工标记”和“自动回合切分”两类片段的回放、定位和结果入口；移除普通产品入口中的模型候选接受/修正/拒绝、人工边界复核、补录、改序号、边界拖拽及 AnalysisBatch 创建。
- 保留候选 artifact、接受/修正/拒绝 API 和审计数据，仅作为隔离的 QA / 回归工具，不再充当正式产品流程或正式模型片段的发布路径。
- **BREAKING**：双摄 `match_default` 分析不再在缺少正式回合切分模型、两路可用输入或有效同步时静默按整场视频继续；将以明确的切分阶段失败结束任务。

## Capabilities

### New Capabilities

- `formal-match-state-segmentation`: 定义生产级双摄回合切分 Runtime、SegmentationRun、算法片段发布、不可变窗口计划及失败/替代语义。

### Modified Capabilities

- `learned-match-state-segmentation`: 将训练/候选复核链路与正式生产切分链路明确隔离，保留 QA 安全契约但不再把人工确认作为正式双摄分析的前提。
- `analysis-job-orchestration`: 为双摄任务增加可恢复的切分前置阶段、进度遥测、输入签名和 job-bound segmentation run 绑定。
- `multiview-analysis-orchestration`: 使 late-fusion 的 source child 在 Parent 切分成功并固定窗口计划后才可执行，并保持 joint 模式的同等前置保证。
- `analysis-artifacts`: 增加正式切分 artifact 与窗口计划的确定性存储、结果引用和受控读取方式。
- `segment-manager`: 将普通片段页改为只读的人工/自动来源展示与回放界面，移除研发复核和片段编辑的产品入口。

## Impact

- 后端：新增数据库模型与迁移、正式模型包配置和校验、`backend/app/vision/match_state/` Runtime、同步采样、artifact 存储、Segment 发布服务、任务/双摄编排以及指标窗口解析。
- 前端：调整双摄任务进度、分析详情的切分状态与来源展示，收敛 `SegmentManagerPage`、API client 和相关测试。
- 数据与兼容：`CaptureSegment` 新增可空 `segmentation_run_id`；已有人工 Segment、候选 artifact 和 review 审计保持可读且不迁移为正式自动片段。
- 运维：新增已签名模型包、权重、运行设备和批大小配置；Worker 以 `(model package hash, device)` 缓存已加载模型，并在部署前校验 Runtime 依赖。
