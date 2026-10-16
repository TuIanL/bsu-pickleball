## MODIFIED Requirements

### Requirement: Deterministic artifact paths

系统 SHALL 为新增分析产物提供确定性的本地存储路径。对于关联 CaptureTake 的录制任务，路径 MUST 位于对应会话目录的 `analysis/<job_id>/` 下；对于无 CaptureTake 的旧任务或上传任务，继续使用兼容的 `outputs/<job_id>/` 目录。

所有产物路径构造 SHALL 经过统一的越界校验：构造结果 MUST 落在该任务被授权的产物根目录之内。任何包含父目录跳转片段、绝对路径或符号链接逃逸的路径输入 MUST 被拒绝，MUST NOT 被静默拼接进产物路径。校验失败时系统 SHALL 返回可解释的拒绝原因，MUST NOT 读写该任务产物根目录之外的文件。

当关联 CaptureTake 的任务无法确定其会话目录时，系统 SHALL 写入独立的降级根目录 `outputs/_degraded/<job_id>/`，MUST NOT 与正常本地 job 共用 `outputs/<job_id>/`。降级 MUST 在任务与产物元数据上显式可观测。

#### Scenario: Resolve capture analysis artifact paths
- **WHEN** 后端为关联 capture_take_id 的任务 `job-123` 解析分析产物路径
- **THEN** `ball-overlay`、`detections`、`ball-trajectory`、`bounce-events` 和可视化产物 MUST 位于该 take 目录的 `analysis/job-123/` 对应子路径
- **AND** 路径解析 SHALL 使用 SQLite 索引中的会话目录，不得重新猜测默认目录

#### Scenario: Preserve legacy artifact paths
- **WHEN** 后端为没有 capture_take_id 的旧任务解析 artifact 路径
- **THEN** 系统 SHALL 继续使用 `outputs/job-123/`
- **AND** 现有 API artifact 名称和读取行为 SHALL 保持兼容

#### Scenario: 路径输入包含父目录跳转

- **WHEN** 参与产物路径构造的任一标识包含父目录跳转片段或绝对路径
- **THEN** 系统 SHALL 拒绝该路径
- **AND** MUST NOT 读写该任务产物根目录之外的任何文件
- **AND** 拒绝原因 SHALL 可解释且不泄漏宿主文件系统结构

#### Scenario: 全部产物构造器统一校验

- **WHEN** 后端为任务构造任一产物路径（视频元数据、检测记录、球轨迹、弹跳事件、可视化 manifest、洞察产物等）
- **THEN** 该构造 SHALL 经过同一个越界校验入口
- **AND** 校验 MUST 覆盖产物根目录本身与其全部子路径
- **AND** MUST NOT 存在绕过校验的产物路径构造路径

#### Scenario: 会话目录不可解析时写入降级根

- **WHEN** 关联 CaptureTake 的任务无法确定其会话目录（外接存储离线、索引缺失或解析失败）
- **THEN** 该任务的全部产物 SHALL 写入 `outputs/_degraded/<job_id>/`
- **AND** MUST NOT 写入 `outputs/<job_id>/`
- **AND** MUST NOT 与任何正常本地 job 的产物共用同一根目录

#### Scenario: 降级在任务元数据上显式标记

- **WHEN** 任务的产物被写入降级根目录
- **THEN** 任务摘要与结果元数据 SHALL 标记该任务的产物处于降级状态及其原因
- **AND** 该标记 MUST NOT 与正常本地任务的产物状态混淆

## ADDED Requirements

### Requirement: 外接存储不可用时的降级必须可观测

系统 SHALL 区分「该 CaptureTake 合法地没有会话目录」与「解析会话目录时发生失败」。前者 SHALL 返回「无会话目录」这一合法结论；后者 SHALL 记录告警并把任务标记为降级，MUST NOT 与前者混为同一返回值。

解析失败时，系统 MUST NOT 把数据库连接失败、模型 package 错误等与「无会话目录」无关的异常一并静默吞掉。调用方 SHALL 能区分这两类结论。

#### Scenario: take 合法地没有会话目录

- **WHEN** CaptureTake 记录存在但其会话目录字段为空，且未发生任何解析错误
- **THEN** 系统 SHALL 返回「无会话目录」结论
- **AND** SHALL NOT 记录降级告警
- **AND** 调用方 SHALL 能把该结论与解析失败区分

#### Scenario: 会话目录解析失败

- **WHEN** 查询 CaptureTake 会话目录时发生数据库连接失败、模型 package 错误或其他异常
- **THEN** 系统 SHALL 记录一条包含失败原因的告警
- **AND** SHALL 把该任务标记为产物降级
- **AND** MUST NOT 把该异常静默转换为「无会话目录」

#### Scenario: 外接存储离线时任务不静默成功

- **WHEN** 一个 CaptureTake 任务执行期间外接存储不可用，产物被迫写入降级根
- **THEN** 任务结果 SHALL 显式表达产物处于降级状态
- **AND** 运维视角 SHALL 能够把该任务与正常产物任务区分开
- **AND** MUST NOT 存在「任务 succeeded 且零降级痕迹」的结果

#### Scenario: 降级不影响任务本身的可读性

- **WHEN** 任务的产物写入降级根并标记降级
- **THEN** 该任务的产物 SHALL 仍能通过既有产物访问机制读取
- **AND** 降级标记 MUST NOT 使产物读取接口返回错误

### Requirement: 产物根索引的并发访问必须线性一致

系统 SHALL 保证「任务 → 产物根目录」索引在多线程与多进程访问下的线性一致性。索引项的创建与其对应的目录准备 MUST 在同一临界区内完成，使并发读取者要么看不到该索引项、要么看到一个已完全可用的产物根目录。

索引的读写 SHALL 受同一把锁保护，与控制面任务存储已具备的锁语义保持一致。系统 MUST NOT 出现同一任务的产物被写入两个不同根目录的情况。

#### Scenario: 目录已建但索引未注册时的并发读取

- **WHEN** 一个线程正在为某任务创建产物根目录，尚未完成索引注册
- **AND** 另一线程同时为同一任务解析产物根目录
- **THEN** 后一线程 SHALL 观察到该索引项已完全可用，或走完整的解析路径得到同一个根目录
- **AND** MUST NOT 观察到「目录存在但索引缺失」而回退到另一个根目录

#### Scenario: 同一任务的产物不写入两个根

- **WHEN** 两个线程并发为同一任务解析产物根目录
- **THEN** 两者 SHALL 得到同一个根目录
- **AND** 该任务的全部产物 SHALL 位于该单一根目录之下
- **AND** MUST NOT 出现产物分散写入两个根目录的情况

#### Scenario: 索引读写与其它控制面状态同等保护

- **WHEN** 产物根索引被并发读写
- **THEN** 索引操作 SHALL 受与控制面任务存储同等的锁保护
- **AND** MUST NOT 出现字典级并发修改导致的不确定结果

### Requirement: SQLite 并发配置在主库与控制面库之间一致

系统 SHALL 对主业务库与分析控制面库施加一致的 SQLite 并发配置（journal mode、`busy_timeout`、`synchronous`），使同一进程内的多个引擎在并发写入时行为一致。系统 MUST NOT 出现一个库启用某配置而另一个库未启用的情形。

WAL 模式依赖内存映射，其在某些可移动卷上存在数据损坏风险。因此当数据库文件位于外接/可移动存储路径时，系统 MUST NOT 对该库启用 WAL。系统 SHALL 按数据库文件的实际路径分支选择 journal mode。

#### Scenario: 主库与控制面库配置一致

- **WHEN** 系统初始化主业务库与分析控制面库
- **THEN** 两者 SHALL 施加相同的 journal mode、`busy_timeout` 与 `synchronous` 配置
- **AND** MUST NOT 出现一个库启用 WAL 而另一个库使用 rollback journal 的情形

#### Scenario: 并发写入不因缺少等待而失败

- **WHEN** 多个线程或进程并发写入同一个 SQLite 库
- **THEN** 冲突 SHALL 由配置的等待超时吸收
- **AND** MUST NOT 因缺少 `busy_timeout` 而立即返回数据库被锁定

#### Scenario: 外接卷上的数据库不启用 WAL

- **WHEN** 数据库文件位于外接或可移动存储路径
- **THEN** 系统 MUST NOT 为该库启用 WAL
- **AND** SHALL 施加与其它库一致的等待超时与同步级别

#### Scenario: 配置在引擎创建时一次性施加

- **WHEN** 数据库引擎被创建或重建
- **THEN** 所需 PRAGMA SHALL 在连接建立时被施加
- **AND** MUST NOT 依赖调用方在连接后手工设置


### Requirement: 降级产物位置跨重启保持稳定

系统 SHALL 持久化降级产物位置与原因。存在降级产物的任务在服务重启或外接盘重新挂载后 MUST 继续从降级目录读取，MUST NOT 隐式切回另一空目录。

#### Scenario: 重启后外接盘已恢复
- **WHEN** 某任务已在降级目录写入产物，进程重启且原会话目录重新可用
- **THEN** 系统 SHALL 仍读取该任务原有的降级产物
- **AND** 降级状态与原因 SHALL 保留
