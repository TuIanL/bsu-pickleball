## Why

当前双摄分析已经能够生成分段轨迹，但前端仍把实现诊断、估算资格、事件锚点和用户结果混在一起展示：数据分析页重复提示球路状态，球路页展示用户不需要阅读的诊断卡，报告页使用难以辨认的 SVG 平面图，3D 视图又与报告数据源不完全一致。评分面板还停留在数据分析页的 mock 方案，与报告页已有的正式评分占位架构重复。

本变更将双摄结果的默认展示收敛为清晰的 PB Vision 风格球场视图：保留后端可审计证据，但只向普通用户展示连续、可读的轨迹和中性末端圆点。

## What Changes

- 移除数据分析页重复的“双摄球路分析”提示卡，球路入口和可用性由上方横向视图导航承载。
- 移除数据分析页底部旧的六维雷达评分面板，不把 mock 评分迁移到报告页；报告页已有的 `PbSkillRatingSection` 作为评分唯一承载位置，真实任务在正式评分模型未生成时继续显示空态。
- 在球路页隐藏正常可用或 degraded 结果的混合分段状态卡、2.5D 资格说明、环境离群诊断和重复的指标限制文案；后端 artifact、`metric_eligibility` 和诊断字段继续保留。
- 将报告页分段球路报告的 SVG 平面图替换为与球路页共享的 3D 球场视图，统一消费同一份 reconstructed trajectory artifact，并支持 `partial/degraded` 结果。
- 参考 PB Vision 增加 45°、俯视、边线、底线和 45°底线五个视角，统一球场与画布背景，消除白色 apron 边界和灰色悬浮感。
- 提升轨迹线的屏幕可见度和连续性：使用稳定的像素宽度、清晰的颜色/透明度和不跨真实丢失边界的连续绘制策略，避免 source 样式切换造成的假断线。
- 移除前端所有击球菱形、弹地橙色圆环、渐隐事件圆点及其图例；每条轨迹只保留中性末端圆点。击球、弹地、loss、界外候选和拒绝原因仍保留在后端语义和 artifact 中，不删除证据。
- 更新前端测试与 OpenSpec 展示契约，确保用户界面不再重复显示“可能界外落点，非自动判罚”等逐段诊断文案，同时保留不可用/加载失败时的必要空态。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `multiview-ball-analysis-display`: 调整数据分析页和报告页对双摄球路状态、降级轨迹及诊断信息的默认展示边界；保留 artifact API 的可审计能力。
- `ball-trajectory-visualization`: 将球路视图统一为共享 3D 球场渲染，新增 PB Vision 风格五视角、连续高可读轨迹和中性末端点语义，取消事件图标展示。
- `player-scoring`: 移除视频分析页旧六维 mock 雷达面板的展示要求，将评分展示位置收敛到报告页，并禁止真实任务使用 mock 数值冒充正式评分。

## Impact

- 前端页面：`VisionPage`、`BallTrajectoryPage`、报告页容器和报告球路组件。
- 前端渲染：`BallTrajectoryScene`、轨迹 adapter、报告证据加载路径、视角控制和 Three.js 场景样式。
- 前端组件：旧 `PlayerScoringPanel` 的使用入口及其测试；`PbSkillRatingSection` 保留为报告页评分架构。
- 测试：轨迹渲染、报告球路、球路页状态、评分入口和报告数据源一致性测试。
- OpenSpec：只调整展示契约，不删除后端 hit/bounce/loss、界外分类、质量资格或诊断字段，不改变原始 evidence 的不可变性。
