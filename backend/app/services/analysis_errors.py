"""分析编排的控制信号异常。

**模块边界（刻意收窄）**：本模块只放「控制信号」异常——即编排层与pipeline
之间用于**表达停止意图**的异常种类，而不是任何业务失败。

加入本模块的原因：`AnalysisPipeline.run` 需要在 `except Exception` 之前
显式重抛这些异常，否则它们会被当成普通失败转成 `status="failed"` 的结果，
使编排层 `:1358-1366` 已有的正确捕获顺序失去作用。而这些异常原先定义在
`job_orchestration.py`，`analysis_pipeline.py` 若import 它会形成循环依赖
（编排层已 import pipeline）。

**不要往这里加业务异常。** 媒体损坏、标定失败、模型环境问题等属于
`analysis_failure_taxonomy` 的 `failure_class` 范畴，应由pipeline 内部
归类后以普通结果/消息表达，不应成为控制信号。
"""


class JobCanceledError(RuntimeError):
    """用户请求取消当前任务。"""


class WorkerLeaseLostError(RuntimeError):
    """Worker 无法继续证明自己拥有当前任务租约。"""


class StageTimeoutError(RuntimeError):
    """某个执行阶段超过允许时长。"""
