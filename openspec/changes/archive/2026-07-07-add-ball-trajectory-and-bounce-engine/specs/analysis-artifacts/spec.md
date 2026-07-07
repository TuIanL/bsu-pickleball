## ADDED Requirements

### Requirement: Ball engine artifacts declare coordinate units
球轨迹与弹跳点引擎写入已预留球相关 artifact 时，系统 SHALL 在 payload 中明确声明 image 坐标和 court 坐标的单位。

#### Scenario: Raw ball trajectory declares coordinate system
- **WHEN** 新球轨迹引擎写入 `ball_trajectory.json`
- **THEN** payload SHALL 声明 image 坐标单位为 pixels
- **AND** payload SHALL 声明 court 坐标单位为 feet
- **AND** payload SHALL 声明标准球场宽度为 20 ft、长度为 44 ft

#### Scenario: Cleaned ball trajectory declares coordinate system
- **WHEN** 新球轨迹引擎写入 `cleaned_ball_trajectory.json`
- **THEN** payload SHALL 声明 image 坐标单位为 pixels
- **AND** payload SHALL 声明 court 坐标单位为 feet
- **AND** payload SHALL 包含清洗和插值配置摘要

#### Scenario: Bounce events declare coordinate system
- **WHEN** 新球轨迹引擎写入 `bounce_events.json`
- **THEN** payload SHALL 声明 image 坐标单位为 pixels
- **AND** payload SHALL 声明 court 坐标单位为 feet
- **AND** payload SHALL 声明弹跳检测 method

### Requirement: Ball engine artifacts remain optional until pipeline integration
球轨迹与弹跳点引擎 artifact SHALL 保持可选，直到后续 change 明确将引擎接入当前真实分析 pipeline。

#### Scenario: Engine package exists but pipeline is not integrated
- **WHEN** 后端代码包含独立球轨迹与弹跳点引擎
- **THEN** `AnalysisPipelineResult.artifacts` MUST 仍允许球相关 artifact 字段为 null
- **AND** 当前 job 缺少球相关 artifact MUST NOT 被视为 pipeline 失败

#### Scenario: Artifact endpoint requests missing ball engine output
- **WHEN** 客户端请求已知的 `ball-trajectory`、`cleaned-ball-trajectory` 或 `bounce-events` artifact，但当前 job 未生成对应文件
- **THEN** API SHALL 返回 404
- **AND** API MUST NOT 返回 422
