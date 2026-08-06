## Why

真实双打视频中，P1-P4 的槽位锁定与短暂漏检后的身份恢复仍不稳定：多个 LOST 槽位可能竞争同一个新 track，短暂换 track 后新观测可能在进入身份层前被过滤，最终检测叠加退化为 `person`。已有单元测试通过，但没有覆盖真实 tracker 换 ID、多个 LOST 槽位竞争以及视频 overlay 帧间身份连续性，因此无法证明归档变更在真实视频上有效。

本变更需要在不重新上传测试视频的前提下，修正身份恢复链路，并使用 `/Users/tuian/Downloads/测试视频25s.mp4` 创建全新的分析任务进行回归验证；旧分析任务保留作为对照基线。

## What Changes

- 为 LOST 槽位的重连增加同一帧候选的一对一约束，防止多个 P 槽位绑定同一个新 track。
- 补齐 bootstrap 槽位的 side/quadrant 元数据，使 P1-P4 的重连评分真正使用初始位置语义。
- 统一短暂漏检、tracker 换 ID、lock hint、soft takeover 与 `eligible_track_ids` 的恢复契约，确保合格的新 track 能回到原 canonical player ID。
- 保证检测叠加在身份恢复后重新显示 `P1`-`P4`，不因前后 overlay 帧的短暂空身份而长期显示 `person`。
- 增加后端单元/集成回归和前端 overlay 帧解析测试。
- 使用指定的 25 秒真实双打视频执行新的分析任务，比较旧任务与新任务的身份稳定性、恢复率和 `person` 退化区间。

## Capabilities

### New Capabilities

- `player-identity-recovery-validation`: 规定真实视频回归夹具、分析任务重跑方式、身份稳定性指标和验收证据。

### Modified Capabilities

- `player-lock-state-machine`: 修改 LOST 重连候选的一对一绑定、槽位位置元数据和 P1-P4 身份锁定契约。
- `player-trajectory-identity`: 修改短暂漏检及 tracker 换 ID 后的 canonical 身份恢复与 eligible track 传递要求。
- `player-identity-display`: 修改检测 overlay 在相邻帧身份暂缺时保持或恢复 canonical 标签的要求。

## Impact

- 后端：`player_lock_manager.py`、`player_lock_types.py`、`player_identity.py`、`analysis_pipeline.py` 及相关 tracking schemas/tests。
- 前端：`videoOverlayPlayback.ts`、`VideoAnalysisCard.tsx` 及相关测试。
- OpenSpec：新增真实视频回归能力，并更新三个球员身份相关能力的 delta spec。
- 测试数据：使用本机外部文件 `/Users/tuian/Downloads/测试视频25s.mp4`，不将该视频复制进仓库；回归结果应记录视频路径、任务 ID、分析参数和 artifact 对比结论。
- API/数据库：不新增公开 API，不迁移历史任务 artifact；验证必须创建新的分析任务。
