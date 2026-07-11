## MODIFIED Requirements

### Requirement: 查询时间线事件

**变更**：修复前端 `listTimelineEvents` 调用参数错误。

**修改前**：`useLiveCoding` 中两处调用为 `listTimelineEvents({ capture_take_id, limit: 200 } as any)`，将对象转为 URL 中的 `[object Object]`，导致初始化或刷新时无法正确恢复事件。

**修改后**：系统 SHALL 使用正确的双参数签名 `listTimelineEvents(fieldSessionId, params)` 调用。
- `capture_take_id` SHALL 作为 `params` 的字段传递，而非取代 `fieldSessionId` 位置
- `limit` 参数 SHALL 按实际 API 设计传递，不传递不支持的筛选字段
