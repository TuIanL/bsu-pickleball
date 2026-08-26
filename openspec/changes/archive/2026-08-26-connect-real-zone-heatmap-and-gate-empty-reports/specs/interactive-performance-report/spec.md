## MODIFIED Requirements

### Requirement: Court visualization

系统 SHALL 可视化当前真实 job 的匹克球场地分析，包括球员移动路径、投影位置、标准球场上下文和由 backend algorithm output 生成的热力图；视频分析页和报告页 SHALL 使用同一 job-scoped canonical visualization artifact。demo 路由可以保留明确标注的样例视觉内容。

#### Scenario: User views demo court analysis

- **WHEN** 没有 job context 且显式打开 sample/demo court visualization
- **THEN** 系统 MAY 显示带有 demo 标记的样例落点、回球路线、移动轨迹或视频 overlay

#### Scenario: User views real movement court analysis

- **WHEN** completed real analysis job 包含 projected tracks 或 heatmap data
- **THEN** 系统 SHALL 从 backend algorithm output 渲染球员移动、场地覆盖或热力分布
- **AND** SHALL NOT 添加未经支持的球落点、击球路线或战术结论

#### Scenario: User views real report zone heatmap

- **WHEN** completed real analysis job 的 structured visualization artifact 包含 `zone_stats`
- **THEN** 报告页 SHALL 从该 artifact 渲染区域空间热力图、三区占用率、NVZ 占用率和站位距离
- **AND** 报告页 SHALL 使用 canonical player identity 与 evidence provenance

#### Scenario: Real court data is unavailable

- **WHEN** completed real job 没有有效 projected tracks、heatmap 或 `zone_stats`
- **THEN** 对应 court visualization SHALL 显示明确 unavailable/insufficient state
- **AND** SHALL NOT 使用 demo 坐标、静态样例热力图或伪造的上传视频结果

#### Scenario: User views the analysis details court plan

- **WHEN** completed job 的 analysis details page 可见
- **THEN** 系统 SHALL 渲染标准 2D pickleball court plan 作为未来 player movement projection 的基础视觉
