## ADDED Requirements

### Requirement: 模式化顶层阶段图

系统 MUST 根据分析模式选择唯一的顶层阶段图，并按图定义的顺序返回 `stages`。`single_view` MUST 保持现有单摄稳定阶段顺序；`late_fusion_v1` MUST 使用 `multiview-input-check`、`multiview-view-a`、`multiview-view-b`、`multiview-fusion`、`multiview-metrics`、`multiview-visualization`、`multiview-report`；`joint_tracking_v2` MUST 使用 `multiview-input-check`、`multiview-joint`、`multiview-metrics`、`multiview-visualization`、`multiview-report`。双摄专用阶段 MUST NOT 被追加到单摄阶段列表末尾。

#### Scenario: 单摄阶段顺序保持兼容

- **WHEN** 前端读取一个 `single_view` 分析任务
- **THEN** API SHALL 按既有单摄稳定阶段顺序返回阶段
- **AND** 新的双摄阶段 ID SHALL NOT 出现在该任务的阶段列表中

#### Scenario: late fusion 按融合前后顺序展示

- **WHEN** `late_fusion_v1` Parent 正在运行
- **THEN** 阶段列表 SHALL 依次包含素材检查、A 机位、B 机位、融合、指标、可视化和报告
- **AND** `multiview-report` SHALL NOT 在 `multiview-fusion`、`multiview-metrics` 或 `multiview-visualization` 之前进入 active 或 done

#### Scenario: joint tracking 按协同分析顺序展示

- **WHEN** `joint_tracking_v2` Parent 正在运行
- **THEN** 阶段列表 SHALL 依次包含素材检查、双摄协同跟踪、指标、可视化和报告
- **AND** `multiview-report` SHALL 只能在 `multiview-joint` 及所有后处理阶段完成后进入 active

### Requirement: 顶层阶段状态转换受状态机约束

系统 MUST 通过统一状态机处理阶段开始、进度更新、完成、跳过、失败和取消事件。同一时刻顶层阶段最多一个为 `active`；当前阶段之后的阶段 MUST 保持 `pending`；阶段完成后才允许进入下一阶段；不在当前模式阶段图中的阶段 ID MUST NOT 被加入或更新。

#### Scenario: 当前阶段更新不提前点亮后续阶段

- **WHEN** `joint_tracking_v2` 的 `multiview-joint` 进度更新为 95
- **THEN** `multiview-joint` SHALL 为 `active` 且进度为 95
- **AND** 指标、可视化和报告阶段 SHALL 仍为 `pending`

#### Scenario: 阶段完成后推进到下一阶段

- **WHEN** 当前阶段收到完成事件且下一阶段可以执行
- **THEN** 当前阶段 SHALL 变为 `done`
- **AND** 下一阶段 SHALL 按顺序变为 `active`
- **AND** 其他更后阶段 SHALL 仍为 `pending`

#### Scenario: 失败和取消保留可解释终态

- **WHEN** 当前阶段收到失败或任务取消事件
- **THEN** 当前阶段 SHALL 分别变为 `failed` 或 `canceled`
- **AND** 后续阶段 SHALL NOT 被标记为 `done`
- **AND** API SHALL 返回对应的错误或取消状态，而不是继续显示下一阶段正在运行

### Requirement: 总体进度按阶段权重单调聚合

系统 MUST 使用当前模式阶段图的稳定权重和阶段进度计算总体 `progress`，取值范围为 0 到 100；MUST NOT 按阶段数量简单平均。对同一任务，新的总体进度 MUST NOT 小于已发布的总体进度；成功任务 SHALL 为 100，失败或取消任务 SHALL 保留最后一个合法进度。Parent 汇总 A/B 时 MUST 将子进度映射到对应顶层阶段，且不得重复计算。

#### Scenario: 活跃阶段接近完成时总体进度反映真实阶段

- **WHEN** `joint_tracking_v2` 的 `multiview-joint` 进度从 80 更新到 95
- **THEN** 总体进度 SHALL 根据 joint 阶段权重向前推进
- **AND** 总体进度 SHALL NOT 因后续阶段仍为 pending 而被阶段数量平均值压低到与早期读取阶段相同的水平

#### Scenario: late fusion 聚合 child 进度

- **WHEN** `late_fusion_v1` 的 A/B child 分别上报进度
- **THEN** Parent SHALL 按当前顶层 A/B 阶段聚合 child 进度
- **AND** child 的同一份进度 SHALL NOT 同时被计入 A/B 阶段和融合阶段

#### Scenario: 进度终态不回退

- **WHEN** 任务已经发布进度 65，随后收到一个延迟到达的旧遥测快照
- **THEN** 新快照的总体进度 SHALL 保持不低于 65
- **AND** 任务成功时最终总体进度 SHALL 为 100

### Requirement: A/B 子运行进度与 Parent 阶段一致

对于存在 A/B 子运行的双摄任务，系统 MUST 在 `viewRuns` 中返回每个机位的 `status`、`stage` 和 `progress`，并使其反映最近可用的实时状态。`late_fusion_v1` 的 `viewRuns` 来源为 dedicated child；`joint_tracking_v2` 的 `viewRuns` 来源为 Parent 内部 `ViewRun`。没有真实子运行数据时，系统 MUST NOT 返回一个用于占位的空 `viewRuns` 对象。

#### Scenario: late fusion 返回 child 子进度

- **WHEN** `late_fusion_v1` 的任一 child 正在处理
- **THEN** Parent SHALL 在对应机位的 `viewRuns` 中返回 child 当前阶段和进度
- **AND** Parent 顶层阶段 SHALL 继续使用聚合阶段语义

#### Scenario: joint tracking 返回内部 A/B 子进度

- **WHEN** `joint_tracking_v2` 已通过素材检查并开始协同跟踪
- **THEN** Parent SHALL 返回 A/B 内部 `ViewRun` 的状态、阶段和进度
- **AND** `viewRuns` SHALL NOT 为空对象

#### Scenario: 单摄任务不伪造子进度

- **WHEN** 前端读取 `single_view` 任务
- **THEN** API SHALL 不返回空的 A/B 子运行来填充界面
- **AND** 前端 SHALL 隐藏双摄子进度区域

### Requirement: 状态 API 和前端使用同一顺序

任务状态 API MUST 返回规范化且按阶段图排序的 `stages`；每个阶段至少包含 `id`、`status`、`progress` 和 `label`，可用时还应包含时间、耗时或错误信息。前端 MUST 使用 API 返回的顺序和状态渲染阶段条，不得在运行时重新套用单摄固定阶段数组。前端在 `viewRuns` 为空或缺失时 MUST 隐藏 A/B 子进度，而不是渲染空卡片。

#### Scenario: 运行中页面与 API 顺序一致

- **WHEN** API 返回 `multiview-joint` 为 active 且报告为 pending
- **THEN** 任务状态页 SHALL 将双摄协同跟踪显示在报告之前
- **AND** 页面 SHALL 高亮 API 标记的当前阶段，而不是根据本地阶段索引高亮其他阶段

#### Scenario: 终态页面显示最后阶段

- **WHEN** API 返回任务 succeeded 且报告阶段 done
- **THEN** 页面 SHALL 按同一阶段图显示报告完成
- **AND** 页面 SHALL 显示总体进度 100

### Requirement: 历史任务读取兼容

系统 MUST 能读取缺少新进度字段或 `executionMode` 的历史任务。缺少新字段的历史单摄任务 SHALL 按 `single_view` 兼容解析；历史双摄任务 SHALL 使用已有可识别的聚合结果或安全降级图，不得因无法构造新阶段图而解析失败。兼容解析 MUST NOT 修改历史任务持久化内容。

#### Scenario: 历史单摄任务继续展示

- **WHEN** 读取一个只包含旧 `stages` 数组的历史单摄任务
- **THEN** 系统 SHALL 成功返回任务状态
- **AND** 页面 SHALL 保持原有单摄阶段和终态展示

#### Scenario: 历史双摄任务安全降级

- **WHEN** 历史双摄任务没有 `executionMode` 或新版本的阶段遥测
- **THEN** 系统 SHALL 返回可解释的兼容阶段快照
- **AND** 不得因为缺少新字段返回 500 或显示一个无阶段的空状态页
