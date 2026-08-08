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

系统 MUST 提供 `MultiViewAnalysisSetupPage`，按「素材检查 → A 机位标定 → B 机位标定 → 确认」四阶段推进；复用共享 `CourtCornerCalibrator`，一次完成两个 calibration（`cam_1 → calibration_1`、`cam_2 → calibration_2`）后才可启动。

#### Scenario: 素材检查

- **WHEN** 页面加载
- **THEN** 展示 A/B 机位视频就绪状态、双摄同步状态、多视角融合支持状态
- **AND** 任一前置不满足时展示原因与操作（重新检查同步 / 改用单摄），不静默

#### Scenario: 双标定

- **WHEN** 用户进入标定阶段
- **THEN** A 与 B 机位各需完成一次四角标定
- **AND** 两个 calibration 都完成前，启动按钮 SHALL 禁用

#### Scenario: 确认启动

- **WHEN** 用户点击「开始双摄协同分析」
- **THEN** 系统 SHALL 只创建 1 个 multiview Parent 任务
- **AND** 成功后 SHALL 导航到 `/analysis/<parentId>`
- **AND** 用户 SHALL NOT 被导航到 child 任务

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

