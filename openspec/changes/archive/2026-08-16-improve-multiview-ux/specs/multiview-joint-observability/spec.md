## ADDED Requirements

### Requirement: Debug Replay 自动加载与按需卸载

双摄协同详情页的 Debug Replay 面板在 canonical debug MP4 可用（section `availability=available` 且 `video_available=true`）时 SHALL 自动加载并渲染视频，无需用户手动点击；同时 SHALL 提供"卸载/重新加载"控制，并在面板内说明大体积回放文件按需加载的设计权衡（避免每次打开详情页无条件下载大文件）。资源不可用时 SHALL 保持现有不可用提示。

#### Scenario: 资源可用时自动加载

- **WHEN** Debug section 标记 `available` 且 `video_available=true`
- **THEN** 面板 SHALL 直接渲染视频播放器，不再要求点击"加载 canonical MP4"
- **AND** 面板 SHALL 展示一段说明文案解释大体积回放按需加载的带宽权衡

#### Scenario: 可卸载与重新加载

- **WHEN** 视频已自动加载
- **THEN** 面板 SHALL 提供"卸载"控制
- **AND** 卸载后 SHALL 提供"重新加载"控制恢复播放器

#### Scenario: 资源不可用保持提示

- **WHEN** Debug section 为 `unavailable` 或 `video_available=false`
- **THEN** 面板 SHALL 保持既有不可用提示（如"未开启详细诊断回放"或"canonical debug MP4 尚未生成"）
- **AND** MUST NOT 渲染空视频播放器

## MODIFIED Requirements

### Requirement: 双摄协同分析页 per-player 显示诊断入口

双摄协同分析页 SHALL 提供 per-player 显示诊断展开面板（默认折叠），用户可对单个球员在单个时间点查询显示漏斗证据链；页面 MUST 通过显示诊断 API 获取数据，MUST NOT 直接加载 raw trace。MVP SHALL 仅支持单球员单时刻窗口查询，不提供整场拉取、GT A/B 或交互式时间线。面板内窗口返回的每个 tick 诊断行 SHALL 默认折叠为标题行（视角 · tick · 时间戳 · 帧状态徽标），点击标题 SHALL 展开该行的完整漏斗字段；窗口内多行 MUST NOT 全部默认展开导致页面无限向下延伸。

#### Scenario: 查看单球员显示诊断

- **WHEN** 用户在双摄协同分析页展开某球员的显示诊断
- **THEN** 页面 SHALL 显示该球员在参考视角与辅助视角的逐 stage 漏斗（候选 / 投影 / formal observation / association / guidance / overlay）
- **AND** 面板默认折叠，展开后按时间窗口请求

#### Scenario: 诊断行默认折叠

- **WHEN** 查询窗口返回多个 tick 的诊断行
- **THEN** 每行 SHALL 默认只展示标题信息（视角 · tick · 时间戳 · 帧状态）
- **AND** 点击某行标题 SHALL 展开该行的完整漏斗字段

#### Scenario: 诊断行展开互不影响

- **WHEN** 用户展开窗口中的某一行诊断
- **THEN** 其他行的折叠状态 SHALL 保持独立
- **AND** 页面高度 SHALL 受控，不因行数增长无限延伸

#### Scenario: 诊断不可用时页面语义

- **WHEN** 该 job 无显示漏斗产物或 `debugTraceEnabled=false`
- **THEN** 页面 SHALL 显示结构化不可用原因
- **AND** 其他区域（Sync / Fusion / Recovery / Refinement）SHALL 不受影响
