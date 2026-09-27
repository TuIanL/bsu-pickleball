## 1. 组件层：标定器嵌入模式（向后兼容）

- [x] 1.1 `CourtCornerCalibrator` 新增可选 props `variant?: "standalone" | "embedded"`（默认 `standalone`）、`title?: string`、`submitLabel?: string`（默认沿用「确认并启动分析」）；`embedded` 时不渲染外层 `section` 边框与「四角标定」大标题层级，点位摘要由 `sm:grid-cols-4` 降为 `grid-cols-2`
- [x] 1.2 `NetProfileCalibrator` 新增可选 props `variant?: "standalone" | "embedded"`、`hideProfilePanel?: boolean`；`embedded` 时强制单列（忽略内部 `lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]`）、隐藏右侧参数面板与 `confirmed` 勾选，`complete` 判定不再依赖内部 `confirmed`
- [x] 1.3 从 `NetProfileCalibrator.tsx` 导出 `buildNetProfile(...)`（现私有 `makeProfile` 改名导出）与参数面板组件 `NetProfileSettings`（现内联 JSX 抽出）
- [x] 1.4 跑 `src/components/platform/CourtCornerCalibrator.test.tsx`、`NetProfileCalibrator.test.tsx`、`src/pages/NewAnalysisPage.test.tsx` 与 `RecordingAnalyzePage` 相关测试，确认单摄流程零回归（默认 props 下行为与外观不变）

## 2. 向导页：三阶段重构

- [x] 2.1 `SetupStep` 由 `0 | 1 | 2 | 3 | 4 | 5` 收敛为 `0 | 1 | 2`，`STEP_LABELS` 改为「球场标定 / 球网标定 / 名册与确认」三项
- [x] 2.2 抽出常驻素材状态条（A/B 视频就绪、录制状态、同步锚点状态与阻断操作、同步质量摘要），从原 step 0 迁出并置于页面顶部，任何阶段可见
- [x] 2.3 将「仅分析指定窗口」「生成 Debug Replay」「分析流程选择」三项迁入名册与确认阶段，并从状态条移除
- [x] 2.4 `handleCalibrationComplete` / `handleNetComplete` 改为「只记录结果不跳步」；新增两路完成度派生（球场就绪、球网就绪）与「下一步」门控，未完成时指明缺失的一路
- [x] 2.5 并排容器：两个标定区改为 `grid gap-6 xl:grid-cols-2`（低于 `xl` 自动纵向堆叠）；页面容器由 `max-w-5xl` 改为 `max-w-7xl`
- [x] 2.6 球网高度 profile 提升为向导页唯一 state（`mode` / `endpointCm` / `centerCm` / `confirmed`），在球网标定阶段顶部渲染一份 `NetProfileSettings`；两路 `onComplete` 时用页面级 profile 覆盖 draft 的 profile 字段后再写入 `netAnnotationA/B`
- [x] 2.7 「机位朝向」radio 组从确认阶段前移到球场标定阶段顶部；朝向改变时清空两路球网点位草稿、保留球场标定，并给出提示
- [x] 2.8 `handleStart` 改用共享 profile 组装 `net_profile` 与 `holdout_control_points`（替换现 `...netAnnotationA.profile` 的取值来源）；确认阶段朝向改为只读回显 + 跳回标定入口
- [x] 2.9 修订 `submitError` 的回退入口：不再 `setStep(0)` 到已不存在的素材检查步，改为就地高亮状态条或回到球场标定阶段

## 3. 测试重整

- [x] 3.1 `src/pages/MultiViewAnalysisSetupPage.test.tsx` 的组件 mock 适配新 props（`variant` / `submitLabel` / `hideProfilePanel` / `NetProfileSettings`）
- [x] 3.2 重写步骤驱动断言以匹配三阶段流程（原 5 次「下一步」链降为 2 次）
- [x] 3.3 新增用例：单路完成不放行并指明缺哪一路；两路拖点互不干扰；共享 profile 的改动进入两路提交载荷；朝向在标定阶段先于标定器出现
- [x] 3.4 重整既有 3 条失败用例（`returns to material checks after a sync preflight submit failure`、`publishes the opt-in Debug Replay flag`、`navigates to Analysis Progress preserving the library return`），保持其原始意图与断言强度（回退行为、`debugTraceEnabled=true`、`return` 路径保留）
- [x] 3.5 跑 `MultiViewAnalysisSetupPage.test.tsx` 与两个标定器测试文件，确认通过

## 4. 验证

- [x] 4.1 前端全量 `npm test -- --maxWorkers=2`，与基线（758 passed / 3 failed）比对，确认失败数不增加、无新增失败文件
- [x] 4.2 对改动文件跑 eslint，确认未引入新的 error（`SegmentManagerPage.tsx` 的 14 条为既有，不修）
- [ ] 4.3 实测 D6 观测点：并排下两路自动标定的总耗时，若明显劣于串行则改为首路完成后触发次路
- [x] 4.4 人工视觉验证（由用户完成）：宽屏并排 / 窄屏堆叠的实际观感、每侧拖点手感、球网共享高度面板的可发现性
