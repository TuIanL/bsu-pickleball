## ADDED Requirements

### Requirement: 窗口具有计算和输出的不同语义
窗口 SHALL 使用半开区间，并区分用户范围、节点必需输入/计算范围和输出选择。Planner MUST 从消费者向生产者传播上下文需求，中间产物可以保留下游所需上下文；用户可见结果按目标选择规则输出，不得提前裁掉下游需要的预热证据。

#### Scenario: 挥拍的前置上下文
- **WHEN** 测试 fixture 的挥拍节点需要请求开始前的姿态
- **THEN** 上游姿态输入范围 SHALL 被扩展
- **AND** 中间产物 SHALL 保留该上下文，最终输出 SHALL 按动作选择规则决定是否包含该挥拍

#### Scenario: 原始检测窗口
- **WHEN** 请求 42s–72s 的 ball.detect 且实现无上下文需求
- **THEN** 模型采样范围 SHALL 限定为该范围
- **AND** SHALL 不继承 legacy 的整场回合切分或其他能力预热

### Requirement: 上下文扩展受有限预算约束
局部请求 SHALL 声明或使用明确的有限扩展预算。v1 默认前后各最多 2000ms；策略、实际扩展和理由 MUST 进入计划。超过预算的必需输入 SHALL 在入队前拒绝，动态边界寻找 SHALL 在预算内结束并表达截断/证据不足，不得隐式扩大整场。

#### Scenario: 依赖层层扩展
- **WHEN** 多层依赖合并后的必需上下文超过请求预算
- **THEN** Planner SHALL 返回 window_budget_exceeded 和需要的范围
- **AND** SHALL 不静默增加预算

#### Scenario: 无法找到完整事件边界
- **WHEN** 在许可未来范围内没有找到 Shot 或挥拍结束边界
- **THEN** 实现 SHALL 输出明确的 truncated/insufficient_evidence 或契约定义的错误
- **AND** SHALL NOT 为寻找边界继续扫描整个 take

### Requirement: 输出选择规则明确且版本化
目标 SHALL 声明样本按时间选取、事件按接触点选取或按区间相交选取等规则，并保留事件边界完整性。未实现事件算法的 v1 SHALL 通过契约 fixture 验证这些选择，不能将模型尚未实现视为已识别。

#### Scenario: 动作跨越请求开始
- **WHEN** fixture 的挥拍在 41s 开始、43s 接触，请求为 42s–72s 且选择按接触点
- **THEN** 该动作 SHALL 被选入，并保留实际起止和截断状态
- **AND** SHALL NOT 把开始时间强行改成 42s 冒充完整动作

### Requirement: 时间映射和采样身份可复现
计划 SHALL 记录来源帧、PTS/公共时间映射、采样方式、stride/频率、相位锚点及初始化模式。单摄与双摄 SHALL 复用既有时间组件，双摄映射不得使用独立 nominal FPS 冒充正式同步。

#### Scenario: 相同 stride 不同相位
- **WHEN** 两种采样都使用 stride=2 但起始相位不同
- **THEN** 系统 SHALL 将其视为不同输入计划与缓存身份

#### Scenario: 双摄无新帧
- **WHEN** canonical clock 对第二机位返回 no_new_frame
- **THEN** 有状态消费者 SHALL 不重复提交同一 source frame
- **AND** 观测清单 SHALL 保留该映射状态

### Requirement: 非法窗口和 seek 失败不得整场回退
缺少成对边界、逆序、无有效媒体交集或时间映射失败 SHALL 返回结构化错误。部分越界 SHALL 记录裁剪和缺少上下文。解码器为关键帧定位读取的额外帧 MUST 与正式模型采样区分，并记录读取范围；seek 失败 MUST NOT 从头分析整段视频。

#### Scenario: 定位失败
- **WHEN** 实际定位不能满足冻结的窗口与时间要求
- **THEN** 节点 SHALL 失败或显式不可用
- **AND** SHALL NOT 把 clip 字段清空后重试全片

#### Scenario: GOP 定位预读
- **WHEN** 解码器需要从附近关键帧开始预读
- **THEN** 预读 SHALL 受定位策略约束并被记录
- **AND** 范围外预读帧 SHALL NOT 被送入未声明需要它们的模型或正式统计
