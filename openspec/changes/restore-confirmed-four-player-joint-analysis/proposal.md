## Why

真实双摄任务 `job-9a640b069a` 已冻结用户确认的四人名册（P1/P2 为 A 队、P3/P4 为 B 队），但正式 joint 跟踪的 Global Roster 始终停在 `BOOTSTRAPPING`、确认人数为 0；可用位置轨迹几乎只覆盖同一半场的两人，视频与热力图仍以 P 编号展示这些未完成身份确认的结果。用户的赛前登记没有形成持续四人跟踪与可信身份展示，任务却以 `completed` 发布。

## What Changes

- 在 `joint_tracking_v2` 执行前加载并校验 Job 冻结的 `AnalysisRosterSnapshot`，把四个身份锚点、Team A/B 和初始端位传入正式跟踪；锚点仅在对应时间和机位参与证据匹配，不充当其他时刻的观测。
- 让双打 Global Roster 按 canonical 球场端位维持两侧各两个候选槽位，诊断并处理早期错误候选占满四槽、后续真实球员长期进入 `unresolved_no_slot` 的情况；保留跨帧、跨机位身份唯一性门槛。
- 将用户槽位到 global 身份的逐人审计作为视频标签、热力图、位置指标和报告的共同身份来源。无法确认时展示明确的未知身份或不可用状态，不把顺序补位编号当作已确认 P 身份。
- 将原始检测、局部跟踪、global 关联、身份确认和正式覆盖率分层统计；四人覆盖不足、同侧集中或长时间无球员时，任务结果明确标记质量不足并指出主要断点。
- 用本次真实双摄素材新建分析 Job 做前后对照，并验证四人覆盖率、两侧归属、最长缺失、身份互换和前端降级展示。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `analysis-roster-confirmation`：冻结名册必须实际进入 joint 跟踪，身份锚点与正式 global 身份完成可审计绑定。
- `multiview-player-identity-stability`：双打分侧依据冻结的 Team 与初始端位及 canonical 球场坐标，Global Roster 不得由同侧重复候选占满。
- `four-player-identification-quality`：分层覆盖率与断点、真实四人质量门槛及新 Job 验收要能识别本次失败。
- `multiview-fused-player-overlay`：用户可见 P 标签必须由已确认的冻结名册映射授权。
- `structured-heatmap`：每人图层只使用已确认身份的有效轨迹，并显式呈现缺失槽位与质量不足。

## Impact

影响 joint executor、`MultiViewJointRun`、Global Roster/association、bootstrap binding audit、结果组装、四人质量产物、fused overlay、位置可视化及分析页。保持现有 API 路径和历史 Job 可读；新增字段以兼容方式扩展产物。真实视频回归需要创建新 Job，旧 Job 产物不被改写为“修复后”结果。
