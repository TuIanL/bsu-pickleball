# library-cover-poster Specification

## Purpose
比赛库卡片封面的预生成 poster 能力：在资产收尾时用 ffmpeg 从已落盘视频抽一帧生成 poster 图，经 serving 端点暴露（带条件缓存），并由 `libraryAdapter` 派生为 `thumbnailUrl` 供前端优先展示；抽帧失败非阻断，完全回退既有视频流首帧链路。

## Requirements
### Requirement: 资产收尾时生成 poster 图

系统 SHALL 在双摄合并完成、单摄录制收尾、以及 upload 视频登记就绪时，从已落盘的可播放视频中抽取一帧生成 poster 图；双摄 poster SHALL 直接取自合并后的单条视频帧（天然左右拼接构图），单摄/upload SHALL 取自该视频文件单帧。

#### Scenario: 双摄合并完成后生成左右拼接 poster
- **WHEN** 双摄 `merge_status` 变为 `completed` 且 `default_analysis_video_id` 对应视频已落盘
- **THEN** 系统 SHALL 从该 merged video 在避开第 0 帧的时间戳抽取一帧，生成 poster 图
- **AND** poster 构图 SHALL 与比赛库双摄封面「左右拼接」视觉一致

#### Scenario: 单摄录制收尾生成 poster
- **WHEN** 单摄 `recording` 视频资产 finalize 完成
- **THEN** 系统 SHALL 从该视频文件抽取一帧生成 poster 图

#### Scenario: 避免黑屏/预热帧
- **WHEN** 系统决定抽帧时间戳
- **THEN** SHALL 跳到第 0 帧之后的画面（如 `min(max(duration*0.15, 2.0), duration-0.1)`），不得使用 time=0

### Requirement: poster 经 serving 端点暴露并可缓存刷新

系统 SHALL 通过 `GET /api/videos/{video_id}/poster` 服务与视频同目录落盘的 poster 图；响应 SHALL 携带 `ETag` / `Last-Modified` 条件缓存头（等效 `?v=<mtime>` 缓存击穿），以便重新合并覆盖同名 poster 后浏览器自动刷新。前端 SHALL 由已注册 video_id 派生 poster URL（与 `getVideoStreamUrl` 同模式），不新增 catalog 字段。

#### Scenario: poster 已生成
- **WHEN** 某素材已生成 poster 且前端请求 `/api/videos/{video_id}/poster`
- **THEN** 端点 SHALL 返回 `image/jpeg` 与 `ETag` / `Last-Modified` 响应头
- **AND** 前端 SHALL 由该 video_id 派生 `thumbnailUrl`

#### Scenario: 重新合并后缓存刷新
- **WHEN** 视频被重新合并且同名 poster 被覆盖
- **THEN** 新 poster 的 `ETag` / `Last-Modified` SHALL 变化
- **AND** 浏览器 SHALL 按条件请求语义重新拉取，不展示陈旧封面

#### Scenario: 未生成 poster
- **WHEN** 素材尚未生成 poster（如待合并、抽帧失败）
- **THEN** 端点 SHALL 返回 404
- **AND** 前端 `thumbnailUrl` SHALL 为 undefined，封面走视频流首帧 / 占位降级

### Requirement: libraryAdapter 映射 thumbnailUrl

`libraryAdapter` SHALL 由已注册 video_id 派生 `thumbnailUrl`（双摄取 `default_analysis_video_id` 优先，其次任一注册机位），覆盖 `sync_recording`、`recording`、`upload` 三类来源；无可用 video_id 时保持未定义，由现有封面降级链路处理。

#### Scenario: 双摄素材映射 poster
- **WHEN** sync recording 存在 `default_analysis_video_id`（或任一 `registered_video_ids`）
- **THEN** `buildLibraryItems` / `resolveLibraryItemByRef` 组装出的 view model SHALL 将 `thumbnailUrl` 设为该 video_id 派生 URL

#### Scenario: 单摄与上传素材映射 poster
- **WHEN** recording 存在 `video_id`，或 upload video catalog 存在 `id`
- **THEN** 对应 view model SHALL 设置 `thumbnailUrl` 为该 id 派生 URL

#### Scenario: 无可用 video_id
- **WHEN** 素材无任何已注册机位/默认分析视频
- **THEN** `thumbnailUrl` SHALL 为 undefined

### Requirement: 抽帧失败非阻断

poster 抽帧 SHALL 包在容错逻辑内；任一来源抽帧失败 SHALL 仅记录 warning 且不落盘 poster 文件，前端自动回到视频流首帧逻辑，不得让卡片表现差于现状。

#### Scenario: ffmpeg/解码不可用
- **WHEN** 抽帧工具不可用或视频无法解码
- **THEN** 系统 SHALL 跳过 poster 生成，不留半成品文件
- **AND** 比赛库封面 SHALL 继续走现有视频流首帧 / 占位降级，行为与未启用本变更一致
