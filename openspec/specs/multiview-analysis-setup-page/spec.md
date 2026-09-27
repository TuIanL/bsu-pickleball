# multiview-analysis-setup-page Specification

## Purpose

定义双摄分析创建向导（MultiViewAnalysisSetupPage）的三阶段流程：球场标定、球网标定、名册与确认，配常驻素材与同步状态条；涵盖双摄主 CTA、标定之前的 CourtOrientation 产品化确认、两路同页标定、一致的业务退出与步骤回退、允许修正已完成的标定，并清理 cameraAngle 的错误映射。
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

### Requirement: CourtOrientation 产品化确认

CourtOrientation 对用户 MUST NOT 暴露 `identity / rotate_180 / mirror_x / mirror_y` 等算法枚举。**MVP 由用户人工确认**每个机位位于哪一端：「A 机位位于球场 A 端底线 / 球场 B 端底线」。后端据用户选择 + `CaptureTrack + Calibration` 生成 `CourtOrientation`。摄像头安装角色自动推断涉及新规则，SHALL NOT 在本 Change 实现。

朝向确认 SHALL 发生在球场与球网标定之前，因为它决定球网左右端的 canonical 语义。用户改变朝向时，系统 SHALL 清空两路已完成的球网点位草稿并提示原因，SHALL 保留已完成的球场标定。名册与确认阶段 SHALL 只读回显当前朝向并提供返回修改的入口，SHALL NOT 重复提供朝向选择控件。

#### Scenario: 人工确认端位置

- **WHEN** 需要确认机位朝向
- **THEN** 界面 SHALL 只呈现「A 机位位于：球场 A 端底线 / 球场 B 端底线」这类产品语义选项
- **AND** SHALL NOT 出现 `identity / rotate_180` 等算法概念

#### Scenario: 朝向在标定之前确认

- **WHEN** 用户进入球场标定阶段
- **THEN** 朝向选择 SHALL 先于任一标定器呈现
- **AND** 球网标定画布的左右端标签顺序 SHALL 与所选朝向一致

#### Scenario: 改变朝向清空球网点位

- **WHEN** 用户在两路球网标注完成后改变机位朝向
- **THEN** 系统 SHALL 清空两路的球网点位草稿
- **AND** SHALL 保留已完成的球场标定
- **AND** SHALL 提示需要重新标注球网

#### Scenario: 确认阶段只读回显

- **WHEN** 用户进入名册与确认阶段
- **THEN** 系统 SHALL 只读回显当前机位朝向
- **AND** SHALL 提供跳回标定阶段修改的入口
- **AND** SHALL NOT 在该阶段重复提供朝向选择控件

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

`MultiViewAnalysisSetupPage` SHALL 在三个阶段提供一致的导航层级：顶部常驻业务退出返回双摄任务管理；第一个阶段（球场标定）只提供退出与下一步；后续阶段提供上一步；最后一个阶段提供上一步与启动。步骤回退 SHALL 不离开当前向导。

#### Scenario: 球场标定阶段退出

- **WHEN** 用户在球场标定阶段点击返回
- **THEN** 页面 SHALL 返回带双摄来源上下文的任务管理页
- **AND** SHALL NOT 导航到 `/capture`

#### Scenario: 球网标定阶段返回

- **WHEN** 用户在球网标定阶段点击上一步
- **THEN** 页面 SHALL 回到球场标定阶段
- **AND** SHALL 保留两路已完成的球场标定结果

#### Scenario: 名册与确认阶段返回

- **WHEN** 用户在名册与确认阶段点击上一步
- **THEN** 页面 SHALL 回到球网标定阶段
- **AND** SHALL 保留两路球场标定、两路球网点位与朝向选择

### Requirement: 双摄向导允许修正已完成的标定

用户返回球场或球网标定阶段时，向导 SHALL 恢复**两路**已保存的点位草稿与 calibration id，且两路的恢复与编辑 SHALL 互不影响。用户重新完成某一路标定后 SHALL 用新的结果替换该路旧结果，SHALL NOT 影响另一路。向导 SHALL 不允许跳过未完成的前置标定。

#### Scenario: 返回后恢复两路球场草稿

- **WHEN** 用户完成两路球场标定、继续到后续阶段、再返回球场标定
- **THEN** 两路标定界面 SHALL 各自恢复已保存的四角草稿
- **AND** 用户 SHALL 可以只重标其中一路并保留另一路原结果

#### Scenario: 返回后恢复两路球网点位

- **WHEN** 用户完成两路球网标注、继续到名册与确认、再返回球网标定
- **THEN** 两路标注界面 SHALL 各自恢复自己的三个控制点与两个 hold-out 点
- **AND** 共享的高度 profile SHALL 恢复为上次确认的取值

#### Scenario: 提交前缺少标定

- **WHEN** 任一路的球场标定或球网标注尚未完成
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

### Requirement: MultiViewAnalysisSetupPage 三阶段与常驻素材状态条

系统 MUST 将 `MultiViewAnalysisSetupPage` 收敛为三个阶段：**球场标定 → 球网标定 → 名册与确认**。「素材与同步前置检查」SHALL NOT 再占用独立步骤，而 SHALL 以页面顶部常驻状态条呈现 A/B 机位视频就绪状态、录制状态与录制级同步锚点状态。

状态条 SHALL 在任何阶段可见，并 SHALL 在硬前置不满足时就地展示原因与对应操作（含进入同步锚点工作台的入口），不静默。启动双摄协同分析 SHALL 仍要求始终满足同一套前置条件，不因阶段合并而放松。

#### Scenario: 素材检查不再是独立步骤

- **WHEN** 用户打开双摄分析设置页
- **THEN** 顶部 SHALL 显示 A/B 机位视频就绪、录制状态与同步锚点状态的常驻状态条
- **AND** 步骤指示器 SHALL 只有「球场标定」「球网标定」「名册与确认」三项
- **AND** SHALL NOT 存在独立的「素材检查」步骤页

#### Scenario: 同步锚点未确认时的就地阻断

- **WHEN** 同步锚点状态为 `required`、`draft` 或 `invalidated` 且策略返回 `analysis_allowed=false`
- **THEN** 状态条 SHALL 就地显示阻断原因与「开始标注 / 继续标注 / 重新标注」操作
- **AND** 进入下一步与启动分析的按钮 SHALL 禁用
- **AND** 用户 SHALL NOT 需要先进入某个「素材检查」步骤才能看到该阻断

#### Scenario: 分析配置归入确认阶段

- **WHEN** 用户进入「名册与确认」阶段
- **THEN** 该阶段 SHALL 提供仅分析指定窗口、Debug Replay 与分析流程选择
- **AND** 这些配置项 SHALL NOT 出现在标定阶段

#### Scenario: 工作台确认后恢复向导

- **WHEN** 用户从状态条进入同步锚点工作台并确认成功
- **THEN** 系统 SHALL 返回同一 CaptureTake 的双摄分析设置页并停留在离开时的阶段
- **AND** SHALL 重新读取状态并在状态条显示确认摘要

### Requirement: 双摄标定阶段两路同页

「球场标定」与「球网标定」阶段 SHALL 各自在同一页内同时承载 A、B 两路标定，**宽屏并排、窄屏纵向堆叠**；布局切换 SHALL NOT 改变步骤数、SHALL NOT 触发翻页。

两路 SHALL 各自独立提交并独立保留草稿；只有两路都完成，本阶段 SHALL 才放行进入下一步。任一路未完成时下一步按钮 SHALL 禁用并指明缺少哪一路。

#### Scenario: 宽屏并排

- **WHEN** 视口达到并排断点
- **THEN** A、B 两路标定器 SHALL 左右并排展示，各占约一半可用宽度
- **AND** 用户 SHALL 能在同一屏内同时看到两路的标定进度

#### Scenario: 窄屏纵向堆叠

- **WHEN** 视口低于并排断点
- **THEN** A、B 两路标定器 SHALL 纵向排列，各自占满内容区宽度

#### Scenario: 单路完成不放行

- **WHEN** 只有 A 路（或只有 B 路）完成球场标定
- **THEN** 进入球网标定阶段的按钮 SHALL 保持禁用
- **AND** 页面 SHALL 指明尚未完成的一路

#### Scenario: 两路互不干扰

- **WHEN** 用户在其中一路拖动标定点
- **THEN** 另一路已保存的草稿 SHALL 保持不变
- **AND** SHALL NOT 触发另一路标定器的草稿重置

#### Scenario: 提交前两路都必须完成

- **WHEN** 用户点击「开始双摄协同分析」
- **THEN** 系统 SHALL 要求两路球场标定与两路球网标注均已提交
- **AND** SHALL 只创建 1 个 multiview Parent 任务
- **AND** 成功后 SHALL 导航到 `/analysis/<parentId>`，SHALL NOT 导航到 child 任务

