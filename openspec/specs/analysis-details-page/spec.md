# analysis-details-page Specification

## Purpose
TBD - created by archiving change analysis-task-management-delete-and-details. Update Purpose after archive.
## Requirements
### Requirement: Job-specific analysis details page

系统 MUST 支持 multiview Parent 任务的详情展示：以聚合阶段进度呈现（素材与同步检查 → A 机位视觉分析 → B 机位视觉分析 → 多视角融合 → 指标重算 → 报告），并暴露 `viewRuns`（`cam_1 / cam_2` 各自的 `status / stage / progress`）两路子进度，不铺 24 行单摄阶段。

#### Scenario: Parent 双摄任务进度

- **WHEN** 用户打开 `analysisKind=multiview` 的 Parent 任务详情
- **THEN** 页面 SHALL 展示六个聚合阶段
- **AND** 同时展示 A/B 两路子进度（`viewRuns`：状态 / 当前阶段 / 百分比）

#### Scenario: 单摄任务详情不变

- **WHEN** 用户打开 `analysisKind=single_view` 的任务详情
- **THEN** 页面 SHALL 维持既有单摄阶段展示

### Requirement: Standard pickleball court plan
The analysis details page SHALL render a standard two-dimensional pickleball court plan as the primary future visualization surface.

#### Scenario: Standard court is displayed
- **WHEN** the analysis details page renders
- **THEN** it shows a 20 ft by 44 ft court plan with outer boundary, net line at 22 ft, non-volley-zone lines at 15 ft and 29 ft, center service lines, and near/far service boxes

#### Scenario: Court plan adapts to viewport
- **WHEN** the details page is viewed on desktop or narrow screens
- **THEN** the court plan preserves its geometry aspect ratio, labels remain legible, and controls or metadata do not overlap the court

#### Scenario: Movement projection is not ready
- **WHEN** player coordinate conversion or displacement tracks are not yet available
- **THEN** the court plan shows an explicit empty or pending visualization state rather than fabricated movement paths

### Requirement: Future player movement projection handoff
The analysis details page SHALL reserve a structured handoff for future player movement visualization on the standard court plan.

#### Scenario: Projected tracks become available later
- **WHEN** a completed job provides projected player positions in standard court coordinates
- **THEN** the details page can render player positions, paths, or heat layers on the same 20 ft by 44 ft court coordinate system without changing the route

#### Scenario: Job lacks calibration
- **WHEN** a completed job has no calibration or no valid projected court coordinates
- **THEN** the details page identifies the missing prerequisite and keeps the court plan in a non-projected state

### Requirement: Projected track explanation
The analysis details page SHALL explain the semantics of projected court marks whenever completed analysis data includes projected player positions.

#### Scenario: User views projected court marks
- **WHEN** the analysis details page renders a completed job with projected player positions
- **THEN** the court visualization identifies plotted points as estimated player footpoints projected from video image space into the standard 20 ft by 44 ft court coordinate system

#### Scenario: User needs to distinguish movement from other events
- **WHEN** projected player positions are displayed alongside any report, metric, or status context
- **THEN** the page distinguishes projected player movement marks from ball contacts, shot landing points, and manually annotated events

#### Scenario: Tracker identity is uncertain
- **WHEN** the page labels projected movement by raw tracker output
- **THEN** it communicates that track labels represent detected movement tracks and are not guaranteed named player identities across the whole video

### Requirement: Projected track legend and filtering
The analysis details page SHALL group projected player positions by track and provide readable controls for identifying and filtering those tracks.

#### Scenario: Multiple tracks are available
- **WHEN** a completed job provides projected positions for more than one track
- **THEN** the court visualization renders distinguishable per-track paths or points and shows a legend with stable display labels for each visible track

#### Scenario: User selects one track
- **WHEN** the user selects a track from the legend or track controls
- **THEN** the court emphasizes that track and reduces visual prominence of unselected tracks without losing the ability to return to the broader view

#### Scenario: Result contains short noisy track fragments
- **WHEN** projected positions include many low-persistence or very short track fragments
- **THEN** the page provides a way to hide or de-emphasize those fragments while preserving access to the full projected data context

#### Scenario: Track summaries are shown
- **WHEN** projected tracks are available
- **THEN** each displayed track summary includes enough context to compare tracks, such as point count, visible time range, and confidence or persistence context

### Requirement: Projected point inspection
The analysis details page SHALL allow users to inspect representative projected points or selected track details with source timing and reliability context.

#### Scenario: User inspects a projected point
- **WHEN** the user hovers, clicks, or otherwise focuses a projected point
- **THEN** the page shows the point's track label, timestamp or frame, court coordinate, and confidence when those fields are available

#### Scenario: User inspects start and latest positions
- **WHEN** a visible track is rendered on the court plan
- **THEN** the visualization distinguishes the track's start and latest rendered positions from intermediate points

#### Scenario: No projected positions are available
- **WHEN** a completed job lacks valid projected player positions
- **THEN** the court plan explains the missing prerequisite or unavailable projected-data state instead of rendering unlabeled placeholder movement marks

### Requirement: Projected court rendering performance
The analysis details page SHALL keep projected court rendering responsive for real analysis results that contain many projected points or fragmented tracks.

#### Scenario: Large projected result is opened
- **WHEN** a completed job contains thousands of projected points or many track identifiers
- **THEN** the page renders a bounded representative visualization without blocking the rest of the analysis details page

#### Scenario: Rendered points are sampled
- **WHEN** the page samples or caps points for drawing performance
- **THEN** the track summaries continue to reflect the complete available projected data rather than only the sampled drawing subset

### Requirement: 降级与失败状态展示

multiview Parent 进入单视角降级（sync 不可用 / 单路失败）时，详情页 MUST 明确展示降级原因与横幅，MUST NOT 静默展示为成功融合。失败/不可用技术细节（child job 失败、mvf not eligible、sync gate）SHALL 只放技术详情区域。

#### Scenario: B 机位失败降级

- **WHEN** Parent 以 cam_1 单视角降级完成
- **THEN** 页面 SHALL 展示「B 机位分析失败，结果已自动降级为 A 机位单视角分析」
- **AND** 数据来源 SHALL 显示球员移动 / 热力图 / 球路 / 姿态均来自 A 机位
- **AND** child 失败技术细节 SHALL 仅出现于技术详情

#### Scenario: sync 不可用降级

- **WHEN** 两路均完成但 sync 不可用、未执行融合
- **THEN** 页面 SHALL 展示「双摄同步校准不可用，本次结果使用 A 机位单视角数据」
- **AND** 明确标注「未执行多视角融合」

### Requirement: 数据来源与融合质量

结果/详情页 MUST 明确展示哪些数据来自多视角融合、哪些取 reference view，并展示融合质量（`fused_diagnostics`：双视角共同观测 / 单视角补偿 / 预测补点 / 不可用占比、视角位置差异中位数、同步质量）。

#### Scenario: 数据来源如实展示

- **WHEN** 双摄融合完成
- **THEN** 报告 SHALL 标注：球员移动 / 热力图 / 移动距离速度 = A+B 多视角融合；姿态 / 球路 / 动作识别 / 分析视频 = A 机位（reference view）
- **AND** 不得将 reference-view 结果标注为融合

#### Scenario: 融合质量区域

- **WHEN** 用户查看双摄任务的技术详情
- **THEN** 页面 SHALL 展示 fused diagnostics 的融合质量指标
- **AND** 供论文 / 比赛展示 / 技术答辩使用

### Requirement: 分析任务详情页提供来源一致的顶部返回

分析任务状态详情页 SHALL 在页面左上方提供统一的返回任务管理入口。返回地址 SHALL 优先使用显式来源上下文；对于没有显式上下文的 multiview Parent SHALL 返回双摄录制 tab，其他未知来源 SHALL 回退到上传视频任务 tab。

#### Scenario: 双摄 Parent 详情返回

- **WHEN** 用户查看 multiview Parent 的分析详情
- **THEN** 页面左上方 SHALL 显示返回任务管理按钮
- **AND** 点击后 SHALL 返回双摄录制任务 tab

#### Scenario: 普通任务详情返回

- **WHEN** 用户查看没有双摄来源的普通分析任务详情
- **THEN** 页面左上方 SHALL 显示同样结构的返回按钮
- **AND** 点击后 SHALL 返回普通任务管理上下文或上传任务 tab

#### Scenario: 详情页加载失败

- **WHEN** 任务详情加载失败或任务不存在
- **THEN** 错误状态 SHALL 仍提供稳定的返回任务管理入口
- **AND** 返回目标 SHALL 遵循相同的来源回退规则

