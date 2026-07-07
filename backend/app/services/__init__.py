"""后端服务层 —— 视频管理、标定服务、分析流水线、任务编排和存储。

本包（package）把"业务逻辑"从 FastAPI 的路由层（api）里抽出来，
让路由只负责"接收请求 / 返回响应"，而真正的计算、读写、调度都放在这里。

包含的子模块：
- storage_service.py       本地文件存储助手（读写 JSON、管理各类产物路径）
- video_service.py         视频上传与元数据管理
- calibration_service.py   场地标定（手工/半自动）的创建、存储与投影
- automatic_calibration_service.py  基于边线分割模型的自动标定建议
- analysis_pipeline.py      端到端分析流水线（检测→跟踪→投影→指标）
- job_orchestration.py      任务生命周期编排（排队、调度、取消、重试）
- mock_analysis.py          MVP 阶段的分析任务 CRUD 与演示报告生成
"""
