# multiview-net-profile-annotation Specification

## Purpose

定义双摄分析设置流程中的球网高度标注交互：两路同页标注、每路独立的 image-space 控制点、以及场景级唯一共享的高度 profile。
## ADDED Requirements

### Requirement: 双摄球网高度标注同页两路

系统 SHALL 在双摄分析设置流程的球网标定阶段，于同一页内承载 A、B 两路的球网高度标注（宽屏并排、窄屏纵向堆叠）。每一路 SHALL 独立标注自己的球网左端、中心、右端三个控制点与两个四分之一 hold-out 点，点位 SHALL 保存为该路的 image-space 坐标。

hold-out 点 SHALL NOT 参与 profile 拟合，只作为独立质量验证观测。

#### Scenario: 两路独立标注

- **WHEN** 用户进入球网标定阶段
- **THEN** 页面 SHALL 呈现两路各自的标注画布与五个可拖动点
- **AND** 某一路的三个控制点与两个 hold-out 点均被拖动后，该路 SHALL 视为点位就绪

#### Scenario: 缺少点位不放行

- **WHEN** 某一路存在未拖动的 hold-out 点
- **THEN** 该路 SHALL 不视为就绪
- **AND** 进入名册与确认阶段的按钮 SHALL 保持禁用并指明未就绪的一路

#### Scenario: 草稿恢复

- **WHEN** 用户重新进入已完成标注的球网标定阶段
- **THEN** 两路画布 SHALL 各自恢复已保存的点位
- **AND** 共享高度 profile SHALL 恢复为上次确认的取值

### Requirement: 球网高度 profile 唯一共享

同一张球网 SHALL 只有一个高度模型。球网标定阶段 SHALL 提供**唯一一份**共享的 profile 设置（profile 类型、两侧高度、中心高度、确认勾选），SHALL NOT 为每一路分别提供高度输入。提交的 `metric_court_scene.v1` 场景载荷 SHALL 以该共享 profile 作为 net profile 与 hold-out 控制点的世界高度来源，两路仅贡献各自的 image-space 坐标。

#### Scenario: 只有一份高度输入

- **WHEN** 用户查看球网标定阶段
- **THEN** profile 类型、两侧高度、中心高度与确认勾选 SHALL 只呈现一次
- **AND** SHALL NOT 在任一路的标注画布内重复提供高度输入

#### Scenario: 任一改动都会生效

- **WHEN** 用户修改共享高度（标准值或现场实测值）
- **THEN** 提交的场景载荷中 net profile 与 hold-out 控制点的世界高度 SHALL 反映该取值
- **AND** SHALL NOT 存在某一路的高度输入被静默忽略的路径

#### Scenario: 构造标准 profile

- **WHEN** 共享 profile 选择标准高度
- **THEN** 场景载荷 SHALL 保存两侧 91.44 cm、中心 86.36 cm 的三维控制点
- **AND** `height_source` SHALL 为 `standard`

#### Scenario: 构造现场实测 profile

- **WHEN** 共享 profile 选择现场实测并填入高度
- **THEN** 场景载荷 SHALL 保存该取值且 `height_source` 为 `measured`
- **AND** hold-out 控制点的世界高度 SHALL 按同一 profile 插值得到

#### Scenario: 未确认高度不放行

- **WHEN** 共享 profile 的确认勾选未勾选
- **THEN** 进入名册与确认阶段的按钮 SHALL 保持禁用
