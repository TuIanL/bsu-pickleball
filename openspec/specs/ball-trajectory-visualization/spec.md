# ball-trajectory-visualization Specification

## Purpose
TBD - created by archiving change add-ball-trajectory-visualization. Update Purpose after archive.
## Requirements
### Requirement: 任务级球路视图
系统 SHALL 为具有任务 ID 的分析任务提供独立球路可视化路由，并 SHALL 从该任务现有的清洗球轨迹、原始球轨迹回退和弹跳候选 artifact 加载数据。

#### Scenario: 从视觉分析进入球路页面
- **WHEN** 用户在已完成任务的视觉分析页面选择球路可视化
- **THEN** 系统导航到 `/analysis/{jobId}/trajectory` 并读取同一任务的轨迹数据

#### Scenario: 清洗轨迹缺失时回退
- **WHEN** 任务没有清洗球轨迹但具有原始球轨迹
- **THEN** 系统使用现有分析 API 返回的原始球轨迹构建视图

### Requirement: 确定性球路分段
系统 SHALL 清理非有限或缺失的二维球场点，按时间排序，并 SHALL 在时间间隙或不合理平面跳变处断开轨迹。系统 SHALL 保留每个渲染点的时间、置信度和插值来源。

#### Scenario: 时间间隙形成新球路
- **WHEN** 两个连续有效轨迹点的时间间隙超过配置阈值
- **THEN** 系统将后一个点放入新的球路段

#### Scenario: 无效点不进入渲染数据
- **WHEN** 轨迹点缺少有限的球场坐标或时间
- **THEN** 系统丢弃该点且不向 Three.js 场景传递非有限坐标

### Requirement: 估算高度的可信表达
系统 SHALL 仅为展示生成确定性的估算高度，并 SHALL 在页面中明确说明高度不是双摄测量结果。系统 MUST NOT 将估算高度显示为真实最高点、真实过网高度或真实三维速度。

#### Scenario: 生成 2.5D 弧线
- **WHEN** 有效球路段至少包含足够的轨迹点
- **THEN** 系统根据段内归一化进度生成首尾回落的平滑估算高度并标记来源为 `estimated`

#### Scenario: 用户查看数据说明
- **WHEN** 球路页面成功显示轨迹
- **THEN** 页面可见区域说明该视图基于单摄二维投影和估算高度，不代表真实三维测量

### Requirement: 交互式标准球场渲染
系统 SHALL 使用 Three.js 按标准 20 ft × 44 ft 比例渲染球场、边线、非截击区和球网，并 SHALL 渲染有效球路及其端点。系统 SHALL 提供斜视、俯视、侧视和端线预设视角以及旋转、缩放和全屏操作。

#### Scenario: 切换预设视角
- **WHEN** 用户选择任一预设视角
- **THEN** 相机移动到对应的稳定构图且球场和可见球路保持在画面内

#### Scenario: 调整观察位置
- **WHEN** 用户在支持指针操作的设备上拖动或缩放场景
- **THEN** 系统更新相机观察位置且不改变页面其余布局尺寸

### Requirement: 轨迹筛选与视觉编码
系统 SHALL 允许用户在全部轨迹和较高可信度轨迹之间筛选，并 SHALL 使用颜色、透明度和点型区分方向、低可信度、插值点和弹跳候选。

#### Scenario: 仅显示较高可信度轨迹
- **WHEN** 用户启用高可信度筛选
- **THEN** 场景仅显示达到规定平均置信度且插值比例未超过规定值的球路

#### Scenario: 选择单条轨迹
- **WHEN** 用户从轨迹列表选择一条球路
- **THEN** 场景突出该球路并显示其时间范围、持续时间、点数和可信度摘要

### Requirement: 完备的运行状态
系统 SHALL 为加载中、无有效数据、API 失败和 WebGL 不可用提供独立状态，并 SHALL 在移动端和桌面端保持画布、工具栏和文字互不遮挡。

#### Scenario: 任务没有有效球场坐标
- **WHEN** artifact 存在但没有可构建球路的有效二维球场点
- **THEN** 页面说明当前任务缺少可视化所需的有效轨迹，并提供返回视觉分析的操作

#### Scenario: WebGL 初始化失败
- **WHEN** 浏览器无法创建 Three.js WebGL renderer
- **THEN** 页面显示渲染不可用状态且应用其余导航继续可用

