## Why

双摄协同分析向导把「同一次标定的两只眼」拆成两个独立步骤：素材检查 → A 球场 → B 球场 → A 球网 → B 球网 → 名册确认，共 6 步。用户每完成一路标定都要点一次「下一步」翻页，其中 4 次翻页只是换一路视频，向导本身的准备成本高，且两路标定无法互相参照。

同时存在一个静默数据丢失缺陷：`handleStart` 组装球网 profile 时使用 `netAnnotationA.profile`，B 侧（cam_2）在「B 球网」步骤里填写的两侧/中心高度改动**被直接丢弃且无任何提示**。

## What Changes

- 向导由 6 步压缩为 3 步：**素材与同步检查 → 球场与球网标定 → 名册与确认**。**BREAKING**：步骤语义、进度条与回退目标改变。
- 「球场标定」阶段改为 A/B 两路**同页**标定：宽屏左右并排（各占一半宽度），窄屏（低于并排断点）纵向堆叠；两路各自独立拖动四角，两路都提交成功才允许进入下一步。
- 「球网标定」阶段同样两路同页，并把**球网高度 profile 收敛为单份共享输入**（同一张网只有一个高度模型：profile 类型、两侧高度、中心高度、确认勾选），两路各自只负责自己的 image-space 三个控制点与两个 hold-out 点。
- 「机位朝向」（A 机位位于球场 A 端 / B 端底线）从确认阶段**前移**到标定阶段之前。它决定球网左右端的 canonical 语义（`displayOrder` 会随 `rotate_180`/`mirror_x` 翻转），原先在标定完成后才询问属于顺序倒置。
- 素材与同步前置检查退化为**页面顶部常驻状态条**（A/B 视频就绪、录制状态、同步锚点状态及其阻断提示），其「分析配置」项（仅分析指定窗口、Debug Replay、分析流程选择）下移到「名册与确认」阶段。
- 修正球网 profile 只取 cam_1 的静默丢弃：两路共享唯一 profile 后，该歧义消失。

## Capabilities

### New Capabilities

- `multiview-net-profile-annotation`: 双摄向导内的球网高度标注交互——两路同页标注、每路三个 net 控制点 + 两个 hold-out 点、单份共享高度 profile、按路独立完成度与整体门控。

### Modified Capabilities

- `multiview-analysis-setup-page`: 阶段划分由「素材与同步前置检查 → A 机位标定 → B 机位标定 → 确认」改为「球场标定 → 球网标定 → 名册与确认」+ 常驻素材状态条；回退语义、下一步门控与朝向确认时机随之改变。

**刻意未列为 Modified 的既有能力**（避免无谓的标题逐字匹配风险）：

- `metric-court-scene-calibration`：其「人工球网标注与草稿微调」「标准球网高度 profile」描述的是场景资产层行为，本 change 的“高度 profile 唯一共享”属于**新增约束**而非改变既有行为，因此收在新能力 `multiview-net-profile-annotation` 里（ADDED），主规格不动。
- `automatic-court-line-calibration`：并排只改变同页实例数量与触发时机（见 design.md D6），单个标定目标的既有交互与「自动标定进入即触发」语义不变。

## Impact

- `src/pages/MultiViewAnalysisSetupPage.tsx`：步骤状态机、进度条、标定阶段布局、素材检查拆分、占位朝向选择。
- `src/components/platform/CourtCornerCalibrator.tsx`：新增嵌入/紧凑模式 props（标题层级、提交按钮文案参数化）。
- `src/components/platform/NetProfileCalibrator.tsx`：高度 profile 参数面板需可外提/可选，新增嵌入模式。
- 可能新增共享参数面板组件与「两路同页标定容器」组件。
- `src/pages/MultiViewAnalysisSetupPage.test.tsx`：步骤驱动断言随步骤名与数量变化重整。
- 单摄流程 `NewAnalysisPage.tsx` / `RecordingAnalyzePage.tsx` 复用同一批标定组件，必须保持行为与外观不变（props 扩展需向后兼容）。
- 后端契约不变：`saveMetricCourtSceneDraft` / `validateMetricCourtScene` / `publishMetricCourtScene` / `createMultiviewAnalysisJob` 的 payload 结构与字段不变。
