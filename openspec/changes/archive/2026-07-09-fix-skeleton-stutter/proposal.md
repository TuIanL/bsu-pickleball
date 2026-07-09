## Why

分析任务中人体骨架在视频播放时呈现卡顿/冻结，不跟随人物移动，严重影响用户对分析结果的基本信任。经诊断确认：**骨架本身 RTMPose 正常**，根因是后端场地视角门控（court-view gate）阈值过严导致 95.7% 的帧被剔除，叠加前端在空洞区间沿用上一帧骨架的冻结策略。

当前配置对多数匹克球比赛视频（含大量近景/观众镜头）会产生严重的数据稀疏问题，需要修复以保障产出的可用性。

## What Changes

1. **后端：松弛场地视角门控阈值** — 降低 `court_view_match_threshold` 或提供按任务动态开关的能力，使得 court-view 通过帧覆盖率达到合理水平（预期从 4.3% 提升至 40%+）。
2. **前端：改善骨架空洞区间视觉反馈** — 当前 `resolvePoseFrame` 在空洞区间沿用上一帧骨架导致长时间冻结（最大 69s），改为空洞超过 N 帧（如 30 帧/0.5s）时淡出/隐藏骨架以避免定格错觉。

## Capabilities

### New Capabilities
- `skeleton-overlay-gap-handling`: 骨架叠加在前端播放时缺失帧的处理策略（淡出/隐藏 vs 沿用上一帧）

### Modified Capabilities
- `court-view-roi-gating`: 调整场地视角门控的匹配阈值或行为逻辑，降低对运动视频中非标准球场视角的误拒率

## Impact

- **后端**: `backend/app/core/config.py`（阈值参数）、`backend/app/services/analysis_pipeline.py`（门控逻辑/抽帧循环）
- **前端**: `src/components/platform/videoOverlayPlayback.ts`（`resolvePoseFrame`、`findFrameWindow` 的空洞处理策略）
- **视觉产物**: `pose_overlay.json` 的覆盖帧数预计从 217 提升至数千帧；`court_view_roi.json` 的 `court_view_frame_count` / `non_court_view_frame_count` 比例改变
