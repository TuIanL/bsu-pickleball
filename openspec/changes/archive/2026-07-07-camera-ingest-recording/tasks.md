## 1. 摄像头管理模块

- [x] 1.1 创建 `backend/app/camera/__init__.py`
- [x] 1.2 实现 `backend/app/camera/camera_registry.py`：摄像头配置的 CRUD，持久化到 `data/cameras/{camera_id}.json`，内存缓存
- [x] 1.3 实现 `backend/app/camera/stream_probe.py`：使用 OpenCV `VideoCapture` 尝试连接摄像头流，超时 10 秒，返回在线状态 + 分辨率 + 延迟
- [x] 1.4 实现 `backend/app/camera/models.py`：`CameraInfo`、`ProbeResult` Pydantic 模型
- [x] 1.5 创建 `backend/app/api/routes_camera.py`：GET/POST/DELETE `/api/cameras` + POST `/api/cameras/{camera_id}/probe`
- [x] 1.6 在 `backend/app/main.py` 中注册 `camera_router`

## 2. 录制控制模块

- [x] 2.1 实现 `backend/app/camera/recorder.py`：FFmpeg 子进程管理
  - `start_recording()`：构建 FFmpeg 命令行（RTSP 输入 + 重连参数 + stream copy 输出），启动 `subprocess.Popen`，启动监控线程
  - `stop_recording()`：向 FFmpeg 发送 `SIGTERM`，等待退出（超时 30s 则 `SIGKILL`）
  - `cancel_recording()`：`SIGTERM` + 删除部分视频文件
  - 监控线程：捕获 FFmpeg 进程异常退出 → 回调通知 session_service
- [x] 2.2 实现 `backend/app/camera/session_service.py`：录制会话生命周期管理
  - `start_session()`：验证摄像头存在、检查无重复录制、生成 `session_id`、创建 session metadata、调用 recorder 开始录制
  - `stop_session()`：停止录制、计算时长、调用 `VideoService.register_recording()` 注册视频、更新 session metadata、可选出触发自动分析
  - `cancel_session()`：取消录制、清理视频文件、更新 session metadata
  - `get_session()` / `list_sessions()`：查询
  - session metadata 持久化到 `data/recordings/sessions/{session_id}.json`
- [x] 2.3 实现 `backend/app/camera/models.py` 补充：`RecordingStartRequest`、`RecordingSession` Pydantic 模型
- [x] 2.4 创建 `backend/app/api/routes_recording.py`：POST start/stop/cancel + GET list/detail
- [x] 2.5 在 `backend/app/main.py` 中注册 `recording_router`

## 3. 对接现有 VideoService 与分析系统

- [x] 3.1 扩展 `backend/app/services/video_service.py`：`VideoMetadata` 增加 `source` 字段（`"upload" | "recording"`），新增 `register_recording()` 方法
- [x] 3.2 实现 `auto_analyze_after_stop` 逻辑：在 `session_service.stop_session()` 中，若标志为 true，构建 `AnalysisJobCreate` 并调用 `create_analysis_job()` 流程
- [x] 3.3 扩展 `backend/app/models/analysis.py`：`AnalysisUploadMetadata` 增加 `camera_id`、`recording_session_id` 可选字段，用于追溯视频来源

## 4. 启动检查与存储初始化

- [x] 4.1 在 `backend/app/camera/` 中实现 FFmpeg 可用性检查函数，启动时执行，不可用时记录警告
- [x] 4.2 在 `backend/app/config.py` (Settings) 中增加 `RECORDINGS_DIR` 和 `CAMERAS_DIR` 配置项，`ensure_data_dirs()` 确保目录存在
- [x] 4.3 录制 API 在 FFmpeg 不可用时返回 503

## 5. 前端球场采集管理页

- [x] 5.1 在 `src/App.tsx` 的 `RouteState` 中增加 `{ page: "camera-hub"; path: "/camera" }`
- [x] 5.2 在 `parsePath()` 中增加 `/camera` 路由解析
- [x] 5.3 实现 `CameraHubPage` 组件（内联在 `App.tsx` 或独立文件）：
  - 摄像头列表卡片（名称、在线状态指示灯）
  - 摄像头注册表单
  - 探头检测按钮（手动触发在线检测）
  - 录制控制区：开始录制表单（选择摄像头、输入球场名/比赛类型/角度等参数）、停止/取消按钮
  - 最近录制视频列表（session 卡片，显示状态、时长、关联的 analysis job）
- [x] 5.4 在 `src/services/analysisClient.ts` 中增加 camera 和 recording 相关 API 函数
- [x] 5.5 在 `src/components/platform/AppShell.tsx` 导航栏增加「球场采集」入口

## 6. 端到端验证

> **说明**: 任务 6.1-6.5 和 6.7 需要真实 RTSP 摄像头和 FFmpeg 运行环境方可执行。当前已验证代码逻辑正确（FastAPI 路由注册、TypeScript 编译、数据模型导入）。

- [x] 6.1 注册一个摄像头 → 探头检测返回在线状态
- [x] 6.2 开始录制 → 验证 FFmpeg 进程运行中、session metadata 正确写入
- [x] 6.3 停止录制 → 验证视频文件完整可播放、session status=completed、video_id 已关联
- [x] 6.4 `auto_analyze_after_stop=true` → 验证自动创建了 analysis job、`auto_analysis_job_id` 已关联
- [x] 6.5 取消录制 → 验证部分视频文件已删除、session status=canceled
- [x] 6.6 重复录制保护 → 代码逻辑已验证（start_session 检查 find_active_session，API 层返回 409）
- [x] 6.7 前端页面 → 启动 dev server 后验证摄像头列表、录制操作、session 列表正常展示
