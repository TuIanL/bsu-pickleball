## Why

双摄分析中的球员即使已经形成稳定检测轨迹，也可能因单视角锁定条件或名册已满而止步于正式身份链路之外。当前未锁定轨迹只进入调试产物，名册满后的 unmatched observation 也不会继续累积证据；因此一次局部漏锁可能演变成长时间缺失，且旧任务在未开启逐帧 debug trace 时无法再定位具体拦截分支。

## What Changes

- 让单视角未锁定但有效的球场轨迹以“候选证据”身份进入双摄恢复流程，与正式 P1–P4 observation 分开。
- 为名册满后的未匹配观测保留有界恢复证据；只有连续身份、场地几何、唯一性和时间连续性均达标时，才允许其恢复到已有 roster global。
- 让候选及恢复状态影响名册确认和质量结论：兜底槽位映射不得伪装成已确认身份，缺少正式身份锚点时明确保持未确认。
- 保留候选、隔离、恢复与拒绝原因的结构化诊断，便于在未来任务中定位证据链断点。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `view-tracking-session`: 保留具备有效场地投影的未锁定轨迹作为候选证据，不将其直接提升为正式单视角身份。
- `multiview-player-association`: 名册满后继续累积 unmatched evidence，并以安全门控恢复到既有 global；歧义候选继续隔离。
- `multiview-global-player-roster`: 区分候选、占位与已确认身份；只有可审计的身份锚点满足条件后才能确认公开映射。
- `four-player-identification-quality`: 将候选恢复结果、未确认映射和未解决缺口纳入质量判定与断点摘要。

## Impact

影响 `ViewTrackingSession` 输出、joint run 的候选观测收集、`GlobalPlayerAssociator` / `GlobalPlayerRegistry` 的恢复队列、名册映射及四人识别质量产物。对外 API 保持兼容；候选不会进入正式轨迹、热力图或报告，直到身份恢复通过门控。
