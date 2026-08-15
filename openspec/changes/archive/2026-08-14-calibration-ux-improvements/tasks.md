## 1. 阶段 stepper 隐藏滚动条

- [x] 1.1 新增 `scrollbar-none` utility（`scrollbar-width: none` + `-ms-overflow-style: none` + `::-webkit-scrollbar{display:none}`）
- [x] 1.2 在 `JobStageStepper.tsx` 用 `scrollbar-none` 替换 `[scrollbar-width:thin]`
- [x] 1.3 验证横向滑动与自动聚焦当前阶段仍正常（含 compact 与非 compact 两种模式）

## 2. 标定首帧加载提速

- [x] 2.1 在 `CourtCornerCalibrator.tsx` 将 `<video preload="auto">` 改为 `preload="metadata"`
- [x] 2.2 将 seek 默认目标从 `duration * 0.1` 改为固定靠前位置（约 0.5s / 第 2~3 帧）
- [x] 2.3 保留并校验"黑场自动前跳"逻辑在靠前 seek 下的行为（小步前跳仍生效）

## 3. 自动标定进入即触发

- [x] 3.1 `CourtCornerCalibrator` 在 `videoId` 就绪且组件挂载后自动调用一次 `requestAutomaticCalibration`
- [x] 3.2 `requestAutomaticCalibration` 支持携带固定靠前抽帧参数（`timestamp_seconds` 或 `frame_index`），后端 `_extract_frame` 按其抽帧
- [x] 3.3 自动标定 `available` 时铺设四边形并展示置信度/预览；`rejected`/`unavailable`/错误时提示"标定失败"并保留人工兜底
- [x] 3.4 保留"重新自动识别"操作供用户重跑

## 4. 手动标定拖拽四边形

- [x] 4.1 以可拖拽四边形覆盖层 + 四个角点手柄 + 四条边命中区替换逐点点击
- [x] 4.2 实现角点拖动（仅更新单点）与边拖动（该边两端点一起平移并 clamp）
- [x] 4.3 复用屏幕% ↔ 原图像素换算（含 object-contain letterbox offset），改为 pointer 事件驱动
- [x] 4.4 保持角点编号映射（top_left/top_right/bottom_right/bottom_left）与 `isBaselineOrderPlausible` 校验
- [x] 4.5 提交仍回传四角 image_points（`acceptAutomaticCalibration` / `createManualCalibration`），按来源判定 `automatic`/`corrected`
- [x] 4.6 手柄/边命中区加 `touch-action: none`，拖拽期间不触发视频 seek

## 5. 测试与回归

- [x] 5.1 更新/新增 `CourtCornerCalibrator.test.tsx` 覆盖自动触发、失败兜底、拖拽角点/边
- [x] 5.2 更新/新增 `JobStageStepper.test.tsx` 覆盖滚动条隐藏与自动聚焦
- [x] 5.3 在单摄（`NewAnalysisPage` / `RecordingAnalyzePage`）与双摄（`MultiViewAnalysisSetupPage`）两条链路手动回归
