## Why

当前发球时刻候选在部分真实视频中只覆盖前半段：tracking 和 pose overlay 仍能覆盖完整视频，但 player trajectory 或发球评分序列提前停止，导致后半段没有任何发球标注可复盘。与此同时，候选 marker 都挤在播放器进度条里，发球一多就难以阅读和点击，需要独立、可横向浏览的回合导航体验。

## What Changes

- 增强发球开始检测的覆盖诊断：检测结果和调试 artifact 必须暴露评分时间覆盖、候选/拒绝原因分布、轨迹覆盖缺口，帮助定位后半段没有候选的原因。
- 改善发球检测对 player trajectory 中断的处理：当稳定 player identity 或 trajectory 提前断开时，系统应给出明确降级状态和可复盘诊断，并在合理情况下回退到 tracking/pose/ROI 信号继续产生候选。
- 将真实视频发球候选从拥挤的进度条 marker 体验升级为播放器下方的独立横向回合导航条。
- 回合导航条中的每个矩形卡片代表一个发球候选/回合起点，显示序号、发球时间、置信度和检测模式，点击后跳转到对应 `seek_time_seconds`。
- 保留播放器原始进度条用于播放控制；发球导航条作为独立数据层加载、滚动、降级和失败，不阻塞视频播放。
- 不引入完整 rally segmentation、回合结束识别、比分识别或战术结论；本 change 仍只处理发球开始候选及其导航。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `serve-start-detection`: 发球检测必须暴露覆盖诊断，并在 player trajectory 提前断开时保留可解释状态或降级候选能力。
- `serve-moment-debug-artifacts`: 调试 artifact 必须覆盖完整检测时域，避免只截取早期 rejected 样本，并提供分桶统计以复盘后半段缺失原因。
- `visual-analysis-workspace`: 真实视频工作台必须提供播放器下方、与视频宽度一致的横向发球候选/回合导航条，替代拥挤的进度条 marker 作为主要发球浏览入口。
- `player-trajectory-identity`: player trajectory identity 必须提供足够的覆盖诊断，使下游发球检测能够识别轨迹提前中断、目标球员过滤过严或身份失联等情况。

## Impact

- 后端：`ServeStartDetector`、分析 pipeline 写入的 `serve_events.json`、`serve_debug_candidates.json`、`serve_score_series.json`、pipeline stage counters、player trajectory identity diagnostics。
- 前端：`VideoAnalysisCard` 的真实视频播放器控制区、发球 marker 解析和展示、发球事件加载/降级状态文案、相关组件测试。
- API/artifact：可扩展发球事件 artifact 和 debug artifact 的诊断字段；保持现有 artifact URL 和基础事件字段兼容。
- 测试：新增后端检测覆盖/降级测试、debug artifact 时间覆盖测试、前端横向导航条渲染与跳转测试。
