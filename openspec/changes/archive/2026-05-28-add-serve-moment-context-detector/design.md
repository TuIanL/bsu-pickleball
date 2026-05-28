## Context

当前真实视频分析 pipeline 已经能输出 tracking、player trajectories、RTMPose overlay 和播放器 marker，但发球候选检测仍主要依赖球员整体位置或人体框中心的低速到高速变化。实拍长比赛里，发球与普通正手挥拍形态接近，且发球者脚步可能几乎不移动；因此“整体位移突增”既容易漏掉真实发球，也容易误报换位、捡球、练习挥拍和普通底线击球。

本次变化把发球检测定位为比赛状态事件检测：先确认候选发生在“回合开始前”的上下文，再在该上下文内定位更接近击球瞬间的局部运动峰值。现有 `serve_events.json` 仍然表示候选事件，不表示完整 rally segmentation。

## Goals / Non-Goals

**Goals:**

- 用上下文发球时刻检测替换单一轨迹突增规则，融合底线站位、发球前低速、手臂/ROI 峰值和发球后回合激活。
- 在候选事件中暴露可解释的 signal scores、候选片段时间窗、检测来源和降级状态。
- 对 court coordinate 单位做显式处理，支持现有米制 `PlayerTrajectoryArtifact` 和旧式英尺坐标。
- 生成调试 artifact，帮助复盘误报、漏报、阈值表现和 hard negative 片段。
- 保持 marker、artifact API、pipeline stage 和前端独立加载语义兼容。

**Non-Goals:**

- 不检测回合结束、净比赛时长、比分、落点、发球合法性或战术结论。
- 不要求第一版训练新模型或引入球/球拍检测模型。
- 不把普通动作分类模型作为唯一判断依据。
- 不要求实时流式检测；本阶段继续面向上传后离线分析。

## Decisions

### 使用状态门槛 + 局部峰值定位，而不是纯线性加权

检测器先应用硬门槛：候选球员在底线附近、候选前存在低速准备窗口、候选之间满足最小间隔。只有通过上下文门槛的时间段才进入软打分：手腕/肘部运动峰值、ROI 帧间差分峰值、发球后多人运动上升、接发方等待状态等。

备选方案：

- 纯 `serve_score = 位置 + 静止 + 手臂峰值 + 后续回合`：实现简单，但普通底线正手可能用高运动峰值和后续回合激活掩盖缺少发球前准备的问题。
- 只做动作分类：发球和正手形态太像，缺少上下文时很难稳定区分。

### 保留 `serve_events.json`，扩展事件字段

现有前端和 artifact API 已围绕 `serve_events.json` 工作，因此保留该 artifact 名称和状态枚举。新增字段以 optional 形式承载 `start_time_seconds`、`end_time_seconds`、`signals`、`context_state`、`detection_mode` 和 debug 引用，旧结果仍可加载。

备选方案：

- 新增 `serve_moments.json` 替代旧 artifact：语义更干净，但会迫使前端、API 和旧任务迁移，且本能力仍是发球候选事件。
- 只把新信号塞进 `reason` 字符串：兼容性好但不可测试、不可排序，也不利于调试和研究记录。

### 统一把检测阈值写成标准场地语义，再按 artifact 单位转换

设计参数可用 `baseline_margin_ft` 表示，但进入检测时必须根据轨迹 `court_unit` 转换为米或英尺。现有 player trajectory artifact 默认输出 `m`，标准长宽约为 6.096m × 13.4112m；旧 homography 和部分测试仍使用 20ft × 44ft。

备选方案：

- 全部改回英尺：会影响现有米制轨迹、身份稳定和 metric artifact。
- 直接使用当前坐标值不看单位：会让底线过滤在米制输出中严重失真。

### 姿态优先，ROI 差分降级

当 RTMPose 可用时，手腕/肘部速度峰值是击球时刻的主要局部运动信号。没有 pose 或关键点置信度不足时，检测器应退化为目标球员 bbox/ROI 内的帧间差分或 bbox 局部变化峰值，并把 artifact 状态标为 `partial` 或在事件 `detection_mode` 中说明降级。

备选方案：

- 没有 pose 就完全不可用：会降低可用性，也浪费已有 tracking 和视频帧。
- 始终只用 ROI 差分：姿态已可用时会丢掉更直接的手臂运动证据。

### 发球后回合激活作为验证信号

候选时刻后 2-4 秒内，检测器应检查是否至少两名主要球员或双方阵营出现持续运动、tracking 连续性和速度上升。该信号用于压低练习挥拍、假动作和暂停时的误报。

备选方案：

- 只看发球前状态和手臂峰值：对练习挥拍、空挥、准备动作中的抖动不够稳。
- 等待完整 rally segmentation：超出本阶段范围，也会阻塞快速定位价值。

### 调试 artifact 是第一版成功条件的一部分

每次检测应能输出候选分数时间序列、候选 JSON、可选候选 clips 和 debug overlay。调试 artifact 用于人工复盘、标注真实发球、积累 hard negatives 和后续模型训练，不应阻塞基础 `serve_events.json` 可用性。

备选方案：

- 只输出最终 marker：实现较快，但无法解释误报/漏报，后续会继续靠感觉调参。
- 先做完整标注工具：更系统，但会延后第一版算法闭环。

## Risks / Trade-offs

- [Risk] 底线站位阈值受标定误差和单位混用影响。→ Mitigation：显式读取 `court_unit`，在 debug artifact 中记录换算后阈值和候选球员 court position。
- [Risk] 姿态关键点在远端球员或遮挡时不稳定。→ Mitigation：使用关键点置信度过滤、短窗口平滑，并退化到 ROI 差分。
- [Risk] 发球后回合激活可能漏掉短回合、接发失误或视频中断。→ Mitigation：将其作为软分或可配置验证，不作为唯一硬门槛。
- [Risk] 候选 clips 和 debug overlay 增加处理时间和磁盘占用。→ Mitigation：默认只生成轻量 JSON/CSV，clips/overlay 可配置开启或限制数量。
- [Risk] 用户误以为 marker 是完整回合边界。→ Mitigation：继续使用“发球候选/发球时刻候选”文案，不输出回合结束或比分类结论。

## Migration Plan

- 以 optional 字段扩展事件 schema，旧 `serve_events.json` 仍可被前端读取。
- pipeline 中替换或包裹现有 `ServeStartDetector`，保留 artifact URL、状态枚举和阶段 id 的兼容路径。
- 新增 debug artifact URL 字段时保持 optional；旧任务没有这些字段时前端显示当前降级状态。
- 可通过配置关闭 debug clips/overlay，仅保留 `serve_events.json` 和轻量 score 文件。

## Open Questions

- 第一版是否默认生成候选 clips，还是只在本地研究/调试模式开启？
- `rally_after_score` 对短回合或发球直接失误应设为软分还是可配置硬门槛？
- UI 是否需要在 marker tooltip 中展示完整 signal breakdown，还是只展示摘要并把详细内容放到分析详情页？
