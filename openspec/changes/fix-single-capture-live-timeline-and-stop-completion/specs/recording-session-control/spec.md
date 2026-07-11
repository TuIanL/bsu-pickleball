## MODIFIED Requirements

### Requirement: 停止录制

**变更**：修复停止路由在媒体已成功停止后因响应组装错误返回 HTTP 500 的问题。

**修改前**：`POST /api/recordings/{session_id}/stop` 路由在调用 `session_service.stop_session()` 成功后，组装 `CaptureStopResult` 时调用未导入的 `get_session_factory()`，抛出 `NameError`，返回 HTTP 500。

**修改后**：系统 SHALL 在停止路由中正确导入 `get_session_factory`。
- 停止端点 SHALL 在 `session_service.stop_session()` 成功后返回 HTTP 200
- 停止端点 SHALL 返回完整的 `CaptureStopResult`，包含 `capture_take`、`tracks`（长度为 1）、`default_analysis_video_id`、`analysis_available`
- 停止端点 SHALL NOT 因响应组装阶段的 import 错误而抛出未处理异常
