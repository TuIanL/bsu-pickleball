## ADDED Requirements

### Requirement: Tracklet 时间窗四槽位分配
bootstrap SHALL 汇总候选 tracklet 的可见时间、置信度、side stability、court/image 横向秩、尺度连续性、重复重叠与合格 appearance template，再执行带 near/far quota 的全局一对一 slot assignment。appearance 只能在 side/geometry 可行候选间软排序。系统 MUST NOT 用单帧候选永久填槽，也 MUST NOT 为凑满四人重复使用同一 tracklet。

#### Scenario: P2 开始数秒后才稳定出现
- **WHEN** 初始帧只有 3 名稳定 tracklet，P2 在 bootstrap window 内稍后形成稳定 tracklet
- **THEN** P2 对应槽位 SHALL 等待并绑定该 tracklet
- **AND** SHALL NOT 在此前复制 P1 tracklet 填充 P2

#### Scenario: 第四候选证据不足
- **WHEN** 第四候选只出现一帧或疑似场外人员
- **THEN** 第四槽位 SHALL 保持 searching
- **AND** 系统 SHALL 宁可报告 roster 不完整也不误锁
