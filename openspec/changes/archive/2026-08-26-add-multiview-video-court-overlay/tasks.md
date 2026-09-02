## 1. 逐机位几何资产与投影契约

- [x] 1.1 在前端建立 `DisplayViewGeometry`、球场投影状态和球网投影状态类型，统一描述 view ID、媒体尺寸、calibration、homography、球网三点、质量和不可用原因。
- [x] 1.2 为浏览器补齐完整 calibration detail 的只读读取函数，并接入任务引用的 metric court scene revision；复用已有 API，只有在响应缺字段时才补充后端只读字段。
- [x] 1.3 在 `VisionPage` 中按 `jointViewInputs` 建立单摄/A/B 几何资产缓存，去重请求并区分 loading、available、unavailable、failed；不得在视频帧回调中请求网络。
- [x] 1.4 实现纯函数 geometry mapper：将标准 local court 点通过当前 view 的 court→image homography 投影到媒体像素，并按 calibration image size 归一化到当前视频 source 尺寸。
- [x] 1.5 实现 canonical→local 的 `courtOrientation` 转换边界，明确 image-space 球网标注不再重复应用 orientation；为 `identity`、`rotate_180`、`mirror_x`、`mirror_y` 编写单元测试。

## 2. 主视频球场与球网投影 renderer

- [x] 2.1 在 `VideoAnalysisCard` 的现有 SVG overlay 中增加球场外框、厨房线和中线 renderer，使用当前 source 的 `viewBox` 与 `preserveAspectRatio`，不得创建第二套视频坐标系。
- [x] 2.2 增加人工球网三点的缩放与曲线/折线 renderer，校验左端、中心、右端和图像尺寸；缺失或无效时不绘制占位球网。
- [x] 2.3 增加“球场投影”和“球网投影”独立开关及可观察的 loading/unavailable 状态；开关不得影响现有人物框、骨架、球点、球路、弹跳、小地图和播放控件。
- [x] 2.4 处理 SVG 与 `<video>` 的 letterbox、全屏、窄屏和自然尺寸变化，确保投影线与视频内容同时缩放且不覆盖底部播放控制。
- [x] 2.5 为 geometry mapper、球场线、球网三点和独立开关增加组件/单元测试，断言投影点、图层可见性和缺失资产降级。

## 3. A/B 展示切换与时间一致性

- [x] 3.1 将当前 view 的 `DisplayViewGeometry` 纳入 `VideoAnalysisCard` 的 active media lifecycle，与 active video source 使用同一 source/view identity 防护。
- [x] 3.2 扩展 pending display switch：切换时保存 canonical 时间和播放状态，目标视频 metadata 与 seek 完成前不显示目标几何，也不沿用旧 view 几何。
- [x] 3.3 验证播放中 A→B、暂停中 B→A 和连续 A→B→A：目标视频使用对应 calibration/net annotation，canonical 时间正确，播放状态按切换前恢复，旧视频事件不再刷新 overlay。
- [x] 3.4 覆盖目标 `play()` 被浏览器拒绝、目标 view 资产加载失败、用户在加载期间暂停以及 requestVideoFrameCallback/RAF fallback 等边界行为。
- [x] 3.5 处理单摄、历史双摄、缺少 scene revision、缺少球网三点和 calibration 质量不可用任务：能显示的图层继续显示，不能显示的图层只降级自身。

## 4. 性能、回归与真实素材验收

- [x] 4.1 对静态几何点、SVG path 和逐机位资产使用 memoization/缓存，确认 60 FPS 播放期间不发生重复 API 请求、重复完整 homography 构造或大 artifact 全量扫描。
- [x] 4.2 运行相关 Vitest 组件测试、geometry 测试、双摄播放同步测试、TypeScript build 和 ESLint，修复由新 props/类型接线产生的回归。
- [ ] 4.3 使用真实固定机位双摄素材人工验收 A/B 切换、近远端方向、四角重合、球网三点重合、拖动 seek、全屏和窄屏布局，并记录标定误差与异常样例。
- [x] 4.4 在验收结论中明确 fixed-camera 限制；确认未实现逐帧相机跟踪、完整三维网面和预渲染叠加视频，并将后续需求另行建 change。
