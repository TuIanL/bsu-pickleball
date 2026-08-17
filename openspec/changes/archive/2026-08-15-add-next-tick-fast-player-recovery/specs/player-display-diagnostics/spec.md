## ADDED Requirements

### Requirement: 漏斗行展示 available_miss_streak

`player-display-diagnostics.v1` 漏斗行 SHALL 增加 `available_miss_streak` 字段（int，缺省 0），表示该 `(player, view)` 在该 tick 的连续 available global-view miss 计数（来源 `ViewBinding.consecutive_available_misses`，语义为"attempted available tick 但无 AssociationUpdate"）。该字段 SHALL 与 `binding_visibility` 并列展示，使"binding 仍为 observed 但已有连续 available miss"这类正交状态可见。查询 API SHALL 直接透传该字段（向后兼容：旧产物缺失时前端按 0 显示）。漏斗行构建 MUST 在 available-miss ledger 之后执行（当前 tick 的 miss 状态不得晚一拍呈现）。

#### Scenario: fast path 触发前后可观测

- **WHEN** 某 `(player, view)` 出现 available miss 并触发 fast path guidance
- **THEN** 漏斗行 SHALL 同时展示 `binding_visibility`（可能仍为 observed）与 `available_miss_streak`（>= 1）
- **AND** `guidance_skip_reason` 或 `guidance_status` 可反映 fast path 触发

#### Scenario: 漏斗不晚一拍

- **WHEN** 某 tick 首次出现 available miss
- **THEN** 该 tick 的漏斗行 SHALL 已显示 `available_miss_streak=1`
- **AND** MUST NOT 显示 0

#### Scenario: 旧产物向后兼容

- **WHEN** 查询历史任务的显示诊断产物（无 `available_miss_streak` 字段）
- **THEN** 前端 SHALL 按 0 展示该字段
- **AND** 查询 API SHALL NOT 因字段缺失报错
