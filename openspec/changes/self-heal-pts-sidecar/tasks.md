# self-heal-pts-sidecar Tasks

## 1. 统一补写器与并发控制

- [ ] 1.1 在 `backend/app/camera/sync_recorder_service.py`（或 services 层）将 `_materialize_registered_video_timing` 提升为可复用入口，包裹 per-video `threading.Lock`（按 media path 索引），三个触发源共用
- [ ] 1.2 补写器保持幂等快路径：sidecar 存在且有效 → summarize 直接返回；缺失 → `write_frame_timing_sidecar` 原子生成；失败 → 返回 unavailable 结构化结果（不抛异常给上层媒体流程）

## 2. materialize 同步接口

- [ ] 2.1 在 `backend/app/api/routes_video.py` 新增 `POST /api/videos/{video_id}/timing/materialize`（同步 `def` 端点），复用补写器
- [ ] 2.2 视频不存在/不可用 → 结构化 404（与 `GET /timing` 一致）；补写成功 → 返回 sidecar summary；补写失败 → 结构化 409（code `source_pts_invalid` 或等价 reason）
- [ ] 2.3 更新 `backend/tests/test_video_timing_api.py`：materialize 成功生成、sidecar 已存在复用（不重复生成）、视频不存在 404、PTS 无效 409

## 3. 启动扫描自愈

- [ ] 3.1 实现启动扫描函数：遍历 video_service 全部 registered videos + sync-recording 会话 `registered_video_ids`（去重），筛出缺失 sidecar 的媒体
- [ ] 3.2 在 `backend/app/main.py` lifespan 内以 daemon 线程触发扫描补写，并发上限由 `PICKLEBALL_PTS_BACKFILL_CONCURRENCY` 控制（默认 1）
- [ ] 3.3 扫描/补写异常全部捕获：外接盘未挂载、媒体缺失、ffprobe 失败仅 `logger.warning`，不阻塞启动；结束输出一条汇总 INFO 日志（成功/跳过/失败计数）
- [ ] 3.4 新增启动扫描测试（mock registered videos：缺失 sidecar 的触发补写、媒体不可用跳过且启动不阻塞）

## 4. merge 收尾补强

- [ ] 4.1 修改 `request_merge` completed 短路分支：即使 `merge_status == completed` 且视频已注册，仍遍历每路 registered video 调用补写器（幂等快路径）后再返回
- [ ] 4.2 新增/更新 `backend/tests/test_dual_camera_sync.py` 或相关 merge 测试：completed 会话缺失 sidecar 时调用 request_merge 后 sidecar 被补写

## 5. 前端"尝试修复"按钮

- [ ] 5.1 在 `src/services/analysisClient.ts` 封装 materialize API（返回结构化错误区分 404/409）
- [ ] 5.2 在 `src/pages/SyncCalibrationWorkbenchPage.tsx` 错误卡新增"尝试修复"按钮：对失败的两路 video_id 依次调 materialize（loading 态），全部成功后 `window.location.reload()`；任一失败在错误卡追加失败原因
- [ ] 5.3 保留"返回双摄分析"出口，修复失败可再次尝试（无死循环）

## 6. 验收与回归

- [ ] 6.1 本地起后端：验证启动扫描日志出现且不阻塞启动
- [ ] 6.2 用 7-20 会话（已手动补写）回归 `GET /timing` 两路均 200；再对一路删掉 sidecar 调 materialize 验证补写恢复
- [ ] 6.3 `npm run build` + 后端 pytest 全量通过
