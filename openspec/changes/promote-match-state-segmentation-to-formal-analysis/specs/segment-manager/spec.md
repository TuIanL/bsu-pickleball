## MODIFIED Requirements

### Requirement: 片段列表提供明确的播放与来源入口

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

### Requirement: 普通片段页不编辑自动或人工边界

普通片段管理页 SHALL 将时间线和片段边界作为只读的回放与定位信息。候选 review、人工边界编辑和管理 API 可为受控 QA / 开发入口保留，但普通页面 MUST NOT 请求或呈现这些工作流，也不得用本地草稿修改 `CaptureSegment`。

#### Scenario: 时间线回放不改变边界
- **WHEN** 用户拖动播放头、点击时间线片段或播放至片段终点
- **THEN** 页面 SHALL 仅更新播放位置和选中高亮
- **AND** MUST NOT 发送 Segment PATCH、review 决定或创建操作

#### Scenario: QA 能力与普通页面隔离
- **WHEN** 普通用户打开 SegmentManagerPage
- **THEN** 页面 SHALL 不调用 match-state candidate/review、boundary review 或 AnalysisBatch API
- **AND** 既有 QA API 的存在 SHALL 不改变普通页面的只读行为
