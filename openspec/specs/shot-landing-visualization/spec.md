# shot-landing-visualization Specification

## Purpose
定义素材工作区独立落点视图的展示契约：仅消费 selected Job 的 `shot-landings.v1`，提供连续坐标与项目十二区两种模式，支持按 canonical 上下文筛选、选中 Shot 并回溯视频，并诚实呈现加载、空、失败与部分可用状态。
## Requirements
### Requirement: 素材工作区提供独立落点视图

系统 SHALL 在 LibraryItemWorkspace 中提供独立 `landing` view，并且 SHALL 仅消费当前 selected Job 的 `shot-landings.v1`。

#### Scenario: 进入落点 Tab
- **WHEN** selected Job 发布了可读的 `shot_landings_url`
- **THEN** 工作区 SHALL 启用“落点”Tab
- **AND** 进入后 SHALL 展示该 selected Job 的落点数据

#### Scenario: 旧任务缺少落点 artifact
- **WHEN** selected Job 未发布 `shot_landings_url`
- **THEN** “落点”Tab SHALL 禁用或显示“该版本未生成落点分析”空态
- **AND** SHALL NOT 使用其他 Job 或 bounce 散点伪造结果

#### Scenario: 落点与三维球路独立
- **WHEN** selected Job 的三维球路不可用但 `shot-landings.v1` 可读
- **THEN** “落点”Tab SHALL 仍可用
- **AND** SHALL NOT 因 `trajectoryReady=false` 禁用落点视图

### Requirement: 落点视图提供连续坐标与十二区两种可用模式

落点视图 SHALL 提供“连续落点”和“项目十二区”模式。连续模式 SHALL 使用保留的实际坐标；十二区模式 SHALL 以 Shot Landing 数量而不是停留时间为分子和分母。

#### Scenario: 显示连续落点
- **WHEN** 用户选择“连续落点”
- **THEN** 每个坐标可用的 Landing SHALL 按其真实位置绘制
- **AND** 界外坐标在可视 buffer 内时 MAY 显示为界外点
- **AND** 前端 MUST NOT 将界外点 clamp 到球场边线

#### Scenario: 显示十二区矩阵
- **WHEN** 用户选择“项目十二区”
- **THEN** 页面 SHALL 显示 K/T/D/VD × L/C/R 的 12 个区域
- **AND** 每区 SHALL 显示 count 与相对于可进入分区落点总数的占比
- **AND** 颜色深浅 SHALL 只表达该占比，不表达落点质量评分

#### Scenario: 论文六区待配置
- **WHEN** `paper6.v1` 未冻结
- **THEN** 页面 MAY 显示“论文六区·待配置”入口
- **AND** 该入口 SHALL 为禁用状态
- **AND** SHALL NOT 显示临时 FZ1–FZ6 数据

### Requirement: 落点数据可按 canonical 上下文筛选

页面 SHALL 支持按 Player、Rally、Shot Stage 和置信门限筛选，并将相同筛选集合同时应用于散点、分区矩阵、摘要指标和 Shot 列表。

#### Scenario: 按球员和拍序筛选
- **WHEN** 用户选择 Player_2 和 `third`
- **THEN** 所有落点视觉与摘要 SHALL 只包含 `hitter_player_id=Player_2` 且 `shot_stage=third` 的项

#### Scenario: 不可用状态可被审计
- **WHEN** 当前筛选集合包含无弹地、无坐标或方向不明的 Shot
- **THEN** 页面 SHALL 在摘要或 Shot 列表中区分显示这些状态
- **AND** SHALL NOT 把它们作为 `(0,0)` 落点绘制

### Requirement: 落点可选中并回溯到 Shot 与视频

连续落点、分区内落点 overlay 和 Shot 列表 SHALL 共享 selected `shot_id`。用户 SHALL 能从选中 Landing 查看其球员、Rally、拍序、时间、绝对坐标、分区、质量和证据状态，并跳到同一素材的视频。

#### Scenario: 点击散点选中 Shot
- **WHEN** 用户点击一个 Landing 散点
- **THEN** 页面 SHALL 选中对应 `shot_id`
- **AND** SHALL 显示该 Landing 的 provenance 与可用字段

#### Scenario: 从落点跳转视频
- **WHEN** 用户对已选中 Landing 触发“查看视频”
- **THEN** 工作区 SHALL 以 replace 语义切换到同一 Library Item 的 `view=video`
- **AND** SHALL 保留当前 selected `analysisJob`
- **AND** 视频定位时间 SHALL 为 `max(0, landing_timestamp_ms - 1200)`

#### Scenario: 选中项被筛选排除
- **WHEN** 用户修改筛选条件使当前 selected Shot 不再可见
- **THEN** 页面 SHALL 清除该选中或确定性选择筛选后的第一条
- **AND** SHALL NOT 显示与当前图形不一致的旧 Shot 详情

### Requirement: 落点页面诚实显示加载、空、失败与部分可用状态

落点页面 SHALL 根据 artifact 的 status/detail 和数据内容区分 loading、available、empty、partial/unavailable 与 failed，且嵌入工作区时 SHALL NOT 渲染旧的独立页 shell。

#### Scenario: Artifact 可读但没有 Shot
- **WHEN** `shot-landings.v1` 可读且 landings 数组为空
- **THEN** 页面 SHALL 显示“未找到可分析 Shot”或等价空态
- **AND** SHALL NOT 显示伪造示例点

#### Scenario: 部分 Shot 无落点坐标
- **WHEN** artifact 包含可用落点与不可用 Shot 的混合结果
- **THEN** 页面 SHALL 继续展示可用落点
- **AND** SHALL 显示空间可测分子/分母或等价的数据完整性提示

#### Scenario: Artifact 读取失败
- **WHEN** manifest 宣告落点可用但 API 读取失败或 payload 无法验证
- **THEN** 页面 SHALL 显示可理解的错误与重试/检查指引
- **AND** SHALL NOT 回退到 bounce 候选散点

