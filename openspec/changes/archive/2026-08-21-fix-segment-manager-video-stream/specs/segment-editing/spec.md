# segment-editing Delta — fix-segment-manager-video-stream

## ADDED Requirements

### Requirement: 片段列表接口暴露编辑契约字段

系统 MUST 在 `GET /api/capture-takes/{id}/segments` 返回编辑器所需的完整契约字段，包括 `edit_status`、`edit_version`、`corrected_start_ms`、`corrected_end_ms`、`effective_start_ms`、`effective_end_ms`，与前端 `CaptureSegmentSummary` 类型保持一致。

#### Scenario: 列表返回编辑状态

- **WHEN** 客户端请求 `GET /api/capture-takes/{id}/segments`
- **THEN** 每个片段 SHALL 包含 `edit_status`（active/superseded/archived）
- **AND** SHALL 包含 `edit_version`

#### Scenario: 列表返回修正与有效边界

- **WHEN** 客户端请求 `GET /api/capture-takes/{id}/segments`
- **THEN** 每个片段 SHALL 包含 `corrected_start_ms` 与 `corrected_end_ms`
- **AND** SHALL 包含 `effective_start_ms` 与 `effective_end_ms`
- **AND** `effective_*` SHALL 遵循 corrected 优先、否则取原始值的规则
