## ADDED Requirements

### Requirement: Shot Landing artifact 路径与 manifest 引用

系统 SHALL 为 job 级 `shot_landings.json` 提供确定性存储路径，并在 `AnalysisPipelineResult.artifacts` 中使用可选的 `shot_landings_json_path`、`shot_landings_url`、`shot_landings_status` 和 `shot_landings_detail` 表达发布状态。

#### Scenario: CaptureTake 任务发布 Shot Landing
- **WHEN** 关联 CaptureTake 的完成 job 成功生成 `shot_landings.json`
- **THEN** 文件 SHALL 位于该 take 的 `analysis/<job_id>/` 目录中
- **AND** result manifest SHALL 提供逻辑 `shot_landings_url`、`available` status 和 detail
- **AND** 公开 result SHALL NOT 泄漏 CaptureTake 的本地绝对路径

#### Scenario: 上传或兼容任务存储
- **WHEN** 无 CaptureTake 的任务生成 `shot_landings.json`
- **THEN** 系统 SHALL 使用现有 `outputs/<job_id>/` 兼容根目录

#### Scenario: 可选组合失败
- **WHEN** Shot Landing Composer 失败或输入证据不足
- **THEN** `shot_landings_status` SHALL 为 `failed`、`unavailable` 或 `skipped`
- **AND** `shot_landings_detail` SHALL 说明原因
- **AND** path/url MAY 为 null
- **AND** 主分析任务 MUST NOT 因该可选 artifact 降级为失败

### Requirement: Shot Landing artifact API 可安全读取

系统 SHALL 在 `GET /api/analysis/jobs/{job_id}/artifacts/shot-landings` 发布已生成的 `shot-landings.v1` JSON，并使用现有 job 归属与存储索引安全边界。

#### Scenario: 读取已生成落点产物
- **WHEN** 客户端请求已存在的 `shot-landings`
- **THEN** API SHALL 返回 200 和 JSON
- **AND** payload SHALL 声明 `schema_version = "shot-landings.v1"`

#### Scenario: 已知落点产物未生成
- **WHEN** job 存在但 `shot_landings.json` 不存在
- **THEN** API SHALL 返回 404
- **AND** MUST NOT 返回 422 或其他 job 的文件

#### Scenario: 请求不得越界读取
- **WHEN** 请求中的 job 或 artifact 路径无法通过存储索引解析
- **THEN** API SHALL 拒绝请求
- **AND** SHALL NOT 根据客户端输入的文件系统路径读取任意文件

### Requirement: Shot Landing artifact envelope 稳定

`shot_landings.json` SHALL 包含 `schema_version`、`job_id`、`video_id`、`status`、`detail`、`generated_at`、`coordinate_system`、`normalization_profile`、`zone_profiles`、`landings`、`summary`、`diagnostics` 和 `source_artifacts`；`landings` SHALL 在无结果时仍保持数组类型。

#### Scenario: 可用落点产物
- **WHEN** Composer 成功处理至少一个 canonical Shot
- **THEN** artifact SHALL 使用 `schema_version=shot-landings.v1`
- **AND** SHALL 声明球场英尺坐标、20 ft × 44 ft 与 `net_y_ft=22`
- **AND** SHALL 声明所用 normalization/profile 版本

#### Scenario: 没有可分析 Shot
- **WHEN** canonical artifact 可读但不包含 Shot
- **THEN** `landings` SHALL 为空数组
- **AND** status/detail SHALL 诚实说明没有可分析 Shot
- **AND** SHALL NOT 生成 demo 或 mock Landing
