## Why

当前系统已有球轨迹、正式 Bounce 事件、canonical Shot 和 20 ft × 44 ft 球场坐标，但还没有把这些证据组合成“每个 Shot 的首次正式落点”这一可追溯事实层。因此现有弹跳候选只能用于辅助复盘，无法稳定支持按球员、Rally 和拍序的落点分布与视频回溯。

## What Changes

- 新增 `shot-landings.v1` 事实 artifact，以 `shot-rally-events.v1` 的 canonical `shot_id` 为唯一 Shot 身份权威，沿 `trajectory.segment_ids → end_event_id → event_id` 精确关联首个正式 Bounce。
- 将落点可用性、球场位置和目标半场关系分离为 `landing_status`、`court_location` 和 `target_relation`；界外落点保留真实坐标，但不进入分区统计。
- 保存绝对球场英尺坐标作为长期空间真值，并在击球者接触时位置或球路方向证据充足时，生成面向目标半场的标准化坐标。
- 新增版本化 `project12.v1` 十二区 profile，支持连续落点与十二区统计；论文六区只保留可扩展位置，本变更不冻结其边界。
- 打通 StorageService、Pipeline Result Manifest、Backend Schema、artifact API 和前端 client 的完整发布契约，并对旧任务显式降级为不可用。
- 在素材工作区新增独立“落点”视图，提供连续散点、十二区矩阵、Player / Rally / Stage / confidence 筛选、Shot 详情及按落点时刻回溯视频。
- 落点 capability 与三维球路 capability 独立门控，允许在三维球路不可用时仍展示有效地面落点。
- 本变更不重新运行球检测、不重建 Shot 身份、不做自动界内外裁判、落点水平评分、战术优劣结论或训练建议，也不在本轮实现 per-Shot 双摄全量融合。

## Capabilities

### New Capabilities

- `shot-landing-facts`: 定义 canonical Shot 到首次正式 Bounce 的确定性组合、落点状态机、坐标真值、目标半场标准化、版本化分区与 provenance。
- `shot-landing-visualization`: 定义素材工作区落点视图、连续散点与十二区矩阵、筛选、Shot 选中和视频时刻联动。

### Modified Capabilities

- `analysis-artifacts`: 将 `shot-landings.v1` 纳入分析产物的存储、manifest 状态、API 发布与缺失降级契约。
- `library-item-workspace`: 新增独立“落点”子视图及基于 `shot_landings_url` 的独立 capability 门控。

## Impact

- 后端：新增 Shot Landing schema/composer/profile，并扩展完成任务后的 canonical artifact 组合流程、StorageService、pipeline result schema 和 artifact route。
- 前端：扩展 report types、analysisClient、LibraryView capability 与 workspace tab，新增落点页面及专用可视化组件。
- 数据：新增 job 级 `shot_landings.json`；继续保持现有 `shot-rally-events.v1`、球轨迹、Bounce 和双摄产物的身份与证据权威不变。
- 向后兼容：历史任务不回填伪造落点；未发布新 artifact 时“落点” capability 显式不可用，其他分析视图不受影响。
