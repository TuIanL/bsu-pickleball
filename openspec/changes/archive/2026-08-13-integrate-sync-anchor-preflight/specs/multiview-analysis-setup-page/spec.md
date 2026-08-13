## MODIFIED Requirements

### Requirement: MultiViewAnalysisSetupPage 四阶段

系统 MUST 提供 `MultiViewAnalysisSetupPage`，按「素材与同步前置检查 → A 机位标定 → B 机位标定 → 确认」四阶段推进；第一阶段 SHALL 查询 CaptureTake 级同步锚点状态，将需要人工锚点的录制引导到内置工作台并在完成后恢复当前向导。复用共享 `CourtCornerCalibrator`，一次完成两个 calibration（`cam_1 → calibration_1`、`cam_2 → calibration_2`）后才可启动。

#### Scenario: 素材与同步前置检查
- **WHEN** 页面加载
- **THEN** 展示 A/B 机位视频就绪状态、录制级同步锚点状态、多视角融合支持状态
- **AND** SHALL 明确区分人工锚点已确认、仅自动估算、无需人工标注、需要标注、草稿未完成和确认已失效
- **AND** 任一硬前置不满足时 SHALL 展示原因与对应操作，不静默

#### Scenario: 必须完成人工锚点
- **WHEN** 同步锚点状态为 `required`、`draft` 或 `invalidated` 且策略返回 `analysis_allowed=false`
- **THEN** 进入 A 机位标定的按钮 SHALL 禁用
- **AND** 页面 SHALL 提供“开始标注”或“继续标注”操作

#### Scenario: 同步前置允许继续
- **WHEN** 同步锚点状态为 `confirmed`、`not_required`，或策略明确允许 `auto_degraded`
- **THEN** 页面 SHALL 允许进入 A 机位标定
- **AND** SHALL 展示当前同步来源及质量，不得把自动估算描述为人工确认

#### Scenario: 双标定
- **WHEN** 用户进入标定阶段
- **THEN** A 与 B 机位各需完成一次四角标定
- **AND** 两个 calibration 都完成前，启动按钮 SHALL 禁用

#### Scenario: 确认启动
- **WHEN** 用户点击「开始双摄协同分析」
- **THEN** 系统 SHALL 在服务端再次执行同步锚点 preflight
- **AND** SHALL 只创建 1 个 multiview Parent 任务
- **AND** 成功后 SHALL 导航到 `/analysis/<parentId>`
- **AND** 用户 SHALL NOT 被导航到 child 任务

#### Scenario: 工作台确认后恢复向导
- **WHEN** 用户从素材检查进入同步锚点工作台并确认成功
- **THEN** 系统 SHALL 返回同一 CaptureTake 的素材检查阶段
- **AND** SHALL 重新读取状态并显示确认摘要
- **AND** SHALL 保留可安全恢复的向导上下文
