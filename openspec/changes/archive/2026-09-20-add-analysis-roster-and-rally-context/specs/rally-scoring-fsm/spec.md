## ADDED Requirements

### Requirement: Rally start 的计分事实封存不扩展 ScoringState
系统 MUST 在创建有效 `rally_start` 时从当前纯计分 reducer 生成 `RallyScoringSnapshot`。ScoringState SHALL 继续只表示比分、发球权、计分阶段、发球站位和比赛结果，MUST NOT 承担 Team A/B court end 或分析名册。

#### Scenario: 现场回合开始
- **WHEN** 有效 match 的 `start_next_rally` 被执行
- **THEN** 系统 SHALL 关联该时点的 server_team、比分和规则版本事实
- **AND** SHALL 不要求该 CaptureTake 已存在 AnalysisJob 或 AnalysisRosterSnapshot
