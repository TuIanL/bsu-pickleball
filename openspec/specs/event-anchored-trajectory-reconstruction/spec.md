# event-anchored-trajectory-reconstruction Specification

## Purpose
定义事件锚定的 2.5D 视觉重建：在图像空间鲁棒拟合，以可信事件锚点在球场坐标重建展示轨迹，并按段类型生成事件边界感知的高度模型；重建链接入球员上下文（`PlayerAttributionContext`），在事件仲裁后执行球员归属与 Shot 组装，输出升级后的 v2 重建产物。不声称真实三维测量。
## Requirements
### Requirement: 图像空间鲁棒拟合
系统 SHALL 在每个飞行段内对图像坐标 `u(t)`、`v(t)` 做带检测置信度权重的鲁棒拟合，拟合发生在测量空间而非已失真的球场坐标。

#### Scenario: 加权 Huber 拟合
- **WHEN** 一个飞行段包含足够的有效观测点
- **THEN** 系统 SHALL 以带置信度权重的 Huber 损失拟合 `u(t)` 与 `v(t)`
- **AND** 拟合输出 SHALL 包含拟合曲线、异常观测标记与图像拟合残差（像素 RMSE）

#### Scenario: 严重离群点先 RANSAC 初始化
- **WHEN** 飞行段内存在严重离群点
- **THEN** 系统 SHALL 先使用 RANSAC 初始化稳健模型再以 Huber 精修
- **AND** RANSAC SHALL 使用固定随机种子以保证确定性

#### Scenario: 损失函数不使用失真球场坐标
- **WHEN** 系统计算拟合损失
- **THEN** 损失函数 SHALL 基于图像坐标拟合残差
- **AND** MUST NOT 直接使用已失真的 `court_xy` 作为拟合目标

#### Scenario: 观测点过少不强行拟合
- **WHEN** 飞行段内有效观测点数量低于配置下限
- **THEN** 系统 SHALL NOT 输出正式拟合曲线
- **AND** 该段 SHALL 保留为原始检测模式

### Requirement: 伪地面轨迹生成
系统 SHALL 将图像拟合结果经 homography 转换为 pseudo-ground path，仅作为方向、弯曲趋势与时间进度的参考。

#### Scenario: 生成 pseudo-ground path
- **WHEN** 图像拟合曲线可用且 homography 可用
- **THEN** 系统 SHALL 计算 `pseudo_court(t) = homography(image_fit(t))`
- **AND** 该路径 SHALL 被标记为中间量，不能直接作为最终球场坐标

#### Scenario: homography 不可用
- **WHEN** 缺少 homography
- **THEN** 系统 SHALL 保留图像拟合结果
- **AND** 重建 SHALL 标记为 `image_only` 模式，不生成球场空间曲线

### Requirement: 单调约束的锚点校正
系统 SHALL 以事件锚点为主轴对 pseudo-ground path 进行校正，并对纵向进度施加单调性约束。

#### Scenario: 建立锚点主轴
- **WHEN** 飞行段起止锚点为 A0 与 A1
- **THEN** 系统 SHALL 以 `axis = normalize(A1 - A0)` 为主轴
- **AND** 将 pseudo path 分解为 `longitudinal_progress(t)` 与 `lateral_residual(t)`

#### Scenario: 纵向进度单调
- **WHEN** 一个飞行段内没有击球或弹地事件
- **THEN** `longitudinal_progress(t)` SHALL 满足 `s(t0)=0`、`s(t1)=1`、`ds/dt >= 0`（isotonic regression 或 monotonic cubic fitting）
- **AND** 系统 MUST NOT 允许无事件的段内纵向折返

#### Scenario: 横向残差受限
- **WHEN** 系统保留 pseudo path 的横向残差
- **THEN** 横向残差 SHALL 经过鲁棒平滑、幅度上限限制与横向加速度限制
- **AND** 端点残差 SHALL 逐渐归零以对齐锚点

#### Scenario: 生成校正后球场坐标
- **WHEN** 锚点与横向残差均确定
- **THEN** 系统 SHALL 输出 `court_xy(t) = A0 + s(t)*(A1 - A0) + bounded_lateral_residual(t)`

### Requirement: 空间锚点可信度分级
系统 SHALL 按锚点类型区分可信度，只有弹地点可无条件经单应转换为可信球场坐标。

#### Scenario: 弹地点为硬锚点
- **WHEN** 锚点类型为 `bounce`
- **THEN** 该锚点 SHALL 为硬锚点，高度严格为 0
- **AND** 其球场坐标 SHALL 视为可信并严格对齐

#### Scenario: 击球点为软锚点
- **WHEN** 锚点类型为 `contact`（击球点）
- **THEN** 该锚点 SHALL 为软锚点，仅作软估计
- **AND** 系统 SHALL 为其保存较大的空间不确定度
- **AND** MUST NOT 因其是事件边界就认为单应映射准确

#### Scenario: 普通端点与丢失边界
- **WHEN** 锚点类型为 `raw endpoint` 或 `loss boundary`
- **THEN** `raw endpoint` SHALL 作为弱约束且不视为地面位置
- **AND** `loss boundary` SHALL 不作为空间锚点参与重建

### Requirement: 锚点数量降级策略
系统 SHALL 根据可用空间锚点数量选择重建模式，锚点不足时不得伪装高可信球场空间重建；单锚点模式 MUST 识别锚点位于段起点还是段终点，并严格对齐对应端。

#### Scenario: 双锚点模式
- **WHEN** 起止均为空间锚点（bounce→hit、hit→bounce、hit→hit、bounce→bounce）
- **THEN** 系统 SHALL 执行 `dual_anchor_warp` 完整双端锚定重建
- **AND** 重建模式 SHALL 记录为 `dual_anchor_warp`

#### Scenario: 起点单锚点模式
- **WHEN** 仅起点有空间锚点（bounce→loss、hit→loss）
- **THEN** 系统 SHALL 将第一个可用重建采样严格对齐起点锚点
- **AND** 另一端 SHALL 使用 pseudo path 相对位移并渐隐，不生成精确终点
- **AND** 该段总体质量上限 SHALL 受限

#### Scenario: 终点单锚点模式
- **WHEN** 仅终点有空间锚点（unknown→bounce、loss→hit）
- **THEN** 系统 SHALL 将最后一个可用重建采样严格对齐终点锚点
- **AND** 未知起点 SHALL 使用反向相对位移并渐隐
- **AND** MUST NOT 把第一个采样错误地对齐终点锚点

#### Scenario: 无锚点模式
- **WHEN** 段两端均无空间锚点（loss→loss、unknown→unknown）
- **THEN** 系统 SHALL 标记 `reconstruction_mode = image_only` 或 `single_view_visual_arc`
- **AND** `single_view_visual_arc` MUST 标记 `metric_validity = visualization_only` 且默认使用低可信视觉编码
- **AND** 原始图像拟合 SHALL 保留用于视频轨迹或调试

#### Scenario: 锚点距离过小
- **WHEN** 两端锚点距离小于 `minimum_anchor_distance`
- **THEN** 系统 SHALL 降级为 `local_visual_arc` 或不输出该重建段
- **AND** MUST NOT 以极小距离为分母计算主轴

### Requirement: 事件边界感知的高度模型
系统 SHALL 按段类型设置高度边界，不得统一把两端强制置零。

#### Scenario: hit → bounce 段高度
- **WHEN** 飞行段类型为 `hit → bounce`
- **THEN** `z_start` SHALL 为 `estimated_contact_height`，`z_end` 严格为 0

#### Scenario: bounce → hit 段高度
- **WHEN** 飞行段类型为 `bounce → hit`
- **THEN** `z_start` 严格为 0，`z_end` SHALL 为 `estimated_contact_height`

#### Scenario: hit → hit 段高度
- **WHEN** 飞行段类型为 `hit → hit`
- **THEN** `z_start > 0` 且 `z_end > 0`，段内 SHALL 存在峰值

#### Scenario: bounce → loss 段高度
- **WHEN** 飞行段类型为 `bounce → loss`
- **THEN** `z_start` 严格为 0，`z_end` SHALL 标记为未知
- **AND** 系统 SHALL 仅显示可信区间，末端渐隐

#### Scenario: 未知到未知段高度
- **WHEN** 段两端均为 `unknown`
- **THEN** 系统 SHALL NOT 伪造完整高度曲线

### Requirement: 可配置接触高度先验
系统 SHALL 使用可配置的全局低可信接触高度先验作为击球点高度来源，不按球场区域自动推导。

#### Scenario: 默认先验配置
- **WHEN** 系统生成击球点高度
- **THEN** 默认使用 `default_contact_height_m = 1.10`，裁剪范围 `0.45–2.40m`
- **AND** `contact_height_uncertainty_m` SHALL 进入质量评分
- **AND** 高度来源 SHALL 记录为 `global_contact_prior`，置信度 SHALL 标记为低

#### Scenario: 不按球场区域自动修改
- **WHEN** 球员位于底线或非截击区（NVZ）
- **THEN** 系统 MUST NOT 依据球场区域自动修改接触高度先验

#### Scenario: serve 边界按 hit 类型处理
- **WHEN** 段边界由 serve 事件产生
- **THEN** 高度 SHALL 按 hit 类型处理
- **AND** 来源 SHALL 标记为 `serve_prior`

### Requirement: 重建模式与有效性声明
系统 SHALL 在重建产物中声明重建模式与坐标语义，避免把估算高度误用于真实测量。

#### Scenario: 声明重建模式
- **WHEN** 输出重建产物
- **THEN** 产物 SHALL 包含 `reconstruction_mode`（如 `event_anchored_2_5d`）
- **AND** 坐标语义 SHALL 标记 `metric_validity = visualization_only`

#### Scenario: 不输出真实三维测量
- **WHEN** 系统缺少相机内外参
- **THEN** 系统 MUST NOT 输出"真实最高点"或"真实三维速度"
- **AND** 系统 SHALL 明确说明估算高度不用于真实最高点与三维球速测量

### Requirement: 球员上下文接入
系统 SHALL 在重建链中接收球员上下文，用于击球归属与 Shot 组装，且 SHOULD 直接使用内存中的球员产物而非重新读取 JSON 文件。

#### Scenario: 内存传递球员上下文
- **WHEN** pipeline 执行重建链
- **THEN** 球员渲染轨迹、姿态帧与跟踪叠加帧 SHALL 直接以内存对象传入重建入口
- **AND** 入口 SHALL 构造 `PlayerAttributionContext` 供归属模块消费

#### Scenario: 无球员上下文时降级
- **WHEN** 球员上下文不可用（如单打简版任务或跟踪失败）
- **THEN** 重建链 SHALL 仍完成事件切段与 2.5D 重建
- **AND** 击球事件 SHALL 输出 `hitter_player_id = null` 与 `ownership_status = unassigned/not_applicable`，MUST NOT 伪造归属

### Requirement: 击球事件时间窗对齐
系统 SHALL 在事件仲裁与归属之间保持时间一致性，归属时间窗以事件时间戳为基准。

#### Scenario: 归属使用事件时间戳
- **WHEN** 击球候选进入归属阶段
- **THEN** 归属 SHALL 以候选 `timestamp_sec` 为基准查询接触时间窗
- **AND** 归属结果 SHALL 关联回原候选，保证 `attributed_frame_index` 与候选事件一致

### Requirement: serve 事件播种
系统 SHALL 将 serve 事件的 `player_id` 传递到 serve_reset 边界事件，供 Shot 播种使用。

#### Scenario: serve player_id 补传
- **WHEN** serve 事件携带 `player_id` 且置信度达标
- **THEN** 转换后的 serve_reset 事件 SHALL 保留该 `player_id`
- **AND** Shot 组装 SHALL 使用该 `player_id` 播种新 Shot

### Requirement: v2 产物输出
系统 SHALL 输出升级后的重建产物，`schema_version` 为 `reconstructed_ball_trajectory.v2`，包含球员名单、事件归属与 Shot 信息。

#### Scenario: 产物含球员名单
- **WHEN** 系统输出 v2 产物
- **THEN** 产物顶层 SHALL 包含 `player_roster`，列出 `player_id`、`render_slot` 与 `initial_side`

#### Scenario: 产物含 Shot 归属
- **WHEN** 系统输出 v2 产物
- **THEN** 每个飞行段 SHALL 包含 `shot_id`、`hitter_player_id`、`hitter_render_slot`、`ownership_status`、`ownership_confidence` 与 `ownership_source_event_id`

#### Scenario: 重建失败降级
- **WHEN** 重建链异常
- **THEN** 产物 SHALL 输出 `status = failed` 且不阻断整个分析任务

### Requirement: 场外球点的证据分类
系统 SHALL 将标准场地边线和可配置比赛环境边界分开处理；坐标越过标准边线 SHALL 只产生位置事实，MUST NOT 单独作为误检拒绝条件或自动界外判罚。

#### Scenario: 真实界外落点候选
- **WHEN** bounce 位于标准场地边线外但仍处于比赛环境边界内，且同段轨迹连续、端点时间与图像证据一致
- **THEN** 系统 SHALL 保留该 bounce 并标记 `legal_out_candidate`
- **AND** SHALL 明确该分类不是自动判罚结论

#### Scenario: 标定不确定可解释的场外坐标
- **WHEN** 点略超比赛环境边界但偏差落在标定/投影不确定范围内
- **THEN** 系统 SHALL 标记 `calibration_uncertain` 并降低质量
- **AND** SHALL NOT 仅凭该坐标删除原始观测

#### Scenario: 环境离群误检
- **WHEN** 点严重超出比赛环境边界且同时出现轨迹跳变、静止模式、高回投残差或另一视角不支持
- **THEN** 系统 SHALL 标记 `environment_outlier` 并从正式重建段排除
- **AND** SHALL 保存所有触发证据用于审计
