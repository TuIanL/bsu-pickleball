## MODIFIED Requirements

### Requirement: 估算高度的可信表达

系统 SHALL 以可信方式表达估算高度，低可信高度、未知端和推算点必须与合格双摄高度区分。

#### Scenario: 推算点样式区分
- **WHEN** 重建样本 `source` 为 `interpolated` 或 `model_predicted`
- **THEN** 场景 SHALL 以虚线或浅色样式绘制，与 `detected` 点可区分

#### Scenario: 高度不可信提示
- **WHEN** 样本高度置信度低于展示阈值或 `height_validity = unknown_open_end`
- **THEN** 场景 SHALL 弱化该段高度信息
- **AND** 说明该高度为视觉估计

#### Scenario: 高度来源保留
- **WHEN** adapter 将 artifact sample 转换为前端 view model
- **THEN** SHALL 保留 `height_source`、`height_confidence`、`height_uncertainty_ft` 和高度有效性
- **AND** 前端 MUST NOT 重新生成统一高度或统一抛物线覆盖 artifact 高度

## ADDED Requirements

### Requirement: 地面以下高度安全渲染

球场视图 SHALL 把地面 `y = 0` 作为高度安全边界，任何负值、非有限值或 artifact 标记为无效的高度不得生成正式 Three.js 轨迹几何。

#### Scenario: 负高度样本
- **WHEN** 前端收到 `estimated_height_ft < 0`
- **THEN** 该 sample SHALL 被过滤或使对应 3D run 断开
- **AND** 页面 MUST NOT 把它裁剪成地面点后继续伪装为有效 3D

#### Scenario: 无效 3D 段存在 2.5D 降级
- **WHEN** 某 3D segment 高度无效但同段存在合格的 visualization-only 2.5D 结果
- **THEN** 页面 SHALL 展示 2.5D 降级结果
- **AND** SHALL 保留 3D 失败原因供技术详情查询

#### Scenario: 无有效高度
- **WHEN** 轨迹没有任何有限且非负的高度样本
- **THEN** 该段 SHALL 不生成场景线条
- **AND** 页面 SHALL 保留既有的无可用球路或降级状态语义，不得静默显示平面线
