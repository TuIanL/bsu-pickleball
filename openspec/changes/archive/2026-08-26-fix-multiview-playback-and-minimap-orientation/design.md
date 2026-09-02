## Context

真实双摄分析页将外部 `videoSrc` 同步到内部 `activeVideoSrc` 后，以后者作为 `<video>` 的 key 和实际媒体源。现有媒体事件/`requestVideoFrameCallback` effect 却依赖外部 `videoSrc`；切换时 effect 可能先绑定旧 video，随后 React 重建新 video，造成新媒体无逐帧时间回调，canonical 时间和 SVG overlay 停滞。

`VisionPage` 已为每个展示机位提供 source timestamp offset/rate，分析产物中的球员、轨迹和球路使用 canonical 坐标。`CourtMinimap` 当前直接将 canonical 坐标映射到固定 SVG 朝向，且没有当前展示机位的 orientation 输入。

## Goals / Non-Goals

**Goals:**

- 让实际挂载的视频元素成为播放状态、当前 source 时间和逐帧调度的唯一权威。
- A/B 切换保留 canonical 播放位置；切换前播放中的视频在目标机位 seek 完成后自动续播。
- 小地图随当前展示机位按 `courtOrientation` 改变视觉朝向，同时保持 canonical 运动数据与 P1–P4 身份不变。
- 保持单摄、不可用机位、无 orientation 元数据和不支持 `requestVideoFrameCallback` 的兼容行为。

**Non-Goals:**

- 不修改后端检测、融合、校准、时间映射或 artifact schema。
- 不重新分配我方/对方或 P1–P4 身份，不在切机位时重算轨迹和球路。
- 不新增用户手动旋转小地图的设置；方向由当前机位已保存的 orientation 决定。

## Decisions

### 1. 用 active media lifecycle 绑定逐帧同步

媒体事件和视频帧回调 effect SHALL 以 `activeVideoSrc`（以及其对应的挂载 video）为依赖与生命周期边界；清理旧视频的事件、帧回调和 fallback RAF 后，再对新视频绑定。`currentTime` 仍保存 source media time，并在渲染前通过现有 offset/rate 转为 canonical time。

这避免把监听器绑定到即将卸载的元素。仅改为监听 `timeupdate` 会降低 60fps overlay 的平滑度，因此保留 `requestVideoFrameCallback` 并以 RAF 作兼容回退。

### 2. 用一次性切换事务恢复时间与播放状态

点击机位时记录 `{ canonicalSeekMs, resumePlayback }`。目标媒体的 metadata 可用后，将 canonical 时间通过目标机位 mapping 转换、clamp 并 seek；收到 `seeked`（或确认当前时间到达目标）后，仅当 `resumePlayback=true` 时调用 `play()`。该请求是一次性的，成功、失败或用户在加载中主动暂停后均应清除，避免旧切换请求影响后续操作。

相较于在 `loadedmetadata` 后立即 `play()`，等待 seek 完成可防止用户先看到 B 的 0 秒帧和错误 overlay；相较于始终自动播放，可尊重原本暂停后切换机位的状态。

### 3. 将小地图方向限定为显示变换

`CourtMinimap` 接收当前展示机位的 `courtOrientation`，在 canonical court point 映射为 SVG point 前应用 inverse viewing transform：`identity` 不变，`rotate_180` 翻转 x/y，`mirror_x` 翻转 x，`mirror_y` 翻转 y。场地边界、厨房线、NET、球员轨迹、球路、球点与弹跳标记全部经过同一个 mapper。

使用每机位已有 orientation，而不是以“B 机位”硬编码翻转。这样可正确支持对置相机（通常 `rotate_180`）以及未来不同安装方向；方向缺失或无效时回退 `identity`。

### 4. 回归测试以可观测时间与几何断言为中心

组件测试模拟 A→B 的 source 替换、metadata、seek、播放与视频帧回调，断言 B 的 current/canonical time 会继续变化且 overlay 位置更新。小地图测试断言同一 canonical 点在 identity 和 rotate_180/mirror_y 下落在预期相反位置，并断言标签/颜色/轨迹数据未被改写。

## Risks / Trade-offs

- [不同浏览器的 metadata/seeked 时序不同] → 以一次性 pending switch 状态和 source identity 校验防止过期事件续播错误视频，并保留 RAF 回退。
- [切换后 `play()` 被浏览器策略拒绝] → 捕获失败，停留在正确 seek 时间并保持可点击播放，不让 overlay 脱同步。
- [orientation 数据不完整或历史任务缺字段] → 统一回退 `identity`，保持当前小地图行为。
- [180° 翻转同时变更左右方向] → 严格遵从保存的 `courtOrientation`；仅要求上下互换的安装应保存为 `mirror_y`，不依据机位名称猜测。

## Migration Plan

此变更为纯前端兼容更新，无数据迁移。发布后，已有任务在提供 orientation 时获得导向小地图；缺少 orientation 的历史任务保持原显示。若发现异常，可回退前端版本，后端 artifact 与任务数据不受影响。

## Open Questions

- 无；默认以每机位持久化的 `courtOrientation` 为方向权威。
