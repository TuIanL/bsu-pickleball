# segment-manager Delta

## REMOVED Requirements

### Requirement: 片段页视频回放源解析

**Reason**: 片段管理页整体删除。数据分析视图的播放源由分析任务自身决定（job 视频/叠加视频 + displayView 机位选择），不再消费 CaptureTake 的 `video_ids` 列表解析播放源；「不得使用 `source_session_id` 拼流地址」的防错约定随该代码路径一并消失。

**Migration**: 回放入口统一为数据分析视图；无替代的机位列表解析需求。

### Requirement: 片段页视频不可用反馈

**Reason**: 片段管理页删除，其独立播放器与「暂无可用视频回放」反馈随之消失；数据分析视图的视频不可用反馈由 `visual-analysis-workspace` 既有契约覆盖。

**Migration**: 视频不可用状态由数据分析视图呈现，无独立片段页反馈。

### Requirement: 片段页数据加载独立兜底

**Reason**: 行为整体迁入新能力 `analysis-view-segment-panel`（同名的「片段面板数据加载独立兜底」requirement），原页面专属措辞移除。

**Migration**: 由 `analysis-view-segment-panel` 的「片段面板数据加载独立兜底」承接，语义保持：三数据源独立 try/catch，任一失败只降级对应区块。

### Requirement: 片段列表提供明确的播放与编辑入口

**Reason**: 片段管理页删除。播放入口迁入数据分析视图片段面板（`analysis-view-segment-panel` 的「片段列表与播放器联动」）；编辑入口按产品决策全部移除，前端切分数据只读化。

**Migration**: 点击回合行定位并起播 → 见 `analysis-view-segment-panel`；边界/标签/复核编辑无前端替代（后端契约保留）。

### Requirement: 片段管理页保持播放头和列表高亮同步

**Reason**: 行为迁入数据分析视图的片段面板（`analysis-view-segment-panel` 的「片段列表与播放器联动」），原页面专属措辞移除。

**Migration**: 播放头与列表高亮同步由片段面板承接。

### Requirement: 片段边界编辑明确影响范围

**Reason**: QA 复核与边界编辑前端整体删除（产品决策：切分结果前端完全只读）；后端编辑契约（`segment-editing`）保留。

**Migration**: 无前端替代。若未来恢复边界复核流程，需重建前端并重新立 spec。
