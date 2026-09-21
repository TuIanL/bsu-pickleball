## ADDED Requirements

### Requirement: 正式回合切分 artifact 与窗口计划

系统 SHALL 为每个正式 SegmentationRun 在关联 Parent 的确定性分析目录内写入 `match_state_segmentation.json`，并在结果/运行摘要中提供受控逻辑引用。artifact MUST 包含 schema version、planning job id、CaptureTake id、SegmentationRun id、状态、模型与输入/sync provenance、decoder、窗口状态概率摘要、unknown rate、algorithm segments 和不可变 `window_plan` 及其 hash；它 MUST NOT 包含训练期人工标签、ground truth、evaluation 或服务器绝对路径。

#### Scenario: 写入成功 artifact
- **WHEN** 正式切分成功或得到 `valid_no_rallies`
- **THEN** 系统 SHALL 在 CaptureTake 的 `analysis/<parent_job_id>/match_state_segmentation.json` 写入 artifact
- **AND** Parent 结果 SHALL 提供逻辑 artifact URL、状态、run id、plan hash 和可解释 detail

#### Scenario: artifact 无法生成
- **WHEN** 正式 Runtime 在产生有效 artifact 前失败
- **THEN** Parent/result SHALL 暴露 failed 或 unavailable 状态及稳定原因
- **AND** artifact API SHALL 不暴露临时文件或本地绝对路径

### Requirement: 正式切分 artifact API

系统 SHALL 支持通过 `GET /api/analysis/jobs/{job_id}/artifacts/match-state-segmentation` 读取已绑定 Parent 的正式切分 artifact。请求 unknown、未绑定或尚未生成 artifact 的 Job 时 SHALL 返回稳定的 known-artifact missing/unavailable 响应，而不是将 candidate artifact 或其它 Job 的 artifact 返回给调用方。

#### Scenario: 读取绑定 artifact
- **WHEN** 客户端请求已成功绑定 SegmentationRun 的 Parent artifact
- **THEN** API SHALL 返回该 Parent 的 `match_state_segmentation.json`
- **AND** 返回的 run id 与 Parent 持久化绑定一致

#### Scenario: 请求没有正式切分的 Job
- **WHEN** 客户端请求单摄、历史 Job 或未成功切分的 Parent 的该 artifact
- **THEN** API SHALL 返回 404 或等价稳定 unavailable 响应
- **AND** MUST NOT 回退到 `data/match_state_candidates` 中的候选文件
