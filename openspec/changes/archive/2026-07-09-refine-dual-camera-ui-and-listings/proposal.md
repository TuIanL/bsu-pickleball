## Why

双摄同步录制功能已完成首版移植，但现场使用暴露出三个设计偏差和一个功能缺陷：
1. 两个摄像头同是底线高机位，却被标记为 `primary`/`secondary`，标签暗示了不存在的层级关系；
2. 双摄控制台只有一个预览窗口，无法同时观察两路画面——现场根本无法判断另一台是否偏了、黑屏或角度不对；
3. 短录测试只返回文字结果，看不见首帧画面，开发期调试效率低；
4. 双摄录制完成后在任务列表完全不可见——`/tasks` 页面只查询单摄 `listRecordings()`，双摄数据烂在磁盘上。

这不是锦上添花的 UI 微调，而是把首版双摄录制从"能跑"推进到"现场真的可用"的修正型 change。

## What Changes

- **机位重命名**：后端 slot key 从 `primary`/`secondary` 改为 `cam_1`/`cam_2`，前端标签从"主机位（底线高机位）/副机位（侧面机位）"改为"底线机位 A/底线机位 B"，默认角度统一为 `baseline_high`。**BREAKING**：已落盘的旧 JSON 中 `camera_slots` key 不兼容，但会在读取层加最小兼容（`primary→cam_1`、`secondary→cam_2`），避免任务页因残留旧数据崩溃。
- **双路并排预览**：双摄模式下预览区改为左右两栏，各用一个独立 `<img>` 加载对应摄像头的 MJPEG 流，上方叠加机位名称标签和在线状态指示。
- **短录首帧展示**：测试 API 响应中新增 `first_frame_url` 字段，后端直接返回可访问的 HTTP URL（通过 static serve 端点提供），前端只需 `<img src={url}>` 渲染，不接触服务端文件路径。
- **双摄录制 Tab**：在 `/tasks` 页面新增第三个 Tab「双摄录制」，调用 `listSyncRecordings()`，用 `SyncRecordingTaskCard` 展示两路视频信息、分段数、重启次数和状态，卡片中不再使用"主机位"称谓，统一为"底线机位 A 视频/底线机位 B 视频"或"默认分析视频"。

## Capabilities

### New Capabilities
- `sync-recording-task-listing`: 在任务列表页面展示已完成的双摄同步录制会话，支持按 Field Session 分组、查看分段摘要和总重启次数。

### Modified Capabilities
- `dual-camera-sync-recording`: 机位 slot key 改为 `cam_1`/`cam_2`，标签改为"底线机位 A/B"，默认角度统一为 `baseline_high`；短录测试结果新增 `first_frame_url` 字段，去除"主机位/副机位"语义。
- `capture-workflow`: 双摄控制台预览区改为并排双路 MJPEG 预览。
- `device-drawer`: 机位槽位卡片标签和选择交互适配新的 `cam_1`/`cam_2` 命名。

## Impact

- 后端：`CameraSlotRole` 字面量、`SyncStartRequest` 字段名、`SyncStopResponse` 中"主机位"语义全面替换为平等机位命名；新增 `first_frame_url` 字段和首帧 static serve 端点；旧 JSON 读取层加 `primary→cam_1`/`secondary→cam_2` 兼容映射。
- 前端：`CaptureConsolePage.tsx` 预览布局从单图改为双图并排，`SlotCard` 标签改为"底线机位 A/B"，`TestResultCard` 增加首帧 `<img>` 展示；`App.tsx` 新增「双摄录制」Tab 和 `SyncRecordingTaskCard` 组件（两路视频信息、分段摘要、状态标签，不再出现"主机位"文案）。
- 存储：旧 `data/sync-recordings/sessions/*.json` 读取时自动做 key 映射，不强制手动迁移。
- 测试：更新双摄相关单元测试中的 slot key 断言；新增双摄任务列表渲染测试。
