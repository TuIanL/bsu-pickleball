"""
动作分类预处理模块（action_classification_preprocessing）。

这个子包的功能是：把一段比赛视频，导出成"某个目标球员"的连续帧图像样本，
用于后续训练一个"动作分类"模型（例如区分发球、正手击球、反手击球等动作）。

整体流程大致是：
1. 用 schemas.py 里定义的 ActionPreprocessingConfig 描述"想要怎么导出"（输入/输出路径、采样帧率、ROI 区域、图像增强、目标球员选择策略等）。
2. preprocessing.py 提供纯图像处理的工具函数（抽帧、裁剪场地 ROI、CLAHE 增强、去噪、裁剪球员、拼 clip 窗口）。
3. selection.py 提供"从一帧里的多个人里，选出哪一个是我们关心的目标球员"的策略。
4. exporter.py 把上面三者串起来，逐帧读取视频 → 增强 → 检测 → 选中目标 → 裁剪 → 拼成 clip → 写出图片和 manifest 清单。

本文件（__init__.py）只做一件事：把最常用的类与函数"再导出"一遍，
这样外部代码写 `from app.vision.action_classification_preprocessing import X` 就能直接拿到，
不用深入到子模块内部。
"""

# 导出器：把整个流程串起来、产出数据集的主入口函数
from app.vision.action_classification_preprocessing.exporter import export_action_classification_dataset

# 预处理工具：纯图像/抽帧相关函数
from app.vision.action_classification_preprocessing.preprocessing import (
    apply_clahe_bgr,
    apply_light_denoise,
    build_clip_windows,
    crop_court_roi,
    crop_player,
    expand_box,
    sample_frame_indices,
)

# 配置与数据结构：导出时用的配置项、各产物（ROI 记录、帧样本、clip 记录、manifest）的数据类
from app.vision.action_classification_preprocessing.schemas import (
    ActionPreprocessingConfig,
    ActionPreprocessingError,
    CLAHEConfig,
    DenoiseConfig,
    ROIConfig,
)

# 目标球员选择：从一帧里的多个人中挑出目标球员
from app.vision.action_classification_preprocessing.selection import select_target_detection

# __all__ 是一个约定：它告诉 Python（以及 IDE、文档工具）"当别人用
# `from 包 import *` 时，应该导出哪些名字"。这里把上面再导出的全部公开符号列出来。
__all__ = [
    "ActionPreprocessingConfig",
    "ActionPreprocessingError",
    "CLAHEConfig",
    "DenoiseConfig",
    "ROIConfig",
    "apply_clahe_bgr",
    "apply_light_denoise",
    "build_clip_windows",
    "crop_court_roi",
    "crop_player",
    "expand_box",
    "export_action_classification_dataset",
    "sample_frame_indices",
    "select_target_detection",
]
