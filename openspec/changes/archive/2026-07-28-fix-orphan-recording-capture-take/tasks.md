## 1. 后端：启动孤儿 CaptureTake 修复

- [x] 1.1 在 `capture_recovery.py` 的 `recover_orphan_recordings()` 末尾新增步骤 4：查询 DB 中所有 `status IN ('starting', 'recording')` 的 `CaptureTake`，调用 `finalize_capture_take(take_id, "failed")` 逐条终态化
- [x] 1.2 修复逻辑使用 `get_session_factory()()` 获取独立 DB session，确保与前述步骤（FFmpeg/Fragment/Lease 清理）共享同一事务边界
- [x] 1.3 添加异常处理：单条 `finalize_capture_take` 失败不中断其他记录的修复（best-effort）
- [x] 1.4 添加日志记录：记录共修复了多少条孤儿 CaptureTake

## 2. 后端：单路 session list_sessions 自愈

- [x] 2.1 在 `session_service.py` 的 `list_sessions()` 方法中，对每个从磁盘加载的 session，新增自愈检测分支：`status == \"recording\"` 且 `find_active_session(session.camera_id)` 返回 None → 触发修复
- [x] 2.2 修复动作：更新 session status → `\"failed\"`、设置 `stopped_at`、`error_message`，调用 `_persist()` 持久化
- [x] 2.3 修复动作：调用 `capture_take_service.finalize_capture_take(db, session.capture_take_id, \"failed\")` 同步清理 CaptureTake
- [x] 2.4 无 `capture_take_id` 的旧 session 只修复 session JSON，不触发 CaptureTake 修复（跳过，不报错）

## 3. 后端：双路 list_sessions 自愈补全 CaptureTake 修复

- [x] 3.1 在 `sync_recorder_service.py` 的 `list_sessions()` 自愈分支（第 1884-1890 行），在 `self._persist(session)` 之后，新增 `finalize_capture_take` 调用
- [x] 3.2 使用独立 DB session 完成 CaptureTake 终态化，异常不阻塞 session 列表返回

## 4. 前端：侧边栏孤儿检测与强制终止

- [x] 4.1 在 `useActiveCaptureTake.ts` 中新增 `isOrphan` 判定逻辑：当 `activeTake` 存在时，尝试调用 `listRecordings({ field_session_id: activeTake.fieldSessionId, status: \"recording\" })` 和对应的 sync 版本，若均返回空 → 判定为孤儿
- [x] 4.2 `useActiveCaptureTake` 新增 `forceCancel` 回调：调用 `cancelRecording` 或 `cancelSyncRecording`（根据 activeTake.captureMode），成功后重新拉取 `getActiveCaptureTake` 刷新状态
- [x] 4.3 在 `AppSidebar.tsx` 的 `ActiveRecordingBlock` 中，当 `isOrphan === true` 时，状态块下方展示红色「强制终止」按钮
- [x] 4.4 「强制终止」按钮使用二次确认（`window.confirm` 或内联确认），防止误触
- [x] 4.5 终止中展示 loading 态，终止成功后隐藏状态块

## 5. 前端：useCaptureRuntime Hydration 孤儿兜底

- [x] 5.1 在 `useCaptureRuntime.ts` 的 `hydrate()` 中，`NO_ACTIVE_SESSION` 分支增加二次查询：用 `status: \"failed\"` 再查一次 session 列表，判断是否 session 已自愈
- [x] 5.2 若检测到 session 已自愈为 failed 但 getActiveCaptureTake 仍返回活跃，dispatch 新 action `ORPHAN_DETECTED`
- [x] 5.3 reducer 新增 `ORPHAN_DETECTED` action：phase 设为 `idle`，同时设置 `orphanInfo` 字段（包含 session 基本信息供 UI 展示）

## 6. 验证

- [ ] 6.1 手动模拟场景：启动单路录制 → 杀掉 Python 进程（模拟崩溃）→ 重启服务 → 确认 `getActiveCaptureTake` 返回 null、409 不再出现
- [ ] 6.2 手动模拟场景：启动双路录制 → 杀掉进程 → 重启 → 确认侧边栏无红点、新录制可正常启动
- [ ] 6.3 手动验证前端：制造孤儿场景后，确认侧边栏显示「强制终止」按钮，点击后 409 解除
