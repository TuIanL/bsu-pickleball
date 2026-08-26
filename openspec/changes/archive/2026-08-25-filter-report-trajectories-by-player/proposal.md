## Why

报告页已经支持在四名球员之间切换，但 3D 球路图没有可靠地同步到当前球员，用户选择球员后仍可能看到整场球路。当前实现还会把未归属轨迹混入球员视图并覆盖原始击球者字段，导致图示与球员统计的语义不一致。

## What Changes

- 报告页 3D 球路图随 `selectedPlayerId` 更新，仅展示该 canonical 球员击打的 Shot 及其全部 segment。
- 未归属、击球者不明或无 Shot 上下文的轨迹不计入任何球员的个人球路视图。
- 保留轨迹原始的 `hitterPlayerId`、`shotId` 和 ownership 字段，不再为满足显示而重写数据。
- 球路显示数量使用筛选后的数据；击球数量等 Shot 级统计按 `shot_id` 去重，避免把同一 Shot 的多个 segment 重复计数。
- 增加球员切换、未归属排除、Shot 多段聚合和空结果状态的自动化覆盖。
- 不修改后端 artifact 结构、球员身份协议或其他分析页面。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `ball-trajectory-visualization`: 明确报告页球员筛选必须严格按 canonical `hitter_player_id` 匹配，仅显示目标球员的 Shot；未归属轨迹不得进入任何球员视图，统计按 Shot 去重。

## Impact

- 前端组件：`src/components/pb-vizion/Pb3DCourtCard.tsx`。
- 前端球路 view model 与筛选逻辑：`src/services/ballTrajectoryVisualization.ts`。
- 自动化测试：`src/components/pb-vizion/Pb3DCourtCard.test.tsx`、`src/services/ballTrajectoryVisualization.test.ts`，必要时补充报告上下文测试。
- 无新增 API、数据库或后端依赖；继续消费现有 reconstructed trajectory artifact 与 canonical `Player_N` 身份。
