# self-heal-pts-sidecar

## Why

双摄同步锚点工作台打开前要求两路 registered video 都具备有效 source PTS sidecar（`GET /api/videos/{id}/timing` 校验，缺失返回 409 `source_pts_missing`）。但 sidecar 的补写只在 merge 后台流程内触发一次：8-13 之前完成 merge 的历史会话（以及任何补写失败/中断的场景）会永久缺失 sidecar，工作台无法打开，且没有任何途径恢复（2026-08-16 实测 7-20 会话 `rec-ae349557ce` / `rec-5acd1eff22` 撞上此问题，需要手动跑 ffprobe 补写）。

## What Changes

- 新增 `POST /api/videos/{video_id}/timing/materialize` 同步补写接口：对 registered video 幂等生成 `<media_path>.pts.jsonl`；sidecar 已存在且有效时直接复用（快路径），缺失时用现有 PTS sidecar writer（ffprobe 提取 + 原子写入），失败返回结构化错误且不影响媒体。
- 后端启动时扫描所有 registered videos（含 sync-recording 会话注册的视频），对缺失 sidecar 的异步补写；并发受限、外接盘未挂载或 ffprobe 失败仅记录 warning，不阻塞启动。
- `request_merge` 对已完成会话的短路分支补强：即使 `merge_status == completed` 且视频可用，也检查并补写缺失的 sidecar（幂等快路径），使"merge 完成"与"timing 可用"同生命周期。
- 双摄同步锚点工作台"工作台无法打开"错误卡新增"尝试修复"按钮：调用 materialize 接口，完成后自动刷新页面重试加载。
- 补充测试：materialize 幂等性、视频不存在 404、sidecar 已存在复用、启动扫描补写、merge 短路分支补写。

## Capabilities

### New Capabilities

（无，避免 spec 碎片化；触发机制并入既有 capability）

### Modified Capabilities

- `multiview-timing-authority`: "Historical registered video sidecar materialization" 需求从"能力存在"扩展为"多触发源自愈机制"——新增 materialize API、启动扫描、merge 收尾三个触发源，并定义并发与失败降级行为。
- `sync-anchor-workflow`: 新增"timing 缺失时的恢复路径"需求——工作台加载失败时可触发 materialize 修复并重试，而非只能返回。

## Impact

- 后端：`backend/app/api/routes_video.py`（materialize 端点）、`backend/app/camera/sync_recorder_service.py`（启动扫描挂载 + merge 收尾补强 + 补写并发控制）、`backend/app/main.py`（lifespan 内触发启动扫描）。
- 前端：`src/pages/SyncCalibrationWorkbenchPage.tsx`（错误卡"尝试修复"按钮）、`src/services/analysisClient.ts`（materialize API 封装）。
- 测试：`backend/tests/test_video_timing_api.py`（materialize 端点）、新增启动扫描/merge 分支测试。
- 无外部依赖变化；复用现有 `write_frame_timing_sidecar` / `_materialize_registered_video_timing`。
