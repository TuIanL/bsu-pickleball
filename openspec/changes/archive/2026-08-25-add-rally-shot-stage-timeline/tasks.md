## 1. 数据适配与纯函数模型

- [x] 1.1 为回合—击球阶段时序图准备 `ShotRallyEventsArtifact` 的前端 fixture，覆盖可用 Rally/Shot、无回合边界、归属不明、无 Shot 和失败状态。
- [x] 1.2 新增纯函数，将 canonical Shot/Rally 事件转换为按 Rally 分组或单行降级时间轴所需的视图模型，并按 `shot_id` 去重。
- [x] 1.3 在纯函数中实现事件时间选择、`stage` 标签映射、canonical 球员归属、中性归属、`quality.band` 展示状态和描述性摘要计算。
- [x] 1.4 确认时序图只消费 `shot-rally-events.v1` 字段，不从数组下标补造 Rally、ordinal、stage、击球者或落点结论。

## 2. 视觉分析数据加载链路

- [x] 2.1 扩展 `useVisualAnalysisReport` 的状态模型，增加 Shot/Rally artifact、加载状态和 detail/error 信息，并保持 demo 路由不请求真实 artifact。
- [x] 2.2 使用现有 `getShotRallyEvents(result)` 独立加载 `shot-rally-events.v1`，使 404、解析错误和后端 unavailable 只影响时序图卡片。
- [x] 2.3 将时序图数据和状态从 `VisionPage` 传递到 `VisualizationArtifactGallery`，不改变现有热力图、散点图和区域热力图的加载/降级行为。
- [x] 2.4 核对真实任务的 `shot_rally_events_url`、artifact status/detail 和历史任务缺失文件行为，必要时补充 API/fixture 兼容测试，但不改变后端事件 schema。

## 3. 时序图组件与交互

- [x] 3.1 新增 `RallyShotTimeline` 展示组件，支持“每个 Rally 一行”和“无 authoritative rally boundary 的单行事件时间轴”两种布局。
- [x] 3.2 实现发球、接发、第三拍、后续击球和未分类的视觉编码，并保留 canonical 球员颜色、击球者不明中性样式和质量等级表达。
- [x] 3.3 实现时序图标题、图例、回合/击球摘要、样本不足提示、暂无 Shot 空态和 artifact unavailable/failed 空态。
- [x] 3.4 为 Shot 节点增加详情展示，只有存在有效 `evidence_windows` 时才启用视频跳转；无证据时显示“暂无可跳转证据”。
- [x] 3.5 将节点点击接入现有视觉分析视频 seek 导航，使用 canonical 毫秒时间和已有 `t`/`seekToMs` 语义，不改变多视角 display view 或 canonical frame。
- [x] 3.6 将时序图卡片加入 `VisualizationArtifactGallery`，放在现有三张位置类可视化之后，并保持现有卡片布局与亮色 sports-tech 视觉风格。

## 4. 测试与回归验证

- [x] 4.1 为时序图纯函数增加单元测试，覆盖 Rally 排序、Shot 去重、contact/start/end 时间回退、stage 映射、归属不明和摘要统计。
- [x] 4.2 为 `RallyShotTimeline` 增加组件测试，覆盖可用数据、无回合边界、无 Shot、artifact loading、unavailable 和 failed 状态。
- [x] 4.3 增加节点点击测试，验证有效证据窗触发正确的 canonical seek 时间，无证据窗不会跳转到默认时间。
- [x] 4.4 增加真实任务 fail-closed 测试，验证时序 artifact 404/解析失败时视频、状态栏和三张现有位置图仍可渲染。
- [x] 4.5 运行相关 Vitest 测试和 TypeScript 构建检查，确认历史任务、demo 路由和已有 `VisualizationArtifactGallery` 测试不回归。
