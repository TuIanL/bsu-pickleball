## ADDED Requirements

### Requirement: 证据关联使用类型化且可解析的对象引用
关系产物 SHALL 使用版本化 ObjectRef，至少包含 artifact_id、object_type、local_id 及适用的主体/机位/epoch 作用域。ObjectRef MUST 可解析至具体源对象；Swing、Contact、Bounce、Shot、Landing、Rally 和动作属性之间的关联 SHALL 存放于独立关系产物，不得通过改写源 payload 添加隐含连接。

#### Scenario: 一次挥拍关联多个接触候选
- **WHEN** fixture 为一个 Swing 给出两个可能的 Contact
- **THEN** 关系产物 SHALL 保留候选引用、分数、时间约束和关联实现版本
- **AND** SHALL 不覆盖 Swing 或 Contact 的原始证据

### Requirement: 关联明确时间约束与歧义
关联实现 SHALL 声明主体约束、时间域/容差、坐标条件、候选排序及冲突策略。missing、ambiguous 和 insufficient_evidence MUST 可表达；不得仅凭最近时间强行补齐已有严格 Shot/segment/event 引用。

#### Scenario: 落点缺少严格引用
- **WHEN** Landing 与 Shot 之间缺少 required event/segment 引用
- **THEN** 系统 SHALL 保留缺失/不确定状态
- **AND** SHALL 不按最近时间猜出看似完整的确定连接

#### Scenario: 引用对象不可读
- **WHEN** 关系指向不可用或损坏的源产物
- **THEN** inspect SHALL 暴露关系可用性和来源问题
- **AND** SHALL 不返回无来源的确定动作结论

### Requirement: 事实与解释分别版本化
观测、运动证据、挥拍阶段、动作属性、Shot 语义及战术解释 SHALL 使用独立产物和版本。新分类模型或规则 SHALL 通过新派生产物引用既有证据，不得修改已发布检测/事件事实。

#### Scenario: 升级丁克球分类器
- **WHEN** 同一 Swing、Contact、Landing、court/rally 上下文被新语义实现重新分类
- **THEN** 系统 SHALL 生产新的 shot.semantic 产物并保留输入引用
- **AND** 原始姿态、球轨迹和落点 SHALL 不因分类规则更新而重算或改变

### Requirement: 动作属性与比赛语义保持正交
动作结果 SHALL 分别表达正反手/挥拍形式、击球技术/战术语义、回合阶段、是否截击等属性，携带 taxonomy 版本、分数及证据充分性。现有 ShotEvent.shot_type 的 legacy stage 含义 MUST 保持兼容，不得直接重定义为 dink/drop。模型置信度与证据充分性 MUST 分开。

#### Scenario: 第三拍丁克假设
- **WHEN** fixture 的动作属性与落点支持某种软击语义，且 rally stage 为 third
- **THEN** 结果 SHALL 分别记录 stage、stroke 属性和 semantic 假设
- **AND** SHALL 不使用同一个互斥字段同时表示 third 与 dink

#### Scenario: 高置信度但证据缺失
- **WHEN** 分类器给出高分而所需球落点不可用
- **THEN** 输出 SHALL 明确缺少的证据和可接受的结论范围
- **AND** SHALL 不把高分作为补齐缺失证据的理由

### Requirement: 未来能力用合同 fixture 验证扩展
v1 SHALL 使用显式测试 fixture 验证 racket.player_association、motion.upper_limb、swing.segment、contact.detect、stroke.classify、shot.assemble、shot.semantic、context.rally 和 tactics.analyze 的声明/关联位置。fixture MUST 与生产 Registry 的 planned 状态区分，不能作为真实球拍、挥拍或动作模型的实现交付。

#### Scenario: 姿态或多模态动作实现扩展
- **WHEN** 测试注册 pose-only、RGB-only 或多模态 stroke.classify fixture
- **THEN** Planner SHALL 按各实现声明展开不同依赖
- **AND** 不要求为所有实现强制增加球拍、姿态或落点依赖
