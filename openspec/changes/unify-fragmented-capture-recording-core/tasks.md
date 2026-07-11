## 0. 行为保护测试

- [x] 0.1 测试：单摄 start → stop → MP4 可播放 + Video 已注册
- [x] 0.2 测试：单摄 FFmpeg 异常退出 → Session failed + CaptureTake failed
- [x] 0.3 测试：双摄正常停止 → 两路 MP4 + cam_1 为 default_analysis_video_id
- [x] 0.4 测试：双摄任一路失败 → 两路同步重启（当前 strict_sync 行为不变）
- [x] 0.5 测试：cancel 后不产生可分析视频 + Fragment discarded
- [x] 0.6 测试：registry 中 capture_take_id 不为空（修复前预期失败）
- [x] 0.7 记录基线：`pytest` + `npm run build`

## 1. 数据契约与数据库迁移

- [x] 1.1 新增 `FragmentRepository` Protocol（create_starting / mark_recording / complete 等）
- [x] 1.2 新增 `ProcessRegistry` Protocol（register_started / register_ended）
- [x] 1.3 新增 `Clock` Protocol（utc_now / monotonic_ms）
- [x] 1.4 新增 `backend/app/models/media_fragment.py`：MediaFragment ORM（id、capture_take_id、capture_track_id、fragment_index、rotation_index、file_path、status、take_start_offset_ms、take_end_offset_ms、media_duration_ms、stop_reason、return_code、file_size、error_message）
- [x] 1.5 FragmentStatus enum：starting/recording/completed/failed/interrupted/discarded
- [x] 1.6 UNIQUE(capture_track_id, fragment_index)
- [x] 1.7 新增 `backend/app/models/track_finalization.py`：TrackFinalization ORM（capture_track_id、manifest_hash、status、output_path、video_id、started_at、completed_at、error_message）
- [x] 1.8 UNIQUE(capture_track_id, manifest_hash)
- [x] 1.9 新增 `backend/app/models/track_timeline_span.py`：TrackTimelineSpan ORM（track_finalization_id、fragment_id、take_start_ms、take_end_ms、output_start_ms、output_end_ms、gap_before_ms）
- [x] 1.10 ffmpeg_registry 新增 fragment_id、return_code、exit_reason 列（幂等 ALTER TABLE）
- [x] 1.11 现有 app.sqlite3 升级测试
- [x] 1.12 实现 `DbFragmentRepository` + `DbProcessRegistry` + `SystemClock`
- [x] 1.13 在 `init_db()` 中注册新模型

## 2. 修改 CaptureStartCoordinator

- [x] 2.1 新增 `PreparedTrack` dataclass（capture_track_id, slot, camera_id, analysis_role）
- [x] 2.2 `PreparedCapture.tracks` 改为 `list[PreparedTrack]`（返回真实 ID，不是 spec）
- [x] 2.3 固化启动顺序：prepare_start → 获得 Take/Track ID → 创建 MediaFragment → 启动 TrackRecorder → activate

## 3. TrackRecorder（独立单轨分片录制）

- [x] 3.1 新增 `backend/app/camera/track_recorder.py`
- [x] 3.2 定义 `FragmentStartSpec`（含 capture_take_id、capture_track_id、fragment_id、stream_url、output_path、fragment_index、rotation_index、take_start_offset_ms）
- [x] 3.3 定义 `FragmentHandle`（request_stop / wait / cancel）
- [x] 3.4 定义 `FragmentExit`、`FragmentStopReason`
- [x] 3.5 实现 `start_fragment(spec) -> FragmentHandle`：构建 FFmpeg TS 命令 → start_new_session → ProcessRegistry.register_started → 启动 monitor 线程
- [x] 3.6 monitor 为唯一完成者：wait returncode → registry.register_ended → FragmentRepository.complete → 设置 FragmentExit → enqueue 一次事件
- [x] 3.7 request_stop(reason) 仅发送 'q'/terminate/kill，不更新 Fragment/registry
- [x] 3.8 Lock + completed_event + callback_emitted 防重入
- [x] 3.9 通过 ProcessFactory、ProcessRegistry（协议）、Clock（协议）注入
- [x] 3.10 测试（FakeProcess）：正常启动→停止、异常 exit、超时 kill、重复停止幂等、回调仅触发一次
- [x] 3.11 迁移 `check_ffmpeg_available()` 到 `backend/app/camera/ffmpeg_utils.py`，更新所有 import

## 4. RecordingPolicy

- [x] 4.1 新增 `backend/app/camera/recording_policy.py`
- [x] 4.2 定义 `TrackRuntimeEvent`、`CaptureRuntimeSnapshot`、`CoordinatorAction`
- [x] 4.3 实现 StrictSyncPolicy / PreservePrimaryPolicy / IndependentPolicy
- [x] 4.4 实现 SingleTrackRestartPolicy（单轨退化：三种行为等价）
- [x] 4.5 重启预算：max_restart_attempts=5，退避 1s/2s/4s/8s/15s
- [x] 4.6 定时切片：max_fragment_duration_seconds=300，计划轮换不消耗 budget
- [x] 4.7 测试：纯函数策略，输入事件+快照 → 输出动作

## 5. CaptureRuntimeCoordinator

- [x] 5.1 新增 `backend/app/camera/capture_runtime_coordinator.py`
- [x] 5.2 start_tracks(tracks, policy)：每个 PreparedTrack 启动一个 TrackRecorder
- [x] 5.3 事件队列：TrackRecorder exit → enqueue → 控制线程消费 → Policy.decide → actions
- [x] 5.4 stop_tracks()：broadcast request_stop → 统一 wait 所有 handle
- [x] 5.5 维护 fragment_index（per-track）、rotation_index（全组）、restart_count
- [x] 5.6 返回 `CaptureRuntimeOutcome`（stopped_by_user、primary_track_lost、restart_budget_exhausted、warnings）
- [x] 5.7 测试：双轨→stop→两轨 completed、事件队列按序消费、restart budget 耗尽正确 outcome

## 6. CaptureFinalizer + CaptureCompletionService

- [x] 6.1 新增 `backend/app/camera/capture_finalizer.py`：`finalize_track(track_id) -> TrackFinalizationResult`
- [x] 6.2 按 take_start_offset_ms 排序有效 Fragment（completed + interrupted 但可读）
- [x] 6.3 生成 ffmpeg concat manifest → concat 到临时 MP4
- [x] 6.4 ffprobe 校验（returncode=0 + 文件 > 0 + 可读）→ 校验成功后 os.replace 到最终路径
- [x] 6.5 记录 TrackFinalization（manifest_hash、status、output_path、video_id）
- [x] 6.6 生成 TrackTimelineSpan[]（关联 track_finalization_id）
- [x] 6.7 幂等：manifest_hash 一致 + 输出存在 + ffprobe 成功 → 复用
- [x] 6.8 新增 `backend/app/camera/capture_completion_service.py`
- [x] 6.9 `complete_take(capture_take_id, outcome, results)` → 组合 RuntimeOutcome + TrackFinalizationResult[] → completed/partial/failed
- [x] 6.10 主分析轨失败 → failed；主轨成功+辅轨失败 → partial；全成功 → completed
- [x] 6.11 回写 Source Session 兼容字段（单摄 RecordingSession、双摄 SyncRecordingSession）+ 更新 CaptureTrack.video_id
- [x] 6.12 测试：正常合并 → MP4 可播放、合并失败不伪 completed、幂等重试

## 7. 双摄迁移

- [x] 7.1 SyncRecordingService.start_session()：CaptureStartCoordinator → TrackRecorder × 2 → Coordinator.start_tracks(StrictSyncPolicy)
- [x] 7.2 SyncRecordingService.stop_session()：Coordinator.stop_tracks → Finalizer × 2 → CompletionService → 回写 SyncRecordingSession 兼容字段
- [x] 7.3 SyncRecordingService.cancel_session()：Coordinator.stop_tracks → Fragment discarded → CleanupService
- [x] 7.4 现有双摄行为测试全部通过

## 8. 单摄迁移

- [x] 8.1 SessionService.start_session()：CaptureStartCoordinator → TrackRecorder × 1 → Coordinator.start_tracks(SingleTrackRestartPolicy)
- [x] 8.2 SessionService.stop_session()：Coordinator.stop_tracks → Finalizer × 1 → CompletionService → 回写 RecordingSession 兼容字段
- [x] 8.3 SessionService.cancel_session()：Coordinator.stop_tracks → Fragment discarded → CleanupService
- [x] 8.4 单摄 FFmpeg 异常退出后可在重启预算内启动新 Fragment
- [x] 8.5 现有单摄行为测试全部通过

## 9. Preflight 适配

- [x] 9.1 实现 `InMemoryFragmentRepository` + `NullProcessRegistry`
- [x] 9.2 双摄短录测试改为 TrackRecorder × 2 + InMemoryFragmentRepository（不创建正式 CaptureTake）
- [x] 9.3 测试：Preflight Fragment 不进入正式 MediaFragment 表

## 10. 恢复与 reconciliation

- [x] 10.1 启动恢复：扫描 ended_at IS NULL 的 registry → 校验 PID/PGID/fingerprint → 清理孤儿 → MediaFragment 标记 interrupted
- [x] 10.2 ffprobe 检测 interrupted Fragment 可恢复性
- [x] 10.3 release 关联 CameraLease
- [x] 10.4 支持幂等调用 CaptureCompletionService 完成 recovery

## 11. CleanupService 扩展

- [x] 11.1 按依赖顺序：TrackTimelineSpan → TrackFinalization → MediaFragment → CaptureTrack
- [x] 11.2 删除 TS 片段文件、concat manifest、临时 MP4、最终 MP4
- [x] 11.3 cancel 标记 discarded 后统一交给 CleanupService

## 12. 删除旧核心

- [x] 12.1 降级 `Recorder` 为 TrackRecorder 适配器（或直接删除）
- [x] 12.2 删除 `SyncRecorder._record_segment_for_stream()` / `_merge_segments()` / processes / failure_event
- [x] 12.3 删除 SessionService 中私有 registry 调用
- [x] 12.4 迁移 check_ffmpeg_available import 到 ffmpeg_utils.py
- [x] 12.5 确认无其他模块引用旧 recorder.py

## 13. 构建与验证

- [x] 13.1 `pytest backend/tests/` 全量通过
- [x] 13.2 `npm run build` + `npm run test` 前端无回归
- [x] 13.3 单摄端到端：start → 断流 → 重启 → stop → 合并 MP4 可播放
- [x] 13.4 双摄端到端：start → cam_2 断流 → 策略行为正确 → stop → 两路 MP4
- [x] 13.5 TrackTimelineMap 可查询（get_track_timeline_map / map_take_time_to_output_time）
- [x] 13.6 Finalizer 幂等：重复执行不报错不覆写
- [x] 13.7 cancel 后无残留分析入口
- [x] 13.8 前端录制流程无回归
