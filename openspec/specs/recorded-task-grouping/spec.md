# recorded-task-grouping Specification

## Purpose
TBD - created by archiving change group-recorded-tasks-by-field-session. Update Purpose after archive.
## Requirements
### Requirement: 按采集任务分组展示录制视频任务
系统 SHALL 在「分析任务」页面的「录制视频任务」Tab 中，按 `FieldSession`（采集任务）对 `RecordingSession` 进行分组展示：先呈现采集任务大分组卡，再在其下分类展示属于该采集任务的录制任务条。

#### Scenario: 录制归属于某采集任务
- **WHEN** 一条 `RecordingSession` 的 `field_session_id` 指向一个已存在的 `FieldSession`
- **THEN** 系统 SHALL 将该录制任务条渲染在对应采集任务分组卡之下
- **AND** 该分组卡的录制数徽标 SHALL 随之增加

#### Scenario: 进入录制 Tab 加载分组骨架
- **WHEN** 用户切换到「录制视频任务」Tab
- **THEN** 前端 SHALL 先获取全量 `FieldSession` 列表作为分组骨架，再获取全部 `RecordingSession` 并按 `field_session_id` 分发到对应分组

#### Scenario: 复用既有录制任务条
- **WHEN** 录制被渲染在分组内
- **THEN** 系统 SHALL 复用既有的 `RecordingTaskCard`（含播放、开始分析、查看分析结果、删除等动作），不重写其行为

### Requirement: 采集任务分组卡展现采集上下文
系统 SHALL 在每组采集任务的大分组卡头部展示足以辨识该采集任务的上下文信息。

#### Scenario: 分组卡头部字段
- **WHEN** 系统渲染一个采集任务分组卡
- **THEN** 头部 SHALL 包含采集任务 `title`、`venue` 与 `court_name`、状态标签、录制数徽标，以及组内最近一次录制的时间

#### Scenario: 组内存在录制中任务
- **WHEN** 某采集任务分组内存在 `status` 为 `recording` 的录制
- **THEN** 该分组卡 SHALL 以高亮方式提示"录制中"

### Requirement: 分组卡支持展开与收起
系统 SHALL 允许用户在「录制视频任务」Tab 中对每个采集任务分组卡执行展开 / 收起操作。

#### Scenario: 收起分组
- **WHEN** 用户点击某采集任务分组卡的收起控件
- **THEN** 系统 SHALL 隐藏该分组内的录制任务条列表，仅保留分组卡头部信息

#### Scenario: 展开分组
- **WHEN** 用户点击已收起分组卡的展开控件
- **THEN** 系统 SHALL 重新展示该分组内的录制任务条列表

#### Scenario: 默认展开
- **WHEN** 用户首次进入录制 Tab 或刷新页面
- **THEN** 所有采集任务分组卡 SHALL 默认处于展开状态

### Requirement: 展示空采集任务分组
系统 SHALL 为没有录制的 `FieldSession` 也渲染分组卡（空分组），不遗漏任何采集任务。

#### Scenario: 空采集任务分组
- **WHEN** 一个 `FieldSession` 当前没有关联的 `RecordingSession`
- **THEN** 系统 SHALL 仍渲染该采集任务分组卡
- **AND** 其列表区 SHALL 显示"暂无录制"占位

### Requirement: 未归类录制兜底分组
系统 SHALL 将无法归入任何采集任务的录制归入一个独立的「未归类录制」兜底分组，避免数据丢失。

#### Scenario: 录制无 field_session_id
- **WHEN** 一条 `RecordingSession` 的 `field_session_id` 为空
- **THEN** 系统 SHALL 将其归入「未归类录制」分组

#### Scenario: 录制指向已删除的采集任务
- **WHEN** 一条 `RecordingSession` 的 `field_session_id` 指向一个已不存在的 `FieldSession`
- **THEN** 系统 SHALL 将其归入「未归类录制」分组

#### Scenario: 未归类组始终置底
- **WHEN** 系统渲染分组列表
- **THEN** 「未归类录制」分组 SHALL 始终排在所有具名采集任务分组之后

### Requirement: 分组排序规则
系统 SHALL 对分组及组内录制采用稳定可预期的排序。

#### Scenario: 组间排序
- **WHEN** 系统渲染多个具名采集任务分组
- **THEN** 分组 SHALL 按"组内最近录制时间"倒序排列；空分组按 `FieldSession.created_at` 倒序参与排序

#### Scenario: 组内录制排序
- **WHEN** 系统渲染某采集任务分组内的录制
- **THEN** 录制任务条 SHALL 按 `started_at` 倒序排列

### Requirement: 顶部统计保持全量计数
系统 SHALL 在分组渲染之外，继续基于全部 `RecordingSession` 计算并展示顶部统计卡片（全部录制 / 录制中 / 已完成 / 失败·取消）。

#### Scenario: 统计与分组解耦
- **WHEN** 用户查看「录制视频任务」Tab
- **THEN** 顶部统计卡片的数字 SHALL 基于录制全量计算，不受分组展开/收起或分组顺序影响

