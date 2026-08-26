## Why

当前球检测使用通用 tennis-ball 权重，并且候选过滤、跨帧跟踪、缺口插值和视频叠加之间缺少统一的质量门。场边物体或广告区域的误检可能被锁定为球，再经过长缺口插值形成看似完整的错误球路；双摄任务还可能把低质量跨视角配对继续交给重建。需要建立“精度优先”的球候选与球路发布约束，避免不确定结果进入默认展示。

## What Changes

- 新增统一的球候选质量门：使用球场空间棱柱投影、候选框尺度/形状、置信度和跨帧连续性过滤明显不合理的候选。
- 调整 BallTracker 状态语义：tentative 候选必须经过短窗口多帧确认后才能进入正式球路；重新捕获使用更严格的门控。
- 将运动连续性约束改为时间感知，增加速度、方向和加速度合理性检查；长时间丢失、轨迹重置和异常跳变不得被插值跨越。
- 将轨迹插值上限从“样本点数量”改为“实际秒数”，并保留 detected、interpolated、predicted 与断点 provenance。
- 加强双摄候选关联：增加重投影误差、3D 物理范围、候选歧义和相邻时刻路径连续性门控；低质量配对只进入诊断，不作为权威重建证据。
- 调整混合轨迹质量分级和视频 overlay 默认策略：低质量单视角视觉弧仅在调试模式显示，默认不绘制不满足真实观测覆盖要求的球路。
- 增加误检诊断与可复现实验数据，包括候选拒绝原因、轨迹断点、插值时长、跨视角配对分数和最终展示资格。
- 保留 raw、cleaned、reconstructed 三套 artifact 的兼容读取，历史任务不回写、不改变既有不可变产物。

## Capabilities

### New Capabilities

- `ball-detection-quality-gates`: 定义球候选过滤、时间连续性、物理约束、双摄共识和质量诊断的统一后端行为。

### Modified Capabilities

- `ball-trajectory-visualization`: 收紧默认展示资格，低质量/单视角视觉弧只在调试模式可见，并按断点和 provenance 表达不确定区间。
- `multiview-ball-analysis-display`: 双摄球路必须区分权威双摄证据、降级单视角证据和仅诊断候选，低质量配对不得直接驱动默认展示。
- `reconstructed-trajectory-artifact`: 为候选质量、轨迹断点、插值时长和展示资格补充可审计字段，保持历史版本兼容。

## Impact

- 后端 `BallTracker`、`TrajectoryCleaner`、双摄 `association`/`canonical_runner`、混合段构建和 artifact writer。
- 后端球路 schema、质量诊断、双摄重建阶段状态与相关单元/回归测试。
- 前端 `VideoAnalysisCard`、球路可视化 adapter 和默认 overlay 过滤逻辑。
- 需要使用真实双摄样例 `sync_20260720_122645_317228` 及其历史误检片段进行离线验收；本 change 不包含重新训练球模型，但会为后续 pickleball 专用模型保留 detector adapter 边界。
