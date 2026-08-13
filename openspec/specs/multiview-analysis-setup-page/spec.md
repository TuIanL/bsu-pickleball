# multiview-analysis-setup-page Specification

## Purpose
TBD - created by archiving change 2026-08-07-integrate-multiview-analysis-orchestration. Update Purpose after archive.
## Requirements
### Requirement: 双摄主 CTA

双摄录制完成后的主按钮 MUST 为「双摄协同分析」并导航到 `/capture/takes/:captureTakeId/analyze`。「仅分析 A 机位 / 仅分析 B 机位」MUST 降级为次级操作（工程调试入口），不再是双摄录制的主流程。

#### Scenario: 录制卡片主按钮

- **WHEN** 用户查看一个已完成合并的双摄录制
- **THEN** 主操作 SHALL 是「双摄协同分析」
- **AND** 次级更多操作中 SHALL 保留「仅分析 A 机位」「仅分析 B 机位」

#### Scenario: 产品语义升级

- **WHEN** 用户发起双摄协同分析
- **THEN** 产品语义 SHALL 为"分析这一次 CaptureTake"而非"分析某一段录像"

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

### Requirement: CourtOrientation 产品化确认

CourtOrientation 对用户 MUST NOT 暴露 `identity / rotate_180 / mirror_x / mirror_y` 等算法枚举。**MVP 由用户人工确认**每个机位位于哪一端：「A 机位位于球场 A 端底线 / 球场 B 端底线」。后端据用户选择 + `CaptureTrack + Calibration` 生成 `CourtOrientation`。摄像头安装角色自动推断涉及新规则，SHALL NOT 在本 Change 实现。

#### Scenario: 人工确认端位置

- **WHEN** 需要确认机位朝向
- **THEN** 界面 SHALL 只呈现「A 机位位于：球场 A 端底线 / 球场 B 端底线」这类产品语义选项
- **AND** SHALL NOT 出现 `identity / rotate_180` 等算法概念

#### Scenario: 自动推断列为后续

- **WHEN** 用户未手动确认朝向，且不存在安装角色记录
- **THEN** 系统 SHALL 要求用户完成端位置确认（不静默猜测朝向）
- **AND** 摄像头安装角色自动推断 SHALL NOT 在本 Change 提供

### Requirement: 清理 cameraAngle 错误映射

系统 MUST 修复 `RecordingAnalyzePage` 中用 `session.match_format`（`singles/doubles`）查 `angleMap`（键为 `baseline_high/sideline/elevated...`）的错误语义，该逻辑几乎恒落 `unknown`。机位角度信息 SHALL 来自真实机位来源，而非比赛制式。

#### Scenario: cameraAngle 不再错误映射

- **WHEN** 创建单摄分析任务
- **THEN** `cameraAngle` SHALL 来自真实机位/录制元数据，而非用 `match_format` 查角度表
- **AND** 不再默认落到无意义的 `unknown`

### Requirement: 双摄向导提供一致的业务退出和步骤回退

`MultiViewAnalysisSetupPage` SHALL 在四个阶段提供一致的导航层级：顶部业务退出返回双摄任务管理，步骤 1 和步骤 2 提供上一步，确认阶段提供上一步，步骤 0 只提供退出和下一步。步骤回退 SHALL 不离开当前向导。

#### Scenario: 素材检查退出

- **WHEN** 用户在素材检查阶段点击返回
- **THEN** 页面 SHALL 返回带双摄来源上下文的任务管理页
- **AND** SHALL NOT 导航到 `/capture`

#### Scenario: A 机位标定返回

- **WHEN** 用户在 A 机位标定阶段点击上一步
- **THEN** 页面 SHALL 回到素材检查阶段
- **AND** SHALL 保留已加载的双摄素材状态

#### Scenario: B 机位标定返回

- **WHEN** 用户在 B 机位标定阶段点击上一步
- **THEN** 页面 SHALL 回到 A 机位标定阶段
- **AND** SHALL 保留已保存的 A 机位标定结果

#### Scenario: 确认阶段返回

- **WHEN** 用户在确认阶段点击上一步
- **THEN** 页面 SHALL 回到 B 机位标定阶段
- **AND** SHALL 保留 A/B 标定 id 及朝向选择

### Requirement: 双摄向导允许修正已完成的标定

用户返回 A/B 标定阶段时，向导 SHALL 恢复该机位已保存的点位草稿和 calibration id；用户重新完成标定后 SHALL 用新的结果替换旧结果。向导 SHALL 不允许跳过未完成的前置标定。

#### Scenario: 返回后恢复 A 机位草稿

- **WHEN** 用户完成 A 机位标定、继续到后续阶段、再返回 A 机位
- **THEN** 标定界面 SHALL 恢复已保存的点位草稿
- **AND** 用户 SHALL 可以重新点选四角并提交新的标定结果

#### Scenario: 提交前缺少标定

- **WHEN** A 或 B 机位尚未完成标定
- **THEN** 开始双摄协同分析按钮 SHALL 保持禁用
- **AND** 页面 SHALL 保留在当前向导流程中

### Requirement: 双摄向导关键按钮具有完整交互样式

双摄向导和其标定组件中的退出、上一步、下一步和开始分析按钮 SHALL 使用应用已定义的按钮样式，包含可见边框或填充、hover、focus 和 disabled 状态，不得依赖未定义的 `primary-button` 或 `sport-button` class。

#### Scenario: 下一步按钮可识别

- **WHEN** 用户查看素材检查阶段
- **THEN** 下一步按钮 SHALL 具有与应用一致的可见按钮外观
- **AND** disabled 时 SHALL 明确显示不可用状态

#### Scenario: 提交按钮状态

- **WHEN** 双摄任务正在提交
- **THEN** 开始分析按钮 SHALL 显示提交中状态并禁用重复点击
- **AND** 返回和上一步按钮 SHALL 遵循当前页面定义的退出策略

