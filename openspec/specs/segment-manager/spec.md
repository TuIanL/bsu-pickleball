# segment-manager Specification

## Purpose

定义片段管理页（SegmentManagerPage）的前端行为：单摄/双摄视频回放源解析、数据加载的独立兜底与错误/空态反馈，确保片段页可加载、可播放、可操作。
## Requirements
### Requirement: 片段页视频回放源解析

系统 MUST 使用可播放的 `video_id` 构造视频流地址，MUST NOT 使用 `source_session_id`（采集会话 ID）作为视频流 ID。

#### Scenario: 单摄素材播放原视频

- **WHEN** CaptureTake 的 `video_ids` 恰好包含一个元素
- **THEN** 播放器源 SHALL 指向 `/api/videos/{video_ids[0]}/stream`
- **AND** 播放器 SHALL 展示单个视频轨道选项

#### Scenario: 双摄素材多机位切换

- **WHEN** CaptureTake 的 `video_ids` 包含多个元素（如 cam_1、cam_2）
- **THEN** 播放器 SHALL 提供机位切换下拉
- **AND** 每个机位 SHALL 指向各自 `/api/videos/{video_id}/stream`
- **AND** 默认选中第一个机位

#### Scenario: 不使用采集会话 ID 拼流地址

- **WHEN** 页面构造视频流 URL
- **THEN** SHALL NOT 使用 `source_session_id` 作为 `video_id`

### Requirement: 片段页视频不可用反馈

系统 MUST 在视频源缺失或不可播放时提供稳定的可见反馈，MUST NOT 静默黑屏。

#### Scenario: 无可用视频源

- **WHEN** `video_ids` 为空或全部不可播放
- **THEN** 页面 SHALL 显示「暂无可用视频回放」类稳定空态
- **AND** 页面 SHALL 保留片段列表与时间轴等其余功能

#### Scenario: 视频流请求失败

- **WHEN** 播放器请求 `/api/videos/{video_id}/stream` 返回 404 或解码失败
- **THEN** 页面 SHALL 显示播放失败/不可用状态

### Requirement: 片段页数据加载独立兜底

系统 MUST 将 take 详情、片段列表、时间轴事件三个数据源独立加载、独立兜底，任一失败不得瘫痪整页。

#### Scenario: 单一数据源失败

- **WHEN** take 详情、segments、timeline-events 中某一个请求失败
- **THEN** 其余成功的数据源 SHALL 正常展示
- **AND** 页面 SHALL 显示明确错误信息

#### Scenario: 关键数据源失败展示错误态

- **WHEN** take 详情（页面渲染必需）请求失败
- **THEN** 页面 SHALL 展示错误态与重试入口
- **AND** 页面 SHALL NOT 永久停留在「加载中...」

### Requirement: 片段列表提供明确的播放与编辑入口

普通片段管理页 SHALL 将片段分为“现场人工标记”和“自动回合切分”两个逻辑区域。人工区域展示拍摄阶段产生的人工关键事件或人工片段；自动区域仅展示当前已发布 SegmentationRun 的 active algorithm Rally，并在区域顶部展示一次模型版本、生成时间和回合数。每条片段 SHALL 提供播放/定位、ordinal、有效边界、持续时长、来源和可用的关联分析结果入口；普通页面 MUST NOT 提供候选 accept/correct/reject、边界复核、边界拖拽、补录 Rally、改序号、split/merge/archive/restore 或 AnalysisBatch 创建入口。

#### Scenario: 用户浏览自动回合
- **WHEN** CaptureTake 存在当前已发布的 SegmentationRun
- **THEN** 页面 SHALL 在“自动回合切分”区域显示其 active algorithm Rally
- **AND** SHALL 显示该 run 的模型版本、生成时间和回合计数摘要一次
- **AND** 不得为每条 Rally 显示研发期置信度、阈值或复核按钮

#### Scenario: 用户浏览现场人工标记
- **WHEN** CaptureTake 存在人工关键事件或人工片段
- **THEN** 页面 SHALL 在“现场人工标记”区域展示它们
- **AND** SHALL 不把它们伪装成模型自动回合或改变其原始时间

#### Scenario: 点击片段播放
- **WHEN** 用户点击任一可播放片段的播放区域
- **THEN** 页面 SHALL 播放该片段有效区间并高亮对应行
- **AND** SHALL 不启动编辑、复核或分析批次创建

### Requirement: 片段管理页保持播放头和列表高亮同步

片段管理页 SHALL 将播放器当前时间传给时间线，并在列表、时间线片段块和播放结束状态之间保持一致。

#### Scenario: 右侧点击片段后同步

- **WHEN** 用户点击右侧某一分
- **THEN** 播放器 SHALL 从该分起点播放
- **AND** 时间线播放头 SHALL 跳转到相同时间
- **AND** 右侧对应行与时间线对应块 SHALL 高亮

#### Scenario: 播放自动停止

- **WHEN** 自动跳过开关关闭，且播放到该分的有效终点
- **THEN** 播放器 SHALL 自动暂停
- **AND** 高亮 SHALL 保留在最后播放的片段上

#### Scenario: 开启自动跳过时的连续播放

- **WHEN** 自动跳过开关开启，播放到某回合的有效终点，且其后仍存在 algorithm 回合区间
- **THEN** 播放器 SHALL 续播下一个区间并跳过两者之间的非比赛时间
- **AND** 列表高亮 SHALL 跟随到新播放的回合
- **AND** 时间线播放头 SHALL 与播放器当前时间保持同步
- **AND** 到达最后一个区间后 SHALL 停止并保留该区间的选中状态

#### Scenario: 被中断的播放不改动结束状态

- **WHEN** 自动跳过开关开启，且用户在某个区间播放期间拖动播放位置
- **THEN** 播放器 SHALL 停在用户指定的位置
- **AND** 高亮 SHALL 按该位置所在的区间更新或被清除
- **AND** SHALL NOT 触发续播到下一个区间

### Requirement: 片段边界编辑明确影响范围

普通片段管理页 SHALL 将时间线和片段边界作为只读的回放与定位信息。候选 review、人工边界编辑和管理 API 可为受控 QA / 开发入口保留，但普通页面 MUST NOT 请求或呈现这些工作流，也不得用本地草稿修改 `CaptureSegment`。

#### Scenario: 时间线回放不改变边界
- **WHEN** 用户拖动播放头、点击时间线片段或播放至片段终点
- **THEN** 页面 SHALL 仅更新播放位置和选中高亮
- **AND** MUST NOT 发送 Segment PATCH、review 决定或创建操作

#### Scenario: QA 能力与普通页面隔离
- **WHEN** 普通用户打开 SegmentManagerPage
- **THEN** 页面 SHALL 不调用 match-state candidate/review、boundary review 或 AnalysisBatch API
- **AND** 既有 QA API 的存在 SHALL 不改变普通页面的只读行为

