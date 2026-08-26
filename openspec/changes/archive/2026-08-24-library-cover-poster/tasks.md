## 1. 后端 poster 抽帧工具

- [x] 1.1 新增 poster 抽帧函数 `backend/app/services/cover_poster.py`：用 ffmpeg `-ss`（输入前快跳）从视频文件抽取一帧，输出宽度 ≤480px、jpeg（`-q:v 5`）；抽帧失败（工具不可用 / 解码失败）仅 warning 并返回 False，不留半成品文件
- [x] 1.2 双摄抽帧直接以 `default_analysis_video_id` 对应的 merged video 为源（天然左右拼接），单摄/upload 以各自视频文件为源；时间戳取 `min(max(duration*0.15, 2.0), duration-0.1)`（ffprobe 读时长，不可用时回退 1.0s），避开第 0 帧
- [x] 1.3 poster 存储路径定为与视频同目录的 `*.poster.jpg`（`poster_path_for`），随视频资产清理而清理，不单独膨胀存储

## 2. 后端 serving 端点 + 前端派生 URL（实施定稿，替代 catalog 字段方案）

- [x] 2.1 新增 `GET /api/videos/{video_id}/poster` 端点：poster 存在时返回 `image/jpeg` + `ETag`/`Last-Modified` 条件缓存头（等效 `?v=mtime`），未生成返回 404；支持 `If-None-Match` → 304
- [x] 2.2 前端新增 `getVideoPosterUrl(id)`（`analysisClient.ts`），与既有 `getVideoStreamUrl` 模式一致，由已注册 video_id 派生 URL，**不新增 catalog 字段**（sync/recording/video 三类序列化均不改动）
- [x] 2.3 双摄/单摄/upload 三来源的 poster 来源 video_id 解析规则统一：双摄 `default_analysis_video_id` 优先 → `cam_1`/`cam_2`；单摄 `rec.video_id`；upload `video.id`

## 3. 挂载生成到资产收尾环节

- [x] 3.1 双摄合并（merged video 经 `register_recording` 登记）后同步抽帧——挂载点 `video_service.register_recording`（`sync_recorder_service.py:2066/2132` 均经此登记）
- [x] 3.2 单摄录制 finalize 后同步抽帧——挂载点 `video_service.register_recording`（`capture_finalizer.py:282` / `session_service.py:439` 均经此登记）
- [x] 3.3 upload 视频登记就绪后抽帧——挂载点 `video_service.save_upload`
- [x] 3.4 重新合并 / 重新 finalize 时覆盖同名 poster 文件；`ETag`/`Last-Modified` 随 mtime 变化触发浏览器重新拉取

## 4. 前端 adapter 映射

- [x] 4.1 `libraryAdapter` 在 `sync_recording`、`recording`、`upload` 三处组装（含 `buildLibraryItems` 与 `resolveLibraryItemByRef` 全部六处）填充 `thumbnailUrl = getVideoPosterUrl(video_id)`
- [x] 4.2 `LibraryCard` 「`thumbnailUrl` → 视频流 → 占位」分支已正确生效；另补 poster 分支（双摄单图）的右上角「双摄」角标，避免改用 `<img>` 后丢失来源标识（原角标仅在 `LibraryCover` 双摄布局内渲染）

## 5. 验证与回归

- [x] 5.1 四类来源适配器级验证：`libraryAdapter.test` 覆盖 upload / recording / sync（含 merged 优先）出 `thumbnailUrl`，无 video_id 的 sync 为 undefined（即回退视频流/占位）；**实机 UI 视觉回归由用户本人执行**（既有惯例）
- [x] 5.2 抽帧失败降级验证：`test_cover_poster.py` 覆盖「文件缺失 → False」「坏文件（非视频）→ False 且无半成品」「ffmpeg 成功路径（testsrc 真实抽帧）→ True」；失败不抛异常、不影响登记流程
- [x] 5.3 单测补充：`libraryAdapter.test.ts` 新增「三来源映射 thumbnailUrl」用例（12 项全过）；`test_cover_poster.py` 4 项全过；`tsc -b` 通过
