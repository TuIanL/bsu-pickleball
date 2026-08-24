## Context

当前双摄结果已经通过 `reconstructed_ball_trajectory` artifact 提供 segment、sample、endpoint、anchor、质量和指标资格信息。前端存在三条相关展示路径：

- `VisionPage` 在数据分析页额外渲染双摄状态提示卡，并在底部渲染旧的 `PlayerScoringPanel`。
- `BallTrajectoryPage` 通过 `BallTrajectoryScene` 展示交互式 Three.js 球场，但页面顶部仍有一整块混合球路状态和诊断说明。
- 报告页的 `Pb3DCourtCard` 从报告 evidence hook 取轨迹，`HybridTrajectoryReportCard` 则直接接收 artifact 并绘制 SVG 平面弧线。前者对 `status=partial` 的 artifact 存在读取门槛，后者与球路页不是同一视觉实现。

本变更只调整用户界面层。后端事件语义、原始 evidence、端点分类、`metric_eligibility`、质量诊断和 artifact API 都继续保留，便于技术详情、测试和后续产品能力使用。

## Goals / Non-Goals

**Goals:**

- 让数据分析页、球路页和报告页对球路结果使用一致的导航和 3D 视觉语言。
- 报告页只保留一个可交互的 3D 球场视图，直接消费统一 reconstructed artifact，并支持 `available`、`partial`、`degraded` 等可展示状态。
- 删除普通用户界面中的混合状态卡、2.5D 资格说明、环境离群诊断、重复界外提示和事件图标。
- 每条轨迹只显示一个中性末端圆点，不根据 hit、bounce 或 loss 使用不同颜色、菱形、圆环或渐隐圆点。
- 通过五个 PB Vision 风格预设视角、统一背景和更高可见度的轨迹线改善 3D 可读性。
- 保持真实不可用、加载失败、WebGL 失败和无有效轨迹时的必要空态。
- 让报告页评分位置唯一且 fail-closed：真实评分模型未生成时不显示 mock 数值。

**Non-Goals:**

- 不修改球检测、击球事件检测、弹地判断、轨迹重建、端点分类或质量门算法。
- 不删除或重命名后端 `hit`、`bounce`、`loss`、`legal_out_candidate`、`environment_outlier` 等语义字段。
- 不把 2.5D 估算升级为真实 3D，也不重新开放无资格的速度、最高点或权威落点。
- 不新增外部图形依赖；优先使用现有 Three.js 能力和已有的 artifact adapter。
- 不在本变更中实现正式六维技能评分模型。

## Decisions

### 1. 分离 artifact 语义与普通用户展示

前端继续解析并保留 anchor、endpoint 和诊断字段，但默认渲染层不根据这些字段创建事件图标，也不把 `non_adjudication_notice` 和环境离群计数放在普通球路卡片中。不可用或失败状态仍显示简短状态空态，成功或 degraded 且存在可视轨迹时不显示解释性状态卡。

**替代方案：** 使用 CSS 隐藏提示或把全部内容放进 tooltip。未采用，因为这些信息本身不属于普通浏览路径，CSS 隐藏还可能造成无障碍树和视觉内容不一致；需要诊断时应直接查询 artifact 或技术详情。

### 2. 报告页与球路页共享一个 3D viewport

将 reconstructed artifact 作为报告上下文的一部分传递给 `Pb3DCourtCard`，由同一个 `buildReconstructedBallTrajectoryVisualization` 适配器构建 `EstimatedBallTrajectory[]`，再由共享的 Three.js viewport 渲染。报告页不再从仅接受 `status=available` 的独立 evidence 路径推断轨迹。

报告页面只保留一个 3D viewport：将 `HybridTrajectoryReportCard` 的标题、段数和必要的报告容器职责并入现有 `Pb3DCourtCard`，移除 SVG 平面图和重复卡片，继续保留报告页的球员筛选、阶段筛选、质量阈值和 Shot 选中交互。

**替代方案：** 在 SVG 卡片中再嵌入一个 3D 场景。未采用，因为会产生两个重复球场、两套选择状态和更高的 WebGL 资源消耗。

### 3. 事件不再使用视觉符号表达

`BallTrajectoryScene` 的轨迹绘制逻辑只取每条轨迹最后一个可渲染 sample，绘制一个中性色末端圆点；删除起点球、击球菱形、弹地橙色圆环和 loss 渐隐圆点。anchor 和 endpoint 仍留在 adapter 的数据对象中，可用于筛选、审计和未来非图标化的详情能力，但不参与默认场景装饰。

轨迹方向仍可使用线条颜色，sample source 仍可使用线型/透明度区分；这些属于轨迹本身的可读性，不表达 hit 或 bounce 事件。

**替代方案：** 保留弹地圆环、只删除击球菱形。未采用，因为用户明确希望取消所有事件图标，并让末端圆点本身成为唯一终点表达。

### 4. 采用五个固定视角并修正场景生命周期

视角枚举改为 45°、俯视、边线、底线和 45°底线。视角切换只更新 camera position、zoom 和 OrbitControls target，不重新创建整个 scene、geometry 和 renderer。场景初始化、轨迹数据变化、选中状态变化和视角变化分别处理，减少切换视角时的闪烁和断线感。

场景背景、容器背景和球场外围使用同一浅色 token；移除有明显矩形边界的 apron，或将其改为与背景完全一致的无边界底面。球场自身保留轻微灰度和清晰线框，避免出现白边、灰色画布和“浮空”效果。

### 5. 轨迹线采用可见的连续基线加来源覆盖

轨迹基础线使用固定屏幕像素宽度，避免 `LineBasicMaterial` 在不同分辨率下过细。source 样式（detected、interpolated、predicted）通过同一段上的覆盖样式表达，而不是在每次 source 切换时丢弃只有一个点的短 run。只有真实时间丢失、无效高度或后端明确的 segment 边界才断线，禁止跨长丢失边界连接。

线条仍使用方向色、选中态加深、低可信度降低透明度和预测区间虚线，但不再通过事件标记重复表达端点。

### 6. 评分只保留报告页承载

移除 `VisionPage` 对 `PlayerScoringPanel` 的挂载和 mock 数据入口，不将旧的发球/接发球/敏捷/击球稳定性六维模型映射到报告页的 PB Vision 六维模型。报告页继续使用 `PbSkillRatingSection` 的正式评分占位；在正式 `player-skill-rating` artifact 未生成时只显示“本次分析暂未生成”，不得展示 mock 数值。

### 7. 测试以展示契约和数据一致性为重点

新增或修改测试覆盖：

- 数据分析页不再出现重复双摄状态卡和旧雷达评分入口。
- 可展示的 partial/degraded artifact 能在报告页进入共享 3D viewport。
- 报告页不渲染 SVG 平面图、2.5D 说明、界外重复提示和事件图标。
- 轨迹场景只渲染中性末端圆点，五个视角均可切换。
- source 样式变化不会制造单点短线或跨真实丢失边界连线。
- 不可用、失败和 WebGL 错误空态仍可用。

## Risks / Trade-offs

- [用户无法从图标直接知道某个端点是击球还是弹地] → 这是明确的产品取舍；后端仍保留完整语义，普通视图优先可读性，未来可在选中详情或技术页以文字方式提供语义。
- [隐藏质量和界外说明可能降低结果透明度] → 保留 artifact API、技术详情和测试诊断；普通报告只负责结果浏览，不承担算法审计。
- [partial/degraded artifact 误进入报告视图] → 继续由统一 adapter 的 display status、segment display level、样本有效性和 environment outlier 门控，不因隐藏文案而放宽数据门槛。
- [更粗的线条在轨迹密集时遮挡球场或彼此重叠] → 采用透明度、选中高亮、来源线型和可调视角；不通过恢复事件图标解决拥挤问题。
- [报告页重复创建 WebGL 场景造成性能下降] → 只保留一个 viewport，并把 renderer/scene 生命周期与视角状态分离。
- [现有测试依赖旧 SVG 和事件图标] → 在实现任务中同步改写这些断言，保留 artifact adapter 与后端语义测试不变。

## Migration Plan

1. 先更新本变更的 delta specs 和前端测试基线，明确旧提示和事件图标不再是验收要求。
2. 将报告 artifact 传入 `PbReportProvider`/报告 3D 组件，统一 partial/degraded 的可展示判断。
3. 重构共享 3D viewport 的场景生命周期、五视角、背景、线条和末端点绘制。
4. 移除数据分析页状态卡、旧评分入口和球路页正常状态诊断卡；删除报告 SVG 与重复文案。
5. 运行前端单元测试、类型检查、生产构建，并用真实双摄任务核对报告页与球路页段数、选中状态和视角表现一致。
6. 若视觉验收不通过，可回滚前端展示变更；后端 artifact 和原始 evidence 不需要回滚或迁移。

## Open Questions

无。用户已确认事件图标全部取消，包括弹地橙色圆环，并确认只保留每条轨迹的中性末端圆点。
