# sync-anchor-workflow Specification

## Purpose
TBD - created by archiving change integrate-sync-anchor-preflight. Update Purpose after archive.
## Requirements
### Requirement: CaptureTake 级同步锚点状态

系统 SHALL 为每个双摄 CaptureTake 提供录制级同步锚点状态，状态 SHALL 至少能表达 `not_required`、`required`、`draft`、`confirmed`、`auto_degraded` 和 `invalidated`。状态响应 SHALL 同时包含是否允许继续双摄分析、判定原因、当前 calibration 来源及可用的质量摘要；系统 SHALL NOT 仅以 `sync_calibration.json` 是否存在表示人工确认完成。

#### Scenario: 人工锚点已确认
- **WHEN** 当前 CaptureTake 存在与两路素材 provenance 匹配且校验通过的 `manual_anchors` calibration
- **THEN** 状态 SHALL 为 `confirmed`
- **AND** 响应 SHALL 标识其为人工确认结果并允许后续分析复用

#### Scenario: 仅存在自动同步估算
- **WHEN** 当前 CaptureTake 仅存在 `auto_degraded_from_recording_timing` calibration
- **THEN** 状态 SHALL 为 `auto_degraded`
- **AND** 页面和 API SHALL NOT 将其描述为人工锚点已确认

#### Scenario: 策略判定需要人工标注
- **WHEN** 后端同步前置策略判定当前 CaptureTake 必须人工确认且不存在有效确认结果
- **THEN** 状态 SHALL 为 `required` 或 `draft`
- **AND** `analysis_allowed` SHALL 为 false
- **AND** 响应 SHALL 提供可展示的判定原因

#### Scenario: 策略判定无需人工标注
- **WHEN** 后端同步前置策略判定当前 CaptureTake 无需人工锚点
- **THEN** 状态 SHALL 为 `not_required`
- **AND** `analysis_allowed` SHALL 为 true
- **AND** 系统 SHALL 保留当前自动同步质量及降级说明

### Requirement: 内置锚点草稿生命周期

系统 SHALL 通过后端 API 按 CaptureTake 保存、读取和更新同步锚点草稿。草稿 SHALL 绑定 reference camera、camera identity、registered video identity、timing provenance 和 revision，并 SHALL 支持用户离开工作台后继续编辑。

#### Scenario: 保存未完成草稿
- **WHEN** 用户在工作台新增、删除或修改共同事件锚点并保存
- **THEN** 后端 SHALL 将草稿关联到当前 CaptureTake
- **AND** CaptureTake 同步锚点状态 SHALL 为 `draft`
- **AND** 草稿 SHALL 可在其他浏览器会话中重新加载

#### Scenario: 并发修改草稿
- **WHEN** 客户端使用过期 revision 更新草稿
- **THEN** API SHALL 拒绝覆盖较新的草稿
- **AND** SHALL 返回当前 revision 供客户端重新加载

#### Scenario: localStorage 旧草稿迁移
- **WHEN** 工作台首次加载且后端没有草稿但当前浏览器存在该 CaptureTake 的旧 localStorage 草稿
- **THEN** 页面 SHALL 允许将旧草稿导入后端
- **AND** 成功保存后 SHALL 以后端草稿为权威来源

### Requirement: 系统内提交、拟合与确认

系统 SHALL 在用户提交锚点时由后端验证 payload、调用既有多锚点拟合逻辑并原子持久化原始锚点、拟合 calibration 和确认元数据。确认成功 SHALL 以服务端校验结果为准，而不是客户端锚点数量判断。

#### Scenario: 提交有效锚点
- **WHEN** 用户提交满足最小数量、camera identity、时间跨度和 residual 阈值的锚点
- **THEN** 系统 SHALL 生成 `source=manual_anchors` 的 `dual_camera_sync_calibration.v1`
- **AND** SHALL 原子保存 anchors、calibration、质量摘要、确认时间及 provenance
- **AND** 状态 SHALL 变为 `confirmed`

#### Scenario: 提交无效锚点
- **WHEN** 锚点不足、camera identity 不匹配、时间跨度不足或拟合 residual 超过确认阈值
- **THEN** API SHALL 返回结构化校验问题
- **AND** SHALL 保留草稿供继续修改
- **AND** SHALL NOT 将状态设为 `confirmed`

#### Scenario: 完成后返回原流程
- **WHEN** 用户从双摄分析向导进入工作台并成功确认
- **THEN** 页面 SHALL 返回同一 CaptureTake 的分析向导
- **AND** 向导 SHALL 重新读取服务端状态并显示人工确认摘要

### Requirement: 跨分析复用与 provenance 失效

已确认同步锚点 SHALL 由同一 CaptureTake 后续创建的所有 AnalysisJob 复用。系统 SHALL 在读取状态和创建分析前比较确认时保存的素材 provenance；registered video、camera identity 或 timing provenance 变化 SHALL 使确认失效，而分析参数变化 SHALL NOT 使确认失效。

#### Scenario: 同一录制再次创建分析
- **WHEN** 用户基于同一 CaptureTake 创建新的双摄分析且素材 provenance 未变化
- **THEN** 系统 SHALL 复用既有 confirmed calibration
- **AND** SHALL NOT 要求重新标注锚点

#### Scenario: 双摄素材被重新生成
- **WHEN** 任一路 registered video identity、camera identity 或 timing sidecar provenance 与确认记录不一致
- **THEN** 状态 SHALL 变为 `invalidated`
- **AND** 分析前置检查 SHALL 提示需要重新确认
- **AND** 系统 SHALL 保留旧版本作为审计记录但 SHALL NOT 用作当前权威映射

#### Scenario: 仅修改分析配置
- **WHEN** 用户修改分析窗口、execution mode、算法配置或创建新的 AnalysisJob
- **THEN** 已确认锚点 SHALL 保持有效
- **AND** SHALL NOT 生成新的录制级锚点 revision

### Requirement: 锚点版本审计与诊断导出

系统 SHALL 保留同步锚点草稿和确认版本的 revision、来源、时间、质量摘要及失效原因。anchors JSON 下载 SHALL 作为诊断和互操作能力保留，但 SHALL NOT 是完成内置标注流程的必需步骤。

#### Scenario: 查看当前确认摘要
- **WHEN** 用户或分析 preflight 查询同步锚点状态
- **THEN** 响应 SHALL 提供当前 revision、anchor count、coverage、residual、quality、source 和 confirmed_at

#### Scenario: 导出已保存锚点
- **WHEN** 用户选择导出 anchors JSON
- **THEN** 系统 SHALL 从服务端当前版本生成兼容现有 CLI 输入格式的文件
- **AND** 导出操作 SHALL NOT 改变确认状态

### Requirement: 工作台 timing 缺失时的恢复路径

系统 SHALL 在同步锚点工作台因两路 registered video 缺少有效 source PTS（或加载失败）而无法打开时，提供"尝试修复"入口：调用 `POST /api/videos/{video_id}/timing/materialize` 为缺失侧补写 sidecar，补写成功后自动重新加载工作台。该入口 SHALL 与既有"返回双摄分析"出口并存，不得阻塞用户返回原流程。

#### Scenario: 工作台因 source_pts_missing 无法打开
- **WHEN** 工作台加载失败且失败原因包含 registered video 缺失 source PTS sidecar
- **THEN** 错误卡 SHALL 展示失败原因
- **AND** SHALL 提供"尝试修复"按钮与"返回双摄分析"按钮

#### Scenario: 尝试修复成功
- **WHEN** 用户点击"尝试修复"且 materialize 补写成功
- **THEN** 页面 SHALL 自动重新加载工作台
- **AND** 两路 timing 可用后 SHALL 正常进入锚点标注

#### Scenario: 尝试修复失败
- **WHEN** 用户点击"尝试修复"且 materialize 返回结构化错误（媒体不可用、PTS 无效等）
- **THEN** 错误卡 SHALL 展示具体失败原因
- **AND** 保留"返回双摄分析"出口
- **AND** 允许用户再次尝试修复

