## ADDED Requirements

### Requirement: 运行状态轮询

前端 SHALL 在 CaptureTake 处于 `recording`、`stopping` 或 `recovering` 阶段时按固定间隔轮询运行状态，并以当前 `captureTakeId` 校验响应归属。

#### Scenario: 录制中轮询

- **WHEN** runtime phase 为 `recording`
- **THEN** 前端 SHALL 以不高于 2 秒的间隔请求运行状态
- **AND** SHALL 使用最新成功响应更新工作台指标

#### Scenario: 过期响应

- **WHEN** 页面已切换到另一个 CaptureTake
- **AND** 旧 Take 的运行状态响应随后返回
- **THEN** 前端 SHALL 丢弃旧响应
- **AND** 不得污染当前页面指标

### Requirement: 运行状态降级

运行状态数据不可用时，前端 SHALL 将每个指标单独显示为 loading、采集中、不可用或错误，不得因为单项指标失败隐藏整个工作台。

#### Scenario: 首次请求尚未返回

- **WHEN** 页面尚未收到任何运行状态快照
- **THEN** 指标区 SHALL 展示稳定的 loading 或 collecting 占位

#### Scenario: 部分指标不可用

- **WHEN** API 返回存储和文件大小但有效帧率为 unavailable
- **THEN** 页面 SHALL 正常展示可用指标
- **AND** 仅将有效帧率标记为不可用

### Requirement: 终态停止轮询

前端 SHALL 在 CaptureTake 进入 `completed`、`partial`、`failed` 或 `canceled` 后停止运行状态轮询，并保留最后一次快照用于完成信息展示。

#### Scenario: 正常停止

- **WHEN** runtime phase 进入 `completed`
- **THEN** 前端 SHALL 停止定时器
- **AND** SHALL 展示最后一次后端返回的文件大小、存储和轨道结果
