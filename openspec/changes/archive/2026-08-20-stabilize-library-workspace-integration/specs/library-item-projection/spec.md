# library-item-projection Specification

## Purpose
在统一投影层补充统一展示状态（displayState）与语义化标题，供 UI 筛选、卡片、Workspace 门控等消费，根除「UI 直接理解底层多轴状态、标题等于 court_name」的问题。

## MODIFIED Requirements

### Requirement: 统一 LibraryItem 投影

系统 SHALL 将 upload / recording / sync_recording 三类来源投影为统一的 `LibraryItemViewModel`，作为用户层主对象，暴露统一身份、三轴生命周期状态（media × availability × analysis）、统一展示状态（displayState）与展示元数据。

#### Scenario: 三类来源统一被投影为 LibraryItem
- **WHEN** 前端存在一个 upload video、一个 RecordingSession、一个 SyncRecordingSession
- **THEN** 三类数据均 SHALL 投影为 `LibraryItemViewModel`，且携带各自的 `LibraryItemRef`（kind + sourceId）

#### Scenario: 展示元数据
- **WHEN** 渲染某个 LibraryItem
- **THEN** 系统 SHALL 提供 title、displayState、thumbnailUrl、previewUrl、sourceType、matchFormat、cameraSetup、startedAt、durationSec、venue、courtName 等字段（缺失时隐藏对应展示而非伪造）

#### Scenario: 语义化标题
- **WHEN** 渲染某 LibraryItem 的标题
- **THEN** 系统 SHALL 按分析 metadata.matchTitle → FieldSession 标题 →「时间 + 比赛形式」→ raw id 的优先级解析语义标题
- **AND** `court_name` 只作为 `courtName` 次要 metadata，SHALL NOT 直接当作用户可见主标题

### Requirement: 三轴生命周期状态

LibraryItem SHALL 使用正交的媒体生命周期（mediaState）、可访问性（availabilityState）与分析生命周期（analysisState），而非单一合并状态；并额外派生统一的用户展示状态 `displayState`（待处理 / 正在分析 / 分析完成 / 失败 / 待合并 等）供 UI 直接消费。

#### Scenario: 状态派生
- **WHEN** mediaState 为 `ready` 且 analysisState 为 `running`
- **THEN** UI 显示「正在分析 62%」

#### Scenario: 录制中
- **WHEN** mediaState 为 `recording`
- **THEN** UI 显示「正在录制」

#### Scenario: 分析完成/失败
- **WHEN** mediaState 为 `ready` 且 analysisState 为 `succeeded`
- **THEN** UI 显示「分析完成」
- **WHEN** analysisState 为 `failed`
- **THEN** UI 显示「分析失败」

#### Scenario: 存储暂不可用不等同于失败
- **WHEN** mediaState 为 `ready`、analysisState 为 `succeeded` 且 availabilityState 为 `unavailable`（如外置存储掉线）
- **THEN** UI SHALL 显示「分析完成 · 视频存储暂不可用」
- **AND** SHALL NOT 将 mediaState 解释为 `failed`

#### Scenario: displayState 统一派生
- **WHEN** Adapter 投影一个 LibraryItem
- **THEN** 系统 SHALL 派生 `displayState`：requiredAction=merge → 待合并；mediaState=ready 且 analysisState=running → 正在分析；analysisState=succeeded → 分析完成；analysisState=failed → 分析失败；其余 → 待处理
- **AND** UI 的「状态筛选」SHALL 消费 `displayState` 而非直接读取底层多轴状态

#### Scenario: displayState 与底层状态解耦
- **WHEN** mediaState=ready 且 analysisState=running
- **THEN** `displayState` SHALL 为「正在分析」
- **AND** 系统 SHALL NOT 将其落入「已完成」筛选