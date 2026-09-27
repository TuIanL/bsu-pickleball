# segment-player-view-controls Delta

## REMOVED Requirements

### Requirement: 片段回放器全屏切换

**Reason**: `SegmentVideoPlayer` 组件随片段管理页整体删除，其独立的全屏切换控件不复存在。数据分析视图主画面的全屏能力由 `visual-analysis-workspace` 的「Fullscreen real-video overlay playback」契约覆盖，不受本变更影响。

**Migration**: 全屏播放入口统一为数据分析视图主画面。

### Requirement: 全屏对象范围与画面填充口径

**Reason**: 该口径绑定 `SegmentVideoPlayer` 的全屏实现；组件删除后无消费者。VideoAnalysisCard 的全屏填充口径由 `visual-analysis-workspace` 既有契约覆盖。

**Migration**: 无替代需求；数据分析视图全屏行为见 `visual-analysis-workspace`。

### Requirement: 片段回放器静音切换

**Reason**: `SegmentVideoPlayer` 删除，其静音控件随之消失。VideoAnalysisCard 的播放控制不受本变更影响。

**Migration**: 无替代需求。

### Requirement: 回放器键盘快捷键

**Reason**: 该 requirement 绑定 `SegmentVideoPlayer` 的键盘快捷键（逐帧/播放暂停/静音等）。组件删除后快捷键随之消失；VideoAnalysisCard 的快捷键行为不在此契约内，保持既有实现。

**Migration**: 逐帧与播放控制在数据分析视图沿用 VideoAnalysisCard 既有交互。

### Requirement: 双摄并排场景下的全屏边界

**Reason**: 双摄并排播放是 QA 复核模式的形态，随 QA 前端整体删除；数据分析视图维持单 display view 播放。

**Migration**: 无替代需求。双摄对比播放不再提供（刻意的产品收窄）。
