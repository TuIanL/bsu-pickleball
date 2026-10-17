# analysis-capability-runtime Specification

## Purpose

定义静态能力注册、类型化依赖规划与模块执行合同，使局部分析仅运行冻结计划所需能力，并清楚区分可执行实现与未来扩展。

## Requirements

### Requirement: 能力与实现使用独立的稳定契约
系统 SHALL 使用静态内置 Registry 描述能力 ID、契约版本、输入输出类型、实现列表和可用状态。每种实现 MUST 单独声明版本、必需/可选输入、替代方案、参数 schema、模型摘要、上下文需求、资源及窗口策略。Registry MUST NOT 使用动态插件发现，也不得在注册或查询时初始化视觉模型。

#### Scenario: 新增球拍能力
- **WHEN** 注册 racket.detect 的新实现
- **THEN** 系统 SHALL 通过声明及适配器接入，而不要求修改 AnalysisPipeline.run()
- **AND** 未请求且无依赖引用时 SHALL 不执行该能力

#### Scenario: 能力与数据版本分别演进
- **WHEN** stroke.classify 的模型变化但输出结构与标签定义不变
- **THEN** 实现版本和模型摘要 SHALL 更新
- **AND** 能力 ID、产物 schema 和标签体系版本 SHALL 不因模型替换而自动改名

### Requirement: 实现选择及输入绑定形成最小依赖闭包
Planner SHALL 按显式实现或确定的默认实现展开类型化依赖，拒绝循环、未知能力和不兼容输入；必需输入 MUST 满足，可选输入的启用、缺失和绑定方式 MUST 明确。已绑定的兼容产物可以满足依赖，无须为其补算生产者。可选证据实际是否被消费 MUST 进入执行记录和缓存身份。

#### Scenario: 只请求球检测
- **WHEN** 请求 ball.detect 且没有其他目标
- **THEN** 计划 SHALL 只包含所选实现需要的帧源/时间信息和球检测节点
- **AND** SHALL NOT 隐式加入 player、pose、回合切分、metrics、insights 或 report

#### Scenario: 替代实现
- **WHEN** 测试 fixture 选择 pose-only 的 swing 实现
- **THEN** Planner SHALL 不加入 racket 依赖
- **AND** 多模态 fixture 才 SHALL 展开所选实现实际声明的输入

#### Scenario: 显式固定输入
- **WHEN** 用户为下游目标绑定了兼容的具体 ArtifactRef
- **THEN** 计划 SHALL 保留该输入及其内容身份
- **AND** SHALL NOT 为方便而改读同类型的最新产物

### Requirement: 全能力地图区分规划与可执行状态
Registry SHALL 为球员、球、球拍、姿态、运动证据、挥拍/接触、Shot/Rally、动作属性、语义、战术及评价定义扩展域，并区分 planned 与 implemented。v1 MUST 真实提供 player.detect、ball.detect、pose.sequence 的适配器；未来能力仅用契约和显式测试 fixture 验证扩展性。

#### Scenario: 请求尚未实现的目标
- **WHEN** run 请求 planned 的 racket.detect 或 shot.semantic 且没有可执行实现
- **THEN** 系统 SHALL 在创建可运行 Job 和加载模型之前返回 capability_not_implemented
- **AND** SHALL NOT 发布空成功产物或自动退回 legacy 完整分析

#### Scenario: 完整产品分析的本期边界
- **WHEN** v1 接收到现有完整比赛分析请求
- **THEN** 系统 SHALL 保持其 legacy 路径及业务定义
- **AND** SHALL NOT 要求本期提前迁移 events、metrics、insights 或报告
- **AND** 后续完整模块化分析 SHALL 作为明确版本的组合计划在独立 change 中接入

### Requirement: 执行计划不可变且指纹稳定
系统 SHALL 在入队前冻结实现、有效参数、模型摘要、来源/上下文身份、采样、窗口、依赖、输入选择、资源策略和失败策略。plan_hash MUST 仅由规范化的计算合同产生，排除 plan_id、job_id、created_at、输出位置、plan_hash 自身、缓存提示及运行状态。显式固定的输入产物身份 MUST 参与指纹。重试和恢复 MUST 沿用原计算合同。

#### Scenario: 同一请求的稳定指纹
- **WHEN** API 与 CLI 分别规划同一逻辑请求，生成不同 ID/时间且缓存可用性改变
- **THEN** 两份计划 SHALL 有相同 plan_hash
- **AND** 缓存提示变化 SHALL 不改变选定的计算语义

#### Scenario: 默认配置在入队后变化
- **WHEN** 模型路径、默认实现或全局推理开关在 Job 入队后改变
- **THEN** Worker SHALL 使用冻结的实现与有效配置
- **AND** 身份无法核验的原模型 SHALL 显式失败，而不是替换为当前默认模型

### Requirement: 窗口解析先于缓存判断
Planner SHALL 先解析依赖的窗口、采样及上下文，再生成缓存身份和预览提示。对于尚未产生的上游，计划 SHALL 保存生产者合同或固定输入，执行时在真实输入就绪后解析下游缓存键并重新验证可用性。缓存提示 MUST NOT 是执行授权或保证。

#### Scenario: 上游完成后判断下游缓存
- **WHEN** 下游依赖的产物在 preview 时尚未存在
- **THEN** preview SHALL 将缓存判断标记为待绑定
- **AND** 执行器 SHALL 使用实际输入产物后再决定 hit/miss

#### Scenario: 入队后缓存被删除
- **WHEN** preview 显示命中但执行时对应缓存已不存在
- **THEN** 系统 SHALL 按原实现合同重新计算或返回明确不可用原因
- **AND** SHALL NOT 使用失效提示跳过计算并伪造输出

### Requirement: 执行图与证据关系图分离
执行依赖 SHALL 是无环的生产/消费关系；事件之间的关联 SHALL 由独立版本化关系对象表达。观测二维轨迹、清洗轨迹、事件约束重建轨迹 MUST 使用不同类型或明确阶段标识，禁止由名称混用引入循环。

#### Scenario: 事件先于重建
- **WHEN** 一个实现由二维轨迹产生接触/弹跳事件，再以这些事件约束三维重建
- **THEN** 计划 SHALL 区分输入观测轨迹与输出重建轨迹
- **AND** SHALL NOT 让同一产物同时成为该节点未完成的输入和输出

#### Scenario: 关联双向查询
- **WHEN** Swing 与 Contact 允许相互查询关联
- **THEN** 这种关系 SHALL 不被解释为两个执行节点相互依赖

### Requirement: 能力运行不隐式继承产品组合
modular_v1 SHALL 只执行冻结计划内所需的计算。资源工厂 MUST 在缓存判断后按实际执行节点初始化资源，缓存满足的目标 MUST 不打开视频或加载模型。

#### Scenario: 全部目标命中
- **WHEN** 所有请求目标及必需输入均由兼容缓存满足
- **THEN** 解码器打开次数和模型执行次数 SHALL 均为零
- **AND** 运行清单 SHALL 记录实际复用的产物
