# 拍动视析 — 匹克球运动表现智能分析平台

基于视觉捕捉与 TENG-IMU 智能球拍的匹克球全维度分析平台，定位为**真实运行的视频分析产品**，同时作为大创竞赛项目的**科研实验平台**。

主流程：用户上传比赛视频 → 标定场地 → 创建分析任务 → 后台 Worker 执行视觉分析 → 输出 JSON 报告 + 视频 Overlay + 阶段遥测 → 前端展示数据看板与训练建议。

## 功能概览

- **视频上传与场地标定**：支持上传比赛视频，通过点选四角完成球场单应性标定（支持手工/自动/半自动三种模式）。
- **球员检测与跟踪**：基于 YOLO11 人体检测 + 多目标跟踪 + 脚点估计 + 球场坐标投影，锁定主球员并维持跨帧身份稳定。
- **姿态估计**：可选启用 RTMPose26（26 关键点）推理，生成骨架叠加可视化。
- **运动指标计算**：移动距离、速度、厨房区停留、双打间距、热力图等匹克球专项指标。
- **球轨迹分析**：球检测、轨迹跟踪、弹跳事件识别（实验性；模型缺失或运行失败时明确标记为 unavailable/failed，不伪造球路）。
- **发球检测**：基于站位/静止/运动峰值/回合线索的上下文发球时刻识别。
- **摄像头录制与双摄同步**：支持实时摄像头预览、单/双摄录制、时间轴事件标记、实时编码计分、场次管理、片段编辑。
- **分析报告**：前端展示视频叠加回放、散点图/热力图、指标卡、诊断结论与训练建议。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, D3.js（热力图/散点图）, lucide-react（图标） |
| 后端 | Python 3.13+, FastAPI, Uvicorn, SQLAlchemy 2（SQLite）, Pydantic 2 |
| 视觉算法 | OpenCV 4.10+, YOLO11（人体检测）, RTMPose26（姿态估计）, 单应性矩阵（球场投影） |
| 测试 | Vitest（前端）, pytest + httpx（后端） |

## 快速开��

### 环境要求

- **前端**：Node.js >= 20，npm >= 10
- **后端**：Python >= 3.13，pip，FFmpeg（录制功能需要）

### 安装

```bash
# 克隆仓库并进入目录
cd pre-pickleball

# 安装前端依赖
npm install

# 安装后端依赖
python3.13 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

# 安装模型权重文件到 models/ 目录
#   - YOLO11n: models/yolo11n.pt（自动下载）
#   - RTMPose: models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth
#   - 球场线分割（可选）: models/court-line/best.pt
```

### 启动

```bash
# 一键同时启动后端 + 前端
npm run app:start

# 或分别启动
npm run dev          # 仅前端（localhost:5173）
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000   # 仅后端

# 停止
npm run app:stop
```

启动后访问 `http://localhost:5173` 即可使用。

macOS 用户也可使用根目录的便捷脚本双击启动/停止：
- `start-pickleball.command`
- `stop-pickleball.command`

### 配置

后端所有配置通过 `PICKLEBALL_` 前缀的环境变量覆盖，默认值定义在 `backend/app/core/config.py`。常用配置项：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `PICKLEBALL_BACKEND_PORT` | 后端端口 | 8000 |
| `PICKLEBALL_DATA_DIR` | 数据目录 | data |
| `PICKLEBALL_ENABLE_POSE_INFERENCE` | 启用姿态推理 | 自动检测模型是否存在 |
| `PICKLEBALL_ANALYSIS_WORKER_MODE` | Worker 模式：`external` / `embedded` | external（本地脚本） |
| `PICKLEBALL_ANALYSIS_WORKER_HEARTBEAT_INTERVAL_SECONDS` | Worker 心跳间隔 | 5 |
| `PICKLEBALL_ANALYSIS_WORKER_HEARTBEAT_TIMEOUT_SECONDS` | 任务失联判定阈值 | 30 |
| `PICKLEBALL_ANALYSIS_CONTROL_DATABASE_PATH` | 分析控制面 SQLite 路径 | data/analysis_control.sqlite3 |

完整配置项列表见 `backend/app/core/config.py` 中的 `Settings` 类。

`npm run app:start` 默认启动三个独立运行单元：API（支持 reload）、analysis-worker
和 Vite 前端。PID 文件位于 `.runtime/pids/`，日志位于 `.runtime/logs/`；API reload
不会重启 Worker。若 Worker 进程异常退出，服务重启或下一次任务查询会将超过 heartbeat
阈值的 `processing` 任务标记为“任务失联”，前端会停止轮询并提供“重新分析”入口。

### 构建

```bash
npm run build     # TypeScript 编译 + Vite 打包 → dist/
npm run preview   # 预览构建产物
```

### 测试

```bash
npm test                                # 前端测试（vitest）
cd backend && python -m pytest          # 后端测试（pytest）
```

## 项目结构

```
pre-pickleball/
├── backend/                          # Python 后端
│   ├── app/
│   │   ├── main.py                   # FastAPI 入口：CORS、路由注册、Worker 启停
│   │   ├── api/                      # API 路由（14 个路由模块）
│   │   │   ├── routes_video.py       # 视频上传、元数据、流播放
│   │   │   ├── routes_calibration.py # 球场标定（手工/自动/半自动）
│   │   │   ├── routes_analysis.py    # 分析任务创建/查询/取消/结果
│   │   │   ├── routes_camera.py      # 摄像头登记/探测/预览
│   │   │   ├── routes_recording.py   # 录制控制（开始/停止/取消）
│   │   │   ├── routes_sync_recording.py # 双摄同步录制
│   │   │   ├── routes_field_sessions.py # 场次管理
│   │   │   ├── routes_timeline_events.py # 时间轴事件 CRUD
│   │   │   ├── routes_coding_actions.py  # 实时编码控制台
│   │   │   ├── routes_segment_editing.py # 片段编辑与批量分析
│   │   │   ├── routes_storage.py    # 本地存储管理
│   │   │   └── routes_vidat.py      # Vidat 标注工作台
│   │   ├── services/                 # 业务逻辑层（24 个服务模块）
│   │   │   ├── analysis_pipeline.py  # 端到端视觉分析流水线
│   │   │   ├── mock_analysis.py      # 任务状态管理 + 后台 Worker
│   │   │   ├── job_orchestration.py  # 任务调度引擎（排队/取消/重试）
│   │   │   ├── calibration_service.py # 手工/半自动标定管理
│   │   │   ├── automatic_calibration_service.py # 自动标定建议
│   │   │   ├── capture_start_coordinator.py # 统一录制启动编排
│   │   │   ├── capture_archive_service.py # 录制数据归档
│   │   │   ├── capture_cleanup_service.py  # 录制资源统一清理
│   │   │   ├── coding_actions_service.py   # 编码命令处理
│   │   │   ├── scoring_fsm.py        # 计分状态机（hybrid_21/side_out）
│   │   │   └── vidat_annotation_service.py # Vidat 标注包生成
│   │   ├── vision/                   # 计算机视觉引擎（8 个子引擎，50+ 模块）
│   │   │   ├── courtvision_calibration_engine/ # 球场标定（几何/线分割/单应性/overlay）
│   │   │   ├── player_tracking_engine/ # 球员跟踪（检测/跟踪/脚点/投影/身份/锁定）
│   │   │   ├── pickleball_game_analysis/ # 比赛分析（球轨迹/弹跳/可视化/诊断）
│   │   │   ├── pickleball_performance_engine/ # 表现指标（距离/速度/区域/间距/热力图）
│   │   │   ├── detectors/            # 检测器适配器（YOLO/球/多目标）
│   │   │   ├── pose/                 # 姿态估计接口（RTMPose26）
│   │   │   ├── events/               # 事件检测（发球）
│   │   │   ├── court/                # 球场标定协议
│   │   │   └── action_classification_preprocessing/ # 动作分类预处理
│   │   ├── camera/                   # 摄像头与录制（18 个模块）
│   │   │   ├── camera_registry.py    # 摄像头配置注册表
│   │   │   ├── camera_lease_service.py # 录制资源租约管理
│   │   │   ├── recorder.py           # FFmpeg 子进程录制器
│   │   │   ├── sync_recorder_service.py # 双摄同步录制引擎
│   │   │   ├── capture_runtime_coordinator.py # 运行期轨道协调
│   │   │   ├── capture_finalizer.py  # 片段合并/校验
│   │   │   └── capture_recovery.py   # 孤儿进程恢复
│   │   ├── core/                     # 应用配置（config.py）+ 日志（logging.py）
│   │   ├── models/                   # SQLAlchemy ORM 模型（14 个）
│   │   ├── schemas/                  # Pydantic 数据契约（17 个）
│   │   └── database.py               # 数据库初始化
│   ├── scripts/                      # 独立脚本（11 个：数据集导出、模型训练、双摄标定等）
│   ├── tests/                        # pytest 测试（38 个）
│   ├── requirements.txt              # Python 依赖
│   └── data/                         # 本地数据目录（uploads/calibrations/outputs/recordings/tmp）
├── src/                              # React 前端
│   ├── main.tsx                      # 应用入口
│   ├── App.tsx                       # 根组件（路由状态 + 全局上下文）
│   ├── app/                          # 路由分发（AppRouter/router/navigationTypes）
│   ├── pages/                        # 页面组件（14 个）
│   │   ├── LandingPage.tsx           # 产品落地页
│   │   ├── NewAnalysisPage.tsx       # 新建分析（上传视频 → 标定 → 提交任务）
│   │   ├── AnalysisJobPage.tsx       # 分析任务进度
│   │   ├── AnalysisDetailsPage.tsx   # 分析详情（流水线结果 + 轨迹投影）
│   │   ├── ReportPage.tsx            # 运动表现报告
│   │   ├── CaptureHomePage.tsx       # 采集首页（场次列表）
│   │   ├── CaptureWizardPage.tsx     # 采集向导（逐步创建场次）
│   │   ├── CameraHubPage.tsx         # 摄像头管理
│   │   ├── CaptureConsolePage.tsx    # 录制控制台
│   │   ├── RecordingWorkspacePage.tsx # 录制工作台（回放 + 时间轴事件）
│   │   ├── SegmentManagerPage.tsx    # 片段管理器
│   │   ├── HardwarePage.tsx          # 智能球拍硬件介绍
│   │   ├── TrainingPage.tsx          # 训练建议首页
│   │   └── VisionPage.tsx            # 视觉工作台
│   ├── components/                   # UI 组件（30+ 个）
│   │   ├── platform/                 # 平台级组件（AppShell/AppSidebar/MetricCard/CourtMinimap/
│   │   │                            #   StructuredHeatmap/StructuredScatterPlot/ReportVisualization/
│   │   │                            #   VideoAnalysisCard/videoOverlayPlayback 等）
│   │   └── capture/                  # 录制控制台组件（CameraPreviewCard/RecordingControlPanel/
│   │                                #   CaptureWorkspaceLayout/EventActionToolbar 等）
│   ├── services/                     # 前端服务层（9 个：API 调用、数据适配、状态管理）
│   │   ├── analysisClient.ts         # 分析 API 客户端（真实失败可见；仅显式 demo 使用本地任务）
│   │   ├── pipelineReportAdapter.ts  # 流水线结果 → 报告格式适配
│   │   ├── captureAdapter.ts         # 录制会话适配器
│   │   └── codingOutbox.ts           # 编码命令 FIFO 发送队列
│   ├── hooks/                        # React Hooks（6 个：摄像头、录制、编码、采集状态）
│   ├── types/                        # TypeScript 类型定义
│   ├── utils/                        # 工具函数（球场几何、分析辅助）
│   └── data/                         # 品牌文案（productCopy.ts）、演示数据（demoData.ts）
├── models/                           # AI 模型权重与配置
│   ├── rtmpose/                      # RTMPose26 姿态估计模型
│   ├── court-line/                   # 球场线分割模型
│   └── ball/                         # 球检测模型
├── scripts/                          # Shell 启动/停止脚本
├── docs/                             # 设计文档
│   ├── system-architecture.md        # 系统架构（已迁移至根目录）
│   ├── court-line-calibration.md     # 球场线标定方法
│   ├── dual-camera-sync-recording.md # 双摄同步录制设计
│   ├── player-trajectory-identity-qa.md # 球员轨迹与身份 Q&A
│   ├── good-pickleball-visualization-migration.md # 可视化迁移方案
│   └── vidat-annotation-workbench.md # Vidat 标注工作台
├── competition-demo/                 # 竞赛演示页面（独立 HTML）
├── data/                             # 实验数据（视频/标定/输出/标注，不入版本管理）
├── datasets/                         # 数据集（图片/标注/COCO 格式，不入版本管理）
├── runs/                             # 训练产物（不入版本管理）
├── openspec/                         # OpenSpec 变更提案/规格记录
├── system-architecture.md            # 系统架构总览（Mermaid 流程图）
├── structure picture.md              # 模块关系与数据流（Mermaid 图表）
├── package.json                      # 前端依赖与 npm scripts
└── pyproject.toml                    # Python 项目元数据
```

## 核心业务流程

```
用户上传视频 → 点选四角标定场地 → 创建分析任务 → 进入本地队列
    ↓
Worker 执行视觉分析：
  帧读取 → YOLO 人体检测 → 主球员筛选 → 多目标跟踪 → 脚点估计
    → 球场坐标投影 → （可选）RTMPose26 姿态推理
    → 球检测/弹跳检测（实验性）
    → 指标计算（距离/速度/区域/间距/热力图/发球事件）
    → 输出 JSON report + 视频 Overlay + Stage telemetry
    ↓
前端展示：视频叠加回放 → 数据看板 → 运动报告 → 训练建议
```

详细架构与数据流参见：
- `system-architecture.md` — 运行时架构、视频分析数据流、流水线分层、模块对照表
- `structure picture.md` — 高层模块说明、产品/科研边界

## API 概览

后端运行在 `http://localhost:8000`，主要 API 端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/videos` | POST | 上传视频 |
| `/api/videos/{id}` | GET | 查询视频元数据 |
| `/api/videos/{id}/stream` | GET | 获取视频流 |
| `/calibration/manual` | POST | 手工标定场地 |
| `/api/calibrations` | GET | 查询标定列表 |
| `/api/analysis/jobs` | POST | 创建分析任务 |
| `/api/analysis/jobs/{id}` | GET | 查询任务状态与进度 |
| `/api/analysis/jobs/{id}/result` | GET | 获取分析结果 |
| `/api/analysis/jobs/{id}/report` | GET | 获取分析报告 |
| `/api/analysis/jobs/{id}/artifacts/{name}` | GET | 获取已生成的 JSON/视频 artifact；已知缺失产物返回 404 |
| `/api/analysis/jobs/{id}` | DELETE | 取消/删除任务 |
| `/api/cameras` | GET/POST | 摄像头管理 |
| `/api/recordings` | POST | 启动录制 |
| `/api/field-sessions` | GET/POST | 场次管理 |
| `/health` | GET | 健康检查 |

## 产品与科研边界

- **产品主流程**以真实上传视频为核心：上传 → 标定 → 分析 → 查看报���。
- Demo/sample 路径保留用于明确的离线演示，页面上下文中与真实任务区分；真实视频或真实 API 失败不会静默创建已完成 demo 任务。
- 分析任务列表规范入口为 `/analysis/tasks`，历史 `/tasks` 链接仍解析到同一页面；录制来源任务会保留 `recording_session_id` / `camera_slot` 归属字段。
- **当前真实结论聚焦**：人员检测、姿态叠加、轨迹投影、移动指标。
- **实验性功能**（不作为真实结论输出）：球追踪、弹跳检测、击球事件、回合分割、战术语义。
- **科研产出来自可复现记录**：输入/配置签名、阶段耗时、模型运行环境、标定质量、轨迹/姿态/热力图产物、失败诊断、指标对比。

## 注意事项

- 生产环境启动后端时建议**不带 `--reload`**，或使用 `--reload-exclude` 排除 `data/`、`.venv/`、模型文件，避免分析任务写盘触发不必要的重载。
- 数据库为本地 SQLite（`data/app.sqlite3`），多实例部署需注意读写冲突。
- RTMPose26 姿态推理为可选项，默认根据模型文件是否存在自动判断；球模型同样支持自动发现，缺失时只报告不可用状态。如需强制开关，设置 `PICKLEBALL_ENABLE_POSE_INFERENCE=true/false` 或 `PICKLEBALL_ENABLE_BALL_DETECTION=true/false`。
- 后端 pytest 使用临时数据库、上传/输出/录制/模型目录，不读取或修改默认运行数据库；完整质量门禁为 `npm run build`、`npm test`、`npm run lint` 和 `cd backend && python -m pytest -q`。
- FFmpeg 为录制功能必需依赖，纯视频分析不需要。
