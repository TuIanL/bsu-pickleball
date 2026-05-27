## Context

当前真实视频分析 pipeline 已经支持上传视频、场地标定、人体检测、player tracking、脚点投影、运动指标、tracking overlay、pose overlay 和前端播放器同步渲染。真实任务报告有意避免输出击球、回合、战术语义，因为现阶段缺少稳定的球轨迹和事件分析能力。

这次变化是事件分析的第一步：只识别“发球开始候选点”，用于长视频快速跳转复盘。它不要求立即完成比赛净时长统计，也不要求完整回合结束检测。用户价值来自快速定位每个回合开头，而不是把候选点包装成最终裁判式结论。

## Goals / Non-Goals

**Goals:**

- 为完成的真实视频分析任务生成发球开始候选事件 artifact。
- 每个事件保留时间戳、帧号、置信度、检测依据、预卷跳转时间和状态信息。
- 将发球事件 artifact 作为独立 artifact 加载，使基础视频和已有 overlay 不受其缺失或失败影响。
- 在真实视频播放器进度条上展示候选 marker，并支持点击跳转到事件附近。
- 用清晰 copy 区分“候选发球开始点”和确定的回合切分结论。
- 保持 demo timeline marker 行为兼容。

**Non-Goals:**

- 不检测回合结束瞬间。
- 不生成完整 rally segmentation、净比赛时长统计或比分推断。
- 不输出击球类型、落点、战术评价或获胜原因。
- 不强制依赖球/球拍检测模型。
- 不要求实时流式识别；本阶段面向上传后离线分析。

## Decisions

### 使用独立 `serve_events.json` artifact

发球事件将作为独立 artifact 写入任务输出目录，并由 pipeline result 的 `artifacts` 字段引用。这样可以保持数据边界清楚，也让前端独立加载状态更自然。

备选方案：

- 写入 report 的 `timelineMarkers`：实现较快，但会把候选事件和报告级结论混在一起，也不利于后续人工修正和事件调试。
- 写入 tracking overlay：时间上相关，但语义不同，会让人体框 overlay 承担事件分析职责。

### 先做候选检测，不做确定回合切分

事件 schema 使用 `status`、`confidence`、`reason` 和 `detector_version` 表达不确定性。前端文案使用“发球候选”或等效表达，不把 marker 称为完整回合边界。

备选方案：

- 直接输出 rally start：更符合最终产品表达，但当前算法证据不足，误报成本较高。
- 完全人工打点：可靠但没有利用现有 player/pose 数据，无法解决长视频初筛效率。

### anchor 采用发球击球瞬间，seek 采用预卷时间

后端事件的 `timestamp_seconds` 表示检测到的发球击球或最接近发球启动的 anchor。事件同时提供 `seek_time_seconds`，前端点击 marker 时跳到 anchor 前约 1.0-2.0 秒，方便用户看到准备动作。

备选方案：

- marker 直接标准备动作开始：体验自然，但算法边界模糊，不同球员准备动作差异大。
- marker 直接跳击球瞬间：数据语义干净，但复盘体验会错过站位和挥拍前状态。

### MVP 检测基于现有 player/pose 信号，允许无 pose 降级

第一版检测器优先复用已有 tracking frames、player trajectories 和可用 pose frames。规则可以组合：服务区附近主要球员从稳定站位进入快速挥拍/上肢动作、全场其他主体短时低移动、候选之间保持最小间隔。没有 pose 时仍可用轨迹和 bbox 动态生成低置信候选；没有足够 tracking 时标记 unavailable。

备选方案：

- 立即引入球/球拍检测：更接近真实发球，但当前模型资产和规格处于非活动状态，风险和工作量都更高。
- 只用音频突变：部分视频可能无声或环境噪声大，且当前 pipeline 没有音频分析基础。

### 前端 marker 层属于真实视频播放器控制区

真实视频播放器已有 range input 和视觉 progress bar。发球 marker 应该和控制条同层展示，点击后设置 `video.currentTime`。tooltip 展示时间、置信度和简短依据；加载中、不可用和无候选状态不应阻塞播放。

备选方案：

- 放到右侧状态栏列表：可读性强，但不满足“在进度条上标记并快速拖拽/跳转”的核心需求。
- 替换现有 demo timeline：会影响无真实任务场景，且 demo marker 与真实事件语义不同。

## Risks / Trade-offs

- [Risk] 规则型 MVP 误报捡球、练习挥拍或暂停后的动作。→ Mitigation：保留置信度、最小间隔、可解释 reason，并在 UI 上标为候选；后续可加入人工修正和球/球拍模型。
- [Risk] 无 pose 或低质量检测会导致候选稀疏。→ Mitigation：artifact 明确 `unavailable`、`partial`、`no_candidates` 状态，不影响已有视频分析结果。
- [Risk] marker 太密会降低进度条可用性。→ Mitigation：检测阶段做去重/最小间隔，前端可聚合相近 marker 或限制 tooltip 显示。
- [Risk] 长视频事件检测增加处理时间。→ Mitigation：复用已有抽帧/overlay 数据，避免重新全量推理；将阶段进度独立记录。
- [Risk] 用户把候选点当作完整净时长统计。→ Mitigation：文案和 spec 明确本阶段只锁定开始点，不输出结束点和净时长结论。

## Migration Plan

- 扩展 schemas 和 artifacts 字段为 optional，旧结果没有发球事件 artifact 时保持可加载。
- 新增 storage path 和 artifact route 分支，删除任务时复用现有输出目录清理能力。
- 后端 pipeline 在 tracking/pose 输出可用后运行发球事件检测；缺少输入时写状态或仅在 result 中标记 unavailable。
- 前端仅在 result 引用事件 artifact 时尝试加载；加载失败显示局部状态，不替换整页。
- 回滚时可移除或禁用检测阶段，旧播放器和 overlay 行为不受影响。

## Open Questions

- 第一版默认预卷时间使用 1.0 秒、1.5 秒还是 2.0 秒？
- 是否需要在 MVP 内支持用户手动新增/删除 marker，还是留到下一次 change？
- 发球候选是否需要按发球方/球员 ID 标注，还是第一版只保留事件级别时间点？
