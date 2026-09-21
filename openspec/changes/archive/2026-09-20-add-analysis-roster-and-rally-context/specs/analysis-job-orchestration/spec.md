## MODIFIED Requirements

### Requirement: Idempotent job submission
The system SHALL support idempotent real-analysis job submission based on stable input and configuration signatures. 对于声明或消费正式 Team A/B 语义的任务，签名 MUST 包含 `AnalysisRosterSnapshot` hash、analysis-rally-context-set hash 与适用 formal plan input hash。

#### Scenario: Duplicate submission is detected
- **WHEN** a client submits the same input video, calibration, analysis options, model/runtime configuration, roster/context signature without requesting a new version
- **THEN** the system returns or references the existing queued, running, or succeeded job rather than starting duplicate work

#### Scenario: New version is requested
- **WHEN** a client explicitly requests a new analysis version for an otherwise identical input signature
- **THEN** the system creates a new job version and records the relationship to the previous signature-compatible job

#### Scenario: Configuration changes
- **WHEN** the same video is submitted with materially different analysis options or model/runtime configuration
- **THEN** the system treats it as a distinct analysis signature and may create a separate job

#### Scenario: 名册或回合上下文不同
- **WHEN** 相同媒体使用不同 roster snapshot 或 analysis-rally-context-set hash 提交
- **THEN** 系统 SHALL 视其为不同输入
- **AND** MUST NOT 返回采用旧身份、队伍或端位结果的 Job/artifact
