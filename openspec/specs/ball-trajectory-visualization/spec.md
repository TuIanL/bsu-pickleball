# ball-trajectory-visualization Specification

## Purpose
定义前端球路视图从"按 segment 展示"升级为"按 Shot 筛选、选中与统计"：动态球员筛选（来自产物 `player_roster`）、点击任意飞行段高亮整个 Shot、列表与统计按 `shot_id` 聚合、未归属分组双语义、旧 v1 产物兼容。
## Requirements
### Requirement: 任务级球路视图
系统 SHALL 将重建产物渲染为任务级球路视图，包含球场、球路、弹地与击球点标记。

#### Scenario: 渲染重建球路
- **WHEN** 任务存在重建产物
- **THEN** 页面 SHALL 以 2.5D 球场渲染飞行段球路
- **AND** 球路 SHALL 来自重建产物，不自行分段

#### Scenario: 无重建产物
- **WHEN** 任务没有重建产物
- **THEN** 页面 SHALL 显示明确的重建不可用状态或降级提示
- **AND** MUST NOT 静默失败

### Requirement: 确定性球路分段
系统 SHALL 使用后端产物的稳定 ID 标识球路，保证分段确定性。

#### Scenario: 后端稳定 ID
- **WHEN** 前端构建球路
- **THEN** 轨迹绘制 ID SHALL 使用后端 `segment_id`
- **AND** 业务击球 ID SHALL 使用后端 `shot_id`
- **AND** MUST NOT 使用前端自生成的序号（如 `trajectory-${sequence}`）作为稳定标识

#### Scenario: 旧任务回退
- **WHEN** 产物缺失 `segment_id` 或 `shot_id`
- **THEN** 前端 SHALL 回退到顺序 ID 仅用于展示，不参与统计

### Requirement: 估算高度的可信表达
系统 SHALL 以可信方式表达估算高度，低可信高度与推算点必须与实测区分。

#### Scenario: 推算点样式区分
- **WHEN** 重建样本 `source` 为 `interpolated` 或 `model_predicted`
- **THEN** 场景 SHALL 以虚线或浅色样式绘制，与 `detected` 点可区分

#### Scenario: 高度不可信提示
- **WHEN** 样本高度置信度低于展示阈值
- **THEN** 场景 SHALL 弱化该段高度信息
- **AND** 说明该高度为视觉估计

### Requirement: 交互式标准球场渲染
系统 SHALL 提供标准 2.5D 球场交互渲染。

#### Scenario: 球场渲染
- **WHEN** 球路页加载
- **THEN** 场景 SHALL 渲染标准匹克球球场，包含发球线、非截击区与网
- **AND** 支持平移、缩放、旋转视角

### Requirement: 轨迹筛选与视觉编码
系统 SHALL 允许用户在全部轨迹、较高可信度轨迹与球员球路之间筛选，并 SHALL 使用颜色、透明度和点型区分方向、低可信度、推算点和弹跳候选。可信度判定 SHALL 使用后端质量评分，而非前端平均置信度。球员筛选选项 SHALL 来自产物 `player_roster`，不得硬编码。

#### Scenario: 仅显示较高可信度轨迹
- **WHEN** 用户启用高可信度筛选
- **THEN** 场景仅显示后端质量评分达到规定阈值且推算比例未超过规定值的重建段

#### Scenario: 按球员筛选
- **WHEN** 用户选择某球员（如 P3）
- **THEN** 场景仅显示 `hitter_player_id == Player_3` 的 Shot 内所有 segment
- **AND** 可见球路的 `hitter_player_id` SHALL 均为 `Player_3`

#### Scenario: 单打双打自适应
- **WHEN** 产物 `player_roster` 只有两名球员
- **THEN** 球员筛选 SHALL 只显示两名球员选项
- **AND** SHALL NOT 显示硬编码的 P1—P4

#### Scenario: 旧任务无归属字段
- **WHEN** 产物为 v1 或无球员归属字段
- **THEN** 球员筛选 SHALL 隐藏或禁用
- **AND** 球路仍正常展示，不伪造归属

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

### Requirement: Shot 级选中
系统 SHALL 以 Shot 为选中单位：点击任意飞行段高亮该 Shot 内的全部 segment。

#### Scenario: 点击 segment 高亮整个 Shot
- **WHEN** 用户点击某个 flight segment
- **THEN** 系统 SHALL 通过该 segment 的 `shotId` 选中对应 Shot
- **AND** 该 Shot 内所有 segment SHALL 同时高亮

#### Scenario: 渲染保持独立段
- **WHEN** 一个 Shot 包含多个 segment
- **THEN** 3D 渲染 SHALL 保持独立 segment line strip，不拼接成单一几何线
- **AND** 选中状态 SHALL 通过共享 `shotId` 判定

### Requirement: Shot 级列表与统计
系统 SHALL 按 Shot 聚合列表与统计，列表项展示击球者、飞行段数与时长，统计按 `shot_id` 去重。

#### Scenario: Shot 列表项
- **WHEN** 右侧列表渲染
- **THEN** 列表项 SHALL 按 Shot 展示（如"球路 7 · P2 · 2 个飞行段 · 3.8 秒"）
- **AND** MUST NOT 按 flight segment 逐条列示同一 Shot

#### Scenario: 统计按 Shot 去重
- **WHEN** 页面统计球路总数与球员击球数
- **THEN** 总数 SHALL 按 `shot_id` 去重计数（含 unassigned，不含 `shotId = null`）
- **AND** 球员击球数 SHALL 按 `hitter_player_id` 匹配的 Shot 去重计数

#### Scenario: 筛选顺序
- **WHEN** 用户同时启用球员筛选、可信度筛选与数量限制
- **THEN** 筛选顺序 SHALL 为：球员归属筛选 → 可信度筛选 → 最近 N 条限制

### Requirement: 未归属双语义分组
系统 SHALL 在"未归属"筛选下区分"击球者不明"与"无 Shot 上下文"两类，避免误解。

#### Scenario: 击球者不明
- **WHEN** Shot 存在但 `ownershipStatus ∈ {ambiguous, unassigned}`
- **THEN** 该类 SHALL 归入"未归属"且标签为"击球者不明"

#### Scenario: 无 Shot 上下文
- **WHEN** segment 的 `shotId` 为 null
- **THEN** 该类 SHALL 归入"未归属"且标签为"无 Shot 上下文"
- **AND** 调试模式下两类 SHALL 可区分展示

#### Scenario: 两类均不计入球员统计
- **WHEN** 系统计算球员击球数
- **THEN** 击球者不明与无 Shot 上下文的轨迹 SHALL 均不计入任何球员

### Requirement: 球路空态返回导航

球路查看页（`/analysis/:id/trajectory`）在"暂无可用球路"与"读取失败"空态下 SHALL 始终提供可用的返回导航，至少包含**返回任务管理**入口，并保留既有**返回视觉分析**入口；任务上下文缺失时返回任务管理路径 SHALL 仍可基于 URL 上下文生成。MUST NOT 出现用户无法返回上一级页面的状态。

#### Scenario: 双摄任务未开启球路识别进入空态

- **WHEN** 用户在双摄协同任务未开启球路识别时进入球路查看页，且页面进入"暂无可用球路"状态
- **THEN** 页面 SHALL 展示"返回任务管理"按钮
- **AND** 页面 SHALL 同时保留"返回视觉分析"按钮

#### Scenario: 球路读取失败

- **WHEN** 球路数据读取失败且任务记录无法加载
- **THEN** 页面 SHALL 仍展示基于 URL 上下文生成的"返回任务管理"按钮
- **AND** 点击 SHALL 导航到对应的任务管理页面（含双摄录制等来源上下文）

#### Scenario: 空态返回不依赖任务记录

- **WHEN** 球路查看页处于空态或失败态
- **THEN** 返回导航 SHALL 不依赖成功读取的 job 数据即可渲染
- **AND** MUST NOT 因 job 数据缺失而只保留单一不可用入口
