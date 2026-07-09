## 1. 后端 slot key + 兼容层

- [x] 1.1 将 `CameraSlotRole` 字面量从 `"primary" | "secondary"` 改为 `"cam_1" | "cam_2"`
- [x] 1.2 将 `SyncStartRequest` 中 `primary_camera_id`/`secondary_camera_id` 改为 `cam_1_id`/`cam_2_id`，`primary_angle`/`secondary_angle` 改为 `cam_1_angle`/`cam_2_angle`，默认值统一为 `baseline_high`
- [x] 1.3 在 `SyncStartRequest` 中临时兼容旧字段 `primary_camera_id`/`secondary_camera_id`（用 validator 或 manual mapping），确保前端改完前不 422
- [x] 1.4 将 `CameraSlotConfig.role`、`SyncSegmentFile.role` 等字段全面切换为 `cam_1`/`cam_2`
- [x] 1.5 将 `SyncRecordingService` 中所有 `primary`/`secondary` 字符串引用替换为 `cam_1`/`cam_2`
- [x] 1.6 在 `SyncRecordingSession._load()` 读取层加旧 JSON 兼容映射：`camera_slots.primary → cam_1`、`camera_slots.secondary → cam_2`
- [x] 1.7 将 `SyncStopResponse` 中 `primary_video_id` 改为 `default_analysis_video_id`，"主机位"文案改为"默认分析视频/底线机位 A 视频"
- [x] 1.8 将 `routes_sync_recording.py` 中请求模型引用更新为新字段名

## 2. 首帧 URL 返回

- [x] 2.1 在 FastAPI 中挂载 `data/sync-recordings/tests/` 静态目录到 `/api/sync-recordings/test-frames/`
- [x] 2.2 修改 `SyncTestResult` 模型：新增 `cam_1.first_frame_url` / `cam_2.first_frame_url` 字段，后端直接拼接完整 URL（不暴露绝对路径）
- [x] 2.3 短录测试完成后构造 first_frame_url，替代原来的 `primary_first_frame_path` 等裸路径字段

## 3. 前端类型 + API client 同步

- [x] 3.1 将 `report.ts` 中 `SyncStartRequest`、`CameraSlotRole`、`CameraSlotConfig`、`SyncStopResponse` 改为 `cam_1`/`cam_2`
- [x] 3.2 将 `analysisClient.ts` 中 `startSyncRecording`、`runSyncTest` 参数更新为新字段名
- [x] 3.3 将 `CaptureConsolePage.tsx` 中 `selectedSlots`、`slotSelecting`、sessionStorage key 从 `primary`/`secondary` 改为 `cam_1`/`cam_2`
- [x] 3.4 将 `SlotCard` 组件标签从"主机位（底线高机位）/副机位（侧面机位）"改为"底线机位 A / 底线机位 B"

## 4. 双路预览

- [x] 4.1 修改 `CaptureConsolePage` 预览区布局，双摄模式下渲染两个并排预览 `<img>` 标签（各加载 `getCameraPreviewUrl(camId)`）
- [x] 4.2 每个预览区上方叠加摄像头名称（底线机位 A/B）和在线状态指示
- [x] 4.3 任一预览加载失败时展示重试按钮，不阻塞另一路预览

## 5. 首帧缩略图

- [x] 5.1 修改 `TestResultCard` 组件，当 `first_frame_url` 存在时渲染 `<img src={url}>` 标签
- [x] 5.2 首帧加载失败或不存在时展示占位提示「首帧不可用」

## 6. 双摄录制 Tab

- [x] 6.1 在 `App.tsx` 的任务页面（`/tasks`）新增「双摄录制」Tab
- [x] 6.2 Tab 内容调用 `listSyncRecordings()` 获取数据
- [x] 6.3 实现 `SyncRecordingTaskCard` 组件：底线机位 A/B 视频、录制时长、分段数、重启次数、状态、默认分析视频入口（全文不出现"主机位"）
- [x] 6.4 按 Field Session 分组展示双摄录制卡片

## 7. 测试更新与清理

- [x] 7.1 更新 `test_sync_recording.py` 中所有 `primary`/`secondary` 断言为 `cam_1`/`cam_2`
- [x] 7.2 更新 `dualCameraCapture.test.ts` 中所有 slot key 断言
- [x] 7.3 新增前端测试覆盖双摄 Task Card 渲染和首帧展示逻辑
- [x] 7.4 全局搜索残留 `primary`/`secondary`、`主机位`/`副机位` 文案并清理
- [x] 7.5 移除 `SyncStartRequest` 中对旧字段 `primary_camera_id`/`secondary_camera_id` 的临时兼容
- [x] 7.6 运行全量测试和 TypeScript 编译验证
