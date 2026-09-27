# analysis-view-segment-panel Specification

## Purpose

定义数据分析视图的只读片段面板、数据加载降级及其与主画面播放器的联动。

## Requirements

### Requirement: 数据分析视图右栏提供片段面板

数据分析视图（VisionPage）SHALL 在主画面右栏提供片段面板，承载原片段管理页普通模式的浏览内容：片段筛选（全部/盘/局/分）、自动回合切分摘要（切分状态徽标、模型版本、生成时间、回合数）、模型回合列表（只读）与拍摄阶段人工标记列表。片段数据 SHALL 通过分析任务元数据的 `capture_take_id` 反查对应 CaptureTake 获得。

#### Scenario: 完成态分析任务进入数据分析视图

- **WHEN** 已完成的分析任务关联了 CaptureTake，且用户进入数据分析视图
- **THEN** 主画面右栏 SHALL 渲染片段面板
- **AND** 面板 SHALL 展示筛选 pills、自动切分摘要、模型回合列表与人工标记列表
- **AND** SHALL NOT 渲染原片段管理页的页头、复核入口或独立播放器

#### Scenario: 模型回合列表只读呈现

- **WHEN** 面板渲染模型回合列表
- **THEN** 每一行 SHALL 展示回合标签与起止时间
- **AND** 系统 SHALL NOT 在面板内提供任何边界编辑、标签编辑或复核操作入口

#### Scenario: 人工标记列表独立呈现

- **WHEN** CaptureTake 存在 `source` 非 algorithm 且无 `segmentation_run_id` 的人工片段
- **THEN** 面板 SHALL 在模型回合列表之外单独展示人工标记列表
- **AND** 人工标记 SHALL NOT 混入模型回合列表

### Requirement: 片段面板数据加载独立兜底

片段面板的三个数据源（CaptureTake 详情、片段列表、正式切分摘要）SHALL 各自独立加载与兜底：任一数据源失败 SHALL 只降级对应区块（显示空态或摘要占位），MUST NOT 让面板或数据分析视图永久停留在加载中状态。

#### Scenario: 切分摘要请求失败

- **WHEN** 正式切分摘要接口请求失败
- **THEN** 面板 SHALL 显示「尚未生成正式模型结果」等占位
- **AND** 片段列表与人工标记列表 SHALL 正常渲染

#### Scenario: 片段列表请求失败

- **WHEN** 片段列表接口请求失败
- **THEN** 面板 SHALL 显示空列表状态
- **AND** 数据分析视图的其余能力（视频播放、叠加、报告入口）SHALL 不受影响

### Requirement: 片段列表与播放器联动

片段面板与主画面播放器 SHALL 共享同一播放头状态：当前播放头所在有效回合区间的列表行 SHALL 高亮；用户点击回合行 SHALL 使播放器定位到该回合的有效起点并自动开始播放；播放中的点击 SHALL 从新位置继续播放。

#### Scenario: 点击回合行定位并起播

- **WHEN** 用户点击模型回合列表中的某一回合行
- **THEN** 播放器 SHALL 定位到该回合的有效起点（`effective_start_ms` 缺省时取 `start_ms`）
- **AND** 播放器 SHALL 自动开始播放
- **AND** 该回合行 SHALL 立即高亮

#### Scenario: 播放头与列表高亮同步

- **WHEN** 播放器播放头进入或离开某个自动回合区间
- **THEN** 面板列表的高亮 SHALL 跟随到当前有效区间对应的行

#### Scenario: 点击不修改片段数据

- **WHEN** 用户点击回合行或面板任意交互控件
- **THEN** 系统 SHALL NOT 发送 Segment PATCH、边界复核决定或 AnalysisBatch 创建请求
- **AND** SHALL NOT 用本地状态修改任何 `CaptureSegment` 边界

### Requirement: 片段面板按素材形态降级

分析任务未关联 CaptureTake（如上传视频）或关联 take 无已发布切分结果时，片段面板 SHALL 显示明确的降级占位说明原因，且 MUST NOT 影响数据分析视图的其余能力。

#### Scenario: 上传视频的分析任务

- **WHEN** 分析任务没有 `capture_take_id`
- **THEN** 面板 SHALL 显示「该素材无片段数据」类占位并说明原因
- **AND** auto-skip 开关 SHALL 处于不可用状态并给出原因

#### Scenario: 关联 take 但无正式切分

- **WHEN** 分析任务关联了 CaptureTake，但该 take 没有已发布的正式切分结果
- **THEN** 面板 SHALL 显示空摘要与空模型回合列表
- **AND** auto-skip 开关 SHALL 处于不可用状态并给出原因

### Requirement: 回合毫秒轴与播放时间轴的映射契约

回合窗口毫秒（segment `start_ms`/`effective_*`）SHALL 按分析任务的 canonical 时间轴解释，与主画面播放器的 canonical 播放头同轴；回合定位 seek SHALL 经 canonical 到目标视频时间的换算（`canonicalTimeToSourceTimeMs`）完成；该换算 SHALL 集中在单一模块，MUST NOT 在多个组件内散落重复实现。

#### Scenario: 单摄任务恒等映射

- **WHEN** 分析任务为单视角且 displayTimeMapping 为恒等
- **THEN** 回合毫秒 SHALL 与源视频媒体毫秒一致

#### Scenario: 双摄任务经 canonical 换算

- **WHEN** 分析任务为双摄且播放器使用 displayTimeMapping
- **THEN** 回合命中判定 SHALL 使用 canonical 播放头对比回合区间
- **AND** 定位 seek SHALL 先把回合起点换算为目标视频时间再应用到媒体元素

#### Scenario: 时间轴判定验证门槛

- **WHEN** 使用含正式切分结果的真实双摄素材验证回合定位
- **THEN** 定位后的画面 SHALL 处于对应回合的内容中，SHALL NOT 出现系统性时间偏移
