# interactive-performance-report Specification

## Purpose
TBD - created by archiving change build-digital-interaction-platform. Update Purpose after archive.
## Requirements
### Requirement: Report-first entry experience

The system SHALL provide a product demo experience where users can enter a pickleball post-session analysis report through the layered overview, visual analysis workspace, and focused report detail pages rather than relying on one long report-first scrolling page.

#### Scenario: User opens the site on desktop

- **WHEN** the user loads the website on a desktop viewport
- **THEN** the first viewport presents the platform name, product value, current demo match context, and clear entry points into visual analysis and report detail workflows

#### Scenario: User opens the site on mobile

- **WHEN** the user loads the website on a mobile viewport
- **THEN** the overview, visual analysis entry, and report entry controls remain visible in a vertically stacked layout without text overlap or horizontal scrolling

### Requirement: Core metric summary
The system SHALL display a concise summary of pickleball performance metrics using structured analysis data, with demo routes using local demo data and completed real job routes using algorithm-derived movement and player-tracking metrics where available.

#### Scenario: Metrics are rendered from demo data
- **WHEN** the report demo or a report detail page without job context is displayed
- **THEN** the system may show sample performance metrics such as overall score, serve or return quality, movement efficiency, rally stability, landing accuracy, unforced errors, or court control while clearly distinguishing them as demo data

#### Scenario: Metrics are rendered from real pipeline output
- **WHEN** a completed uploaded-video job has MVP pipeline metrics
- **THEN** the system shows available algorithm-derived metrics such as movement distance, speed summaries, kitchen dwell, doubles spacing, heatmap coverage, processed frame counts, or person detection counts

#### Scenario: A requested metric is unavailable
- **WHEN** a real-job report module would require ball tracking, landing detection, hit events, shot classification, rally segmentation, or pose diagnosis that the current pipeline does not produce
- **THEN** the system omits that metric or marks it as unavailable instead of presenting fabricated uploaded-video results

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

### Requirement: Responsive report layout

The system SHALL keep report panels, controls, text, navigation, and visualizations legible across desktop and mobile viewport sizes.

#### Scenario: Layout adapts to narrow screens

- **WHEN** the viewport width is narrow
- **THEN** report pages and visual analysis modules stack into stable blocks with constrained visualization aspect ratios and no incoherent overlap

### Requirement: Algorithm-derived feedback copy

The system SHALL translate available algorithm metrics and performance insights into concise coaching feedback for real uploaded-video jobs while avoiding unsupported ball, landing, shot, or rally claims; real-job reports SHALL NOT mix sample-only performance conclusions with algorithm-derived content.

#### Scenario: Movement feedback is available

- **WHEN** the pipeline result includes movement distance, speed, spacing, zone dwell, or heatmap metrics
- **THEN** the report surfaces generate readable feedback that cites those metrics as evidence

#### Scenario: Insight findings are available

- **WHEN** the job has a generated `performance_insights.json` with findings
- **THEN** the report presents findings with their evidence, priority, and linked training recommendations
- **AND** findings whose data is insufficient SHALL be presented as insufficient-evidence states rather than definitive conclusions

#### Scenario: Tactical feedback is not supported by the MVP result

- **WHEN** the report page would otherwise show shot-pattern, rally, landing, ball-trajectory, or motion-diagnosis claims that require unsupported algorithms
- **THEN** the system either hides those claims for the real job or labels them as not available in the current analysis

#### Scenario: Real-job report contains zero demo performance conclusions

- **WHEN** a real-job report is rendered through any path including degradation paths
- **THEN** the report contains no demo performance conclusions such as sample overall scores, sample movement efficiency, or sample diagnosis wording
- **AND** sample content SHALL only appear on routes explicitly labeled as demo/sample

### Requirement: Algorithm-derived ball facts in reports
The system SHALL allow completed real-job reports to display ball trajectory and bounce candidate facts when those facts are backed by generated pipeline artifacts.

#### Scenario: Ball trajectory facts are available
- **WHEN** a completed uploaded-video job has ball trajectory or cleaned ball trajectory artifacts
- **THEN** report modules MAY show trajectory availability, sample coverage, candidate quality, or synchronized visual references derived from those artifacts
- **AND** the report SHALL distinguish those fields as algorithm-derived uploaded-video results

#### Scenario: Bounce candidate facts are available
- **WHEN** a completed uploaded-video job has `bounce_events.json`
- **THEN** report modules MAY show candidate bounce counts, timestamps, confidence, and review links
- **AND** the report MUST label them as candidates unless a later capability provides confirmed event semantics

#### Scenario: Ball facts are unavailable
- **WHEN** a real-job report module would use ball facts but the corresponding artifacts are skipped, unavailable, partial, failed, or absent
- **THEN** the report SHALL omit that module or mark it unavailable with the relevant stage reason
- **AND** the report MUST NOT fill the module with sample landing, shot, or ball-route data

### Requirement: Unsupported match semantics remain unavailable
The system SHALL keep shot classification, rally segmentation, scoring, landing-statistics, and tactical conclusions unavailable for real jobs until dedicated capabilities implement them.

#### Scenario: Report asks for shot or rally semantics
- **WHEN** a real-job report surface requires shot type, rally boundary, rally winner, score, fault, landing distribution, or tactical recommendation
- **THEN** the report SHALL use unavailable, limited, or sample-only state as appropriate
- **AND** the report MUST NOT infer those semantics solely from ball trajectory or bounce candidate artifacts

### Requirement: Performance insights respect unsupported match semantics

Performance insight rules SHALL NOT infer shot classification, rally segmentation, scoring, landing statistics, or tactical conclusions from ball trajectory or bounce candidate artifacts; ball/bounce candidates MAY only appear as a separate algorithm-candidate-facts section without becoming performance findings.

#### Scenario: Insight rule consumes rally timeline windows

- **WHEN** a rule uses manually marked `rally_start` / `rally_end` timeline windows
- **THEN** the finding copy SHALL only express statements scoped to "在人工标记的有效回合窗口中"
- **AND** the finding MUST NOT infer rally outcome, error type, or tactical effect

#### Scenario: Bounce candidates are excluded from findings

- **WHEN** `bounce_events.json` contains candidate events
- **THEN** insight rules MUST NOT produce findings that describe landing control, depth, or placement concentration from those candidates
- **AND** the performance report MAY show candidate counts and confidence as candidate facts only

