## Context

项目已有完整的分析任务系统（`AnalysisWorkerRuntime` + `JobStore` + `AnalysisPipeline`），但视频来源仅支持手动上传。需要在不动摇现有架构的前提下，增加"摄像头实时录制 → 自动提交分析"的入口链路。

## Goals / Non-Goals

**Goals:**
- 提供独立的摄像头管理模块，支持注册、查询、在线探测
- 提供录制会话的完整生命周期控制（开始/停止/取消）
- 录制停止后自动保存视频文件并持久化 session metadata
- `auto_analyze_after_stop=true` 时，自动创建分析 Job 并进入现有 Worker 队列
- 前端提供球场采集管理页面，支持基础录制操作

**Non-Goals:**
- 不做实时流预览（后续阶段）
- 不做多路同时录制（后续阶段）
- 不做录制时长限制或自动分段
- 不修改现有分析 Pipeline 的内部逻辑
- 不引入数据库——沿用项目现有的 JSON 文件持久化模式

## Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 录制引擎 | FFmpeg 子进程 | 内置 RTSP 断线重连（`-reconnect 1`），支持 stream copy 避免重编码，资源占用低 |
| 探头检测 | OpenCV `VideoCapture` 抓单帧 | 轻量，项目已有 opencv-python 依赖，不需要额外进程 |
| Session 状态机 | `recording → completed / failed / canceled` | 与现有 Job 状态机（`queued → running → succeeded/failed/canceled`）平行但独立，语义清晰 |
| 视频存储 | 统一走 `VideoService`，新增 `source: "upload" | "recording"` | 录制视频和上传视频在同一体系管理，现有 Job 创建流程（需要 `videoId`）可直接消费 |
| 相机信息持久化 | `data/cameras/{camera_id}.json` | 与项目现有 JSON 文件模式一致，不引入 SQLite |
| Session metadata 持久化 | `data/recordings/sessions/{session_id}.json` | 与 Job 存储模式一致 |
| Camera ID | 用户自定义简短标识符 | 当前测试阶段只需区分不同摄像头，不做球场语义绑定 |
| FFmpeg 安装 | 系统级依赖，启动时做可用性检查 | 与 MMPose 的依赖检查模式一致，清晰报错 |

## Session 状态机

```
POST /api/recordings/start
        │
        ▼
┌──────────────┐
│  recording   │ ◀── FFmpeg 子进程运行中
└──────┬───────┘
       │
  ┌────┼────┐
  ▼    ▼    ▼
┌────┐┌────┐┌────┐
│com-││fai-││can-│
│ple-││led ││cel-│
│ted ││    ││ed  │
└──┬─┘└────┘└────┘
   │
   ▼
┌───────────────┐
│ auto_analysis │  ◀── 仅当 auto_analyze_after_stop=true
│  _triggered   │      且 status=completed
└───────────────┘
```

- **recording → completed**: 用户调用 `/stop`，FFmpeg 正常退出，视频文件完整
- **recording → failed**: FFmpeg 进程异常退出（流断开超过重连容忍时间），部分视频可能可用
- **recording → canceled**: 用户调用 `/cancel`，FFmpeg 被 SIGTERM，视频文件丢弃或标记为不完整
- `completed` + `failed` 是终态，不可再转换

## API 设计

### Cameras

```
GET    /api/cameras                     → list[CameraInfo]
POST   /api/cameras                     → CameraInfo
DELETE /api/cameras/{camera_id}         → { deleted: true }
POST   /api/cameras/{camera_id}/probe   → ProbeResult
```

`POST /api/cameras` 请求体：
```json
{
  "camera_id": "baseline-cam",
  "name": "底线高角度摄像头",
  "stream_url": "rtsp://192.168.1.101:554/stream",
  "protocol": "rtsp",
  "username": "admin",
  "password": "***"
}
```

`ProbeResult`：
```json
{
  "camera_id": "baseline-cam",
  "online": true,
  "latency_ms": 245,
  "resolution": "1920x1080",
  "detected_at": "2026-07-05T14:30:00Z"
}
```

### Recordings

```
POST   /api/recordings/start            → RecordingSession
POST   /api/recordings/{session_id}/stop    → RecordingSession
POST   /api/recordings/{session_id}/cancel  → RecordingSession
GET    /api/recordings                      → list[RecordingSession]
GET    /api/recordings/{session_id}         → RecordingSession
```

`POST /api/recordings/start` 请求体：
```json
{
  "camera_id": "baseline-cam",
  "court_name": "北体匹克球场",
  "match_format": "doubles",
  "camera_angle": "baseline_high",
  "fps": 60,
  "resolution": "1920x1080",
  "auto_analyze_after_stop": true
}
```

`RecordingSession` 响应：
```json
{
  "session_id": "rec_20260705_143000",
  "camera_id": "baseline-cam",
  "court_name": "北体匹克球场",
  "match_format": "doubles",
  "camera_angle": "baseline_high",
  "fps": 60,
  "resolution": "1920x1080",
  "auto_analyze_after_stop": true,
  "status": "recording",
  "started_at": "2026-07-05T14:30:00Z",
  "stopped_at": null,
  "duration_sec": null,
  "video_path": null,
  "video_id": null,
  "auto_analysis_job_id": null,
  "error_message": null
}
```

## 对接现有 Job 系统

```
session_service.stop(session_id)
  │
  ├─▶ FFmpeg SIGTERM → 等待进程退出 → 视频文件就绪
  │
  ├─▶ VideoService.register_recording(
  │      file_path=...,
  │      source="recording",
  │      metadata={...}
  │    )
  │    → 返回 video_id
  │
  ├─▶ 更新 session: status=completed, video_path, video_id
  │
  └─▶ if auto_analyze_after_stop:
        create_analysis_job(
          AnalysisJobCreate(
            videoId=video_id,
            metadata=AnalysisUploadMetadata(
              court_name=session.court_name,
              match_format=session.match_format,
              ...
            )
          )
        )
```

关键点：`VideoService.register_recording()` 是现有 `VideoService.save_upload()` 的新兄弟方法。它共享相同的 `VideoMetadata` 模型（扩展 `source` 字段），使录制视频和上传视频在同一个命名空间中。

## Risks / Trade-offs

- **FFmpeg 子进程管理**：进程异常退出时需要正确捕获并更新 session 状态。使用 `subprocess.Popen` + 独立线程监控返回码。
- **长录制会话**：单次录制可能持续数十分钟，FFmpeg 以 stream copy 模式运行时 CPU 开销很低，但需要确保磁盘空间充足。后续可增加磁盘空间检查。
- **流断开处理**：FFmpeg `-reconnect 1` 可处理短暂断连，但长时间断开会导致录制卡住。设置合理的 `-reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 30` 参数。
- **并发录制**：当前阶段不支持多路同时录制，`session_service` 内通过检查是否存在 `recording` 状态的 session 来防止重复启动。

## Open Questions

无。所有设计决策已在探索阶段确认。
