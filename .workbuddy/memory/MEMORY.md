# 项目背景备忘

## 项目概况
- 名称：`pre-pickleball`（产品名「拍动视析」），匹克球（pickleball）运动表现智能分析平台。
- 定位：真实运行的视频分析产品 + 科研实验平台（大创竞赛项目）。基于视觉捕捉与 TENG-IMU 智能球拍。
- 主流程：用户上传比赛视频 → 点选四角标定场地 → 创建分析任务 → 后台队列/Worker 执行视觉分析 → 输出 JSON 报告 + 视频 Overlay + stage telemetry → 前端展示数据看板与训练建议。
- 边界：当前真实结论聚焦人员检测、姿态叠加、轨迹投影、移动指标；球追踪/击球事件/回合分割/战术语义暂不作为真实输出。

## 技术栈
- 前端：React 19 + Vite 7 + TypeScript + Tailwind CSS 4 + lucide-react。
- 后端：Python FastAPI。
- 视觉算法：OpenCV + YOLO11（人体检测）+ RTMPose26（姿态）。
- 模型权重：`models/`（rtmpose、YOLO）。
- 本地存储：`backend/data/`（uploads/calibrations/outputs/tmp）。

## 关键目录
- `src/`：React 前端。`App.tsx` 路由；`services/analysisClient.ts`（API 封装 + demo/localStorage 兜底）、`pipelineReportAdapter.ts`（后端结果转报告）；`components/platform/`（AppShell、VideoAnalysisCard、ReportVisualization、MetricCard、videoOverlayPlayback 等）；`data/`（demoData.ts、productCopy.ts）；`types/report.ts`。
- `backend/app/`：FastAPI 后端。`main.py` 入口；`api/`（video/calibration/analysis/camera/recording 路由）；`services/`（video/calibration/job_orchestration/mock_analysis/automatic_calibration/storage/analysis_pipeline）；`vision/`（courtvision_calibration_engine、detectors、player_tracking_engine、pose、pickleball_performance_engine、events、action_classification_preprocessing、court_view）；`schemas/`（metrics/tracking/pose/calibration/pipeline 等）；`camera/`（摄像头登记/推流/录制）；`core/`（config、logging）。
- `docs/`：court-line-calibration.md、system-architecture.md、player-trajectory-identity-qa.md。
- `openspec/`：243 个 md，OpenSpec 变更提案/规格记录。
- `scripts/`：start-local-runtime.sh / stop-local-runtime.sh（同时启后端+前端，写 `.runtime` 日志）、train-court-line-windows.ps1。
- `data/ datasets/ runs/`：数据集、训练产物、实验输出（文件量极大，非核心代码）。

## 启动方式
- `npm run app:start`（= bash scripts/start-local-runtime.sh）同时启动后端与 Vite 前端。
- `npm run dev` 仅前端；`npm run build` = tsc -b && vite build；`npm test` = vitest。
- 仓库根有 `start-pickleball.command` / `stop-pickleball.command` 便捷脚本。

## 架构文档（权威参考）
- `system-architecture.md`（运行时架构 + 视频分析数据流 + 流水线分层 + 模块对照表）。
- `structure picture.md`（高层模块说明 + 产品/科研边界）。
