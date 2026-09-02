## Why

真实双摄任务 `job-43e7475fd8` 在视频约 7–13 秒出现 P2/P4 识别频闪、框与脚点脱离，以及跨机位身份串位。当前已有的四人识别和 overlay 稳定机制没有覆盖这段交叉/漏检场景，导致错误的 local slot reassociation 被传播到 fused trajectory 和视频叠加层，因此需要建立针对性修复与回归验收。

## What Changes

- 收紧双摄 local slot 到 global player 的 reassociation：不再仅依赖短期几何优势，必须同时满足 tracklet 连续性、球场侧/区域一致性、唯一槽位和连续强证据；证据不足时保持 incumbent 或标记 ambiguous，不直接换人。
- 处理 P2/P4 在参考视角缺检期间的跨视角补全，禁止投影候选与可信球员框冲突时继续发布会与脚点脱离的旧框。
- 为 fused overlay 增加投影碰撞、几何跳变、box/footpoint 一致性和短窗口状态振荡的可审计诊断。
- 保持用户可见的 canonical `P1–P4` 映射稳定；不得因单机位 local `Player_N` 变化而重排 canonical roster 或污染正式轨迹。
- 增加真实任务 7–13 秒片段的结构化回归：验证 P2/P4 不发生错误换位、overlay 不出现高频 box/point 振荡、投影碰撞时不会绘制误导性人体框。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `multiview-player-association`: 强化 local slot、tracklet 与 global player 的跨视角绑定和 reassociation 安全门。
- `multiview-fused-player-overlay`: 强化投影框碰撞、几何连续性及 bbox/footpoint 一致性，避免错误 geometry 进入正式 overlay。
- `stabilize-multiview-overlay-display`: 将短窗口频繁的真实框/投影框/投影点振荡纳入稳定性约束，并定义碰撞时的安全降级。
- `player-display-diagnostics`: 增加 local slot rebind、投影拒绝和显示状态振荡的逐 tick 可追溯信息。
- `four-player-identification-quality`: 增加 view-slot reassociation、P2/P4 定点片段和 overlay 稳定性验收门。

## Impact

- 后端：`association_global.py`、`global_state.py`、`multiview_joint_run.py`、`fused_overlay_builder.py`、`overlay_display_state.py` 及相关 artifact writer。
- 前端：继续消费后端 canonical overlay；必要时补充对 `display_state`、碰撞降级和诊断字段的展示，不在前端重新推断身份。
- 产物/API：扩展 fused overlay、player display diagnostics、fusion diagnostics 和 four-player identification quality 的 additive 字段；现有旧产物保持兼容。
- 测试与验收：新增 P2/P4 7–13 秒回归夹具，覆盖 identity binding、projection collision、box/footpoint 一致性、状态振荡和正式轨迹污染隔离。
