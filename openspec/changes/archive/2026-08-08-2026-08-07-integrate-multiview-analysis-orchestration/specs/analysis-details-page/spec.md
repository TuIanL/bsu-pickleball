# analysis-details-page Specification

## Purpose

TBD - created by archiving change analysis-task-management-delete-and-details. Update Purpose after archive.

本 Change 为 `analysis-details-page` 新增：multiview Parent 任务的聚合阶段展示、`viewRuns` 子进度、fusion/fallback 状态、数据来源与融合质量；降级提示明确展示，技术细节只放技术详情。

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Job-specific analysis details page

系统 MUST 支持 multiview Parent 任务的详情展示：以聚合阶段进度呈现（素材与同步检查 → A 机位视觉分析 → B 机位视觉分析 → 多视角融合 → 指标重算 → 报告），并暴露 `viewRuns`（`cam_1 / cam_2` 各自的 `status / stage / progress`）两路子进度，不铺 24 行单摄阶段。

#### Scenario: Parent 双摄任务进度

- **WHEN** 用户打开 `analysisKind=multiview` 的 Parent 任务详情
- **THEN** 页面 SHALL 展示六个聚合阶段
- **AND** 同时展示 A/B 两路子进度（`viewRuns`：状态 / 当前阶段 / 百分比）

#### Scenario: 单摄任务详情不变

- **WHEN** 用户打开 `analysisKind=single_view` 的任务详情
- **THEN** 页面 SHALL 维持既有单摄阶段展示
