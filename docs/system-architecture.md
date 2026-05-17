# 匹克球智能分析系统架构示意图

这版示意图用于汇报和展示，重点表达系统由“前端交互、后端接口、视觉分析、数据与模型”四部分组成。

## 1. 系统总体架构

```mermaid
flowchart LR
  user["用户<br/>上传视频 / 标定场地 / 查看报告"]

  frontend["前端展示层<br/>React + Vite<br/>上传分析、任务进度、视频工作台、分析报告"]

  backend["后端服务层<br/>FastAPI<br/>视频上传、场地标定、任务管理、结果查询"]

  algorithm["视觉分析层<br/>OpenCV + YOLO + RTMPose<br/>球员检测、姿态识别、轨迹跟踪、指标计算"]

  storage["数据与模型层<br/>本地视频、标定文件、分析结果、模型权重"]

  user --> frontend
  frontend -- "HTTP API" --> backend
  backend --> algorithm
  backend --> storage
  algorithm --> storage
  storage --> backend
  backend -- "报告 / 视频流 / Overlay" --> frontend
  frontend --> user
```

## 2. 核心业务流程

```mermaid
flowchart TD
  start["用户上传比赛视频"] --> calibrate["点选四个场地角点<br/>完成球场标定"]
  calibrate --> create["创建分析任务"]
  create --> analyze["后端执行视觉分析<br/>检测球员、识别姿态、跟踪轨迹"]
  analyze --> metrics["生成运动指标<br/>移动距离、速度、热力图、站位表现"]
  metrics --> result["输出分析结果<br/>JSON 报告 + 视频 Overlay"]
  result --> display["前端展示<br/>视频工作台、数据看板、训练建议"]
```

## 3. 模块说明

| 模块 | 作用 |
| --- | --- |
| 前端展示层 | 提供视频上传、场地标定、任务进度、视频回放和报告展示界面 |
| 后端服务层 | 负责接口管理、任务调度、数据读写和分析结果返回 |
| 视觉分析层 | 完成人体检测、姿态识别、轨迹跟踪、坐标投影和运动指标计算 |
| 数据与模型层 | 保存上传视频、标定数据、分析结果、Overlay 文件和本地模型权重 |
