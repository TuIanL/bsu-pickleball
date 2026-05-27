## Why

长时间固定机位视频里包含捡球、站位、暂停和其他非比赛片段，当前真实视频分析只能播放整段视频和人员/姿态 overlay，用户难以快速定位每个回合的有效开始点。先自动识别发球开始候选点，并把它们标记到播放器进度条上，可以显著提升回放复盘效率，同时为后续回合分割和比赛净时长统计打基础。

## What Changes

- 新增发球开始检测能力：后端在完成真实视频分析时产出发球开始候选事件 artifact，包含时间戳、帧号、置信度、检测依据和可用状态。
- 新增 artifact API 暴露：完成任务结果引用发球事件 artifact，前端可独立加载，加载失败或不可用不阻塞基础视频播放。
- 在真实视频播放器进度条上渲染每个发球开始候选 marker，支持点击 marker 跳转到对应时刻附近进行回放分析。
- 将“发球击球瞬间”作为算法 anchor，但播放器跳转可提前少量预卷时间，便于用户看到准备站位和挥拍前动作。
- 保持当前范围只做回合开始锁定，不做回合结束检测、完整回合分割、战术结论或比赛净时长自动统计。
- 保留人工校验空间：候选点需要置信度和状态说明，避免把低置信度检测包装成确定结论。

## Capabilities

### New Capabilities

- `serve-start-detection`: 覆盖发球开始候选事件的后端生成、数据契约、artifact 状态、置信度和降级行为。

### Modified Capabilities

- `visual-analysis-workspace`: 增加真实视频播放器上发球开始 marker 的展示、点击跳转、加载状态和缺失状态要求。

## Impact

- 后端 pipeline：新增发球开始检测阶段或子阶段，基于现有视频帧、tracking、pose 或轻量动作特征生成候选事件。
- 后端 schemas/storage/API：新增发球事件 artifact schema、存储路径、结果引用字段和 `/api/analysis/jobs/{job_id}/artifacts/...` 读取分支。
- 前端 types/client：新增 artifact 类型、结果字段和独立加载函数。
- 前端视频工作台：真实视频播放器进度条新增 marker 层、tooltip/status copy 和 click-to-seek 行为。
- 测试：覆盖 artifact schema、检测器可用/不可用状态、API 读取、前端 marker 渲染与跳转逻辑。
