## MODIFIED Requirements

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
