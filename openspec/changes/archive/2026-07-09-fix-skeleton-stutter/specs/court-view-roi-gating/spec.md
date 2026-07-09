# court-view-roi-gating Specification (Delta)

## MODIFIED Requirements

### Requirement: 球场视角门控匹配阈值可配置
系统 SHALL 允许按任务覆盖或调整 `court_view_match_threshold` 配置，使处理长视频时不会因阈值固定过严导致 95%+ 帧被门控剔除。

#### Scenario: 默认阈值可用
- **WHEN** 任务未显式指定 court_view_match_threshold
- **THEN** 系统 SHALL 使用 `PickleballSettings` 默认值（0.75），保持向后兼容

#### Scenario: 阈值可被任务级参数覆盖
- **WHEN** 分析任务请求中显式指定了 court_view_match_threshold
- **THEN** 系统 SHALL 使用该值替代默认配置，并记录在 court_view_roi artifact 的 thresholds 字段中

### Requirement: 过严门控导致渲染稀疏时应有诊断提示
当 court-view gate 导致的剔除比例超过阈值（如 `non_court_view_frame_count / processed_frame_count > 0.9`）时，系统 SHALL 在任务日志或 artifact detail 中输出预警提示，不自动中断任务。

#### Scenario: 高剔除率预警
- **WHEN** 任务完成时 non_court_view_frame_count 超过 processed_frame_count 的 90%
- **THEN** court_view_roi artifact 的 detail 字段 SHALL 包含类似"门控剔除率过高（XX%），骨架输出可能极度稀疏"的提示
