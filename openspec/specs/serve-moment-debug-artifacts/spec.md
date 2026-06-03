# serve-moment-debug-artifacts Specification

## Purpose
TBD - created by archiving change add-serve-moment-context-detector. Update Purpose after archive.
## Requirements
### Requirement: 发球候选调试 artifact

系统 SHALL 为上下文发球时刻检测生成可选调试 artifact，用于复盘候选分数、检测信号、误报原因、漏报原因、时域覆盖和后续人工标注。

#### Scenario: 生成候选调试 JSON
- **WHEN** 发球时刻检测运行完成且调试 artifact 生成开启
- **THEN** 系统 SHALL 写入候选调试 JSON，包含每个候选的时间、球员、court position、检测模式、通过或拒绝原因、signal scores、使用的阈值摘要和检测覆盖摘要

#### Scenario: 生成 score 时间序列
- **WHEN** 检测器计算每帧或每个采样时间点的上下文发球分数
- **THEN** 系统 SHALL 能写入 CSV 或 JSON score 时间序列，包含 timestamp、player_id、baseline score、pre-stillness score、arm or ROI peak score、rally-after score、最终候选标记、拒绝原因和可用输入模式

#### Scenario: 调试 artifact 覆盖完整检测时域
- **WHEN** 源视频、tracking overlay 或 pose overlay 覆盖到后半段
- **THEN** 调试 artifact SHALL 暴露评分时域最早和最晚时间，并保留或汇总后半段拒绝原因，不得只保留最早若干条 rejected 样本而让后半段不可复盘

#### Scenario: 生成拒绝原因分桶统计
- **WHEN** 拒绝样本数量较多而需要限制明细体积
- **THEN** 系统 SHALL 写入按时间段和拒绝原因聚合的统计，至少能区分 not-near-baseline、missing-pre-stillness、no-local-motion-peak、low-confidence、missing-trajectory 或 missing-identity 等原因

#### Scenario: 调试 artifact 不阻塞主结果
- **WHEN** 调试 artifact 生成失败但 `serve_events.json` 可生成
- **THEN** 系统 SHALL 保持发球事件 artifact 可用，并把调试 artifact 状态标记为失败或不可用

### Requirement: 发球候选片段导出

系统 SHALL 支持为发球时刻候选导出短视频片段，便于人工复核、删除误报和积累 hard negatives。

#### Scenario: 导出候选片段
- **WHEN** 检测器输出候选且候选片段导出开启
- **THEN** 系统 SHALL 按候选 `start_time_seconds` 到 `end_time_seconds` 截取源视频片段，并在 manifest 中记录片段路径、候选 id、anchor 时间、球员 id 和置信度

#### Scenario: 片段时间被裁剪到视频范围
- **WHEN** 候选片段时间窗接近视频起点或终点
- **THEN** 系统 SHALL 将片段开始和结束时间裁剪到源视频有效范围内，并在 manifest 中保留实际导出的时间窗

#### Scenario: 限制调试片段数量
- **WHEN** 候选数量超过配置的调试片段导出上限
- **THEN** 系统 SHALL 只导出排序后的有限候选片段，并在 manifest 中记录未导出的候选数量

### Requirement: 发球 debug overlay

系统 SHALL 支持生成可选 debug overlay 视频或帧序列，在源画面上展示检测器用于判断的核心信号。

#### Scenario: Debug overlay 显示核心信号
- **WHEN** debug overlay 生成开启且源视频可读取
- **THEN** overlay SHALL 显示球员 bbox、player_id、底线附近状态、可用手腕/肘部关键点、候选峰值、serve score 摘要和候选片段区间

#### Scenario: Debug overlay 缺少 pose
- **WHEN** pose 不可用但 tracking 或 ROI 差分可用
- **THEN** overlay SHALL 显示降级检测模式和可用的 bbox、ROI 或运动峰值信息，而不是伪造骨架关键点

#### Scenario: Debug overlay 不作为前端必需层
- **WHEN** 完成任务包含 debug overlay artifact 引用
- **THEN** 前端 SHALL 不要求加载 debug overlay 才能展示基础视频、tracking、pose 或发球 marker
