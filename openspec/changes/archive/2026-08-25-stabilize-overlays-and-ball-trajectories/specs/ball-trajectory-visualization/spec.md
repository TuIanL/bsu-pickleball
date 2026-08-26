## ADDED Requirements

### Requirement: 相邻球路片段唯一渲染

前端球路 compositor 在每个播放时刻 SHALL 以 `render_view_id`、时间窗口和稳定 `segment_id` 过滤并去重，默认只渲染一个 active segment 的视频尾迹。已结束 segment 的 retention 只有在不存在已开始的后继 segment 时才允许生效；不得因固定 retention 窗口同时绘制两条相邻轨迹。

#### Scenario: 33 秒相邻片段切换
- **WHEN** `flight-42` 在 33.166 秒结束且 `flight-43` 从 33.166 秒开始
- **THEN** 33.166 秒及之后的活动轨迹 SHALL 只包含 `flight-43`
- **AND** SHALL NOT 因 `flight-42` 的 retention 与 `flight-43` 同时产生两条视频轨迹

#### Scenario: 不同 primary view 不产生双坐标叠加
- **WHEN** 相邻 segment 的 `primary_view_id` 分别为 `cam_2` 和 `cam_1`
- **THEN** compositor SHALL 先统一到任务 `render_view_id`
- **AND** 若某段无法统一， SHALL 跳过该段的视频 path并保留可查询的 skip reason

#### Scenario: 重复 segment 输入
- **WHEN** adapter 因重试、插值或旧 artifact 返回相同 `segment_id` 的重复记录
- **THEN** compositor SHALL 只保留一份确定性 geometry
- **AND** 不得通过重复记录叠加线宽、透明度或端点

#### Scenario: 时间边界回放稳定
- **WHEN** 播放器在 segment start/end 边界前后往返拖动
- **THEN** 同一时刻 SHALL 得到相同的 active segment 集合和同一 `render_view_id`
- **AND** SHALL 不出现边界前后两条路径短暂同时闪现
