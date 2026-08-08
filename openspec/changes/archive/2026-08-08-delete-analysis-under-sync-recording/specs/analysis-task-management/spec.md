# analysis-task-management Delta Specification

## ADDED Requirements

### Requirement: 双摄录制卡片删除分析任务

「双摄录制」Tab 的录制卡片 SHALL 在存在分析任务时提供「删除分析任务」入口，用于清除该录制派生的所有分析任务及其本地产物，同时保留录制本身。

#### Scenario: 卡片显示删除分析任务按钮

- **WHEN** 录制卡片存在任一分析任务（multiview Parent、A 机位或 B 机位单摄任务）
- **THEN** 卡片 SHALL 提供「删除分析任务」操作
- **AND** 该操作 SHALL 区别于「删除」（整条录制）按钮

#### Scenario: 卡片无分析任务时不显示

- **WHEN** 录制卡片不存在任何分析任务
- **THEN** 卡片 SHALL 不显示「删除分析任务」操作

#### Scenario: 用户确认后删除分析任务

- **WHEN** 用户确认删除该录制的分析任务
- **THEN** 前端 SHALL 调用后端录制级删除接口
- **AND** 删除完成后 SHALL 刷新任务列表
- **AND** 录制卡片 SHALL 保留在「双摄录制」Tab

#### Scenario: 有活跃分析任务被阻断

- **WHEN** 删除结果中包含 `blocked`（处理中任务）或 `failed` 项
- **THEN** 前端 SHALL 报告哪些任务已删除、哪些需要用户处理
- **AND** SHALL NOT 将阻塞项当作删除成功移除

### Requirement: 分析任务删除清理完整产物目录

删除分析任务 SHALL 清除该任务在本地磁盘的**完整产物目录**，而不只是部分已知文件；录制资产 MUST NOT 被误删。

#### Scenario: capture job 产物目录整体删除

- **WHEN** 用户删除一个产物位于 `take_dir/analysis/<job_id>/` 的 capture 分析任务
- **THEN** 后端 SHALL 删除该 `<job_id>` 目录及其全部内容，包括 `analysis_overlay.mp4`、`position_visualizations/`、`fused_*.json`、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`、`player_render_trajectory.json`、`players_trajectory.*`、`detections.jsonl` 等
- **AND** `take_dir` 下的录制视频、分段与 `sync_calibration.json` SHALL 保留

#### Scenario: 删除路径安全校验

- **WHEN** 后端准备整体删除分析任务产物目录
- **THEN** 目标路径 SHALL 严格匹配 `<take_dir>/analysis/<job_id>` 或 `<outputs_dir>/<job_id>` 格式
- **AND** `job_id` SHALL 以 `job-` 前缀开头并仅含 URL 安全字符（`^job-[A-Za-z0-9_-]+$`），避免误删录制目录

#### Scenario: 非 capture job 行为不变

- **WHEN** 用户删除产物位于 `<outputs_dir>/<job_id>` 的非 capture 分析任务
- **THEN** 后端 SHALL 删除该 job 的输出目录
- **AND** 既有删除行为 SHALL 保持一致
