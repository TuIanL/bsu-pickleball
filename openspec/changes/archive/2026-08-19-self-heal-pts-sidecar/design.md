# self-heal-pts-sidecar Design

## Context

双摄同步锚点工作台打开前，前端对两路 registered video 调用 `GET /api/videos/{id}/timing` 校验 source PTS sidecar（`{media_path}.pts.jsonl`），缺失返回 409 `source_pts_missing`。

sidecar 的生成当前只有一条路径：merge 后台任务（`_merge_session_videos_background`）内的 `_materialize_registered_video_timing`。该函数已具备幂等快路径（sidecar 存在 → summarize；缺失 → `write_frame_timing_sidecar` ffprobe 提取 + 原子写入；失败 → unavailable 降级），但**触发机会只有 merge 一次**：

- 8-13 commit `394e231` 才引入该机制，此前完成 merge 的会话（如 7-20 录制的 `sync_20260720_124214_01b591`）永远缺失 sidecar；
- `request_merge` 对 `merge_status == completed` 且视频可用的会话直接短路返回，不会补写；
- 无启动扫描、无修复接口、无前端恢复路径。

2026-08-16 实测：7-20 会话两路视频（174/175 merged.mp4，各 1.29GB、43805 帧、730s）手动补写 sidecar 成功（各 ~150s，PTS 零单调性违规），证明 ffprobe 补写链路对历史数据完全可行。本 change 把"补写能力"升级为"自愈机制"。

约束：本地工具场景（单机、外接盘媒体库）、后端 FastAPI + 前端 React，现有 `write_frame_timing_sidecar` / `_materialize_registered_video_timing` 直接复用。

## Goals / Non-Goals

**Goals:**
- 提供 `POST /api/videos/{video_id}/timing/materialize` 同步补写接口（幂等、结构化错误）。
- 后端启动时自动扫描 registered videos，异步补写缺失 sidecar（并发受限、失败静默降级、不阻塞启动）。
- `request_merge` 对已完成会话的短路分支补强为"仍校验并补写缺失 sidecar"。
- 工作台"无法打开"错误卡提供"尝试修复"按钮，补写成功后自动重载。
- 用 per-video 锁串行化并发补写，避免同一视频重复 ffprobe。

**Non-Goals:**
- 不做异步任务 + 轮询的 materialize 形态（本地场景同步足够）。
- 不重构 `write_frame_timing_sidecar` 的 ffprobe 提取逻辑（现状满足需求，实测 43805 帧零违规）。
- 不做前端自动弹修复（用户需要可见的失败原因与主动操作）。
- 不修改 `/timing` 端点语义（保持只读校验；修复动作显式走 materialize）。

## Decisions

### D1：materialize 接口同步执行
`POST /api/videos/{video_id}/timing/materialize` 使用同步 `def` 端点（FastAPI 线程池执行，不阻塞事件循环），阻塞至补写完成（大视频约 2-3 分钟，受 `PICKLEBALL_PTS_PROBE_TIMEOUT_SECONDS` 控制，默认 3600s）。
- **备选**：202 + 任务 id + 前端轮询 —— 拒绝。本地工具场景徒增任务表与轮询状态机，收益为零。
- **理由**：实现最小、语义直接；前端按钮加载态天然覆盖等待窗口。

### D2：启动扫描 = 异步后台线程 + 并发上限
lifespan 内对 registered videos（video_service 全部注册元数据 + sync-recording 会话 `registered_video_ids` 去重）逐个检查 sidecar，缺失的进入后台补写队列；并发上限由 `PICKLEBALL_PTS_BACKFILL_CONCURRENCY` 控制（默认 1）。补写线程 daemon 化，任何失败仅 `logger.warning`。
- **备选**：lifespan 内同步全量补写 —— 拒绝。多个 1.3GB 视频会阻塞启动数分钟。
- **理由**：历史会话重启即自愈，且对启动零影响。

### D3：统一补写器 + per-video 锁
把 `_materialize_registered_video_timing`（或等价逻辑）提升为可复用入口，包裹 per-video `threading.Lock`（`dict[str, Lock]` 按 video_id/path 索引）。三个触发源（API、启动扫描、merge 收尾）全部走该入口；锁保证同一视频不会并发跑两次 ffprobe，原子写入（temp + `os.replace`）保证最终一致性。
- **理由**：三个触发源共享一套幂等/降级语义，避免各自重复实现。

### D4：merge 收尾补强
`request_merge` 的 completed 短路分支（当前：`completed` 且全部注册且可用 → 直接返回）改为：仍遍历每路 registered video 调用补写器（幂等快路径，已存在即 summarize，几乎零成本），随后才短路返回。
- **理由**：语义上"merge 完成 = 媒体可用 + timing 可用"；对已健康的会话无感知，对缺失会话自动兜底。

### D5：启动扫描范围 = 全部 registered videos
不区分 `source=recording` / `source=upload`：`/timing` 端点对所有 video_id 开放，任何 registered video 都可能被工作台消费；扫描全部最简单且不会漏。本地数据量小，全量扫描无性能问题。
- **备选**：仅扫 recording 来源 —— 拒绝。上传视频同样可能被双摄/分析流程消费，漏扫即复现 409。

### D6：前端"尝试修复"按钮
工作台错误卡在 `loadError` 展示区新增"尝试修复"按钮：对失败的两路 video_id 依次调 materialize（复用 `analysisClient` 封装），全部成功或部分成功后 `window.location.reload()` 重试加载；任一失败则在错误卡追加失败原因，保留"返回双摄分析"。
- **理由**：用户一次点击完成"修复 + 重试"，无需手动刷新。

## Risks / Trade-offs

- [大视频补写耗时 2-3 分钟，接口同步等待] → 前端按钮带 loading 态；超时由 `PICKLEBALL_PTS_PROBE_TIMEOUT_SECONDS` 控制；失败返回结构化 409 可重试。
- [启动扫描与 merge 补写并发同一视频] → per-video 锁串行化，重复请求走快路径。
- [外接盘未挂载时扫描/补写报错] → 全部捕获为 warning + unavailable，不阻塞启动、不影响媒体；卷恢复后下次启动或手动 materialize 自愈。
- [极端视频 PTS 非单调导致补写失败] → materialize 返回 `source_pts_invalid` 结构化错误；媒体不变；工作台仍可"返回双摄分析"降级路径。
- [前端 reload 后仍失败（如媒体不可用）] → 错误卡保留原因与出口，允许再次尝试，不陷入死循环（每次尝试都是用户主动触发）。

## Migration Plan

- 无数据迁移。历史会话缺失的 sidecar 由"启动扫描"一次性自愈（启动后后台补写，前端无需感知）。
- 部署顺序：后端（补写器 + 端点 + 启动扫描 + merge 补强）→ 测试 → 前端按钮。
- 回滚：接口与扫描均为增量能力；删除 materialize 端点与启动扫描入口即可退回现状，不影响既有媒体与分析。

## Open Questions

- 启动扫描是否需要控制台/日志摘要（补写成功/跳过/失败计数）？—— 默认仅 per-video warning + 一条汇总 INFO 日志。
- materialize 端点是否需要鉴权？—— 本地工具场景暂不需要，与现有 `/timing` 一致。
