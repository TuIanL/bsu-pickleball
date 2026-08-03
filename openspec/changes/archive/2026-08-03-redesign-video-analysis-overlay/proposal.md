## Why

当前真实视频分析页的视频内小地图采用固定尺寸、低信息密度的基础 SVG，只显示球场和球员短轨迹，球轨迹与弹跳候选没有进入小地图。视频上的球线也只保留很短的固定点数窗口，导致球员移动方向、移动状态和球的飞行过程都不容易被观察。真实任务已经具备稳定球员身份、球场投影、球轨迹和弹跳候选数据，现在需要把这些数据组织成清晰、可读、可交互的视频分析 HUD。

## What Changes

- 重做视频内小地图的视觉层级、球场比例、配色、图例和信息条，形成与比赛视频融合的半透明分析 HUD。
- 在小地图中同步显示球员当前位置、时间尾迹、移动方向、速度摘要、球轨迹和弹跳候选。
- 将球员、人框、骨架、球点、球路和弹跳候选拆分为独立的可见性控制，保留播放、拖动和全屏能力。
- 将轨迹窗口改为基于时间和数据缺口的渲染规则，避免因固定点数过短或缺失数据而看不到轨迹，或错误连接不连续点。
- 对有效检测、插值点、低置信度候选和超出球场范围的点使用不同的视觉语义。
- 在视频叠加中明确区分图像空间球路、球场平面投影和弹跳候选；当前没有真实高度数据时，将空中弧线标记为视觉估算，不宣称为三维测量结果。
- 保持现有 artifact API 和真实任务数据来源不变，缺少某一图层时显示明确的 unavailable/degraded 状态。

## Capabilities

### New Capabilities

- `video-overlay-hud`: 定义视频内分析 HUD 的球场小地图、球员移动、球轨迹、弹跳候选、图层控制、状态摘要和降级展示行为。

### Modified Capabilities

- `visual-analysis-workspace`: 扩展真实视频叠加区域的移动可视化、球轨迹展示、图层控制和全屏状态要求。

## Impact

- 前端主要影响 `src/components/platform/CourtMinimap.tsx`、`src/components/platform/VideoAnalysisCard.tsx`、`src/pages/VisionPage.tsx` 及相关类型、纯计算服务和测试。
- 前端需要组合现有 `PipelineTrackPoint`、`BallTrajectoryArtifact`、`BounceEventsArtifact` 和发球候选数据，不要求新增后端 API。
- 可能调整已有视觉分析 workspace 的 OpenSpec requirement，并新增 HUD 专属 spec。
- 需要补充 SVG 渲染、轨迹时间窗口、缺口断线、速度摘要、图层开关和真实任务降级状态的测试。
- 后端视频叠加生成器和球检测算法不在本 change 的首期实现范围内；如后续需要下载版叠加视频同步升级，另行提出 change。
