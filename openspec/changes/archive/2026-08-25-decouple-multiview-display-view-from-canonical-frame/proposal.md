## Why

双摄协同分析完成后，用户需要在 A/B 两个视频视角之间自由切换，同时继续看到与当前视频机位一致的 Player 框、球路和时间位置。当前实现把分析参考机位、视频展示机位和 Canonical Court Frame 混在一起：一旦切换机位或重试时改变端点定义，就可能触发 `canonical frame conflict`，并且正式 Player overlay 主要只覆盖参考机位。

本变更将“分析使用的默认参考机位”和“用户当前查看的展示机位”分离。分析只执行一次，默认仍使用 A 机位；用户切换到 B 机位时，只替换对应视频与 image-space overlay，不改变球员身份、统一球场坐标、时间轴或分析任务输入。

## What Changes

- 新增双摄结果页的 A/B 展示视角切换控件，默认展示任务的 `referenceViewId`，并支持刷新后恢复用户选择。
- 引入独立的 `displayViewId` 语义；展示视角切换不得重新创建 AnalysisJob、重新运行识别或修改 `canonicalFrameId`、`referenceViewId`、`courtOrientation`。
- 为每个展示视角提供统一 canonical 时间戳到真实视频帧/媒体时间的映射，切换视频后保持播放位置和证据时间一致。
- 扩展正式 Player overlay，使 A/B 两路都能输出 image-space bbox/footpoint，同时复用同一套 canonical Player 身份映射；切换视角时“谁对应谁”不得变化。
- 让球路在切换后消费目标视角对应的 image-space path；小地图继续消费统一 Canonical Court Frame 的位置和身份，不把某一路像素坐标混入另一视角。
- 对当前机位不可见、遮挡或缺少对应坐标的 Player/球路提供明确降级状态，不进行重新编号或静默伪造。
- 双摄设置页在已有 canonical frame 的 take 上恢复并沿用已保存的物理朝向；展示视角选择不得再次生成不同的 endpoint definition。
- 统一场景标定、canonical frame 和多视角结果中对 canonical frame 的引用，兼容历史任务中缺少新展示字段的 artifact。

## Capabilities

### New Capabilities

- `multiview-display-view-switching`: 定义双摄结果的默认参考机位、可切换展示机位、统一时间轴、视角级视频/overlay 选择以及切换时的身份与坐标一致性。

### Modified Capabilities

- `multiview-analysis-input-contract`: 明确 `referenceViewId`、`canonicalFrameId` 和 `courtOrientation` 是任务级不可变分析输入，`displayViewId` 是不参与分析创建的展示状态。
- `multiview-fused-player-overlay`: 正式 Player overlay SHALL 支持按 view 输出，同时复用只读 canonical Player 身份和统一 tick。
- `multiview-ball-analysis-display`: 球路和视频展示 SHALL 支持目标 view 切换，并保持 canonical 时间轴与目标视频帧对齐。
- `reconstructed-trajectory-artifact`: 补充多视角 image-space 展示路径的消费约束和缺失视角时的安全降级语义。
- `analysis-flow-navigation`: 在分析工作区 URL/刷新/内部视图导航中保留可选的展示机位选择。

## Impact

- 前端：双摄分析结果页、`VideoAnalysisCard`、视角选择控件、视频时间同步、小地图和球路 overlay 适配器。
- 后端：joint fused Player overlay 生成器、按 view 的投影/overlay artifact、分析结果 API 与历史 artifact 兼容读取。
- 数据契约：新增 `displayViewId`/view-scoped display metadata；保留 `referenceViewId` 作为默认参考和 canonical timeline 权威，不改变现有分析算法的 reference timeline 语义。
- 场景坐标：继续使用同一个不可变 Canonical Court Frame；视角切换不得产生新的 frame 或端点定义。
- 测试：增加 A→B→A 切换、播放时间一致性、P1-P4 身份稳定、Player/球路/小地图坐标一致、缺失视角降级、历史 artifact 兼容和 canonical conflict 回归测试。
