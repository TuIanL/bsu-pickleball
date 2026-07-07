"""
姿态估计（Pose Estimation）模块。

职责：把「球员跟踪引擎」给出的人体检测框，进一步细化为「人体关键点坐标」，
为前端姿态叠加（skeleton overlay）、动作分类等下游任务提供结构化输入。

本目录文件：
- base.py：姿态估计的基础数据结构与适配器协议（PoseKeypoint / PoseResult / PoseEstimatorAdapter）。
- rtmpose26_adapter.py：基于 MMPose 的 RTMPose26 适配器，输出 26 个归一化关键点。
"""
