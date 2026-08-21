## Context

比赛库（/library）通过 `AppRouter` 按路由切换渲染不同页面，切走后 `LibraryPage` 卸载，返回时重新挂载：重新 `buildLibraryItems()` 拉元数据 + 重新用 `<video preload="metadata">` 请求视频流解码封面首帧。视频量大时，每次往返都重复解码，卡顿明显。

封面数据现状：`libraryAdapter` 为每个 `LibraryItem` 生成单个 `coverVideoUrl`——`sync_recording` 取 `default_analysis_video_id ?? cam_1 ?? cam_2`，因此双摄与单摄封面视觉无差别。`SyncRecordingSession.registered_video_ids.cam_1/cam_2` 两路机位流本身都存在，具备拼接条件，且复用既有 `GET /api/videos/{id}/stream`（`getVideoStreamUrl`），不新增后端接口。

导航衔接断裂三处：上传页（`/upload`，landing shell 无侧边栏）无返回入口；首页「进入开始使用」跳 `/capture`；`/capture` 在 [router.ts](src/app/router.ts) 被映射为 `navigationSection: "videos"`，而侧边栏 [AppSidebar](src/components/platform/AppSidebar.tsx) 仅有 `library/capture/devices`，导致「现场采集」始终不高亮。

## Goals / Non-Goals

**Goals:**
- 同一浏览器会话内，从比赛库切到其它页面再返回时，已加载过的封面立即显示，不重新解码。
- `sync_recording` 素材封面以 `cam_1 | cam_2` 左右拼接展示，一眼可辨双摄联动任务。
- 修复三处导航衔接：上传页可返回比赛库、首页入口进入比赛库、进入现场采集时侧边栏正确高亮。

**Non-Goals:**
- 不做跨会话/跨浏览器重启的持久化封面缓存（cache 存储 / IndexedDB），仅缓存当前会话。
- 不新增后端接口或字段；不改动三轴生命周期语义。
- 不做封面 hover 播放预览（另属 `add-library-media-previews` 范畴）。

## Decisions

**D1. 封面解码缓存：module 级 `Map<src, 首帧 dataURL>`。**
新增独立的封面预览模块，内部维护 `Map<string /* stream url */, string /* dataURL */>`。组件首次挂载时若命中缓存直接渲染 `<img>`；未命中则渲染临时 `<video>` 静音、`playsInline`、`preload="metadata"`，解码到约 `0.05s`（`seeked`/`loadeddata` 兜底）后用离屏 `canvas`（最大宽度 480，`jpeg` 0.7）绘制首帧并写回缓存，随后以 `<img>` 展示，卸载临时 `<video>`。
- 为何 module 级而非 Context/状态：module 单例在 SPA 跨路由渲染时不会被卸载重置（仅整页刷新清空），恰好满足「本次使用期间每次点回可见」，无需侵入 App 状态树。
- 备选（否决）：Cache API / IndexedDB 持久化——跨会话失效成本与复杂度高于当前收益，作为后续增强。
- 边界：条目上限做 LRU 约 200 条，避免超大视频库撑爆内存。

**D2. 封面渲染按来源分派 + 双摄左右拼接。**
`LibraryCard` 封面区改为调用统一封面组件，按 `item.cameraSetup`/`sourceType` 分派：
- 单摄 / 上传：单画面全幅 `object-cover`。
- 双摄（`sync_recording` 且两路机位流可用）：flex 横向布局，`cam_1` 左、`cam_2` 右，各占半幅，`object-cover` 裁掉黑边，中间细分割线 + 右上角「双摄」角标。
- 双摄但某一路流缺失/不可用：对应半幅显示中性占位，不伪造画面；两路皆无则退回单画面或占位。

**D3. 数据侧：双摄暴露两路机位流。**
`libraryAdapter` 的 `sync_recording` 分支在保留 `coverVideoUrl`（兼容现有消费方）之外，新增字段（如 `cameraCoverSources?: { cam_1?: string; cam_2?: string }`），由 `getVideoStreamUrl(registered_video_ids.cam_1 / cam_2)` 构建。`buildLibraryItems` 与 `resolveLibraryItemByRef` 两处同步补充。

**D4. 三处导航修复。**
- `src/app/router.ts`：`captureHome (/capture)` 的 `navigationSection` 由 `"videos"` 改为 `"capture"`，命中侧边栏「现场采集」高亮；同步更新 `router.test.ts` 断言。
- `src/pages/LandingPage.tsx`：「进入开始使用」`onNavigate("/capture")` → `onNavigate("/library")`。
- `src/pages/NewAnalysisPage.tsx`：Landing shell 下（页面无侧边栏）顶部主视觉区新增「返回比赛库」按钮 → `onNavigate("/library")`。

## Risks / Trade-offs

- [双摄任一路流不可用导致拼接断图] → 半幅中性占位 + 角标，不伪造画面；两路均无回退占位。
- [module 级缓存易膨胀（大视频库）] → LRU 上限 ~200 条；dataURL 压缩为小尺寸 jpeg。
- [`app-sidebar`/`product-landing` 规格与现有代码有历史出入] → delta 对齐当前实际代码语义，只补正确行为、不推翻。
- [`router.test.ts` 断言 `/capture` navigationSection] → 同步更新相关用例，避免回归。