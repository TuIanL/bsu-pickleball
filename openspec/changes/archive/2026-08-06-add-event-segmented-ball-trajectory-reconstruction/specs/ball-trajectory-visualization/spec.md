# ball-trajectory-visualization Specification (Delta)

## ADDED Requirements

### Requirement: 事件锚点视觉语义
系统 SHALL 按重建产物中的事件类型与样本来源渲染视觉标记，使击球、弹地、推算点与丢失边界在场景中可区分。

#### Scenario: 弹地点标记
- **WHEN** 重建段以弹地事件为锚点
- **THEN** 场景 SHALL 以橙色圆环标记弹地点

#### Scenario: 击球点标记
- **WHEN** 重建段以击球事件为锚点
- **THEN** 场景 SHALL 以菱形标记击球点

#### Scenario: 推算点虚线
- **WHEN** 重建样本 `source` 为 `interpolated` 或 `model_predicted`
- **THEN** 场景 SHALL 以虚线或浅色样式绘制该部分，与 `detected` 点可区分

#### Scenario: 丢失边界断开
- **WHEN** 两个重建段之间存在长时间丢失边界
- **THEN** 场景 SHALL 视觉上断开，不跨丢失边界连线

#### Scenario: 击球/弹地边界保持几何连续
- **WHEN** 两个重建段共享同一击球或弹地锚点
- **THEN** 场景 SHALL 在共享锚点处保持几何连续（两段各自独立 geometry，但端点重合）

## MODIFIED Requirements

### Requirement: 任务级球路视图
系统 SHALL 为具有任务 ID 的分析任务提供独立球路可视化路由，并 SHALL 优先从重建产物 `reconstructed_ball_trajectory.json` 加载数据；重建产物不可用时，再回退到清洗球轨迹、原始球轨迹和弹跳候选 artifact。

#### Scenario: 从视觉分析进入球路页面
- **WHEN** 用户在已完成任务的视觉分析页面选择球路可视化
- **THEN** 系统导航到 `/analysis/{jobId}/trajectory` 并读取同一任务的重建轨迹数据

#### Scenario: 重建产物缺失时回退
- **WHEN** 任务没有重建产物但具有原始球轨迹
- **THEN** 系统使用现有分析 API 返回的原始球轨迹以降级模式构建视图

### Requirement: 确定性球路分段
系统 SHALL 直接消费后端重建产物中的飞行段，不再自行分段。系统 SHALL 清理非有限的球场坐标，按段内时间排序，并 SHALL 保留每个重建样本的时间、置信度、插值来源与段归属。

#### Scenario: 分段由后端负责
- **WHEN** 球路页加载重建产物
- **THEN** 页面 SHALL 按产物中的 `segments` 渲染，每个段对应独立 geometry
- **AND** 页面 SHALL NOT 自行按时间间隙或平面跳变重新分段

#### Scenario: 无效点不进入渲染数据
- **WHEN** 重建样本缺少有限的球场坐标或时间
- **THEN** 系统丢弃该样本且不向 Three.js 场景传递非有限坐标

#### Scenario: 段级渲染不共享样条
- **WHEN** 两个飞行段相邻
- **THEN** 场景 SHALL 为每段创建独立 geometry，不得让单一样条跨越事件边界平滑

### Requirement: 估算高度的可信表达
系统 SHALL 仅使用重建产物中后端生成的估算高度用于展示，并 SHALL 在页面中明确说明高度不是双摄测量结果。系统 MUST NOT 将估算高度显示为真实最高点、真实过网高度或真实三维速度。

#### Scenario: 高度来自后端重建
- **WHEN** 球路页渲染轨迹
- **THEN** 每个点的 `estimated_height_ft` 与 `height_source` SHALL 来自重建产物
- **AND** 页面 SHALL NOT 自行生成统一高度弧线或把段端点强制置零

#### Scenario: 用户查看数据说明
- **WHEN** 球路页面成功显示轨迹
- **THEN** 页面可见区域说明该视图基于单摄二维投影和估算高度，不代表真实三维测量

### Requirement: 交互式标准球场渲染
系统 SHALL 使用 Three.js 按标准 20 ft × 44 ft 比例渲染球场、边线、非截击区和球网，并 SHALL 按重建段渲染有效球路及其锚点。系统 SHALL 提供斜视、俯视、侧视和端线预设视角以及旋转、缩放和全屏操作。

#### Scenario: 切换预设视角
- **WHEN** 用户选择任一预设视角
- **THEN** 相机移动到对应的稳定构图且球场和可见球路保持在画面内

#### Scenario: 调整观察位置
- **WHEN** 用户在支持指针操作的设备上拖动或缩放场景
- **THEN** 系统更新相机观察位置且不改变页面其余布局尺寸

#### Scenario: 按段构造渲染几何
- **WHEN** 场景渲染一条轨迹
- **THEN** 系统 SHALL 以重建段的密集采样点构造 line strip
- **AND** 系统 SHALL NOT 使用跨越击球或弹地事件边界的 Catmull-Rom 单一样条

### Requirement: 轨迹筛选与视觉编码
系统 SHALL 允许用户在全部轨迹和较高可信度轨迹之间筛选，并 SHALL 使用颜色、透明度和点型区分方向、低可信度、推算点和弹跳候选。可信度判定 SHALL 使用后端质量评分，而非前端平均置信度。

#### Scenario: 仅显示较高可信度轨迹
- **WHEN** 用户启用高可信度筛选
- **THEN** 场景仅显示后端质量评分达到规定阈值且推算比例未超过规定值的重建段

#### Scenario: 选择单条轨迹
- **WHEN** 用户从轨迹列表选择一条球路
- **THEN** 场景突出该球路并显示其时间范围、持续时间、点数和可信度摘要

#### Scenario: 低可信段仅调试显示
- **WHEN** 重建段质量评分低于默认展示阈值或为 `image_only` 模式
- **THEN** 场景 SHALL NOT 在默认球场视图显示该段，除非用户开启调试/原始检测模式

### Requirement: 完备的运行状态
系统 SHALL 为加载中、无有效数据、API 失败、WebGL 不可用和重建产物不可用提供独立状态，并 SHALL 在移动端和桌面端保持画布、工具栏和文字互不遮挡。

#### Scenario: 任务没有有效球场坐标
- **WHEN** artifact 存在但没有可构建球路的有效二维球场点
- **THEN** 页面说明当前任务缺少可视化所需的有效轨迹，并提供返回视觉分析的操作

#### Scenario: 重建产物不可用
- **WHEN** 任务未生成重建产物
- **THEN** 页面显示重建不可用状态或降级到原始轨迹模式，且 MUST NOT 静默失败

#### Scenario: WebGL 初始化失败
- **WHEN** 浏览器无法创建 Three.js WebGL renderer
- **THEN** 页面显示渲染不可用状态且应用其余导航继续可用
