## 1. 统一报告页轨迹数据源

- [x] 1.1 将 `trajectoryArtifact` 纳入报告上下文或等价的共享输入，使 `Pb3DCourtCard` 直接消费 `reconstructed_ball_trajectory` artifact，而不是仅依赖 `status=available` 的 evidence 路径
- [x] 1.2 复用 `buildReconstructedBallTrajectoryVisualization` 的 display status、segment quality、样本有效性和 environment outlier 门控，确保 `partial/degraded` 任务可以展示合格轨迹且不放宽指标资格
- [x] 1.3 将 `HybridTrajectoryReportCard` 的报告标题、段数和必要容器职责合并到唯一的 3D 轨迹卡，移除 SVG 平面图和重复的报告球路 viewport
- [x] 1.4 保留报告页现有球员筛选、击球阶段筛选、击球类型筛选、质量阈值和 Shot 选中逻辑，并验证筛选结果与球路页使用同一 segment/shot 数据

## 2. 重构共享 3D 球路视图

- [x] 2.1 将视角配置改为 45°、俯视、边线、底线和 45°底线五个预设，并为按钮补齐稳定的 label、pressed state 和响应式布局
- [x] 2.2 拆分 Three.js 初始化、轨迹数据更新、选中态更新和视角更新的生命周期，避免切换视角时重新创建 renderer、scene 和全部 geometry
- [x] 2.3 统一 renderer、viewport 容器、球场外围和报告卡的背景色，移除可见 apron 白边、灰色悬浮底板和不必要的场景边界
- [x] 2.4 使用可控的屏幕像素线宽或等价的高可见度线材质绘制轨迹，保留方向颜色、选中高亮、低可信透明度和 source 虚线编码
- [x] 2.5 重写轨迹 run 组装逻辑：source 切换不得产生单点短线，真实长丢失、无效高度和明确 segment 边界必须断开，禁止跨真实丢失边界连线
- [x] 2.6 删除轨迹起点球、击球紫色菱形、弹地橙色圆环、loss 渐隐圆点和对应图例；每条轨迹只在最后一个可渲染 sample 绘制中性末端圆点
- [x] 2.7 保留 anchor、endpoint、outcome 和 notice 在 view model/artifact 数据中，但确保默认渲染层不根据这些字段生成事件图标或重复诊断文字

## 3. 清理页面展示与评分入口

- [x] 3.1 从 `VisionPage` 移除重复的“双摄球路分析”提示卡，保留横向视图导航和必要的球路跳转入口
- [x] 3.2 从 `VisionPage` 移除旧 `PlayerScoringPanel` 的挂载、导入和 mock 评分展示；确认球员轨迹、视频回放和其他状态 rail 不受影响
- [x] 3.3 清理不再使用的旧评分组件、雷达图和 mock 数据依赖；若仍被其他页面引用，保留类型兼容层但禁止真实 job 使用 mock 数值
- [x] 3.4 保持报告页 `PbSkillRatingSection` 的 fail-closed 行为：正式评分 artifact 不存在时只显示评分未生成空态
- [x] 3.5 从 `BallTrajectoryPage` 移除 available/degraded 正常状态下的混合分段状态卡、2.5D 资格说明、环境离群诊断、逐段界外提示和重复指标限制文案
- [x] 3.6 保留加载中、失败、WebGL 不可用、无有效轨迹和 `display_trajectory_status=unavailable` 的简短必要空态与返回导航

## 4. 更新前端测试与验收

- [x] 4.1 更新 `BallTrajectoryScene` 测试，覆盖五个视角、source 切换连续性、真实丢失边界断开和仅一个中性末端点的渲染契约
- [x] 4.2 更新球路页测试，确认 available/degraded 结果不显示诊断卡和重复提示，unavailable/failed 结果仍显示必要空态
- [x] 4.3 更新报告组件测试，确认 partial/degraded artifact 能进入共享 3D viewport，SVG 平面图、事件图标、2.5D 说明和界外重复文字不再出现
- [x] 4.4 更新 VisionPage 与评分测试，确认双摄提示卡和旧雷达评分入口不存在，报告评分空态仍可渲染
- [x] 4.5 运行相关 Vitest、TypeScript 检查和生产构建，并在真实双摄任务上人工核对报告页与球路页的段数、筛选、选中态、五个视角、线条连续性和背景融合效果
