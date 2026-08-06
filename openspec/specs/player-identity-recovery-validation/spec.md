# player-identity-recovery-validation Specification

## Purpose
TBD - created by archiving change fix-player-identity-recovery. Update Purpose after archive.
## Requirements
### Requirement: 真实视频回归必须创建新的分析任务

真实身份回归 SHALL 使用 `/Users/tuian/Downloads/测试视频25s.mp4` 作为输入，并通过现有上传/注册和分析任务流程创建新的 analysis job；刷新历史任务 SHALL NOT 被视为重新运行身份管线。

#### Scenario: 使用指定视频创建新任务

- **WHEN** 回归开始且指定视频文件可读
- **THEN** 测试 SHALL 记录输入文件路径、视频 ID、新 job ID、标定 ID、source FPS 和 frame stride
- **AND** SHALL 保留旧 job 作为 baseline

#### Scenario: 历史任务刷新不能替代回归

- **WHEN** 只重新请求已有 job 的 result 或 artifact
- **THEN** 测试 SHALL 将其识别为 artifact 读取
- **AND** SHALL NOT 宣称锁定/身份代码已在视频上重新验证

### Requirement: 真实视频身份稳定性验收

新分析任务的 artifact 和诊断 SHALL 支持验证 P1-P4 的槽位稳定性与短暂漏检恢复。

#### Scenario: canonical player 数量受控

- **WHEN** 新任务完成真实双打分析
- **THEN** trajectory、render trajectory 和 detection overlay 中的 player identity SHALL 仅使用 `Player_1`..`Player_4`
- **AND** 数量 SHALL 不超过实际 `effective_player_count`

#### Scenario: 同帧不出现重复槽位绑定

- **WHEN** 检查 lock diagnostics、track history 和 overlay frame mappings
- **THEN** 同一 frame 的一个 source track SHALL 不得同时对应多个 player_id
- **AND** 一个 player slot SHALL 不得同时对应多个当前 track

#### Scenario: 短暂换 track 后恢复原身份

- **WHEN** 真实视频中某球员在漏检后出现新的 source track
- **THEN** 新 track SHALL 在恢复窗口内获得原 canonical player ID，或被记录为明确的门控拒绝
- **AND** SHALL NOT 长时间持续显示 `person` 且没有 unmatched/reconnect 诊断

### Requirement: 回归结果可与旧任务对照

回归 SHALL 保存足以比较旧任务与新任务的结构化证据，不得只依赖人工观看视频。

#### Scenario: 记录身份恢复指标

- **WHEN** 新任务和旧任务均可读取
- **THEN** 回归记录 SHALL 至少包含 P 槽位数量、source track history、重连事件数、unmatched/filtered 事件数、`person` 连续区间和 trajectory 覆盖度

#### Scenario: 代码修复未改善时任务不标记通过

- **WHEN** 新任务仍出现重复 slot-track 绑定或漏检后长期 `person`
- **THEN** 回归 SHALL 标记为失败或 residual risk
- **AND** SHALL 保留新旧 artifact 与诊断路径供进一步排查

#### Scenario: 视频文件不进入仓库

- **WHEN** 真实视频回归完成
- **THEN** 仓库 SHALL 只保存测试说明或结果摘要
- **AND** SHALL NOT 提交 `/Users/tuian/Downloads/测试视频25s.mp4` 的二进制内容

