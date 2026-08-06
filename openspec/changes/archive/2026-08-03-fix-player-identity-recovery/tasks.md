## 1. 锁管理器同帧恢复

- [x] 1.1 在 `PlayerLockManager.update()` 中区分已正常匹配的 current track、未占用观测和恢复候选，建立同帧 slot-track 一对一分配流程。
- [x] 1.2 修正 LOST/LOCKED 短暂换 track 的同槽位恢复：候选命中时输出唯一 `track_identity_hints`、加入 `eligible_track_ids`，未命中时保留现有 LOST 硬锁语义。
- [x] 1.3 在 bootstrap 分配时写入 `side_hint` 和必要的 `home_quadrant` 元数据，并保持 `assignment_side` 与 home quadrant 语义分离。
- [x] 1.4 为锁管理器增加重复候选、两个候选分别回连、短暂漏检恢复和 side/quadrant 元数据测试。

## 2. 身份层与分析管线接线

- [x] 2.1 确认 `PlayerLockUpdate` 的恢复候选在分析管线中与 selector 建议合并，并在 identity layer 过滤前保留 lock manager 的权威候选。
- [x] 2.2 调整 `PlayerIdentityManager` 的 hint、既有映射、soft takeover、unmatched 顺序，确保恢复 track 绑定原 canonical player 且不创建第五身份。
- [x] 2.3 增加 tracker `track A -> 短暂漏检 -> track B`、无 selector suggestion、候选未进入 eligibility 和超过软接管距离等后端测试。
- [x] 2.4 增加 pipeline 级测试，断言 `FrameDetection.player_id`、trajectory sample 和诊断事件能反映原 P ID、tentative 恢复或明确 unmatched 原因。

## 3. Overlay 身份连续性

- [x] 3.1 更新 `resolveDetectionFrame()`：相同 `track_id` 的下一帧已具备 canonical `player_id` 时，插值检测同步继承该身份和 canonical label。
- [x] 3.2 保持不同 `track_id` 之间不由前端按空间距离猜测 P ID，并继续隐藏 raw `track_id` 的用户可见文本。
- [x] 3.3 增加 overlay playback 测试，覆盖当前帧 `person` 到下一帧 P1、不同 track 无身份和 canonical label 不泄漏 raw ID。
- [x] 3.4 运行 `VideoAnalysisCard` 相关组件测试，确认 tentative、lock hint 恢复和未关联检测的显示行为符合 spec。

## 4. 真实视频回归准备

- [x] 4.1 确认 `/Users/tuian/Downloads/测试视频25s.mp4` 可读，记录视频时长、分辨率、source FPS 和实际可识别球员数量。
- [x] 4.2 通过现有上传/注册流程准备该视频的 video ID 和有效 calibration，记录本次回归使用的 frame stride、match format 与 job 参数。
- [x] 4.3 创建新的 analysis job 运行修复后的管线；不得用刷新旧 job artifact 代替重新分析，也不得删除旧 job。

## 5. Artifact 对比验收

- [x] 5.1 从新旧 job 读取 `tracking-overlay`、`player-trajectories`、`player-render-trajectories` 和相关 diagnostics，建立可复查的对比记录。
- [x] 5.2 检查 P1-P4 数量、slot-track 一对一关系、track history、重连事件、unmatched/filtered 事件和 trajectory coverage。
- [x] 5.3 标记视频中短暂漏检位置，确认新 track 恢复原 P ID，且不存在长期无诊断的 `person` 区间。
- [x] 5.4 保存新旧 job ID、参数、关键指标和残余风险说明；只提交 markdown/JSON 摘要，不提交测试视频二进制。

## 6. 全量验证与交付

- [x] 6.1 运行后端球员锁定/身份/分析管线定向 pytest。
- [x] 6.2 运行前端 overlay、VideoAnalysisCard 和相关 typecheck/lint/Vitest。
- [x] 6.3 运行 OpenSpec 校验并确认所有 apply-required artifacts 完成。
- [x] 6.4 只有在自动化测试和真实视频 artifact 对比均通过后，才将 change 标记为可归档。
