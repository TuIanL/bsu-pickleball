## Context

当前双摄分析请求已经携带 `clipStartMs/clipEndMs`。在 `late_fusion_v1` 中，Coordinator 会把公共时间轴窗口映射到两个 child，SingleView executor 也会把窗口传给 `AnalysisPipeline`；但叠加视频生成器仍从源视频第 0 帧读取到结尾。`joint_tracking_v2` 则直接按完整 reference 视频帧数驱动 `MultiViewJointRun`，完全没有消费 Parent 的窗口字段。

本 change 需要同时处理任务编排、两套执行模式、双摄同步时间轴和可视化输出。现有 `dual_camera_sync`、`CanonicalAnalysisClock`、Pipeline 的 pre-roll/post-roll 和 `clipStartMs/clipEndMs` 字段继续作为基础契约，不引入数据库迁移或新的同步算法。

## Goals / Non-Goals

**Goals:**

- 将窗口定义为 reference view 的公共 take 时间轴半开区间 `[start_ms, end_ms)`。
- 让 late fusion 的两个 child、joint tracking 的两路 runtime、融合/指标和分析叠加视频都遵守同一请求窗口。
- 保留默认的 `pre_roll_ms=1500` 与 `post_roll_ms=500` 上下文，但不把预热帧纳入正式指标和用户请求范围。
- 对 secondary view 使用现有权威 sync mapping 转换窗口，并保留窗口映射诊断。
- 让任务进度、结果 metadata 和 artifact manifest 能明确区分 requested clip、decoded range、实际处理帧数和源视频总帧数。
- 保证未传窗口时的整场分析行为保持不变。

**Non-Goals:**

- 不修改双摄同步校准算法、Canonical Timeline 的配对容差或球员身份融合算法。
- 不改变 `late_fusion_v1` 与 `joint_tracking_v2` 的产品选择和默认模式策略。
- 不物理裁剪或覆盖 CaptureTake 的原始视频；窗口只约束分析和派生 artifact。
- 不把窗口扩展为多个不连续区间；本 change 只支持一个连续时间区间。

## Decisions

### 1. 统一以 reference 时间轴传递窗口

API 和 Parent 继续使用 `clipStartMs/clipEndMs` 表示 reference view 的公共时间轴。late fusion 创建 child 时沿用现有 `_map_clip_to_view()` 将 secondary 窗口转换到其媒体时间轴；joint tracking 不复制一套映射逻辑，而是把 reference 窗口交给 `CanonicalAnalysisClock`，由 clock 在每个 reference tick 中按既有 sync mapping 选择 secondary source frame。

这样可以避免两套执行模式对“窗口起点”的解释不一致，也不会用 `offset_ms=0` 替代缺失的同步 authority。备选方案是在每个 view 上提前生成独立 clip 文件，但会增加 I/O、临时文件清理和时间戳重建复杂度，且不符合“不物理裁剪原始视频”的现有设计。

### 2. joint tracking 在 canonical tick 层限制范围

为 `MultiViewJointRun.run()` 增加可选的 reference frame 起止边界或等价的窗口参数。传入窗口时，run 只生成 decode range 对应的 reference ticks；每个 tick 的 timestamp 仍使用原始 source frame index / reference FPS 计算，确保输出时间戳和同步映射保持原视频坐标。无窗口时沿用从第 0 帧到末尾的现有循环。

窗口边界在 executor 统一转换为：

```text
requested_range = [clip_start, clip_end)
decode_range    = [max(0, start - pre_roll), min(duration, end + post_roll)]
metric_range    = requested_range
```

joint 的预热帧用于初始化 tracker 状态，但只有 `metric_range` 内的 sample 可以进入指标和正式融合统计。

### 3. 叠加视频直接按窗口读取源帧

给 `OverlayVideoWriter.write()` 增加可选 `clip_start_ms/clip_end_ms` 或已解析的 frame range。窗口存在时 seek 到 decode range 或 requested range 的明确起点，并在结束边界停止写出；输出结果记录源视频时间起点，避免前端把一个短 artifact 误当成从 0 秒开始的完整视频。根据产品目标，叠加视频最终写出 requested range，预热帧只服务于跟踪状态，不写入用户可见 artifact。

备选方案是继续输出完整视频、只在窗口内绘制 overlay。该方案虽然兼容现有播放 URL，但仍会读取和编码全片，无法解决用户反馈的计算成本和“全片分析”感知，因此不采用。

### 4. 明确范围元数据和进度口径

在 Pipeline、joint run 和叠加视频结果中统一记录：

- `requested_clip`: 用户请求的 `[start_ms, end_ms)`；
- `decoded_range`: 实际允许读取的预热范围；
- `processed_frame_count`: 实际执行推理/跟踪的帧数；
- `source_frame_count`: 源视频总帧数；
- `output_time_origin_ms`: 派生叠加视频相对源视频的时间起点。

窗口存在时，抽帧阶段和 joint 阶段的进度分母使用窗口内计划处理帧数，而不是源视频总帧数；无窗口时继续使用源视频总帧数。child 的 `analysisScope` 继续表示分析内容 scope，不再被解读为时间范围，实际时间范围以 clip 字段和结果 metadata 为准。

### 5. 以测试锁定“没有窗口”和“有窗口”两种行为

增加以下测试层次：

- 前端：勾选窗口后请求体包含毫秒范围，未勾选时字段省略。
- 编排：Parent/child 持久化窗口，secondary 使用 sync offset 映射，边界和非法范围被拒绝或按视频时长裁剪。
- Pipeline：合成短视频时只访问 decode range，正式轨迹/指标只保留 requested range。
- Overlay：输出帧数和起止帧对应请求窗口，不再无条件写完整源视频。
- Joint：`MultiViewJointRun` 只产生窗口内 canonical ticks，secondary 仍按同步 clock 配对。
- 兼容性：不带 clip 的单摄、late fusion 和 joint tracking 继续处理完整视频。

## Risks / Trade-offs

- [视频 seek 精度受编码格式影响] → 用 frame index 作为硬边界，允许 seek 后丢弃边界外帧，并在 manifest 中记录实际首尾帧。
- [短窗口缺少 tracker 初始化上下文] → 保留现有 pre-roll/post-roll；当窗口靠近视频首尾时按有效视频范围裁剪。
- [叠加视频从完整视频变为短 artifact 可能影响播放体验] → 写入 `output_time_origin_ms` 和 requested range，前端按源时间轴展示；原始 source video URL 继续保留。
- [joint 与 late 的进度结构不同] → 两者都以实际计划 tick/frame 数作为进度分母，并保留 source total 作为诊断字段。
- [历史任务没有窗口 metadata] → 缺失字段按整场分析处理，不执行迁移；只有新建或重试任务使用新语义。

## Migration Plan

1. 先实现窗口解析、映射和结果 metadata，并补齐单元测试。
2. 接入 late fusion Pipeline/Overlay，再接入 joint executor/run，分别验证两条执行路径。
3. 增加端到端短视频测试，确认窗口外帧不会进入跟踪、融合或叠加输出。
4. 发布后旧任务继续按无窗口整场语义读取；不需要修改已有 JSON 文件。
5. 若新逻辑出现问题，可通过回滚代码恢复旧执行逻辑；历史原始视频和既有任务产物不受影响。

## Open Questions

- 前端是否需要在分析详情页明确展示“请求窗口 / 实际解码范围”，还是只在诊断信息中展示？本 change 默认后端结果提供字段，前端至少展示请求窗口。
- 叠加视频是否必须支持从源视频任意时间点继续跳转？本设计默认短 artifact 以 `output_time_origin_ms` 对齐，后续再决定是否需要拼接或 Range 映射。
