## ADDED Requirements

### Requirement: 场景标定驱动的高度可信表达

系统 SHALL 以可信方式表达 metric、approximate 和 visualization-only 高度；低可信高度、未知端和推算点必须与合格双摄高度区分。前端 SHALL 消费 artifact 中的 `metric_validity`、scene calibration status、height confidence 和 uncertainty，不得自行把不同来源合并成一个精确高度。

#### Scenario: metric 高度
- **WHEN** 重建样本来自 ready scene revision 且 `metric_validity = metric_multiview`
- **THEN** 场景 SHALL 保留其高度来源、置信度和不确定度
- **AND** 可以按产品阈值使用 metric 3D 轨迹和高度指标

#### Scenario: approximate 或 visualization-only 高度
- **WHEN** 样本来自 approximate scene、单摄弧线、`interpolated` 或 `model_predicted`
- **THEN** 场景 SHALL 使用虚线、浅色、透明度或标签与 metric 高度区分
- **AND** SHALL 说明该高度为近似或仅用于可视化

#### Scenario: 高度来源保留
- **WHEN** adapter 将 artifact sample 转换为前端 view model
- **THEN** SHALL 保留 `height_source`、`height_confidence`、`height_uncertainty_ft`、`height_validity`、`metric_validity` 和 scene calibration reference
- **AND** 前端 MUST NOT 重新生成统一高度或统一抛物线覆盖 artifact 高度

### Requirement: 场景 profile 驱动的可变高度球网渲染

系统 SHALL 提供统一的标准匹克球 3D/2.5D 球场交互渲染。场景 SHALL 包含发球线、非截击区、由 scene calibration profile 生成的球网和可读轨迹，并提供 PB Vision 风格的五个固定视角：45°、俯视、边线、底线和 45°底线。场景 SHALL 支持平移、缩放和旋转；视角切换不得重新创建整套 renderer 和轨迹几何。

#### Scenario: 渲染可变高度球网
- **WHEN** 任务 artifact 包含有效 net profile
- **THEN** 场景 SHALL 按 profile 渲染两侧 91.44 cm、中心 86.36 cm 或现场 measured height
- **AND** 球网、网柱与球路 SHALL 使用同一个 Canonical Court Frame

#### Scenario: 缺少场景 profile
- **WHEN** 任务没有可用 scene calibration profile
- **THEN** 场景 SHALL 使用明确标记的兼容网模型或展示降级状态
- **AND** SHALL NOT 将固定高度网模型描述为现场实测几何

#### Scenario: 固定视角与自由交互
- **WHEN** 用户打开视角工具栏或拖动、滚轮缩放、触摸操作球场
- **THEN** 工具栏 SHALL 保留五个固定视角，场景 SHALL 支持平移、缩放和旋转
- **AND** 操作不得改变 artifact 数据或生成新的轨迹段
