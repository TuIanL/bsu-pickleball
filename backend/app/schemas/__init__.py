"""
后端共享数据模型（Schemas / Pydantic 模型）包

本目录定义了整个后端"对外的数据格式约定"（也叫 Schema）。
- 接口（api 层）用它们来声明"请求收什么、响应返回什么"；
- 服务层（services）和算法层（vision）也用它们来组织计算结果。

Pydantic 会在数据进出时自动做类型校验，保证前后端看到的数据结构一致。
各子文件按业务领域划分：video（视频）、calibration（标定）、analysis（分析任务）、
pipeline（流水线结果）、metrics（指标）、tracking（跟踪）、multitarget（多目标检测）、
pose（姿态）、events（发球事件）、court_view（场地视角）。
"""
