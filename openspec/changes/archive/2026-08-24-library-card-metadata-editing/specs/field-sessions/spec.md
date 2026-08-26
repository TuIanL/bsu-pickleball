## MODIFIED Requirements

### Requirement: Field Session 数据模型

系统 MUST 为 Field Session 保存采集任务上下文字段。

#### Scenario: 保存完整上下文

- **WHEN** 系统保存 Field Session
- **THEN** Field Session SHALL 包含 `id`、`title`、`venue`、`court_name`、`capture_mode`、`match_format`、`camera_setup`、`display_mode`、`status`、`notes`、`started_at`、`ended_at`、`created_at` 和 `updated_at`
- **AND** `display_mode` SHALL 使用 `standard` 或 `showcase`
- **AND** 缺失历史值时 SHALL 按 `standard` 兼容读取

#### Scenario: started_at 可更新

- **WHEN** 系统通过 `PATCH /api/field-sessions/{id}` 提交 `started_at`
- **THEN** 系统 SHALL 持久化该场次开始时间（比赛日期）
- **AND** 该值 SHALL 作为卡片日期编辑的场次真源，供 Library 卡片展示与搜索使用

## ADDED Requirements

### Requirement: 通过 PATCH 更新场次日期

系统 MUST 允许通过 `PATCH /api/field-sessions/{id}` 更新 `started_at`，以支持比赛库卡片的日期编辑写入场次真源。

#### Scenario: 更新比赛日期
- **WHEN** 用户在某 `recording` / `sync_recording` 素材卡片上编辑日期，且该素材归属某个 FieldSession
- **THEN** 系统 SHALL 以新的 `started_at` 写入该 FieldSession
- **AND** 同 FieldSession 下所有素材的展示日期 SHALL 同步更新
- **AND** 进行中（`live` / `recording`）的场次 SHALL 仍可更新 `started_at`（仅改日期，不影响采集状态）

#### Scenario: 仅更新未提供的字段保持原值
- **WHEN** `PATCH` 请求仅含 `started_at`
- **THEN** 系统 SHALL 仅修改 `started_at`，其余字段（title/venue 等）保持原值
