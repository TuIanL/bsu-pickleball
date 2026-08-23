## ADDED Requirements

### Requirement: Parent 结果正式引用双摄球产物
joint 任务的 Parent `AnalysisResult.artifacts` SHALL 正式引用 `reconstructed_ball_trajectory.v3` 与 `multiview_ball_stereo_evidence.v1`。每个产物 SHALL 同时提供内部 path、公开 URL、status 和 detail；前端 MUST 只从 Parent 引用读取公开入口，不得依赖子任务私有路径。

#### Scenario: 双摄球产物可用
- **WHEN** joint 任务完成球分析并生成两个 JSON 产物
- **THEN** Parent artifacts SHALL 包含两个产物的 `*_json_path`、`*_url`、`*_status` 与 `*_detail`
- **AND** URL SHALL 能通过现有 artifact API 获取

#### Scenario: 双摄球产物不可用
- **WHEN** 球分析失败、超时或质量不足
- **THEN** Parent artifacts SHALL 仍提供对应 status/detail
- **AND** 缺失 path/url 不得被解释为分析尚未执行

### Requirement: 双摄球产物状态与 schema 版本一致
双摄球 evidence SHALL 使用 `multiview_ball_stereo_evidence.v1`，用户轨迹 SHALL 使用 `reconstructed_ball_trajectory.v3`。artifact 状态 SHALL 与产物 `overall_status`、`schema_version` 和质量信息保持一致，MUST NOT 发布一个版本字段与内容不匹配的产物。

#### Scenario: v3 轨迹发布
- **WHEN** Parent 引用 reconstructed ball trajectory
- **THEN** JSON SHALL 声明 v3 schema
- **AND** SHALL 包含整体状态、validity 分级、落点信息与可用的三维质量指标

#### Scenario: evidence 发布
- **WHEN** Parent 引用 stereo evidence
- **THEN** JSON SHALL 声明 v1 schema
- **AND** 每条证据 SHALL 可追溯到 canonical tick、双摄帧和候选输入

### Requirement: 球相关 artifact API 保持安全边界
artifact API SHALL 允许读取上述两个公开 artifact 名称，并继续拒绝任意文件路径。API 的公开返回 SHALL 只暴露任务作用域内的文件内容或受控下载响应。

#### Scenario: 读取 Parent 球路产物
- **WHEN** 客户端使用合法 task id 与 `reconstructed-ball-trajectory` 或 `multiview-ball-stereo-evidence` 请求 artifact
- **THEN** API SHALL 返回对应 JSON
- **AND** 返回内容 SHALL 来自该 task 的已发布路径

#### Scenario: 越权读取
- **WHEN** 请求携带其他 task 的路径、绝对路径或路径穿越片段
- **THEN** API SHALL 拒绝请求
- **AND** SHALL 不泄露宿主文件系统信息
