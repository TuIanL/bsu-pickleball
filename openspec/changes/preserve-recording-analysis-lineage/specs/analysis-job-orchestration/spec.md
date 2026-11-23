## ADDED Requirements

### Requirement: 任务来源快照与计算签名分离

系统 SHALL 为每个新建分析任务持久化一份来源快照，记录该任务的业务来源（录制会话、登记视频、CaptureTake、机位标识）及其获得方式。

来源快照 MUST NOT 参与 `inputSignature`、`configSignature` 或 `plan_hash` 的计算。既有计算缓存身份 MUST 逐字保持不变：`metadata` 中已存在的来源声明继续按既有规则参与签名，实现 MUST NOT 通过移除或忽略 metadata 字段来改变签名。

来源快照 MUST 只由服务端在创建时写入，MUST NOT 从请求体读取。旧任务缺少该字段时 MUST 视为来源未知，且 MUST NOT 因读取该字段而失败。
双摄 Parent 的来源快照 MUST 保存通过既有绑定核验的完整 `(videoId, cameraSlot, cameraId)` 集合。完整快照 MUST NOT 出现在 HTTP schema；任务摘要只 MAY 暴露安全来源状态投影。

#### Scenario: 来源快照不改变签名

- **WHEN** 同一 `AnalysisJobCreate` 载荷在附带与不附带来源快照两种情况下分别计算签名
- **THEN** 两次 `inputSignature` 与 `configSignature` SHALL 相等
- **AND** `plan_hash` SHALL 相等

#### Scenario: metadata 内的来源声明照旧参与签名

- **WHEN** 两个请求的 `metadata.recording_session_id` 不同
- **THEN** 其 `inputSignature` SHALL 不同（既有行为，本 change 不改变）
- **AND** 实现 MUST NOT 通过剥离 metadata 字段或改写签名算法来消除该差异

#### Scenario: 历史任务缺少来源快照仍可读

- **WHEN** 读取一个不包含来源快照字段的历史任务
- **THEN** 系统 SHALL 正常返回该任务摘要
- **AND** 其来源 SHALL 视为未知，而不是报错、推断或等同于「无来源」

#### Scenario: 来源不进入计划哈希

- **WHEN** 模块任务在来源不同的情况下使用相同计划
- **THEN** `plan_hash` MUST 相等
- **AND** 节点缓存与发布记录 MUST 不受来源影响

### Requirement: 来源身份等价与历史声明解析

系统 MUST 使用规范化业务身份比较录制来源。来源获得方式和审计字段 MUST NOT 被误当作业务身份；来源快照缺失的历史任务只有在声明一致且服务端重新核验成功时才 MAY 参与同源筛选。

#### Scenario: 完整一致的历史声明重新核验

- **WHEN** 历史 Job 没有 `sourceSnapshot`，但持久化来源声明一致、足以定位来源，且 Session、Video、Take/绑定重新核验成功
- **THEN** 系统 SHALL 将该候选作为临时 `verified_declared` 来源参加同源比较
- **AND** MUST NOT 回写或改造该历史 Job

#### Scenario: 历史来源声明冲突

- **WHEN** 历史 Job 的顶层来源字段与 metadata 中相同概念的来源字段不一致
- **THEN** 系统 SHALL 将来源状态判为 `unknown`
- **AND** MUST NOT 任选一处声明或复用该候选

#### Scenario: 来源获得方式不同但业务身份相同

- **WHEN** 两份来源的 Session、Video、Take 和完整多视角绑定身份相同，但 `provenance` 分别为 `verified_internal` 与 `verified_declared`
- **THEN** `source_identity_equivalent()` SHALL 判定为等价
- **AND** `declaredBy` 不得改变身份比较或 `fingerprint`

#### Scenario: 单摄机位字段一侧缺省

- **WHEN** 一侧 `cameraSlot` 缺省，另一侧有值，且服务端登记能唯一证明双方指向同一 Video 与机位
- **THEN** 系统 MAY 判为来源等价
- **AND** 只要双方都有 `cameraSlot` 且值不同时 MUST 判为不等价

#### Scenario: 历史来源声明均缺失

- **WHEN** 历史 Job 没有来源快照且所有持久化来源声明均缺失
- **THEN** 系统 SHALL 将其标记为 `unknown`
- **AND** MUST NOT 将其当作显式无来源 Upload

### Requirement: 同签名候选的完整枚举与稳定选择

系统 SHALL 在判定「是否存在可复用任务」时枚举**全部**签名匹配的候选，而不是只取第一条命中。

选择 MUST 分两步且顺序不可交换：先按来源等价判定候选资格，再在合格候选内按可复用状态与不可变排序键选择。来源判定 MUST NOT 依赖任务状态；失败、取消、运行中或中断的任务同样 MUST 参与来源判定，只是不参与最终选择。

排序键 MUST 由不可变字段构成（创建时间与任务 ID）。系统 MUST NOT 以随状态推进而变化的字段（例如最后更新时间）作为选择依据。

当没有任何候选同时满足「签名等价」与「来源等价」时，系统 SHALL 创建独立任务，并 MUST NOT 修改任何旧候选。

#### Scenario: 异源或无来源的首条不遮挡同源候选

- **WHEN** 同签名候选依次为「无来源」「同源」「异源」
- **THEN** 系统 SHALL 复用其中同源且状态可复用的那一条
- **AND** MUST NOT 因首条不可复用就直接新建任务

#### Scenario: 顶层与 metadata 声明不一致的候选不可复用

- **WHEN** 候选任务的顶层录制会话字段与其 metadata 中的录制会话字段不一致
- **THEN** 该候选的来源 MUST 判为不可证明
- **AND** 系统 MUST NOT 任选其中一处当作权威，也 MUST NOT 复用该候选
- **AND** 顶层字段不参与签名，因此该候选仍可能与请求签名相同，系统 MUST 依靠来源判定而非签名差异排除它

#### Scenario: 无合格候选时新建

- **WHEN** 同签名候选全部为异源或无来源
- **THEN** 系统 SHALL 新建独立任务
- **AND** 旧任务的 payload、状态与签名 MUST 保持不变

#### Scenario: 多个同源候选的选择稳定

- **WHEN** 同签名同来源存在多个候选，其中一个为 succeeded、其余为 canceled 或 interrupted
- **THEN** 系统 SHALL 选择 succeeded 的那一条
- **AND** 同一输入在重复调用、进程重启后 SHALL 得到相同选择

#### Scenario: 枚举不设隐藏上限

- **WHEN** 同签名候选数量增长
- **THEN** 系统 SHALL 完成全量枚举后才给出结论
- **AND** MUST NOT 以分页或截断的方式只检查前若干条

## MODIFIED Requirements

### Requirement: Idempotent job submission
系统 SHALL 基于稳定输入和配置签名支持真实分析任务的幂等提交。 对于声明或消费正式 Team A/B 语义的任务，签名 MUST 包含 `AnalysisRosterSnapshot` hash、analysis-rally-context-set hash 与适用 formal plan input hash。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

幂等复用 SHALL 同时要求计算签名等价与 `source_identity_equivalent()` 判定的业务来源等价。现代任务使用经服务端核验的 `sourceSnapshot`；历史任务只可使用声明一致且重新核验通过的临时来源。任一身份字段无法证明、声明冲突或来源未知时 MUST 判为不等价。

#### Scenario: Duplicate submission is detected
- **WHEN** 客户端以相同视频、标定、分析选项、模型/运行配置和 roster/context 签名提交，且未要求新版本
- **THEN** 系统 SHALL 返回或引用已有 queued、running 或 succeeded 任务，避免重复执行
- **AND** 该已有任务的来源 SHALL 与本次请求来源等价；来源无法证明等价时 MUST NOT 复用

#### Scenario: New version is requested
- **WHEN** 客户端对相同输入签名显式请求新的分析版本
- **THEN** 系统 SHALL 创建新任务版本，并记录与之前签名兼容任务的关系

#### Scenario: Configuration changes
- **WHEN** 同一视频使用实质不同的分析选项或模型/运行配置提交
- **THEN** 系统 SHALL 将其视为不同分析签名，并可创建独立任务

#### Scenario: 名册或回合上下文不同
- **WHEN** 相同媒体使用不同 roster snapshot 或 analysis-rally-context-set hash 提交
- **THEN** 系统 SHALL 视其为不同输入
- **AND** MUST NOT 返回采用旧身份、队伍或端位结果的 Job/artifact

#### Scenario: 模块任务按合同去重
- **WHEN** 相同 analysisEngine=modular_v1 与 plan_hash 被重复提交且未请求新版本
- **THEN** 系统 SHALL 复用或引用匹配的 queued/running/succeeded Job
- **AND** plan_hash SHALL 包含目标、已消费上下文、窗口、采样与失败策略，排除缓存提示和随机 ID
- **AND** 该 Job 的来源 MUST 与本次请求等价

#### Scenario: Modular 同计划同来源正常复用

- **WHEN** `modular_v1` 以相同 `plan_hash`、相同来源重复提交且未请求新版本
- **THEN** 系统 SHALL 复用同源且状态可复用的 Job
- **AND** 不得因来源快照不进入 `plan_hash` 而跳过来源比较

#### Scenario: Modular 同计划异来源创建独立 Job

- **WHEN** 两个 `modular_v1` 请求具有相同 `plan_hash` 但来源身份不同
- **THEN** 第二个请求 MUST NOT 返回第一个 Job
- **AND** SHALL 创建具有独立来源快照的 Job

#### Scenario: Modular 新版本只关联同源前序 Job

- **WHEN** `modular_v1` 请求新版本且当前只有同 `plan_hash` 的异源前序 Job
- **THEN** 新 Job MUST NOT 设置该异源 Job 的 `previousJobId`
- **AND** SHALL 在存在同源前序 Job 时只关联同源 Job，否则省略 `previousJobId`

#### Scenario: 计算缓存身份与 Job 来源隔离

- **WHEN** 不同录制来源的 Job 消费符合现有缓存合同的相同计算输入
- **THEN** 系统 MAY 共享符合条件的不可变计算产物
- **AND** MUST 保持各自 Job、来源快照和版本链独立
- **AND** 来源快照 MUST NOT 加入 `plan_hash` 或节点缓存键

#### Scenario: 模块未消费名册
- **WHEN** 纯图像检测未消费 roster/context 且这些字段变化
- **THEN** 系统 SHALL 不因此改变该模块计划身份
- **AND** SHALL 不使用 legacy 的全量任务签名代替模块缓存键

#### Scenario: 签名相同但来源不同
- **WHEN** 同签名候选声明的来源与本次请求来源不同
- **THEN** 系统 MUST NOT 复用该候选
- **AND** SHALL 新建独立任务，并保持旧任务原样

#### Scenario: 无来源请求与无来源候选
- **WHEN** 普通上传请求（无录制来源）遇到同样无来源的同签名候选
- **THEN** 系统 SHALL 按既有幂等语义复用该候选
- **AND** MUST NOT 因缺少来源而拒绝普通上传
