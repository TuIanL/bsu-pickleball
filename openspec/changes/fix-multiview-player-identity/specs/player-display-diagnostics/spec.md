# player-display-diagnostics Delta

## MODIFIED Requirements

### Requirement: 诊断失败隔离

显示诊断构建失败 MUST NOT 导致核心 joint 分析失败。当漏斗构建器抛错或产物写盘失败时，核心 joint result SHALL 保持成功，`player_display_diagnostics_status` SHALL 为 `failed` 并附结构化 reason。产物缺失或构建失败时，composer SHALL 仍写盘一个占位 artifact（`status=failed` 或 `status=unavailable`），使查询 API 能返回结构化响应，MUST NOT 留下"文件不存在"状态导致 API 404。

#### Scenario: 诊断构建失败不影响核心结果

- **WHEN** joint run 完成但显示漏斗构建器抛出异常
- **THEN** 核心 joint result SHALL 仍为成功
- **AND** 系统 SHALL 记录 `player_display_diagnostics_status=failed` 与 reason
- **AND** composer SHALL 写盘占位 artifact（`status=failed`），查询 API 可读

#### Scenario: joint output 缺少 payload 时写占位产物

- **WHEN** joint run 完成但 `joint_output.display_diagnostics_payload` 缺失或非 dict（如构建失败、行数为空且校验拒绝）
- **THEN** composer SHALL 写盘一个占位 artifact（`status=unavailable`，`detail` 说明原因）
- **AND** 查询 API SHALL 返回该占位响应，MUST NOT 返回 404 "no artifact"

#### Scenario: 无确认球员/可用视角时仍产出空产物

- **WHEN** joint run 全程没有 roster confirmed player 或任何 available view
- **THEN** 系统 SHALL 产出 `status=unavailable` 的空 rows 产物（`rows=[]`）
- **AND** 查询 API SHALL 返回结构化 `unavailable` 而非 404

## ADDED Requirements

### Requirement: 查询 API 产物缺失时返回结构化 unavailable

`GET /analysis/jobs/{job_id}/multiview/players/{player_id}/display-diagnostics` 在产物文件缺失、产物 `status=unavailable/failed`、或窗口内无该球员行时，SHALL 返回结构化 `unavailable` 响应（携带 `reason` 与 `job_id`），前端据此显示"诊断暂不可用"状态。API SHALL NOT 以 404 HTTP 状态码表达"产物未生成"这一业务状态。

#### Scenario: 产物文件缺失

- **WHEN** `player_display_diagnostics_json_path(job_id)` 不存在（历史任务或构建完全失败）
- **THEN** API SHALL 返回结构化 `unavailable` 响应与 reason
- **AND** 响应 SHALL 携带 `job_id` 且 HTTP 状态码为非 404（如 200 或 422 语义错误之外的状态）

#### Scenario: 窗口内无该球员行

- **WHEN** 产物存在但窗口内没有 `player_id` 匹配的行
- **THEN** API SHALL 返回空 `rows` 列表的结构化响应
- **AND** SHALL NOT 返回错误或伪造数据
