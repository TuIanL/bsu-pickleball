## 1. 前端录制入口

- [x] 1.1 将 `src/pages/CaptureConsolePage.tsx` 的 `recordingFps` 默认值改为 60。
- [x] 1.2 将 `CaptureConsolePage` 单摄录制 FPS 下拉选项改为最高 60fps，并移除 90fps/120fps。
- [x] 1.3 将 `CaptureConsolePage` 双摄同步录制 FPS 下拉选项改为最高 60fps，并移除 90fps/120fps。
- [x] 1.4 将旧入口 `src/App.tsx` 的录制表单默认 FPS 改为 60。
- [x] 1.5 将旧入口 `src/App.tsx` 的实时录制 FPS 下拉选项改为最高 60fps，并移除 90fps/120fps。

## 2. 后端录制合同

- [x] 2.1 将 `backend/app/camera/models.py` 中 `RecordingStartRequest.fps` 默认值改为 60，校验上限改为 60。
- [x] 2.2 将 `backend/app/camera/models.py` 中 `SyncStartRequest.fps` 默认值改为 60，校验上限改为 60。
- [x] 2.3 将 `backend/app/camera/recorder.py` 中 `Recorder.start()` 的 FPS 默认参数从 90 改为 60。
- [x] 2.4 全仓搜索实时录制相关的 90fps/120fps 选项或默认值，确认没有遗漏的录制入口。

## 3. 测试与验证

- [x] 3.1 更新 `src/services/sourceFps.test.ts`，确保单摄和双摄录制请求使用 60fps，不再验证 90fps 录制请求。
- [x] 3.2 运行前端相关测试，确认 FPS 类型和录制请求测试通过。
- [x] 3.3 运行或补充后端模型校验测试，确认 `fps=60` 被接受且 `fps=61` 被拒绝。
- [x] 3.4 运行 OpenSpec 校验，确认 `cap-recording-fps-at-60` 变更 apply-ready。
