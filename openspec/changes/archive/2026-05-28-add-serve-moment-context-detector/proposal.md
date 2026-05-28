## Why

当前发球开始检测主要依赖球员轨迹或人体框中心从稳定到突增的规则，在真实长比赛视频中容易把换位、捡球后启动、练习挥拍或普通底线击球误判为发球。发球动作本身与普通正手击球形态相近，因此需要把问题重新定义为“比赛状态上下文中的发球击球时刻候选检测”，而不是纯动作分类或单一速度阈值检测。

## What Changes

- 将现有发球候选检测升级为上下文驱动的 `ServeMomentDetector` 能力，结合底线站位、发球前低速准备、手腕/肘部或 ROI 局部运动峰值、发球后进入回合状态等信号。
- 保留当前 `serve_events.json` artifact 边界和候选语义，但让每个候选暴露更细的信号分解、检测状态、候选片段时间窗和可复盘原因。
- 明确处理 court coordinate 单位：检测器必须根据轨迹 artifact 的 `court_unit` 使用米或英尺阈值，避免把标准场地英尺阈值直接套到米制轨迹上。
- 新增调试与数据集导出 artifact：候选 score CSV/JSON、候选短片段、可选 debug overlay，用于复盘误报、漏报和积累 hard negatives。
- 将 pipeline 阶段说明从“发球开始检测”扩展为可追踪的上下文发球时刻检测，并在失败或输入不足时保持视频、tracking、pose 和既有报告可用。
- 不引入完整 rally segmentation、回合结束、比分推断、落点判断或战术结论。

## Capabilities

### New Capabilities

- `serve-moment-debug-artifacts`: 定义发球时刻候选的调试、评分、片段导出和人工复盘 artifact。

### Modified Capabilities

- `serve-start-detection`: 将发球开始候选检测要求从低信息量轨迹突增升级为上下文发球时刻候选检测，包含多信号评分、单位安全、候选时间窗和可解释信号。
- `visual-analysis-workspace`: 在真实视频播放器中继续展示候选 marker，同时支持展示更丰富的候选依据、置信度和降级状态，而不把候选点表述成完整回合切分。

## Impact

- 后端事件检测：`backend/app/vision/events/serve_start_detector.py` 或新增同层检测器模块需要支持上下文状态、姿态峰值、ROI 退化信号和发球后回合验证。
- 后端 schema/API：`backend/app/schemas/events.py`、pipeline artifacts 和 artifact route 需要承载信号分解、候选片段时间窗、debug artifact 引用和状态说明。
- 后端 pipeline：`backend/app/services/analysis_pipeline.py` 需要在 tracking、player trajectory、pose 可用后运行上下文发球时刻检测，并把阶段 counters 和 artifact URL 写入结果。
- 前端播放器：`src/components/platform/VideoAnalysisCard.tsx` 和相关客户端类型需要保留 marker 跳转，同时展示候选依据和局部不可用状态。
- 测试与评估：需要覆盖米/英尺单位转换、发球前静止门槛、姿态峰值定位、后续回合验证、无 pose 退化、debug artifact 生成和旧 artifact 兼容。
