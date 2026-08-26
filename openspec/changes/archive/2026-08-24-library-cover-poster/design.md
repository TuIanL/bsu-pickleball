## Context

比赛库卡片封面当前只有一条渲染链路：`LibraryCard` 在 `thumbnailUrl` 缺失时，用 `coverVideoUrl` / `cameraCoverSources` 驱动的 `<video>` 首帧方案（`LibraryCover` + `CoverVideo`）。该方案在素材已注册可播放视频时可用，但在「待合并 / 待分析」或流端 range/seek/CORS 异常时会退化为灰底占位，且网格内多卡片并发解码视频流，首屏慢、资源重。

关键现状：
- `LibraryItemViewModel.thumbnailUrl` 字段已声明（`libraryAdapter.ts:94`），`LibraryCard.tsx:135-150` 已存在「`thumbnailUrl` → 视频流 → 占位」的优先分支，但 `libraryAdapter` 三处组装（sync/recording/upload）从未赋值，故前端始终走视频流。
- 后端在双摄合并完成、单摄录制收尾时，已经把可播放视频资产落盘（参考 `browser-playable-merged-video` 能力），poster 只是「从已落盘视频抽一帧」的确定性衍生物。

本设计的目标是把 poster 生成挂到既有的资产收尾环节，前端仅补一行映射即可获得稳定封面，不引入新队列、不新增结构性前端改动。

## Goals / Non-Goals

**Goals:**
- 资产就绪（合并完成 / 录制收尾）时同步生成 poster 图，并在 catalog 返回 `thumbnail_url`。
- 前端 `libraryAdapter` 将 `thumbnail_url` 映射到 `thumbnailUrl`，让 `LibraryCard` 已有分支生效。
- poster 命中时直接 `<img>`，跳过视频流解码；缺失/失败则完全回退现有视频流首帧逻辑。
- 双摄 poster 使用左右拼接构图（与现有双摄封面视觉一致）。

**Non-Goals:**
- 不替换、不删除现有视频流首帧链路（保留为降级）。
- 不引入独立的异步抽帧任务 / 消息队列。
- 不改动 `LibraryCover` / `CoverVideo` 的现有 fallback 行为（仅在其之上增加更优的首选项）。
- 不做封面编辑/裁剪交互（用户选帧等）。

## Decisions

### Decision 1：poster 生成挂载在资产收尾环节，而非独立后台任务
**选择**：在双摄合并产出、单摄录制 finalize 产出可播放视频之后，立即用同一流水线同步抽一帧。
**理由**：poster 完全由已落盘视频决定，没有独立调度需求；独立任务会增加队列/状态/重试复杂度，且封面只是增强项，不值得。
**备选**：独立抽帧 worker——被否决，overhead 与收益不匹配。

### Decision 2：双摄 poster 直接从「合并后的视频」抽帧，而非分别抽两路再合成
**选择**：双摄在合并完成后已存在单条 merged video（`default_analysis_video_id`），poster 直接对该视频 `-ss` 抽一帧即可，天然是左右拼接构图。
**理由**：避免分别抽 cam_1/cam_2 再 hstack 的额外步骤；与用户看到的「双摄左右拼接」视觉一致，且合并前本就无封面（回退视频流）。
**备选**：分别抽帧 + ffmpeg hstack / PIL 拼接——仅当未来需要在「合并前」也出双摄封面时才需要，本变更不取此路。

### Decision 3：抽帧时间戳避开第 0 帧
**选择**：使用 `-ss`（输入前快跳）到 `min(max(durationSec*0.15, 2.0), durationSec-0.1)` 附近取一帧，而非 time=0。
**理由**：第 0 帧常为黑屏/设备预热帧，正是当前「看着像没封面」的隐性原因之一；跳到开球后片刻能稳定拿到有内容的画面。
**备选**：固定 time=0——被否决，正是要解决的问题。

### Decision 4：后端 serving 端点 + 前端由 video_id 派生 URL（实施定稿，替代原 catalog 字段方案）
**选择（定稿）**：后端新增 `GET /api/videos/{video_id}/poster` 端点服务同目录落盘的 `*.poster.jpg`（带 ETag/Last-Modified 条件缓存，等效 `?v=mtime` 缓存击穿）；前端新增极薄的 `getVideoPosterUrl(id)`（与 `getVideoStreamUrl` 同模式），由已注册 video_id 派生，**不新增 catalog 字段**。
**理由**：与既有 `coverVideoUrl = getVideoStreamUrl(video_id)` 的派生模式完全一致，避免 sync/recording/video 三类序列化各加一个字段的耦合；ETag/Last-Modified 用标准 HTTP 语义解决「重新合并后 poster 刷新」，不污染 URL。
**备选（原案）**：catalog 序列化加 `thumbnail_url`——实施时弃用：多端点序列化耦合 + 前端仍需 URL 包装，收益不抵复杂度。

### Decision 5：生成失败非阻断
**选择**：抽帧步骤包 `try/except`；失败仅记录 warning 且不落盘 poster 文件，前端自动回到视频流首帧。
**理由**：封面是增强项，绝不应因抽帧失败让卡片比现在更差（现在至少还有视频流 fallback）。

## Risks / Trade-offs

- **[Risk] ffmpeg 运行时不可用** → 抽帧跳过，poster 不生成，完全回退视频流；不影响任何现有行为。
- **[Risk] 重新合并后 poster 陈旧**（浏览器缓存旧图）→ 每次 finalize 覆盖同名文件，ETag/Last-Modified 随之变化，浏览器自动重新拉取（等效 `?v=mtime`）。
- **[Risk] 额外存储占用** → poster 限制宽度 ≤480px、jpeg q70，单张约 20–60KB；纳入既有视频资产保留/清理策略，不单独膨胀。
- **[Risk] 双摄未合并（无 merged video）** → 此时本就无 `default_analysis_video_id`，poster 不生成，回退视频流（与现状一致），不退化。
- **[Trade-off]** 同步抽帧会让合并/finalize 延长数十毫秒~数百毫秒（取决于 `-ss` 快跳效率），在收尾环节可接受。

## Migration Plan

1. 后端：新增 `cover_poster.generate_poster` 并挂载到 `video_service.save_upload` / `register_recording`；新增 `GET /api/videos/{video_id}/poster` 端点。
2. 前端：新增 `getVideoPosterUrl`；`libraryAdapter` 三处组装补 `thumbnailUrl` 映射；`LibraryCard` poster 分支补「双摄」角标。
3. 验证：对「已合并双摄」「单摄录制」「待合并双摄」「upload 视频」四类分别确认封面表现（前两类出 poster，后两类回退视频流/占位，均不差于现状）。
4. 回滚：删除 `thumbnailUrl` 映射与 poster 端点即可完全回到视频流方案，无数据迁移。

## Open Questions

- 抽帧具体挂载点需实现时确认：`mergeSyncRecording` 与录制 finalizer 的精确函数位置（代码侧定位）。
- poster 尺寸/质量基线是否统一为 480px / q70，还是按卡片 DPR 出 2x（建议先 480 单倍，后续可加）。
- 是否对 `upload` 类大视频也强制抽帧（建议是，同一路径，成本低）。
