"""
API 路由包（package）

这个目录把后端对外提供的所有 HTTP 接口（也就是"网址 + 处理方法"）组织在一起。
FastAPI 在启动时，会从 main.py 里导入这里的各个 router（路由表），
从而把这些接口注册到服务器上，前端才能访问它们。

本包包含以下接口文件：
- routes_video.py       ：视频上传 / 查看元数据 / 播放视频流
- routes_calibration.py ：球场标定（手工 / 自动 / 半自动 三种方式）
- routes_analysis.py    ：分析任务的创建、查询、取消、删除，以及结果/报告/产物读取
- routes_camera.py      ：摄像头设备的登记、查询、删除、连接探测
- routes_recording.py   ：基于摄像头的录制控制（开始 / 停止 / 取消 / 查询）
- analysis.py           ：对 routes_analysis 的再导出（兼容旧导入路径，本身不含接口）
"""
