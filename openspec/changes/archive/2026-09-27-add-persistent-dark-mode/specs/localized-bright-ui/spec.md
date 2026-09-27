## MODIFIED Requirements

### Requirement: Bright primary visual theme
系统 SHALL 将分层底色的亮色运动分析主题作为首次访问与显式选择亮色时的视觉；平台界面语义色 SHALL 引用全局设计 Token（`--capture-*`），主品牌绿为深绿 `#23985B`。迁移到语义色后，亮色模式的现有视觉结果 SHALL 保持一致；用户可另行选择暗色模式，其要求由 `persistent-ui-theme` 规定。

#### Scenario: User opens the app shell
- **WHEN** 应用以亮色模式渲染 header、body 背景、主卡片、导航和 footer
- **THEN** 主导表面 SHALL 为 canvas（`#F1F5F3`）→ surface-soft（`#F7FAF8`）→ surface（`#FFFFFF`）三层底色层级，配深色可读文字与克制阴影
- **AND** 颜色 SHALL 来自全局 Token，不散落硬编码 hex

#### Scenario: User views analysis cards and controls
- **WHEN** 亮色模式中的卡片、按钮、筛选器、表格、图表和报告面板可见
- **THEN** 默认态 SHALL 使用分层亮色表面、可读深色文字、统一边框（`#D9E3DD`/`#C7D5CD`），并保留精致的 hover 与 active 态

#### Scenario: Accent colors are preserved
- **WHEN** 亮色界面传达成功、积极表现、动作强调、训练上下文、风险或错误
- **THEN** 系统 SHALL 保留绿/蓝/橙/红等强调色关系；主品牌绿 SHALL 为深绿 `#23985B`（白字按钮用 `--capture-brand-strong` `#197947`，hover 用 `--capture-brand-primary-hover` `#14683D`），不使用荧光绿 `#00ff41`

#### Scenario: Report page converges to the unified green family
- **WHEN** 用户以亮色模式打开新版或旧版报告页
- **THEN** 报告页主色 SHALL 收敛到深绿家系，且 6 维度专属色语义保留
- **AND** 热力三段渐变（黄→绿→粉）的绿 SHALL 使用独立可视化绿 `#3AAF6B`，不与品牌装饰色绑定

#### Scenario: Accent and lime stay as accents
- **WHEN** 亮色界面使用 Cyan 或 Lime 强调
- **THEN** Cyan（`#72B8C4`）SHALL 仅用于 AI/技术提示与辅助 icon，不做 Primary CTA；Lime（`#B8DE64`）SHALL 仅作数据高亮/微点缀，占比 < 5%，不做大面积背景、正文或主按钮

#### Scenario: Light appearance remains stable after token migration
- **WHEN** 用户选择亮色模式并打开现有首页、工作区和报告页面
- **THEN** 原有界面元素的背景、文字、边框、阴影和交互颜色 SHALL 与迁移前保持一致，新增主题按钮除外
