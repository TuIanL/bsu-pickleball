## ADDED Requirements

### Requirement: Sync authority preflight

多视角创建和执行前的 preflight SHALL 调用与 executor 一致的严格 sync authority validator，并以当前 Parent 的 reference/secondary view identity 验证 mapping。

#### Scenario: preflight 拒绝错误 mapping

- **WHEN** sync 文件存在但缺少当前 secondary mapping 或 mapping identity 不一致
- **THEN** preflight SHALL 返回结构化问题
- **AND** 系统 SHALL NOT 创建一个会静默使用错误 mapping 的多视角运行

### Requirement: Effective mode 编排传播

Parent 的结果、manifest、summary 和用户可见 message SHALL 传播同一个 effective mode。`fusion_performed`、orchestration status 和 effective mode SHALL 分别表示执行事实、生命周期状态和证据质量，不得互相替代。

#### Scenario: pipeline 执行但无双摄证据

- **WHEN** fusion pipeline 已执行但 `dual_evidence_samples == 0`
- **THEN** Parent SHALL 标记为 `single_view_fallback`
- **AND** summary/message SHALL 不得标记为正常 `multiview_fused`
