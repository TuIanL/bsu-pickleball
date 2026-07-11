## MODIFIED Requirements

### Requirement: 恢复网络不确定性

**变更**：进入 `recovering` 后增加自动恢复机制，无需用户手动点击；恢复结果保留完整媒体和分析入口。

**修改前**：`recovering` 仅显示"重试恢复"按钮等待用户手动操作。`recover()` 恢复时构造的结果固定为空 `tracks`、`analysisAvailable: false`，丢失视频与分析入口。

**修改后**：除现有手动恢复外，系统 SHALL 在进入 `recovering` 后自动查询服务器。
- 系统 SHALL 在进入 recovering 后 500ms 启动第一次查询
- 系统 SHALL 使用 `recoveryRef` 控制查询状态（查询次数、飞行中标志、定时器引用）
- 查询成功且终态为 `completed/partial/failed` 时 SHALL 自动进入对应终态
- 查询结果为 `recording` 时 SHALL 保持 recovering，每 3 秒继续查询
- 查询发生网络错误时 SHALL 保持 recovering，更新 `operationError`，不进入 `failed`
- 超过 30 秒后 SHALL 停止自动高频轮询，仍保持 recovering，显示"再次停止"和"取消录制"

### Requirement: 恢复结果完整性

**变更**：恢复时联合 Source Session 和 CaptureTake 构造完整结果。

**修改前**：恢复时仅使用 `sourceSession.status` 映射为 `completed`，结果对象固定为 `tracks: []`、`analysisAvailable: false`。

**修改后**：系统 SHALL 联合 Source Session 和 CaptureTake 恢复完整停止结果。
- 系统 SHALL 查询 Source Session 获取媒体信息（`video_id`、`duration_sec`、`camera_id`）
- 系统 SHALL 查询 CaptureTake 获取业务终态（`completed/partial/failed`）
- 系统 SHALL 使用 CaptureTake 的 `status` 决定终态（而非 Source Session 的 `status`）
- `normalizeRecoveredSingleResult` SHALL 从单摄 Session 恢复 `videoId`、`durationMs`、`tracks`、`analysisAvailable`
- `normalizeRecoveredDualResult` SHALL 从双摄 Session 恢复 `registered_video_ids`、`default_analysis_video_id`、`camera_slots`

### Requirement: 统一 elapsedMs 从服务器时间派生

**变更**：停止后 elapsedMs 优先从恢复结果的 track duration 读取，而非从 `result.capture_take.duration_ms`。

**修改前**：`STOP_SUCCEEDED` 后从 `result.tracks[0]?.durationMs` 读取。

**修改后**：`STOP_SUCCEEDED` 和 `RECOVERED` 后均 SHALL 从结果的 track duration 读取 elapsedMs。
- 系统 SHALL 在 `RECOVERED` 时更新 elapsedMs 为 `result.tracks[0]?.durationMs ?? 0`
