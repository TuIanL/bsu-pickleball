# ball-contact-event-detector Specification

## Purpose
定义启发式击球候选检测（raw hit candidate）与事件仲裁的两阶段职责：`BallContactEventDetector` 只负责球运动突变检测，`BallEventResolver.prefilter` 成为弹地抑制的唯一权威，`finalize` 结合球员归属输出最终事件。suppressed/rejected 候选不进入正式事件列表。
## Requirements
### Requirement: 启发式击球候选检测
系统 SHALL 提供基于轨迹运动特征而非姿态关键点的启发式击球候选检测器，输出原始候选事件状态。检测器 SHALL 只负责球运动突变检测，不读取 `bounce_events`，不执行弹地抑制。

#### Scenario: 输出击球候选
- **WHEN** 检测器在突变前后均检测到连续有效观测，且速度方向变化达到阈值或速度幅值发生明显变化
- **THEN** 检测器 SHALL 输出 `hit_candidate` 事件
- **AND** 候选事件 SHALL 包含 frame_index、timestamp_sec、image_xy、confidence 与 diagnostics

#### Scenario: 候选缺少前后连续观测
- **WHEN** 突变前或突变后缺少足够连续的有效观测点
- **THEN** 检测器 SHALL 标记该候选为 `rejected_hit`
- **AND** 拒绝原因 SHALL 记录为结构化字符串（如 `insufficient_context_before` / `insufficient_context_after`）

#### Scenario: 长缺失后首次重新锁定不作为击球
- **WHEN** 当前帧是长时间缺失之后的首次重新锁定
- **THEN** 检测器 SHALL NOT 将该帧标记为击球候选
- **AND** 该帧仅作为轨迹恢复点处理

#### Scenario: 满足最小事件间隔
- **WHEN** 连续两个击球候选的时间间隔小于配置的最小事件间隔（refractory period）
- **THEN** 检测器 SHALL 保留置信度更高的候选
- **AND** 丢弃间隔内的另一个候选

#### Scenario: 检测器不读取弹地事件
- **WHEN** 检测器执行候选检测
- **THEN** 检测器 SHALL NOT 接收或读取 `bounce_events`
- **AND** 弹地抑制 SHALL 只由 `BallEventResolver.prefilter` 执行

### Requirement: 突变上下文与拟合残差校验
系统 SHALL 在突变前后分别校验轨迹拟合残差，确认突变不是孤立误检造成的假象。

#### Scenario: 突变前后拟合残差较低
- **WHEN** 突变前后两段轨迹的拟合残差分别低于阈值
- **THEN** 候选 SHALL 保留并继续进入仲裁
- **AND** 前后残差 SHALL 记录在 diagnostics 中

#### Scenario: 突变一侧拟合残差过高
- **WHEN** 突变前或突变后的拟合残差超过阈值
- **THEN** 候选 SHALL 被标记为 `rejected_hit`
- **AND** 拒绝原因 SHALL 记录为 `high_fit_residual`

### Requirement: 击球与弹地候选仲裁
系统 SHALL 通过 `BallEventResolver` 两阶段仲裁解决击球候选与弹地候选的冲突：`prefilter` 为弹地抑制唯一权威，`finalize` 结合球员归属输出最终事件。弹地抑制 SHALL 使用有符号非对称时间窗口。

#### Scenario: 高可信弹地存在时抑制击球
- **WHEN** 候选时间与已确认 bounce 的有符号时间差位于非对称窗口内（bounce 前 0.07 秒内或 bounce 后 0.10 秒内），且 bounce 置信度达标
- **THEN** prefilter SHALL 标记该候选为 `suppressed`
- **AND** 该候选 SHALL 只进入 diagnostics，MUST NOT 生成正式边界事件

#### Scenario: bounce 后超出容差的候选放行
- **WHEN** 候选时间晚于 bounce 超过配置的 after 容差（如 +0.12 秒）
- **THEN** prefilter SHALL NOT 仅凭时间接近抑制该候选
- **AND** 候选 SHALL 进入球员归属阶段，由球员时空证据继续判断

#### Scenario: 最终事件只含确认结果
- **WHEN** prefilter 与 finalize 完成
- **THEN** 正式事件列表 SHALL 只包含 `event_status ∈ {confirmed, ambiguous}` 的击球事件
- **AND** 事件列表 SHALL NOT 包含 `suppressed_by_bounce` 类型的 HIT 事件

#### Scenario: 抑制窗口配置快照
- **WHEN** 系统执行弹地抑制
- **THEN** 配置快照 SHALL 记录 `bounce_suppress_before_sec`、`bounce_suppress_after_sec`、`effective_fps` 与 `frame_stride`
- **AND** 快照 SHALL 写入产物 diagnostics 以便数据集调参

### Requirement: 击球事件来源标注
系统 SHALL 为每个被确认的击球事件记录事件来源类型与归属方法。

#### Scenario: 启发式来源
- **WHEN** 击球事件由纯启发式规则确认且无球员归属
- **THEN** 事件 `source` SHALL 为 `heuristic`

#### Scenario: 归属来源标注
- **WHEN** 击球事件完成球员归属
- **THEN** 事件 SHALL 记录归属方法（如 `pose_bbox_fused`、`bbox_fused`、`serve_seeded`）
- **AND** 归属方法 SHALL 区分是否使用了姿态证据

### Requirement: 确定性输出
系统 SHALL 对相同输入产生确定性的候选事件序列。

#### Scenario: 相同输入产生相同事件
- **WHEN** 对同一份轨迹输入重复运行击球检测
- **THEN** 击球候选、仲裁结果与事件 ID 序列 SHALL 完全一致

### Requirement: 击球候选检测使用真实时间连续性
系统 SHALL 以 `timestamp_sec`、effective FPS 和 frame stride 判断击球候选前后的连续观测、长缺失与最小事件间隔，MUST NOT 使用固定 `frame_index` 差为 1 作为连续条件。

#### Scenario: 抽帧轨迹中的正常连续点
- **WHEN** 连续处理样本的 source frame index 差等于配置 frame stride 且时间差在容差内
- **THEN** detector SHALL 将其作为连续上下文参与方向和速度突变检测
- **AND** SHALL NOT 将该点当成长缺失后的首次重新锁定

#### Scenario: 真实长时间丢失
- **WHEN** 相邻有效观测的时间差超过配置的 contact context gap
- **THEN** detector SHALL 在缺口两侧停止构造击球候选
- **AND** SHALL 保存基于秒的拒绝诊断
