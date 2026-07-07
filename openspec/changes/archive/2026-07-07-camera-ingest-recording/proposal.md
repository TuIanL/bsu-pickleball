## Why

目前系统只支持手动上传视频 → 手动创建分析任务，适合演示场景但不适合球场实地部署。在球场边，用户需要的是"点击开始录制 → 点击停止录制"，系统自动生成视频文件并自动提交分析任务。需要建立从摄像头采集到分析任务触发的完整链路的第一阶段。

## What Changes

### 新增模块
- **`backend/app/camera/`** — 独立的摄像头采集模块（`camera_registry.py` / `stream_probe.py` / `recorder.py` / `session_service.py`）
- **`backend/app/api/routes_camera.py`** — 摄像头管理 API（CRUD + 探头检测）
- **`backend/app/api/routes_recording.py`** — 录制控制 API（开始/停止/取消/查询）
- **前端「球场采集管理」页面** — 摄像头在线状态、开始录制、停止录制、查看最近录制视频

### 对接现有系统
- 录制停止后，通过 `VideoService` 注册录制视频（扩展 `source` 字段区分"上传"与"录制"）
- `auto_analyze_after_stop=true` 时，自动调用现有 `POST /api/analysis/jobs` 创建分析任务
- 复用现有 `AnalysisWorkerRuntime` 异步执行分析

### 关键设计决策
- **FFmpeg 子进程**做主录制（内置 RTSP 断线重连），**OpenCV** 做探头帧抓取
- Recording Session 独立状态机：`recording → completed/failed/canceled`
- 录制视频统一走 `VideoService` 管理，扩展 `source` 字段
- Camera registry 只存连接信息，不存球场语义（当前测试阶段只需区分不同摄像头）

## Capabilities

### New Capabilities
- `camera-ingest-management`: 摄像头注册、在线探测、连接信息管理
- `recording-session-control`: 录制会话的完整生命周期控制（开始/停止/取消/查询）

### Modified Capabilities
- `video-analysis-job-flow`: 补充"录制完成后自动创建分析任务"的触发路径
- `analysis-job-orchestration`: 补充录制视频来源的 Job 创建集成点

## Impact

- **新增目录**: `backend/app/camera/`
- **新增 API 路由**: `/api/cameras` (3 endpoints), `/api/recordings` (5 endpoints)
- **新增前端页面**: CameraHubPage (`/camera`)
- **修改文件**: `backend/app/services/video_service.py`（扩展 `source` 字段）, `backend/app/main.py`（注册新路由）
- **依赖**: FFmpeg（系统级）、opencv-python（已存在）
- **存储**: `data/recordings/{date}/{camera_id}/` 存放录制视频文件，`data/recordings/sessions/` 存放 session metadata JSON
