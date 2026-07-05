## Why

真实比赛视频通常包含镜头切换、暂停、非球场画面、邻场球员和观众干扰。当前 pipeline 会在已标定视频的抽样帧上直接运行检测、跟踪和投影，缺少一个低成本的“球场视角是否有效”门控层，也没有在模型推理前用标定结果收窄检测区域。

借鉴 Good-Pickleball 的逐帧 baseline，我们可以先引入保守的球场视角片段候选和标定感知 ROI 过滤，让现有 player tracking、pose、serve-start 和指标链路获得更干净的输入，同时不提前声明完整回合、击球、弹跳或得分语义。

## What Changes

- 新增球场视角门控能力：在真实、已标定的视频分析中，为处理帧计算 court-view 状态，并基于连续帧阈值输出 `court_view_segments` 候选片段。
- 新增检测 ROI 能力：从已存储的四角标定点或同等图像角点推导 expanded ROI，用于限制 person detection / pose subject preparation 的输入范围，并保留 ROI 诊断。
- 修改视频分析 job flow：pipeline stage 和 raw result artifact 需要暴露 court-view/ROI 的状态、计数、跳过原因和输出引用。
- 修改 player tracking 行为：真实检测、跟踪、投影路径需要在 court-view gate 与 ROI 可用时优先使用过滤后的帧/检测输入，同时保留可复盘诊断。
- 不启用 ball tracking、bounce detection、shot events、完整 rally segmentation 或战术结论。

## Capabilities

### New Capabilities

- `court-view-roi-gating`: 定义球场视角候选片段、标定感知 detection ROI、状态诊断和 artifact 合同。

### Modified Capabilities

- `video-analysis-job-flow`: 增加 court-view/ROI 阶段与 raw pipeline result artifact 引用，确保任务进度和结果页能解释门控状态。
- `player-tracking-engine`: 增加 court-view/ROI 对检测、跟踪、pose 输入和诊断记录的要求。

## Impact

- 后端 pipeline：`AnalysisPipeline._run_tracking` 需要在逐帧循环中加入 court-view gate、ROI 推导、诊断计数和 artifact 写入。
- 后端 schemas/storage：需要新增或扩展 court-view/ROI artifact schema、storage path、result artifact 引用。
- Player Tracking Engine：person detection 前或检测后增加 ROI 过滤；非球场候选帧可跳过模型推理或标记为 gated。
- 前端/API：raw result 和任务阶段可展示 court-view/ROI 状态；现有 tracking/pose overlay 应继续可用。
- 测试：覆盖 ROI 推导、court-view state machine、pipeline artifact serialization、非球场帧跳过、缺少标定时的保守降级。
