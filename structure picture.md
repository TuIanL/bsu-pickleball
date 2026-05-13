# 匹克球智能分析系统架构示意图

本文档根据当前仓库实现整理，覆盖浏览器端、FastAPI 后端、本地视觉算法流水线、模型资产和文件存储之间的关系。

## 1. 运行时总体架构

```mermaid
flowchart LR
  user["用户<br/>上传比赛视频、点选四角标定、查看报告"]

  subgraph browser["浏览器端：React + Vite"]
    shell["AppShell / 页面路由<br/>总览、上传、任务状态、视觉工作台、报告、训练、硬件"]
    upload["NewAnalysisPage<br/>视频选择、标定帧截取、四角点选"]
    jobpage["AnalysisJobPage<br/>轮询任务进度"]
    vision["VisionPage<br/>视频回放 + 检测框/骨架 overlay"]
    report["ReportPage / pipelineReportAdapter<br/>算法结果转报告、指标和训练建议"]
    client["analysisClient.ts<br/>HTTP API 封装 + demo/localStorage 兜底"]
  end

  subgraph api["Python 后端：FastAPI"]
    main["app.main<br/>CORS + 路由注册"]
    videos["/api/videos<br/>上传、元数据、视频流"]
    calibration["/calibration/manual<br/>/api/calibrations<br/>手工标定、投影、预览"]
    analysis["/api/analysis/jobs<br/>建任务、查状态、查结果、查报告、查 artifact"]
  end

  subgraph services["应用服务层"]
    video_service["VideoService<br/>保存视频和读取视频元数据"]
    calibration_service["CalibrationService<br/>四角标定、单应性矩阵、坐标投影"]
    job_service["mock_analysis.py<br/>任务状态、后台任务、报告封装"]
    pipeline["AnalysisPipeline<br/>真实视频分析编排"]
    storage_service["StorageService<br/>本地 JSON/视频/artifact 路径管理"]
  end

  subgraph vision_engines["视觉算法与指标引擎"]
    court["CourtVision Calibration Engine<br/>标准球场、homography、场地 overlay"]
    detector["Player Tracking Engine<br/>YOLO 人体检测、主球员筛选、多目标跟踪、脚点估计"]
    pose["Pose Engine<br/>RTMPose26 关键点/骨架 overlay"]
    metrics["Pickleball Performance Engine<br/>距离、速度、厨房区停留、双打间距、热力图"]
  end

  subgraph local_assets["本地运行资产"]
    storage["backend/data<br/>uploads、calibrations、outputs、tmp"]
    models["models/rtmpose + YOLO 权重<br/>本地模型配置与 checkpoint"]
    runtime[".runtime<br/>本地启动日志和 pid"]
  end

  user --> shell
  shell --> upload
  shell --> jobpage
  shell --> vision
  shell --> report
  upload --> client
  jobpage --> client
  vision --> client
  report --> client

  client -- "HTTP / JSON / FormData" --> main
  main --> videos
  main --> calibration
  main --> analysis

  videos --> video_service
  calibration --> calibration_service
  analysis --> job_service
  job_service --> pipeline
  video_service --> storage_service
  calibration_service --> storage_service
  job_service --> storage_service
  pipeline --> storage_service

  calibration_service --> court
  pipeline --> court
  pipeline --> detector
  pipeline --> pose
  pipeline --> metrics

  storage_service --> storage
  detector --> models
  pose --> models
  runtime -. "npm run app:start / app:stop" .- main
```

## 2. 视频分析数据流

```mermaid
sequenceDiagram
  autonumber
  actor U as 用户
  participant FE as React 前端
  participant API as FastAPI
  participant VS as VideoService
  participant CS as CalibrationService
  participant JOB as 任务服务
  participant PIPE as AnalysisPipeline
  participant STORE as backend/data
  participant MODEL as YOLO / RTMPose

  U->>FE: 选择视频并点选四个场地角点
  FE->>API: POST /api/videos/upload
  API->>VS: 保存源视频和元数据
  VS->>STORE: 写入 uploads/video-* 与 metadata JSON
  API-->>FE: videoId

  FE->>API: POST /calibration/manual
  API->>CS: 计算 homography 和标准场地映射
  CS->>STORE: 写入 calibrations/calib-*.json
  API-->>FE: calibrationId

  FE->>API: POST /api/analysis/jobs
  API->>JOB: 创建 queued 任务
  JOB->>PIPE: 后台执行真实视频分析
  API-->>FE: jobId + 阶段状态

  loop 前端轮询
    FE->>API: GET /api/analysis/jobs/{jobId}
    API-->>FE: queued / processing / completed / failed
  end

  PIPE->>VS: 读取视频路径和帧信息
  PIPE->>CS: 读取标定矩阵
  PIPE->>MODEL: YOLO 人体检测
  PIPE->>PIPE: 主球员筛选、多目标跟踪、脚点估计、球场坐标投影
  PIPE->>MODEL: 可选 RTMPose26 姿态识别
  PIPE->>PIPE: 计算移动距离、速度、厨房区停留、热力图等指标
  PIPE->>STORE: 写入 result / tracking / overlay / pose JSON
  JOB->>STORE: 写入 job summary 和 report JSON

  FE->>API: GET /api/analysis/jobs/{jobId}/result
  FE->>API: GET /api/analysis/jobs/{jobId}/report
  FE->>API: GET /api/analysis/jobs/{jobId}/artifacts/*
  FE->>API: GET /api/videos/{videoId}/stream
  API-->>FE: 报告 JSON、overlay JSON、源视频流
  FE-->>U: 展示视频工作台、指标卡、报告和训练建议
```

## 3. 后端流水线分层

```mermaid
flowchart TD
  input["输入<br/>videoId + calibrationId + metadata + frameStride"] --> read["读取视频<br/>VideoService + OpenCV"]
  read --> calib["读取标定<br/>CalibrationService + homography"]
  calib --> detect["人体检测<br/>PersonDetector / YOLO<br/>或 EmptyPersonDetector 降级"]
  detect --> select["主球员筛选<br/>PrimaryPlayerSelector"]
  select --> track["多目标跟踪<br/>MultiObjectTracker"]
  track --> foot["脚点估计<br/>FootpointEstimator"]
  foot --> project["球场投影<br/>PlayerProjector"]
  project --> pose_choice{"姿态推理启用？"}
  pose_choice -- "是" --> pose_run["RTMPose26Adapter<br/>生成骨架关键点 overlay"]
  pose_choice -- "否" --> pose_skip["跳过姿态阶段<br/>保留检测/轨迹 overlay"]
  pose_run --> metrics
  pose_skip --> metrics
  metrics["指标计算<br/>距离、速度、厨房区、双打间距、热力图"] --> artifacts["输出 artifact<br/>result_json、tracking_result、tracking_overlay、pose_overlay、report"]
  artifacts --> frontend["前端适配和展示<br/>pipelineReportAdapter + VideoAnalysisCard + ReportVisualization"]
```

## 4. 关键模块对照

| 层级 | 主要文件/目录 | 责任 |
| --- | --- | --- |
| 前端入口 | `src/App.tsx` | 页面路由、上传标定流程、任务状态、视觉工作台、报告页 |
| API 客户端 | `src/services/analysisClient.ts` | 视频上传、标定、任务、结果、报告、overlay 请求 |
| 报告适配 | `src/services/pipelineReportAdapter.ts` | 将后端 pipeline result 转成前端报告模型 |
| FastAPI 入口 | `backend/app/main.py` | CORS、健康检查、路由注册 |
| API 路由 | `backend/app/api/` | 视频、标定、分析任务相关接口 |
| 服务层 | `backend/app/services/` | 存储、视频、标定、任务状态、pipeline 编排 |
| 算法层 | `backend/app/vision/` | 场地标定、检测跟踪、姿态、运动指标 |
| 本地数据 | `backend/data/` | 上传视频、标定文件、任务结果、overlay artifact |
| 模型资产 | `models/` | YOLO/RTMPose 配置和权重 |
| 本地运行 | `scripts/start-local-runtime.sh` | 同时启动后端和 Vite 前端，写入 `.runtime` 日志 |
