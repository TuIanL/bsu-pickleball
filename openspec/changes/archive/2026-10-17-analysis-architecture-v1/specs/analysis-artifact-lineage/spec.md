## ADDED Requirements

### Requirement: 产物引用与清单保持任务独立
系统 SHALL 分离轻量 ArtifactRef、不可变 ArtifactManifest 与 Job 的使用绑定。Manifest MUST 记录类型/schema、来源、机位、计算/输出范围、采样、生产者、模型/参数、输入、所消费上下文、坐标/单位、质量和内容摘要。created_by_job_id 只能作为来源记录，不得作为业务身份。

#### Scenario: 跨任务使用姿态
- **WHEN** Job B 复用 Job A 生产的姿态
- **THEN** 系统 SHALL 保留原 artifact_id 和不可变内容
- **AND** B 的运行信息 SHALL 通过绑定表达，而不覆盖原 payload 的归属字段

### Requirement: 缓存键限定为实际计算输入
cache_key SHALL 由实现/输出版本、来源身份、机位、采样与初始化、计算范围、输出选择、实际输入、有效模型/参数及所消费上下文产生。job_id、路径、报告样式和未消费上下文 MUST NOT 参与。content_sha256 MUST 与计算键分开，分别表达物理完整性与计算身份。

#### Scenario: 修改比分
- **WHEN** 只修改名册或比分，纯图像 ball.detect 不消费这些字段
- **THEN** 球检测缓存 SHALL 保持命中
- **AND** 消费相关快照的语义消费者 SHALL 使用新的身份

#### Scenario: 修改模型或采样
- **WHEN** 权重内容、有效参数、采样相位或已消费的同步/标定变化
- **THEN** 受影响产物 SHALL 使用不同缓存键
- **AND** 无依赖的分支 SHALL 保持原缓存身份

#### Scenario: 相同计算范围但输出不同
- **WHEN** 两个请求具有相同上下文范围但正式输出范围或选择规则不同
- **THEN** resolver SHALL 区分输出身份或提供显式可审计的选取绑定
- **AND** SHALL NOT 将不同的裁剪 payload 当作完全相同产物

### Requirement: 缓存指针与不可变产物版本分离
系统 SHALL 允许同一计算键在损坏恢复或重新生产后关联新 artifact_id。当前可用结果的唯一性 SHALL 由独立缓存条目/指针管理，而不是禁止同键历史产物存在；旧版本、失效原因和历史引用 MUST 保留。

#### Scenario: 同键损坏后重建
- **WHEN** A 的物理内容校验失败，使用相同计算合同重新生产 B
- **THEN** A SHALL 标记完整性不可用，B SHALL 获得新 artifact_id，缓存指针 SHALL 可转向 B
- **AND** 已固定 A 的历史引用 SHALL 不被静默改成 B

#### Scenario: 两个生产者同时发布
- **WHEN** 两个有效尝试计算相同缓存键
- **THEN** 系统 SHALL 原子选择一个可用缓存指针
- **AND** SHALL NOT 覆盖任何已经发布的产物内容或让消费者看到半成品

### Requirement: 引用生命周期覆盖血缘和媒体来源
删除 Job SHALL 解除其引用，不得删除其他 Job、固定输入或仍存活下游产物依赖的上游证据及来源媒体。物理回收 MUST 先确认没有直接、血缘或活动发布引用，并满足明确保留策略。v1 默认 SHALL 保守保留共享产物，自动 GC 不作为必交付功能。

#### Scenario: 直接消费者删除
- **WHEN** A 被 Job-1 与 Job-2 使用，Job-1 被删除
- **THEN** A SHALL 仍能被 Job-2 读取

#### Scenario: 仅有间接引用
- **WHEN** 存活的语义产物引用姿态产物，而姿态不再被 Job 直接引用
- **THEN** 系统 SHALL 保留姿态及关联证据
- **AND** SHALL NOT 仅因直接引用数为零而回收

### Requirement: 完整性和存储可用性分别核验
缓存命中 SHALL 验证已发布状态、schema/输入兼容、内容完整性及位置可读性。存储离线 MUST 与计算质量不足或内容损坏区分；恢复存储不应自动改变计算身份。相关产物不得静默改道本地盘冒充原共享结果。

#### Scenario: 外接盘离线
- **WHEN** 索引存在但产物位于未挂载卷
- **THEN** resolver SHALL 返回 location_unavailable 及逻辑位置
- **AND** SHALL NOT 将其报告为 cache_hit 或直接认定算法失败

#### Scenario: 无候选结果复用
- **WHEN** 检测正常完成、结构完整且没有候选
- **THEN** no_candidates 产物 SHALL 能命中缓存
- **AND** SHALL NOT 因没有检测点而反复重算

### Requirement: 持久化清单通过受控逻辑引用访问
系统 SHALL 提供按 artifact_id 和 Job 查询的只读清单/内容入口，限定在受控产物存储及引用范围内。公共响应 MUST NOT 暴露绝对路径或允许调用方指定任意文件。

#### Scenario: 读取共享产物
- **WHEN** CLI 或 API 读取 Job 使用的 ArtifactRef
- **THEN** 系统 SHALL 返回类型、版本、来源、窗口、质量与可用性
- **AND** SHALL 通过逻辑定位解析其内容
