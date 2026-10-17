## ADDED Requirements

### Requirement: 执行状态与产物可用性和质量正交
节点状态 SHALL 使用 pending、running、cached、completed、failed、blocked、canceled、skipped；availability SHALL 使用 available、location_unavailable、missing、corrupt；quality SHALL 表达 sufficient、insufficient_evidence、truncated 或 no_candidates 等契约值。unavailable MUST NOT 作为混用的节点状态。模型缺失 SHALL 表达稳定的执行错误和 model_environment 归因。

#### Scenario: 没有检测目标
- **WHEN** 检测正常运行且产物结构有效，但无候选
- **THEN** 节点 SHALL 为 completed，产物 SHALL 为 available，质量 SHALL 为 no_candidates
- **AND** SHALL 不制造算法失败或空文件占位

#### Scenario: 必需上游失败
- **WHEN** 某节点的必需上游失败且无兼容替代输入
- **THEN** 下游 SHALL 为 blocked 并引用阻断原因
- **AND** SHALL 不初始化该下游模型

### Requirement: 目标成功策略显式且可重现
默认 failure_policy=all_targets SHALL 要求所有请求目标处于 completed/cached，已执行但非必需的可选证据失败不得单独导致 Job 失败。显式 best_effort SHALL 仅在至少一个请求目标完成且其余目标失败/阻断时返回 succeeded 与 partial 完整性；全部目标失败 SHALL 仍为 failed。独立成功产物 MUST 保留；质量不足 SHALL 按输出契约表达，不自动等同计算失败。

一个分支计算失败 SHALL 只阻断依赖它的必需消费者，其余独立请求分支 SHALL 继续至可判定终态；取消、lease 丢失等控制信号可中止所有未完成计算。

#### Scenario: 两个目标一成一败
- **WHEN** player.detect 完成、ball.detect 失败
- **THEN** all_targets SHALL 得到 failed 与 partial 运行清单
- **AND** best_effort SHALL 得到 succeeded 与 partial 运行清单
- **AND** 两种策略 SHALL 均保留人框产物，且不得把 partial 显示为完整成功

#### Scenario: 可选证据失败
- **WHEN** 所有请求目标完成，但一个声明为可选且允许缺失的证据节点失败
- **THEN** Job SHALL 可成功
- **AND** 实际缺失及未消费状态 SHALL 进入产物身份和诊断

### Requirement: 节点间以持久化产物交付
v1 SHALL 使用已发布产物作为跨节点输入边界，并允许后续节点对其有界窗口重新解码所需 RGB。Resources SHALL 按实际执行节点懒加载并在 finally 中释放；不得持久化整片 RGB 帧缓存，不得承诺所有能力共享一次解码。现有 joint 内部协同运行 SHALL 保持一个受控执行边界。

#### Scenario: 从人框计算姿态
- **WHEN** player.detect 已被缓存而 pose.sequence 未被缓存
- **THEN** 姿态 SHALL 复用人框并只对所需窗口取得 RGB
- **AND** SHALL 不重新运行人框检测

#### Scenario: 全缓存执行
- **WHEN** 所有目标由已验证的产物满足
- **THEN** 运行 SHALL 不创建 capture 或模型资源

### Requirement: 原子发布受执行租约保护
发布 SHALL 依次使用尝试隔离的临时输出、内容/schema 校验、文件 finalize 和控制面事务。事务 MUST 核验当前 lease/attempt，再原子登记 Manifest、Job 引用、输入血缘、节点终态及缓存指针。数据库提交前的文件 MUST 不成为可复用完成产物；文件系统与 SQLite 不得被描述为同一个物理事务。

#### Scenario: finalize 后进程崩溃
- **WHEN** 文件已 finalize 而数据库发布事务尚未提交
- **THEN** 文件 SHALL 是可对账的 orphan，不得被缓存命中
- **AND** 后续尝试 SHALL 不覆盖原文件

#### Scenario: 租约过期的迟到生产者
- **WHEN** 旧 Worker 在 lease 丢失后尝试发布
- **THEN** 数据库事务 SHALL 拒绝其结果绑定与缓存指针更新
- **AND** 其文件 SHALL 保持未发布状态并可安全清理

### Requirement: 节点重试和恢复保留成功证据
modular_v1 SHALL 在有限策略内重新执行失败节点，并在重试前重新核验已发布输入。v1 不要求节点内部 checkpoint；失败节点 SHALL 从该节点起始状态重跑，不得沿用不完整有状态实例。已发布上游/独立分支 SHALL 不因节点重试被删除。job attempt 与 node_attempt MUST 分开记录；重启恢复 SHALL 在原冻结计划上核验产物后复用。

#### Scenario: 姿态失败后重跑
- **WHEN** pose.sequence 执行失败且可重试，人框已发布
- **THEN** 重试 SHALL 复用通过完整性校验的人框
- **AND** SHALL 不重跑人框、球检测或完整 legacy executor

#### Scenario: 重启后缓存损坏
- **WHEN** interrupted Job 被显式恢复，而一个已发布产物被判定损坏
- **THEN** 系统 SHALL 仅重算该产物及受实际输入变化影响的消费者
- **AND** SHALL 保留原尝试失败证据与旧产物历史引用

### Requirement: 控制信号穿透并保留部分产物
取消、lease 丢失和超时 SHALL 作为既有控制信号传至 Worker，不得转换为通用 internal_defect。执行 SHALL 在解码/推理安全检查点响应并释放资源；已合法发布产物 SHALL 保留为部分结果，未发布临时文件 SHALL 清理或标记。部分结果 MUST 不作为完整成功报告返回。

#### Scenario: 双摄节点取消
- **WHEN** 模块双摄检测收到有效取消
- **THEN** 执行 SHALL 在安全检查点退出并 release 两路 capture
- **AND** Job SHALL 为 canceled，运行清单 SHALL 明确未完成目标和已保留产物
