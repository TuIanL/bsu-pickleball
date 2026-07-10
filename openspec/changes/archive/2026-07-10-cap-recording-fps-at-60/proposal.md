## Why

当前录制入口仍暴露 90fps/120fps 选项，并且部分后端默认值或校验上限仍允许高帧率请求。实际采集电脑无法稳定承载 90fps 录制，因此需要把单摄与双摄录制的默认值、可选项和后端合同统一收敛到 60fps，避免用户误选或绕过 UI 触发高负载录制。

## What Changes

- 将单摄录制与双摄同步录制的默认 FPS 调整为 60fps。
- 将采集控制台、旧录制入口中的录制 FPS 选项限制为最高 60fps，移除 90fps 和 120fps 录制选项。
- 将后端单摄/双摄开始录制请求的 FPS 校验上限收紧为 60fps，拒绝超过 60fps 的录制请求。
- 清理 FFmpeg 录制器中遗留的 90fps 默认参数，避免未来调用遗漏 FPS 时回退到 90fps。
- 更新相关类型测试，确保录制请求合同与 60fps 上限一致。
- **BREAKING**: 通过 API 提交 `fps > 60` 的单摄或双摄录制请求将不再被接受。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `recording-session-control`: 单摄录制的默认 FPS 与允许 FPS 范围改为以 60fps 为最高支持值。
- `dual-camera-sync-recording`: 双摄同步录制的默认 FPS 与允许 FPS 范围改为以 60fps 为最高支持值。

## Impact

- 前端：`src/pages/CaptureConsolePage.tsx`、`src/App.tsx` 的录制 FPS 状态默认值与下拉选项。
- 后端：`backend/app/camera/models.py` 的 Pydantic 请求校验、`backend/app/camera/recorder.py` 的默认参数。
- 测试：`src/services/sourceFps.test.ts` 及可能覆盖录制请求类型/选项的测试。
- API 合同：`POST /api/recordings/start` 与 `POST /api/sync-recordings/start` 不再接受超过 60fps 的录制请求。
