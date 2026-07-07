"""
摄像头模块（camera package）

本目录负责"摄像头接入"与"基于摄像头的录制"功能，主要包括：
- models.py          ：摄像头与录制会话的数据模型（Pydantic）
- camera_registry.py ：摄像头配置的登记与持久化（存到 data/cameras/）
- stream_probe.py    ：用 OpenCV 探测摄像头是否在线、分辨率、延迟
- recorder.py        ：调用 FFmpeg 子进程，把视频流录制为 MP4
- session_service.py ：录制会话的生命周期管理（开始 / 停止 / 取消 / 查询）
- __init__.py        ：本文件（包标识，本身不含代码）

这些功能由 backend/app/api/routes_camera.py 和 routes_recording.py 的接口调用。
"""
