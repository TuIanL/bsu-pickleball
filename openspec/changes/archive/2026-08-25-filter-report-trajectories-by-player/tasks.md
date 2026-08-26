## 1. 球路筛选纯逻辑

- [x] 1.1 在 `src/services/ballTrajectoryVisualization.ts` 中整理报告页使用的球员/Shot 筛选入口，使用 canonical player ID 和 `ownership_status === "confirmed"`，排除未归属、歧义归属、无 `shot_id` 或无法解析身份的数据。
- [x] 1.2 保证筛选以 `shot_id` 为单位：命中目标球员的 Shot 时保留该 Shot 的全部 segment，并保留每条轨迹原始的 `hitterPlayerId`、`shotId` 和 ownership 字段。
- [x] 1.3 补充球路筛选纯函数测试，覆盖 Player_1/Player_2 隔离、同一 Shot 多 segment、null/ambiguous/unassigned 排除和无匹配结果。

## 2. 报告页 3D 球路接入

- [x] 2.1 修改 `src/components/pb-vizion/Pb3DCourtCard.tsx`，移除“保留未归属轨迹”和“把轨迹改写成当前球员”的逻辑，改为消费统一的严格球员筛选结果。
- [x] 2.2 保持现有阶段筛选、质量阈值和 `BallTrajectoryScene` 交互，在球员归属筛选之后应用其他筛选，并在切换球员后清理不再可见的 `selectedShotId`。
- [x] 2.3 让球路数量和 Shot 级统计派生自最终筛选结果；无匹配结果时显示明确空态，禁止回退渲染整场球路。

## 3. 报告页回归测试

- [x] 3.1 更新 `src/components/pb-vizion/Pb3DCourtCard.test.tsx` 的 artifact fixture，为轨迹补充不同球员和归属状态，并验证选择 Player_1 时场景只收到 Player_1 的球路。
- [x] 3.2 增加球员切换和空结果测试，验证切换到 Player_2 后不残留 Player_1 的轨迹，且未归属轨迹不会被显示。
- [x] 3.3 运行相关 Vitest 测试，确认现有球路 view model、报告卡片和其他报告组件测试不回归。

## 4. 完成校验

- [x] 4.1 运行 TypeScript/Vite build，确认新增筛选逻辑、类型和组件依赖均可编译。
- [x] 4.2 对照 `ball-trajectory-visualization` delta spec 检查实现，确认未修改后端 artifact、身份协议或其他页面行为。
