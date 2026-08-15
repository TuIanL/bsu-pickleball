## Why

双摄同步分析（以及单摄上传分析）的场地标定环节存在几处体验问题：任务进行页的横向阶段进度条底部有一根碍眼的滚动条；视频体量越大，加载首帧进行标定的等待越久；自动标定需要用户手动点击按钮才触发；手动标定需要按固定顺序逐点点击四个角，操作不够直观。这些问题拖慢了标定效率，也影响视觉观感。

## What Changes

- **任务阶段进度条去滚动条**：任务进行页的水平胶囊阶段 stepper 隐藏可见的横向滚动条，同时保留左右滑动、触摸/触控板拖动与"自动聚焦当前阶段"的能力。
- **标定首帧加载提速**：保留 `<video>` seek 方案（不新增后端抽帧缩略图接口），将 `preload="auto"` 改为 `preload="metadata"`，并把 seek 目标从 `duration * 0.1` 改为固定靠前位置，避免浏览器加载整段视频，显著缩短等待时间。
- **自动标定进入即触发**：打开标定组件即自动发起 `requestAutomaticCalibration`，成功后把返回的角点铺设成可拖拽四边形供用户确认；失败或拒绝则提示"标定失败"并保留人工标定兜底。
- **手动标定改为拖拽四边形**：由"依次点击四个角点"改为"可拖拽四边形"（四角 + 四边），最终仍将四个角点坐标回传给后端（接口契约不变）。
- **自动标定抽帧位置固定靠前**：自动标定后端抽帧位置从 10% 比例改为固定靠前（靠近开头），前后端统一。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `automatic-court-line-calibration`: 自动标定由"手动点击触发"改为"进入即自动触发"、抽帧位置改为固定靠前、失败时给出明确提示并保留人工兜底；手动标定交互由"逐点点击"改为"拖拽四边形"。
- `video-analysis-job-flow`: 水平阶段 stepper 隐藏可见滚动条，保持横向可滚动与自动聚焦。

## Impact

- **前端组件**：
  - `src/components/platform/CourtCornerCalibrator.tsx`（核心改动：自动触发、拖拽四边形、首帧加载优化、失败提示）。
  - `src/components/platform/JobStageStepper.tsx`（隐藏滚动条）。
  - 共用 `CourtCornerCalibrator` 的 `NewAnalysisPage.tsx`、`RecordingAnalyzePage.tsx`、`MultiViewAnalysisSetupPage.tsx` 无需改动，改动自动全局生效。
- **前端服务**：`src/services/analysisClient.ts` 的 `requestAutomaticCalibration` 可能需要携带抽帧参数（`frame_index` / `timestamp_seconds`）。
- **后端**：`backend/app/services/automatic_calibration_service.py` 的 `_extract_frame` 抽帧逻辑支持固定靠前（已有 `payload.frame_index` / `payload.timestamp_seconds` 支持，可能仅需前端传参或调整默认比例）。对外接口与数据契约不变。
- **无新增依赖，无破坏性变更**。
