## Context

首版双摄同步录制（`add-dual-camera-sync-recording`，已归档）沿用了师哥独立脚本的三摄设计痕迹，将两路摄像头标记为 `primary`（主机位，底线高）和 `secondary`（副机位，侧面）。实际现场两个摄像头均为底线高机位，不存在主副关系。此外，控制台只有一个预览窗口、短录测试不展示首帧图、双摄录制在任务列表完全不可见——四处在现场验证后暴露的问题。

## Goals / Non-Goals

**Goals:**
- 将 slot key 从 `primary`/`secondary` 重命名为 `cam_1`/`cam_2`，标签改为"底线机位 A/B"，默认角度统一为 `baseline_high`，并清除全文"主机位/副机位"残余文案
- 双摄控制台预览区显示两路并排 MJPEG 实时画面
- 短录测试结果卡片展示两路首帧缩略图（后端直接返回 `first_frame_url`，前端不接触文件路径）
- 任务列表新增「双摄录制」Tab，展示同步录制会话

**Non-Goals:**
- 不合并单摄和双摄录制到同一个 Tab（数据结构差异大，合并增加复杂度）
- 不在双摄预览中做画中画或切换模式
- 不做旧 JSON 的正式迁移脚本（仅加读取层兼容映射）

## Decisions

### D1: slot key 全面重命名为 `cam_1`/`cam_2`，读取层加最小兼容

涉及范围：后端 `CameraSlotRole` 字面量、`CameraSlotConfig.role`、`SyncStartRequest` 字段名、`SyncSegmentFile.role`；前端 `SlotPair` 类型、`selectedSlots` 状态、`slotSelecting` 状态、sessionStorage key 前缀、所有 UI 标签文案。

**兼容层**：在 `SyncRecordingSession` 的读取路径（`_load` 方法）中加一次简单的 key 映射：
```
camera_slots.primary → camera_slots.cam_1
camera_slots.secondary → camera_slots.cam_2
```
不做正式迁移脚本，不处理 segments 内的子字段。目的只有一个：**避免残留旧 JSON 导致任务页整个 Tab 加载崩溃**。

替代方案：保留 `primary`/`secondary` 但改标签文案。否决——语义本身就暗示了主副关系，后续维护者容易误读。

### D2: 双路预览用两个独立 `<img>` 并排

```
当前（单摄）:                      双摄:
┌──────────────────────────┐    ┌──────────┐ ┌──────────┐
│                          │    │ 预览 A   │ │ 预览 B   │
│    单个大预览             │    │ (cam_1)  │ │ (cam_2)  │
│                          │    │          │ │          │
└──────────────────────────┘    └──────────┘ └──────────┘
```

两个 `<img>` 各自加载 `getCameraPreviewUrl(camId)` 返回的 MJPEG 流。每个预览区上方叠加摄像头名称标签（底线机位 A/B）和在线状态指示。

替代方案：复用单摄大预览 + 右上角画中画。否决——两个都是平等摄像头，不应有主次视觉差异。

### D3: 首帧 URL 由后端直接返回，前端只负责渲染

测试 API 响应新增 `first_frame_url` 字段：

```json
{
  "cam_1": {
    "first_frame_url": "/api/sync-recordings/test-frames/xxx/cam_a_first_frame.jpg",
    "first_frame_exists": true
  },
  "cam_2": { ... }
}
```

后端 mount `data/sync-recordings/tests/` 到 `/api/sync-recordings/test-frames/`，在响应中拼接完整 URL。前端只做 `<img src={result.cam_1.first_frame_url}>`，不接触、不知晓服务端文件系统路径。

替代方案 A：用 Base64 编码首帧嵌在 JSON 响应中。否决——图片体积不可控，增加 API 延迟。
替代方案 B：返回绝对路径让前端拼接。否决——前端不应知悉服务端目录结构，以后改存储对象时维护成本高。

### D4: 双摄录制 Tab 作为独立 Tab 插入 `/tasks` 页面

在现有「上传视频任务」和「录制视频任务」Tab 之后新增「双摄录制」Tab，调用 `listSyncRecordings()` API。

卡片展示内容（全文不出现"主机位"）：
- 底线机位 A 视频、底线机位 B 视频
- 录制时长、分段数、重启次数
- 状态标签（completed/failed/canceled）
- 默认分析视频入口（如果可用）
- 点击卡片跳转到对应 Field Session 采集控制台

替代方案：合并到「录制视频任务」Tab。否决——`RecordingSession` 和 `SyncRecordingSession` 字段差异大，混合展示需大量条件逻辑。

### D5: 首帧展示为过渡期功能

用户明确前期需要看到首帧图方便调试，后期只需通过/失败标识。本次 change 不引入开关机制，`TestResultCard` 中将首帧 `<img>` 渲染为默认行为。后续隐藏只需删掉 `<img>` 标签，改动量极小。

## Risks / Trade-offs

- [Risk] slot key 变更导致旧会话 JSON 字段不兼容 → Mitigation：读取层加 `primary→cam_1`/`secondary→cam_2` 兼容映射，避免任务页崩溃；旧数据量极少（<5 条），即使映射失效也仅影响极少条目。
- [Risk] `SyncStartRequest` 字段名 `cam_1_id`/`cam_2_id` 是 API contract 变更，前后端同时改可能导致衔接断裂 → Mitigation：后端先支持新字段 + 临时兼容旧字段 → 前端改调用 → 确认无残留后移除旧字段兼容。
- [Risk] 双路 MJPEG 预览同时加载两路流，带宽翻倍 → Mitigation：MJPEG 预览仅在用户可见时加载，切换 Tab 或离开页面时自动断开。
- [Risk] 首帧 static serve 路径暴露文件系统结构 → Mitigation：挂载点限定在 `data/sync-recordings/tests/`，前端仅使用后端返回的 URL，不自行拼接路径。

## Migration Plan

```
1. 后端先支持 cam_1/cam_2，加 old→new key 兼容映射，临时兼容 primary_camera_id/secondary_camera_id 请求字段
2. 前端类型和 API client 改为 cam_1/cam_2
3. 改 CaptureConsolePage 的 slot 状态、标签文案和 sessionStorage key
4. 做双路并排预览
5. 做首帧 static serve + SyncTestResult 新增 first_frame_url
6. 做 TestResultCard 首帧展示
7. 做 /tasks 双摄录制 Tab + SyncRecordingTaskCard
8. 最后统一测试、删除明显旧文案和临时兼容字段
```

原则：先保证数据契约稳定，再做 UI；先控制台可用，再做任务列表可见。

## Open Questions

- 分析流程目前只能取一路视频做分析，称其为"默认分析视频"而非"主机位视频"是否够清晰？
- 不需要首帧图时，删 `<img>` 标签即可，不需要额外的 toggle 逻辑。
