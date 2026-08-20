# sync-anchor-workflow delta

## ADDED Requirements

### Requirement: 工作台 timing 缺失时的恢复路径

系统 SHALL 在同步锚点工作台因两路 registered video 缺少有效 source PTS（或加载失败）而无法打开时，提供"尝试修复"入口：调用 `POST /api/videos/{video_id}/timing/materialize` 为缺失侧补写 sidecar，补写成功后自动重新加载工作台。该入口 SHALL 与既有"返回双摄分析"出口并存，不得阻塞用户返回原流程。

#### Scenario: 工作台因 source_pts_missing 无法打开
- **WHEN** 工作台加载失败且失败原因包含 registered video 缺失 source PTS sidecar
- **THEN** 错误卡 SHALL 展示失败原因
- **AND** SHALL 提供"尝试修复"按钮与"返回双摄分析"按钮

#### Scenario: 尝试修复成功
- **WHEN** 用户点击"尝试修复"且 materialize 补写成功
- **THEN** 页面 SHALL 自动重新加载工作台
- **AND** 两路 timing 可用后 SHALL 正常进入锚点标注

#### Scenario: 尝试修复失败
- **WHEN** 用户点击"尝试修复"且 materialize 返回结构化错误（媒体不可用、PTS 无效等）
- **THEN** 错误卡 SHALL 展示具体失败原因
- **AND** 保留"返回双摄分析"出口
- **AND** 允许用户再次尝试修复
