## ADDED Requirements

### Requirement: 发球检测时域覆盖诊断

系统 SHALL 在发球事件 artifact 或 pipeline 阶段 counters 中暴露检测时域覆盖诊断，使用户和开发者能够判断发球检测是否覆盖了源视频的后半段。

#### Scenario: 检测覆盖完整视频
- **WHEN** 真实视频分析任务完成且发球检测输入覆盖接近完整源视频时长
- **THEN** 发球事件 artifact SHALL 暴露源视频时长、评分输入最早和最晚时间、评分样本数量、候选最早和最晚时间，以及覆盖比例摘要

#### Scenario: 评分时域明显短于源视频
- **WHEN** tracking 或 pose artifact 覆盖完整视频但发球评分输入的最晚时间明显早于源视频结束时间
- **THEN** 系统 SHALL 在发球事件 detail、diagnostics 或阶段 counters 中说明检测覆盖不足，并标识可能缺失的输入类型，例如 player trajectory、stable player identity、target-court eligibility 或 trajectory samples

#### Scenario: 后半段没有候选
- **WHEN** 发球事件候选只出现在源视频前段且后段没有评分样本或候选
- **THEN** 系统 SHALL 保留可复盘诊断，而不得仅返回“没有达到阈值”的泛化说明

### Requirement: Player trajectory 中断时的发球检测降级

系统 SHALL 在稳定 player trajectory 或 player identity 提前中断时保守降级发球检测，而不是静默停止后续时段评分。

#### Scenario: Player trajectory 提前结束但 tracking 可用
- **WHEN** player trajectory 的最后样本时间明显早于 tracking overlay 的最后时间，且后续 tracking 检测仍存在 court-relevant 人体框
- **THEN** 检测器 SHALL 标记 trajectory 覆盖不足，并可使用 tracking、pose 或 ROI 运动信号继续生成 `partial` 发球候选

#### Scenario: 降级候选缺少底线坐标
- **WHEN** 降级检测无法安全获得球场坐标或底线站位分数
- **THEN** 候选事件 SHALL 记录 `partial` 或降级检测模式、可用信号和缺失原因，而不得伪造底线站位分数

#### Scenario: 降级后仍无候选
- **WHEN** trajectory 中断后 tracking 或 pose 信号仍不足以产生发球候选
- **THEN** 发球事件 artifact SHALL 输出覆盖不足和降级尝试结果，帮助区分“确实无候选”和“输入链路断开”

### Requirement: 发球候选覆盖摘要兼容现有事件

系统 SHALL 在扩展发球诊断字段时保持现有 `events`、`timestamp_seconds`、`seek_time_seconds` 和 artifact URL 合同兼容。

#### Scenario: 老前端读取新 artifact
- **WHEN** 客户端只依赖已有发球事件字段
- **THEN** 新增覆盖诊断字段 SHALL 不破坏现有事件数组、状态字段、时间字段和跳转行为

#### Scenario: 新前端读取旧 artifact
- **WHEN** 客户端加载缺少覆盖诊断字段的旧发球事件 artifact
- **THEN** 前端 SHALL 仍能显示候选事件，并把覆盖诊断显示为不可用或未知
