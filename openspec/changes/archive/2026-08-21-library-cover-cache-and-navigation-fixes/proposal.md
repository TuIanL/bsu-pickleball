## Why

比赛库页面存在三个体验问题：(1) 每次从比赛库切到其它页面再切回，所有视频封面都会重新加载，视频量大时等待成本高且往返卡顿；(2) 双摄（`sync_recording`）素材的封面与单摄无异，都是单一画面，无法直观看出这是双视角联动分析任务；(3) 前端重构后导航衔接断裂——上传页没有返回比赛库的入口、首页「进入开始使用」进入的是现场采集而非视频库、进入现场采集页时左侧导航未高亮。

## What Changes

- **封面会话内缓存 + 解码渲染抽象**：新增模块级封面帧缓存（`Map<src, 首帧 dataURL>`），卡片封面首帧解码后写入缓存；在同一浏览器会话内从工作区返回比赛库直接命中缓存显示 `<img>`，无需重新解码视频流。
- **双摄封面左右拼接**：`sync_recording` 素材封面由 `cam_1 | cam_2` 两路机位流左右拼接、各半幅 `object-cover` 裁切填满（无黑边），一眼可辨为双摄联动任务。封面渲染按来源分派——单摄/上传为单画面，双摄为左右双画面。
- **上传页返回入口**：`/upload`（NewAnalysisPage）顶部新增「返回比赛库」按钮，`onNavigate("/library")`。
- **首页入口修正**：LandingPage「进入开始使用」跳转目标从 `/capture` 改为 `/library`。
- **现场采集页导航高亮修正**：将 `/capture`（captureHome）的 `navigationSection` 从 `"videos"` 修正为 `"capture"`，使其命中侧边栏「现场采集」并高亮。

## Capabilities

### New Capabilities
- `library-cover-preview`: 比赛库卡片封面的解码缓存（会话内首帧 dataURL 复用）与按来源分派的封面渲染（单摄单画面 / 双摄左右拼接）。

### Modified Capabilities
- `library-item-projection`: 双摄 `sync_recording` 展示元数据需额外暴露 `cam_1`/`cam_2` 两个机位流地址，供双摄封面拼接渲染。
- `app-sidebar`: `/capture`（现场采集首页）应命中侧边栏「现场采集」导航项并正确高亮（修正 navigationSection 映射）。
- `product-landing`: 首页「进入开始使用」入口跳转到 `/library`；上传工作流页面（`/upload`）提供「返回比赛库」出口。

## Impact

- **前端**：
  - `src/services/libraryAdapter.ts`（类型 + 双摄分支暴露 cam_1/cam_2 流地址）
  - `src/components/library/LibraryCard.tsx`（封面渲染分派 + 复用缓存）
  - 新增封面预览能力模块（缓存 + 解码 + 拼接），放 `src/components/library/`
  - `src/app/router.ts`（captureHome 的 navigationSection 修正）
  - `src/pages/LandingPage.tsx`（入口跳转目标）
  - `src/pages/NewAnalysisPage.tsx`（返回按钮）
- **依赖/API**：无后端接口形状变化；复用既有 `GET /api/videos/{id}/stream`（`getVideoStreamUrl`）与 `registered_video_ids.cam_1/cam_2`。
- **测试**：更新 `router.test.ts`（/capture 的 navigationSection）、`libraryAdapter` 相关单测；新增封面预览能力渲染测试与缓存命中断言。
- **风险**：某一路双摄机位流不可用时，拼接对应半幅做中性占位而非伪造画面，避免出现断图。