## Context

`CourtCornerCalibrator` 是场地标定的唯一前端组件，被三个页面共用：`NewAnalysisPage`（上传视频分析）、`RecordingAnalyzePage`（录制后分析）、`MultiViewAnalysisSetupPage`（双摄同步分析）。当前标定流程为：

1. `<video preload="auto">` 拉取全量视频流，`onLoadedMetadata` 后 seek 到 `duration * 0.1`，抽帧到 canvas 作为标定底图；
2. 自动标定需要用户点击"自动识别"按钮才触发；
3. 手动标定按固定顺序（远端左 → 远端右 → 近端右 → 近端左）逐点点击。

后端 `automatic_calibration_service.suggest` 已支持按 `frame_index` / `timestamp_seconds` 抽帧，默认回退到 `court_line_frame_ratio = 0.1`。后端 `stream_video` 已支持 HTTP Range 断点续传。

## Goals / Non-Goals

**Goals:**

- 隐藏任务进行页水平阶段 stepper 的可见滚动条，同时保留横向滑动与自动聚焦。
- 缩短标定首帧加载等待，且不新增后端接口。
- 打开标定即自动触发自动标定，成功铺设四边形、失败则提示并回退人工。
- 用可拖拽四边形（四角 + 四边）替代逐点点击，最终仍回传四角坐标。

**Non-Goals:**

- 不新增"后端抽帧缩略图"接口。
- 不做整体拖动四边形（只做四角 + 四边）。
- 不改动后端标定接口契约与数据模型（仍为四角 image_points）。
- 不改动自动标定的分割模型、置信度算法与单应性计算。

## Decisions

### D1：首帧加载保留 `<video>` seek，靠 `preload` 与 seek 目标优化

- **选择**：保留 `<video>` seek，将 `preload="auto"` 改为 `preload="metadata"`，seek 目标从 `duration * 0.1` 改为固定靠前位置（约 `0.5s` 或固定第 2~3 帧）。
- **理由**：后端 stream 已支持 HTTP Range（`Accept-Ranges: bytes`），浏览器 seek 只需拉取目标帧附近的字节段，无需加载整段视频。当前慢的根因是 `preload="auto"` 激进预缓冲 + seek 到 10% 深处（字节偏移远、关键帧解码开销大）。
- **备选（已放弃）**：新增后端抽帧缩略图接口。放弃原因：自动标定失败兜底仍需 `<video>` seek，重复造轮子；且 Range 方案已足够。
- **保留**：现有"黑场自动前跳"逻辑（`isProbablyBlankFrame` + `calibrationAutoSeekAttemptsRef`）继续工作，前跳改为小步长。

### D2：自动标定进入即触发

- **选择**：`CourtCornerCalibrator` 在 `videoId` 就绪且组件挂载后，自动调用一次 `requestAutomaticCalibration`；成功后 `applyAutomaticKeypoints` 铺成四边形，用户确认即可提交；失败/拒绝/不可用则显示"标定失败"并保留人工拖拽。
- **理由**：自动标定已返回"角点 + 置信度 + 预览图"，进入即触发能一次性给出结果，用户只需"确认 / 修正"，显著减少操作。
- **抽帧位置**：前端请求携带固定靠前参数（`timestamp_seconds` 约 `0.5s` 或 `frame_index` 第 2~3 帧），覆盖默认 10% 比例；后端 `_extract_frame` 已支持该参数，无需改默认值即可生效。
- **状态机**：`idle → detecting → ready(available) | rejected | unavailable | error`；保留"重新自动识别"按钮供重跑。
- **提交来源判定**：自动标定 available 且用户未改动 → `source="automatic"`（走 `acceptAutomaticCalibration`）；被改动或自动失败 → `source="corrected"` / 手工（走 `createManualCalibration`）。

### D3：手动标定改为可拖拽四边形

- **选择**：以四边形覆盖层 + 四个角点手柄 + 四条边命中区呈现；角点 pointer 拖动更新单点，边拖动更新该边两个端点（`dx/dy` 相同，clamp 到画面内）；提交仍回传四角 image_points。
- **坐标换算**：复用现有 `handleCalibrationClick` 的屏幕% ↔ 原图像素换算（含 object-contain 的 letterbox offset 计算），改造为 pointer 事件驱动。
- **编号语义**：角点仍固定映射 ①top_left ②top_right ③bottom_right ④bottom_left，保证 `isBaselineOrderPlausible` 远端/近端校验与后端 keypoint 顺序不变。
- **交互细节**：手柄加 `touch-action: none` 以支持移动端拖动；拖拽期间不触发视频 seek。

### D4：滚动条隐藏用 `scrollbar-none` utility

- **选择**：新增 `scrollbar-none` utility（`scrollbar-width: none` + `-ms-overflow-style: none` + `::-webkit-scrollbar{display:none}`），替换 `JobStageStepper` 的 `[scrollbar-width:thin]`。
- **理由**：`[scrollbar-width:thin]` 仅 Firefox 生效，Chrome/Safari 回退成默认尺寸滚动条；`scrollbar-none` 跨浏览器隐藏，同时 `overflow-x-auto` 与自动聚焦逻辑保留，滑动能力不受影响。

## Risks / Trade-offs

- [固定靠前帧可能抽到黑场/过渡帧] → 保留黑场前跳逻辑；自动标定后端对坏帧会 reject → 走人工兜底。
- [`preload="metadata"` 下 seek 后抽帧时序] → 保留现有 `readyState >= 2` 检查与 `onSeeked` 捕获兜底，seek 未就绪时显示"正在读取标定画面"。
- [拖拽四边形与切帧/按钮的手势冲突] → 拖拽只作用于四边形命中区，按钮与切帧控件在四边形之外；拖拽期间 `touch-action: none`。
- [自动触发增加后端调用（双摄两路）] → 双摄页面本就分 step 逐机位标定，自动触发为按需串行，不新增并发压力；失败后不自动重试，由用户手动"重新自动识别"。
- [隐藏滚动条后用户失去"可滑动"暗示] → stepper 已有自动聚焦当前阶段，且滑动能力保留，可接受。

## Migration Plan

- 纯前端交互改动 + 后端抽帧参数微调，无数据迁移、无 schema 变更。
- 回滚：恢复 `CourtCornerCalibrator` / `JobStageStepper` 即可，后端如未改默认值则无需回滚。

## Open Questions

- 固定靠前帧的具体值：建议 `0.5s` 或第 2~3 帧，实现时以实测黑场表现微调。
- 是否需要"重置为自动结果"按钮（用户拖乱后一键回到自动铺设）：建议提供，属低成本的可用性增强。
