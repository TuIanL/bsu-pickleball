## ADDED Requirements

### Requirement: Semantic boundary evaluation artifact is versioned and optional

系统 SHALL 支持可选的 `ball_semantic_boundary_eval.v1` artifact，用于记录语义边界 replay、证据摘要、adjudication 结果和评估指标；该 artifact 不得替代或破坏既有球轨迹、球 overlay 和球员分析 artifact。

#### Scenario: Evaluation artifact has a deterministic path and status

- **WHEN** 启用语义边界评估的 CaptureTake 分析任务完成回放
- **THEN** artifact SHALL 写入对应 session 的 `analysis/<job_id>/ball_semantic_boundary_eval.json`
- **AND** result SHALL 暴露 schema version、path/url、status 和 detail

#### Scenario: Legacy output path remains compatible

- **WHEN** 任务没有 CaptureTake 上下文而使用旧 `outputs/<job_id>/` 路径
- **THEN** 系统 SHALL 将 artifact 写入兼容 outputs 目录
- **AND** 既有 artifact path resolver 和历史球轨迹读取行为 SHALL 保持不变

#### Scenario: Missing or disabled evaluation is explicit

- **WHEN** 语义边界评估关闭、没有参考标签或评估依赖不可用
- **THEN** artifact status SHALL 为 `skipped`、`unavailable` 或 `partial`
- **AND** 主球检测、球跟踪、球路和球员分析 SHALL 不因此失败

### Requirement: Semantic boundary evaluation payload supports replay and metrics

`ball_semantic_boundary_eval.v1` SHALL 包含 job/take identity、policy version、rollout snapshot、source metadata、按 canonical timestamp 排序的 tick records、evidence summary、pending/confirmed phase、boundary action、formal candidate before/after、segment id、fallback/error 和 metrics。

#### Scenario: Tick records can be replayed

- **WHEN** 客户端或离线工具读取 evaluation artifact
- **THEN** 每个 tick record SHALL 能恢复 phase、authority、evidence ids、adjudication state 和 action result
- **AND** 同一输入按相同 policy version 重放 SHALL 得到确定性结果

#### Scenario: Metrics distinguish recommendation and execution

- **WHEN** fixture 或人工参考边界存在
- **THEN** metrics SHALL 分别记录 Shadow recommendation、Enforced execution 和 reference comparison
- **AND** 至少包含 boundary precision、recall、confirmation latency、false suppression 和 cross-segment contamination

#### Scenario: Artifact API accepts the known artifact name

- **WHEN** 客户端请求当前任务已有的 `ball-semantic-boundary-eval`
- **THEN** API SHALL 返回 200 JSON
- **AND** 当 artifact 未生成时 SHALL 返回 404，而不是 422
