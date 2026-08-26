## Why

比赛库卡片目前只依赖「视频流首帧」绘制封面（`<video>` 拉流解码第 0 帧）。该方案在未合并/未注册的双摄素材上会退化为灰底占位，且多卡片网格下浏览器需并发解码大量视频流，首屏慢、易闪烁、且依赖流端 range/seek/CORS 支持，稳定性差。用户实测：同一比赛库中仅「分析完成」的双摄有封面，其余「待分析/待合并」双摄全部空白。

后端已具备在录制收尾 / 合并完成时落盘视频资产的能力，抽一帧 poster 是低成本的确定性增强。前端 `LibraryCard` 早已预留 `thumbnailUrl` 优先分支（`LibraryCard.tsx:135-150`），只是 `libraryAdapter` 从未填充该字段。因此本变更让「已完成的素材」直接拿到稳定 poster，未完成的继续走现有视频流/占位兜底，整体不退化。

## What Changes

- 后端在双摄合并完成（以及单摄录制收尾、upload 登记）时，用 ffmpeg 抽取一帧，生成 poster 图（双摄直接抽 merged video，天然左右拼接）与视频同目录落盘，并通过 `GET /api/videos/{video_id}/poster` 端点服务（带 ETag/Last-Modified 缓存刷新，等效 `?v=mtime`）。
- `libraryAdapter` 由已注册 video_id 派生 `thumbnailUrl`（与 `getVideoStreamUrl` 同模式，三处组装：`sync_recording`、`recording`、`upload`），不新增 catalog 字段。
- 前端封面渲染顺序保持 `thumbnailUrl → 视频流（coverVideoUrl / cameraCoverSources） → 中性占位`；poster 命中时直接 `<img>`，不再解码视频流。
- poster 生成失败或缺失时，完全回退到当前视频流首帧逻辑，不影响现有行为。
- poster 时间戳选择「开球后若干秒」而非第 0 帧，避免黑屏/设备预热帧。

> 实施修正（2026-08-24）：原方案拟在 catalog 序列化新增 `thumbnail_url` 字段；实施时改为「后端 serving 端点 + 前端由 video_id 派生 URL」，与既有 `coverVideoUrl` 派生模式保持一致，避免 schema 变更与多端点序列化耦合。

## Capabilities

### New Capabilities
- `library-cover-poster`: 后端在资产就绪时生成并服务 poster 图（单摄单帧 / 双摄左右拼接），以及其在 `libraryAdapter` 到 `thumbnailUrl` 的映射契约。

### Modified Capabilities
- `library-cover-preview`: 新增「封面优先使用预生成 poster」要求，`thumbnailUrl` 命中时直接 `<img>` 展示；保持视频流首帧与中性占位作为降级链路。

## Impact

- 后端：新增 `backend/app/services/cover_poster.py`（抽帧，非阻断）；`video_service.save_upload` / `register_recording` 挂载抽帧（覆盖 upload、单摄、双摄合并）；新增 `GET /api/videos/{video_id}/poster` 端点。poster 与视频同目录落盘（`*.poster.jpg`），随视频清理策略。
- 前端：`src/services/analysisClient.ts`（新增 `getVideoPosterUrl`）；`src/services/libraryAdapter.ts`（三处组装填 `thumbnailUrl`）；`src/components/library/LibraryCard.tsx`（poster 分支补「双摄」角标，保留既有分支结构）。
- 依赖：ffmpeg（含 ffprobe）需可在运行时调用；不可用则 poster 跳过、前端回退视频流，无破坏。
- 风险：poster 与视频不同步（重新合并后需刷新）→ ETag/Last-Modified 覆盖同名文件后自动失效；生成失败需有兜底，不应让卡片比现在更差。
