## MODIFIED Requirements

### Requirement: Deterministic artifact paths

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

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

#### Scenario: 模块共享产物位置
- **WHEN** modular_v1 发布或跨 Job 读取 Artifact
- **THEN** 系统 SHALL 通过 artifact_id 在获授权的共享产物根内定位，Job 私有清单/trace 仍使用 Job 根
- **AND** 所有构造器 SHALL 经过统一越界校验，调用方不能提供绝对路径或逃逸根目录
- **AND** legacy 根解析规则 SHALL 不被用于递归删除共享产物

#### Scenario: 模块存储位置不可用
- **WHEN** 已登记模块产物位置离线
- **THEN** 系统 SHALL 返回 location_unavailable 及逻辑原因
- **AND** SHALL 不套用 legacy degraded 路径静默改写共享结果

### Requirement: Pipeline result references new artifacts

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

系统 SHALL 在 `AnalysisPipelineResult.artifacts` 中描述会话目录内新增分析产物的 path、url、status 和 detail 字段，且所有新增字段 MUST 可选以保持旧结果兼容。可选 artifact 即使没有文件，也 SHALL 保留可解释的状态。

#### Scenario: Capture analysis result references session artifacts

- **WHEN** 录制会话的分析任务生成 artifact 文件
- **THEN** `AnalysisPipelineResult.artifacts` MUST 包含该 artifact 的逻辑引用和实际文件状态
- **AND** artifact API SHALL 通过 job_id 和 SQLite 索引解析到对应 capture 会话目录

#### Scenario: Missing capture artifact remains compatible

- **WHEN** 录制会话没有生成某个可选 artifact
- **THEN** 对应 artifact 字段 MUST 允许为 `null`
- **AND** API MUST 返回 404 而不是暴露绝对路径或返回 422
- **AND** 结果 SHALL 继续返回该 artifact 的 `status` 和 `detail`（若调用方支持）

#### Scenario: Optional artifact status is explicit

- **WHEN** pipeline 处理一个可选 artifact
- **THEN** `status` SHALL 为 `available`、`skipped`、`unavailable` 或 `failed` 之一
- **AND** `detail` SHALL 说明跳过原因、能力不可用原因或执行错误
- **AND** `available` SHALL 仅用于文件已成功写入并可通过 artifact API 读取的情况

#### Scenario: Artifact state survives missing file

- **WHEN** artifact status 为 `skipped`、`unavailable` 或 `failed` 且没有对应文件
- **THEN** `path` 和 `url` MAY 为 `null`
- **AND** `status` 与 `detail` MUST NOT 被清空或根据 `path` 重新推导为 `null`

#### Scenario: 模块结果使用通用引用
- **WHEN** modular_v1 发布新增类型产物
- **THEN** 系统 SHALL 在 ModularRunManifest 中记录 ArtifactRef 与可用性/质量
- **AND** SHALL 不要求在 AnalysisPipelineResult.artifacts 为每种模块增加固定字段

## ADDED Requirements

### Requirement: 模块产物读取保留旧 artifact API
模块 SHALL 通过受控 artifact_id 入口读取通用类型，旧 job_id/artifact_name 入口 SHALL 保持 legacy 内容与缺失行为。新入口 MUST 避免既有动态 Literal 路由冲突；共享产物访问 SHALL 校验可见范围和逻辑引用。

#### Scenario: 读取新旧产物
- **WHEN** 客户端分别读取旧 pose-overlay 和新模块姿态 ArtifactRef
- **THEN** 两者 SHALL 按各自 schema 正常返回
- **AND** SHALL 不要求旧结果迁移到新 Manifest 或暴露物理路径
