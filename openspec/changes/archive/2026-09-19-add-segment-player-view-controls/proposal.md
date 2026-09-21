## Why

片段页的播放器是用户看回放、核对回合边界的主界面，但它是目前唯一缺全屏与静音的播放器：`VideoAnalysisCard` 早已有全屏与静音（`src/components/platform/VideoAnalysisCard.tsx:592-602` 状态同步、`:805-813` 切换、`:1229-1259` 两个控件），`SegmentVideoPlayer` 两者都没有。片段页因此无法把画面放大到全屏——固定机位比赛视频里远端球员很小，全屏是看清动作的最低成本手段，也直接影响回合边界的人工确认效率。

补齐它不需要新的后端、数据或接口：播放器组件内已有 `data-[fullscreen=true]:` 尺寸变体这套现成约定可以照搬。

## What Changes

- `SegmentVideoPlayer` 新增**全屏 / 退出全屏**：
  - 全屏对象是「视频画面 + 播放进度条 + 控制条」这一整块，而不只是 `<video>`，因此全屏后仍能拖进度、逐帧、切机位。
  - 全屏时画面按原比例居中（`object-contain`），**不裁切、不拉伸、不留未使用画面**。
  - 遵循既有约定：`document.fullscreenEnabled` 不可用时控件禁用；用 `fullscreenchange` 事件与 `document.fullscreenElement` 同步状态；容器按 `data-[fullscreen=true]:` 变体切换尺寸。
- 新增**静音 / 取消静音**：状态由 `<video>.muted` 驱动，并通过 `volumechange` 事件回同步。
- 新增键盘快捷键 `F`（全屏）与 `M`（静音），与既有 `←`/`→`（逐帧）、`Shift+←/→`（1 秒）、`Space`（播放/暂停）并列。
- 非全屏状态下的外观、控制行为与既有能力保持可用；全屏内已归档的自动回合回放提示（中央「第X回合」与进度条区间配色）随画面一并呈现，不需要额外处理。
- 双摄复核模式（两个播放器并排）下**只全屏被点击的那一路**；另一路继续按既有同步逻辑播放与计时，退出全屏后仍与原视角对齐。
- **非目标**：不做画面裁切放大（`cover`）、不做滚轮缩放与拖拽平移、不做倍速播放、不做画中画与单帧截图导出。

## Capabilities

### New Capabilities

- `segment-player-view-controls`: 定义片段回放器的视图与音频控制——全屏切换（含全屏对象范围、画面填充口径、能力不可用时的降级）、静音切换，以及两者对应的键盘快捷键与在双摄并排场景下的行为边界。

### Modified Capabilities

<!-- 无。本变更只新增回放器控制能力，不改变任何既有规格的需求语义。 -->

## Impact

- 前端（组件层）：`src/components/SegmentVideoPlayer.tsx` —— 全屏容器与尺寸变体、两个新控件、`F`/`M` 快捷键。
- 前端（样式层）：`src/index.css` —— 仅在需要覆盖全屏下的圆角/边框时新增作用域样式。
- 自动获得（同一组件共用实现）：`ScoringCalibrationWorkbenchPage.tsx:541` 与片段页第二个机位播放器也会具备这两项能力；两者的非全屏外观与交互不变。
- 不受影响：后端与全部 API 契约；`EditableSegmentTimeline`；已归档的 `auto-rally-playback-cues`（本变更不修改其数据口径与触发规则）。
