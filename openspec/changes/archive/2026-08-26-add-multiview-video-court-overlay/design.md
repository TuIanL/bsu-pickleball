## Context

识别分析页的真实视频由 `VideoAnalysisCard` 播放，并在与视频相同的 SVG `viewBox` 上实时绘制人物框、骨架和球相关图层。当前球场矩形、厨房线、球网和球场坐标点主要由 `CourtMinimap` 绘制；四角人工标定已经在后端生成图像→球场及球场→图像的 homography，双摄场景标定还按 view 保存了球网左端、中心、右端的 image-space 标注。

双摄展示状态已经包含当前视频、source timestamp mapping 和 `courtOrientation`。已有同步修复负责视频元素生命周期和 canonical 时间连续性，但主视频还没有消费每个 view 的标定几何。因此本变更的主要工作是数据读取、几何映射和渲染接线，而不是重新检测球场或修改分析指标。

系统将摄像机视为 fixed camera：一次人工标定在同一段视频播放期间保持有效。球场边界是平面几何，可以通过每个 view 的 homography 投影到视频；球网 MVP 使用当前 view 已人工确认的三点 image-space 标注绘制网顶曲线。三维网高、网柱和完整网面不作为本次默认交付范围。

## Goals / Non-Goals

**Goals:**

- 在主视频中按当前展示 view 显示真实标定的球场外框和可配置的球场线。
- 在主视频中显示当前 view 的人工球网顶部标注，并与视频像素坐标严格对齐。
- 让 `video source`、canonical 时间映射、标定几何、球网标注和展示方向在 A/B 切换时保持同一 view 事务的一致性。
- 复用现有视频帧时间驱动和 SVG overlay，不为静态几何每帧请求 API 或生成新视频。
- 对旧任务、单摄任务和缺失/无效标定提供可解释的降级，不显示伪造几何。
- 通过纯几何单元测试、组件切换测试和真实双摄人工验收验证投影与切换行为。

**Non-Goals:**

- 不修改 YOLO、球检测、球员跟踪、球路重建、canonical player ID 或分析指标。
- 不在正常播放期间进行逐帧相机运动跟踪、自动重新标定或镜头畸变校正。
- 不生成完整三维网面、网柱、遮挡关系或可导出的预渲染带框视频；这些属于后续增强。
- 不把 `courtOrientation` 当成对视频像素的直接镜像；它只参与 canonical 与当前 view 本地球场坐标之间的转换。
- 不把缺失的球网人工标注用静态示意线替代；缺少网标注时仅按能力显示球场投影并标记球网投影不可用。

## Decisions

### 1. 使用前端 SVG 交互式投影，而不是默认生成叠加视频

主视频已经有同尺寸 SVG overlay，使用它能继续支持播放、暂停、seek、图层开关和 A/B 切换，静态几何不需要逐帧重新编码。后端现有 `court_overlay` 的投影逻辑可以作为几何契约和测试参考，但不把新的投影层绑定到 GB 级的视频渲染任务。

备选方案是修改 `OverlayVideoWriter`，在后端逐帧烧录球场线和球网。这适合导出文件，但会增加 CPU、存储、任务耗时，并且双摄需要为每个 view 管理独立的视频 artifact，不能直接解决交互式切换中的状态一致性，因此不作为本变更主路径。

### 2. 标定几何按 view 读取并缓存

`VisionPage` 为当前任务建立 `DisplayViewGeometry`，至少包含：view ID、视频尺寸、calibration ID、球场→图像 homography、标定质量、球网三点 image-space 标注、球网投影质量和资产状态。单摄任务只建立一个 view；双摄任务按 `jointViewInputs` 建立 A/B 两份数据。

前端增加或复用只读 API 读取完整 calibration detail；metric scene 使用任务的 `capture_take_id` 和 `sceneCalibrationRevision` 读取对应 revision。数据加载按 view 去重和缓存，播放帧期间只消费内存中的几何，不在 `requestVideoFrameCallback` 中请求网络。

### 3. 所有主视频几何使用同一个 SVG 坐标管线

球场标准点先经过当前 view 的 local court → image homography，得到原始视频像素坐标，再放入当前视频 SVG 的 `viewBox`。标定图片尺寸与媒体自然尺寸不一致时，按宽高分别归一化到当前 source 尺寸；SVG 与 `<video>` 均使用 `preserveAspectRatio="xMidYMid meet"`，保证 letterbox 下二者仍重合。

球网 MVP 直接使用该 view 的三个人工 image-space 控制点，在同一个 SVG 坐标系绘制折线/平滑曲线。球网的高度 profile 和 holdout 点继续作为场景质量来源，但不在浏览器中宣称已经完成三维网面投影。

### 4. `courtOrientation` 只用于坐标语义，不直接翻转视频

homography 通常是在当前 camera local court frame 上计算的。若某个几何点来自 canonical court frame，先使用当前 view 的 orientation 做 canonical→local 转换，再进入 homography；若数据本身已是该 view 的 image-space 标注，则不再应用 orientation。这样 A/B 视频的左右像素关系不会被错误二次翻转，小地图仍可独立使用既有 orientation 显示变换。

### 5. A/B 切换采用几何与媒体的同一事务

切换时保存 canonical 时间和播放状态，目标 view 的 video、时间映射和 `DisplayViewGeometry` 一起成为 pending switch。目标视频 metadata 可用且时间 seek 完成后才将目标几何作为可见主视频 overlay；旧 view 的 SVG 监听和几何引用在清理时失效。切换前播放则目标 seek 成功后续播，切换前暂停则保持暂停。

这项设计依赖当前双摄播放同步变更的 source identity 防护；几何层使用相同的 view/source guard，避免 A 的旧事件在 B 已挂载后继续刷新 overlay。

### 6. 图层开关和降级状态独立表达

增加“球场投影”和“球网投影”两个独立控制。几何资产完整时默认启用；用户关闭其中一层不得影响其他视频图层、播放位置或小地图。球场 calibration 缺失/无效时隐藏球场层；球网 scene revision 或三点标注缺失时只隐藏球网层，并在状态区显示对应原因，不绘制 demo 几何。

## Risks / Trade-offs

- [摄像机在录制期间移动、变焦或裁切] → 明确 fixed-camera 适用范围；检测到尺寸/资产不匹配时降级提示，逐帧相机跟踪列为后续能力。
- [四角标定误差导致整块球场线偏移] → 展示 calibration quality，保留标定预览和人工复核；真实验收以四角误差和主视频重合度为门槛。
- [球网三点来自单独标定帧或分辨率不同] → 保存 image width/height/frame provenance，渲染前统一缩放，并在资产状态中标记 frame/尺寸不一致。
- [A/B 切换时新视频先渲染而几何尚未加载] → 使用 pending geometry 和 source identity，几何未就绪时暂不显示，不沿用旧 view 几何。
- [把 canonical orientation 误用于像素镜像] → 将 local/canonical 转换封装在 mapper 中，增加 identity、rotate_180、mirror_x、mirror_y 的坐标测试。
- [完整三维球网需求超出 MVP] → 当前只承诺人工 image-space 网顶曲线；后续若要网柱/网面，基于已发布 camera model 单独设计三维 renderer。

## Migration Plan

1. 先发布只读 geometry API 接线和前端 renderer；不修改既有分析 artifact、任务状态或场景 revision。
2. 对新任务直接使用现有 calibration 与 metric scene revision；历史任务按资产可用性自动显示或降级。
3. 通过单摄、双摄 A/B→A、暂停切换、seek、缺失资产和真实固定机位视频验收后开启默认显示。
4. 若发现投影异常，可关闭两个新图层或回退前端版本；人物框、球路、小地图和分析结果不受影响。

## Open Questions

- MVP 的球场线是否只显示外框与球网，还是同时显示厨房线和中线；设计默认包含外框、厨房线、中线和球网，但允许通过样式常量收窄。
- 若产品最终要求完整“球网矩形框”而不只是网顶曲线，需要确认是否接受使用场景 `camera_model` 做三维投影；这应作为后续扩展，不阻塞本次二维人工标注版本。
