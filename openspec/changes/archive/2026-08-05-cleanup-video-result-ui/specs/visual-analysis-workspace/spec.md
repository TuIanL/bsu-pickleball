## ADDED Requirements

### Requirement: 完成态视频视图不显示开发向状态卡片与占位比分

真实视频分析工作台的完成态视频卡片 SHALL NOT 在视频下方渲染面向用户的 artifact 可用性卡片（YOLO 人体框、RTMPose 骨架、球轨迹、弹跳候选四张卡片及其 status/detail 文案）。视频标题右侧的比分胶囊 SHALL 仅在存在真实比分时显示，SHALL NOT 显示 "MVP" 之类的占位符。图层可用性状态 SHALL 仍通过视频内状态徽章与图层开关呈现。

#### Scenario: 完成态真实任务不显示四张卡片

- **WHEN** 用户打开完成态真实分析任务的视频工作台
- **THEN** 视频下方不显示 YOLO 人体框 / RTMPose 骨架 / 球轨迹 / 弹跳候选 四张信息卡及其 detail 文案

#### Scenario: 标题不显示 MVP 占位比分

- **WHEN** 真实分析任务的 `match.score` 为占位符 "MVP"
- **THEN** 视频标题右侧不渲染该占位比分胶囊

#### Scenario: demo 显示真实比分

- **WHEN** demo 或任务存在真实比分（如 "11 - 8"）
- **THEN** 视频标题右侧渲染该比分胶囊

#### Scenario: 图层状态仍可通过视频内控制查看

- **WHEN** 用户需要查看人体框、骨架、球或弹跳图层的可用性
- **THEN** 通过视频内的状态徽章或图层开关查看，视频播放层不因移除四张卡片而改变
