# ball-trajectory-visualization Specification

## Purpose
定义前端球路视图从"按 segment 展示"升级为"按 Shot 筛选、选中与统计"：动态球员筛选（来自产物 `player_roster`）、点击任意飞行段高亮整个 Shot、列表与统计按 `shot_id` 聚合、未归属分组双语义、旧 v1 产物兼容。
## Requirements
### Requirement: 任务级球路视图

系统 SHALL 将重建产物渲染为任务级 3D 球路视图，包含标准球场、独立飞行段、方向/来源线条和每条轨迹唯一的中性末端圆点。击球、弹地、loss、界外候选和环境离群语义 SHALL 保留在 artifact 和内部 view model 中，但 MUST NOT 通过菱形、橙色圆环、渐隐圆点或其他事件图标装饰默认球场视图。

#### Scenario: 渲染重建球路

- **WHEN** 任务存在可展示的重建产物
- **THEN** 页面 SHALL 以共享的交互式 3D/2.5D 球场渲染独立飞行段球路
- **AND** 球路 SHALL 来自重建产物，不自行分段
- **AND** 每条轨迹 SHALL 只显示一个中性末端圆点

#### Scenario: 事件语义保留但不使用事件图标

- **WHEN** 重建段包含 hit、bounce、loss 或其他 endpoint/anchor 语义
- **THEN** 前端 view model SHALL 保留这些语义供筛选、审计和详情使用
- **AND** 默认球场视图 MUST NOT 为这些语义渲染击球菱形、弹地圆环、渐隐点或事件图例

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

### Requirement: 交互式标准球场渲染

系统 SHALL 提供统一的标准匹克球 3D/2.5D 球场交互渲染。场景 SHALL 包含发球线、非截击区、球网和可读轨迹，并提供 PB Vision 风格的五个固定视角：45°、俯视、边线、底线和 45°底线。场景 SHALL 支持平移、缩放和旋转；视角切换不得重新创建整套 renderer 和轨迹几何。

#### Scenario: 球场渲染

- **WHEN** 球路页或报告页加载可展示轨迹
- **THEN** 场景 SHALL 渲染标准匹克球球场，包含发球线、非截击区与网
- **AND** 球场外围 SHALL 与画布背景融合，不显示突兀的白色 apron 边界或灰色悬浮底板

#### Scenario: 固定视角

- **WHEN** 用户打开视角工具栏
- **THEN** 工具栏 SHALL 提供 45°、俯视、边线、底线和 45°底线五个视角
- **AND** 每个视角 SHALL 更新相机位置、缩放和控制目标
- **AND** 视角切换 SHALL 保留当前轨迹、筛选和选中状态

#### Scenario: 自由交互

- **WHEN** 用户拖动、滚轮缩放或触摸操作球场
- **THEN** 场景 SHALL 支持平移、缩放和旋转
- **AND** 操作不得改变 artifact 数据或生成新的轨迹段

### Requirement: 轨迹筛选与视觉编码

系统 SHALL 允许用户在全部轨迹、较高可信度轨迹与球员球路之间筛选，并 SHALL 使用方向颜色、透明度、线宽和来源线型区分方向、低可信度、推算点和预测区间。可信度判定 SHALL 使用后端质量评分和段级展示资格，而非前端平均置信度。球员筛选选项 SHALL 来自产物 `player_roster`，不得硬编码。默认视图 MUST NOT 使用事件点型区分击球或弹地，也 MUST NOT 绘制 `display_eligible = false` 的 segment。

#### Scenario: 仅显示较高可信度轨迹

- **WHEN** 用户启用高可信度筛选
- **THEN** 场景仅显示后端质量评分达到规定阈值、推算比例未超过规定值且 `display_eligible = true` 的重建段

#### Scenario: 按球员筛选

- **WHEN** 用户在报告页选择某个 canonical 球员（如 `Player_3`）
- **THEN** 场景 SHALL 仅显示 `hitter_player_id == Player_3` 且 `ownership_status == confirmed` 的 Shot
- **AND** 该 Shot 关联的全部 segment SHALL 保留并传入场景，即使一个 Shot 包含多个 segment
- **AND** 可见球路的原始 `hitter_player_id` SHALL 均为 `Player_3`，前端不得通过覆盖字段伪造归属

#### Scenario: 未归属球路不进入球员视图

- **WHEN** Shot 或 segment 的归属为 `ambiguous`、`unassigned`、缺少 `hitter_player_id`，或 `shot_id` 为空
- **THEN** 该球路 SHALL 不进入任何指定球员的个人筛选结果
- **AND** 该数据 SHALL 保留给全部轨迹或未归属视图使用，并 SHALL 不计入指定球员统计

#### Scenario: 报告页切换球员

- **WHEN** 用户从 `Player_1` 切换到 `Player_2`
- **THEN** `BallTrajectoryScene` SHALL 在下一次渲染中只接收 `Player_2` 的筛选结果
- **AND** SHALL NOT 保留上一名球员的可见轨迹或当前选中的不可见 Shot

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
- **AND** 选中状态 MAY 使用中性色加深或线宽变化，但 MUST NOT 恢复事件图标

#### Scenario: 低可信段仅调试显示

- **WHEN** 重建段质量评分低于默认展示阈值、`display_eligible = false` 或为 `image_only` 模式
- **THEN** 场景 SHALL NOT 在默认球场视图显示该段，除非用户开启调试/原始检测模式

#### Scenario: 断点和来源不被前端重新连接

- **WHEN** artifact 标记两个样本区间之间存在长缺口、lost/reset 边界或 `display_break = true`
- **THEN** 前端 SHALL 保持几何断开
- **AND** MUST NOT 为了视觉连续性自行插值、平滑或跨段连线

### Requirement: 完备的运行状态

系统 SHALL 为加载中、无有效数据、API 失败、WebGL 不可用和重建产物不可用提供独立状态，并 SHALL 在移动端和桌面端保持画布、工具栏和文字互不遮挡。对于存在可展示轨迹的 available 或 degraded 结果，页面 MUST NOT 额外渲染混合球路状态卡、2.5D 限制说明、环境离群诊断或逐段界外提示。

#### Scenario: 任务没有有效球场坐标

- **WHEN** artifact 存在但没有可构建球路的有效二维球场点
- **THEN** 页面说明当前任务缺少可视化所需的有效轨迹，并提供返回视觉分析的操作

#### Scenario: 重建产物不可用

- **WHEN** 任务未生成重建产物或 `display_trajectory_status` 为 `unavailable`
- **THEN** 页面显示简短的重建不可用状态或降级到原始轨迹模式，且 MUST NOT 静默失败
- **AND** 页面 MAY 提供返回视觉分析或技术详情的入口

#### Scenario: WebGL 初始化失败

- **WHEN** 浏览器无法创建 Three.js WebGL renderer
- **THEN** 页面显示渲染不可用状态且应用其余导航继续可用

#### Scenario: 可展示轨迹正常加载

- **WHEN** artifact 存在可展示的轨迹段
- **THEN** 页面 SHALL 直接渲染球场和轨迹
- **AND** SHALL 不显示重复的状态卡、2.5D 资格文案、环境离群计数或多条界外提示

### Requirement: 事件锚点视觉语义

系统 SHALL 保留重建产物中的事件类型、样本来源和长丢失边界语义，但默认球场视图 MUST NOT 使用事件图标表达 hit、bounce 或 loss。每条轨迹 SHALL 只使用一个中性末端圆点作为视觉终点；来源和连续性仍通过线条样式表达。

#### Scenario: 事件锚点不渲染图标

- **WHEN** 重建段包含 hit、bounce、loss 或 raw endpoint 锚点
- **THEN** 场景 SHALL 不渲染紫色击球菱形、橙色弹地圆环、灰色 loss 圆点或对应图例
- **AND** 场景 SHALL 只在该轨迹最后一个可渲染 sample 位置绘制中性末端圆点

#### Scenario: 推算点虚线

- **WHEN** 重建样本 `source` 为 `interpolated` 或 `model_predicted`
- **THEN** 场景 SHALL 以虚线、浅色或透明度方式绘制该部分，与 `detected` 区间可区分
- **AND** source 切换不得导致只有一个点的孤立短线

#### Scenario: 丢失边界断开

- **WHEN** 两个重建段之间存在长时间丢失边界、无效高度或后端明确的 segment 边界
- **THEN** 场景 SHALL 视觉上断开，不跨丢失边界连线

#### Scenario: 事件边界保持几何连续

- **WHEN** 两个重建段共享同一事件锚点且两侧 sample 有效
- **THEN** 两段 SHALL 保持各自独立 geometry
- **AND** 允许在共享坐标处几何连续，但 MUST NOT 通过额外事件图标强调该边界

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

系统 SHALL 按 Shot 聚合列表与统计，列表项展示击球者、飞行段数与时长，统计按 `shot_id` 去重。所有列表和统计 SHALL 基于当前球员、阶段、质量和数量限制后的可见结果计算，不得使用筛选前的整场轨迹数量。

#### Scenario: Shot 列表项

- **WHEN** 右侧列表渲染
- **THEN** 列表项 SHALL 按 Shot 展示（如“球路 7 · P2 · 2 个飞行段 · 3.8 秒”）
- **AND** MUST NOT 按 flight segment 逐条列示同一 Shot

#### Scenario: 统计按 Shot 去重

- **WHEN** 页面统计球路总数与球员击球数
- **THEN** 总数 SHALL 按 `shot_id` 去重计数（含 unassigned，不含 `shotId = null`）
- **AND** 球员击球数 SHALL 按 `hitter_player_id` 匹配且已确认的 Shot 去重计数
- **AND** 统计 SHALL 不包含未归属、击球者不明或另一球员的 Shot

#### Scenario: 筛选顺序

- **WHEN** 用户同时启用球员筛选、可信度筛选与数量限制
- **THEN** 筛选顺序 SHALL 为：球员归属筛选 → 可信度筛选 → 最近 N 条限制

#### Scenario: 无匹配球路

- **WHEN** 当前球员和其他筛选条件组合后没有可展示的 Shot
- **THEN** 页面 SHALL 显示明确的“当前筛选下没有可显示的球路”空态
- **AND** SHALL NOT 回退显示整场球路

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

### Requirement: 球路页面展示 v3 双摄三维结果

任务级球路页面 SHALL 展示统一重建 artifact 中可用的三维与估算 2.5D segment、落点数据、整体状态和质量指标，并 SHALL 使用清晰的线条和来源样式区分双摄估算三维、单摄估算弧线与预测区间。事件端点语义 SHALL 保留在数据层，但默认视图只显示中性末端圆点，不显示击球、弹地或未知端点图标。

#### Scenario: 展示完整三维结果

- **WHEN** 页面读取到 `FULL_ESTIMATED_3D` 段
- **THEN** 页面 SHALL 展示三维轨迹、可用落点、覆盖率、重投影误差与有资格的速度
- **AND** SHALL 通过统一 3D 视图展示轨迹，不额外显示状态说明卡

#### Scenario: 展示混合结果

- **WHEN** 同一任务同时包含 3D 段和 visualization-only 2.5D 段
- **THEN** 页面 SHALL 逐段使用 reconstruction mode、来源和质量门控制可见性
- **AND** 预测区间 SHALL 使用虚线或降低透明度
- **AND** 页面 SHALL 不显示重复的 2.5D 资格说明或环境诊断文案

#### Scenario: 仅估算 2.5D 可用

- **WHEN** 3D overall status 为 `UNAVAILABLE` 但 `display_trajectory_status` 可用
- **THEN** 页面 SHALL 展示估算弧线
- **AND** SHALL 隐藏无资格的真实高度、三维球速和权威落点指标
- **AND** SHALL 保留后端 artifact 中的质量和来源字段供技术查询

### Requirement: 页面展示球分析运行状态与失败原因

页面 SHALL 从 Parent artifacts 的 status/detail 处理 `queued`、`running`、`succeeded`、`degraded`、`failed` 或 `UNAVAILABLE` 等状态，不得把缺少 URL 直接显示为“没有数据”。当已有可展示轨迹时，页面 SHALL 依靠视图导航和轨迹本身表达结果，不再显示重复状态卡；当球分析仍在运行、失败或不可用时，页面 SHALL 保留简短且必要的状态空态和返回入口。

#### Scenario: 球分析仍在运行

- **WHEN** Parent 已可查询但球分析 status 为 running
- **THEN** 页面 SHALL 显示分析进行中状态
- **AND** SHALL 不显示空的“暂无球路”结论

#### Scenario: 球分析失败

- **WHEN** status 为 failed 或 unavailable 且 detail 可用
- **THEN** 页面 SHALL 显示简短失败原因与返回视觉分析或技术详情的入口
- **AND** SHALL 允许用户继续访问球员轨迹、指标或报告页面

#### Scenario: 球分析已有可展示轨迹

- **WHEN** `display_trajectory_status` 为 `available` 或 `degraded` 且存在至少一个可展示 segment
- **THEN** 页面 SHALL 直接展示统一 3D 轨迹
- **AND** MUST NOT 显示混合分段状态卡、2.5D 限制说明、环境离群诊断或逐段界外提示

### Requirement: 页面兼容旧版球路产物
旧任务仅包含 legacy `ball_trajectory_url`、`cleaned_ball_trajectory_url` 或 v2 轨迹时，页面 SHALL 继续按既有兼容规则渲染；新任务若同时包含 v3 与 legacy 产物，默认 SHALL 选择 v3，并保留旧数据的明确标识。

#### Scenario: 旧任务读取
- **WHEN** Parent 没有 v3 但有 legacy 轨迹
- **THEN** 页面 SHALL 使用兼容读取路径
- **AND** SHALL 不因新增 v3 字段而报错

#### Scenario: 新任务双版本并存
- **WHEN** Parent 同时发布 v3 与旧版轨迹
- **THEN** 页面默认 SHALL 展示 v3
- **AND** SHALL 标注旧版数据不可与双摄三维质量指标等价

### Requirement: Vision 页面提供双摄球分析入口但不伪造像素叠加

Vision 页面 SHALL 通过现有横向视图导航或紧凑操作入口提供球路页面访问，不得在已有球路视图入口时重复渲染双摄球路状态提示卡。视频叠加 SHALL 使用当前机位自身的 image-space 观测/拟合或经过验证的 world-to-pixel 投影，MUST NOT 把球场世界坐标直接当作视频像素坐标。

#### Scenario: 已有球路视图入口

- **WHEN** 用户打开已完成的双摄分析结果，且横向导航已提供球路视图
- **THEN** Vision 页面 SHALL 保留球路导航入口
- **AND** SHALL 不再显示额外的“双摄球路分析”提示卡

#### Scenario: 播放当前飞行段

- **WHEN** 播放时间进入具有当前机位 image-space 轨迹的 segment
- **THEN** Vision 页面 SHALL 绘制该段截至当前时间的球路尾迹
- **AND** detected、interpolated 与 predicted 区间 SHALL 使用不同视觉编码

#### Scenario: 无有效像素映射

- **WHEN** 当前 segment 既没有当前机位 image-space 轨迹，也没有经过验证的 world-to-pixel 投影
- **THEN** Vision 页面 SHALL 不绘制伪造叠加
- **AND** SHALL 引导用户进入标准球场球路视图

### Requirement: 球路报告展示端点与场外语义

球路报告 SHALL 使用统一 reconstructed artifact 的 3D 球场视图展示可读的分段轨迹。报告 SHALL 保留端点和场外分类在 artifact 中，但普通报告 MUST NOT 显示击球/弹地/未知端点图标、`non_adjudication_notice` 文案或重复的逐段“可能界外落点，非自动判罚”提示。

#### Scenario: 真实界外候选点

- **WHEN** segment 结束于 `legal_out_candidate` bounce
- **THEN** 报告 SHALL 在实际估算位置保留该轨迹的中性末端圆点
- **AND** SHALL 不把该点吸附回场内
- **AND** endpoint 分类和非判罚语义 SHALL 继续保留在 artifact API 中

#### Scenario: 环境离群点

- **WHEN** endpoint 被分类为 `environment_outlier`
- **THEN** 正式报告 SHALL 不把该点作为球路端点或轨迹 segment 展示
- **AND** 技术详情或 artifact 查询 SHALL 仍能提供其拒绝理由和原始证据

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

### Requirement: 相邻球路片段唯一渲染

前端球路 compositor 在每个播放时刻 SHALL 以 `render_view_id`、时间窗口和稳定 `segment_id` 过滤并去重，默认只渲染一个 active segment 的视频尾迹。已结束 segment 的 retention 只有在不存在已开始的后继 segment 时才允许生效；不得因固定 retention 窗口同时绘制两条相邻轨迹。

#### Scenario: 33 秒相邻片段切换
- **WHEN** `flight-42` 在 33.166 秒结束且 `flight-43` 从 33.166 秒开始
- **THEN** 33.166 秒及之后的活动轨迹 SHALL 只包含 `flight-43`
- **AND** SHALL NOT 因 `flight-42` 的 retention 与 `flight-43` 同时产生两条视频轨迹

#### Scenario: 不同 primary view 不产生双坐标叠加
- **WHEN** 相邻 segment 的 `primary_view_id` 分别为 `cam_2` 和 `cam_1`
- **THEN** compositor SHALL 先统一到任务 `render_view_id`
- **AND** 若某段无法统一， SHALL 跳过该段的视频 path并保留可查询的 skip reason

#### Scenario: 重复 segment 输入
- **WHEN** adapter 因重试、插值或旧 artifact 返回相同 `segment_id` 的重复记录
- **THEN** compositor SHALL 只保留一份确定性 geometry
- **AND** 不得通过重复记录叠加线宽、透明度或端点

#### Scenario: 时间边界回放稳定
- **WHEN** 播放器在 segment start/end 边界前后往返拖动
- **THEN** 同一时刻 SHALL 得到相同的 active segment 集合和同一 `render_view_id`
- **AND** 不得出现边界前后两条路径短暂同时闪现

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

