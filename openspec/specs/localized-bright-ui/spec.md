# localized-bright-ui Specification

## Purpose
Defines the Chinese-first, bright visual presentation layer for the pickleball product demo across the existing overview, analysis, report, training, and hardware pages.
## Requirements
### Requirement: Chinese-first visible interface
The system SHALL present the current web demo's visible user-facing prose, labels, navigation, buttons, table headers, filters, chart legends, tooltips, report titles, overlay labels, and status text in natural Chinese.

#### Scenario: User views top-level product pages
- **WHEN** the user opens the overview, visual analysis, training, or hardware page
- **THEN** the page chrome, headings, body copy, navigation labels, CTAs, cards, and footer actions are written in Chinese without mixed English marketing or workflow labels

#### Scenario: User views report and analysis modules
- **WHEN** the user opens any supported report detail page or visual analysis module
- **THEN** report titles, metric labels, insight text, shot filters, table headers, table values, timeline labels, chart legends, video overlay labels, and action affordances are written in Chinese

#### Scenario: Technical identifiers remain visible only when appropriate
- **WHEN** the UI displays technical acronyms, units, report IDs, dates, player markers, or hardware terminology such as TENG, IMU, `km/h`, or `m/s`
- **THEN** the system MAY keep those identifiers unchanged when they are technical labels rather than English prose

### Requirement: Bright primary visual theme
系统 SHALL 使用分层底色的亮色运动分析主题作为应用主导视觉，而非黑色主界面；平台颜色 SHALL 引用全局设计 Token（`--capture-*`），主品牌绿收敛为深绿 `#23985B`。

#### Scenario: User opens the app shell
- **WHEN** 应用渲染 header、body 背景、主卡片、导航和 footer
- **THEN** 主导表面 SHALL 为 canvas（`#F1F5F3`）→ surface-soft（`#F7FAF8`）→ surface（`#FFFFFF`）三层底色层级，配深色可读文字与克制阴影，而非黑色背景配白字
- **AND** 颜色 SHALL 来自全局 Token，不散落硬编码 hex

#### Scenario: User views analysis cards and controls
- **WHEN** 卡片、按钮、筛选器、表格、图表和报告面板可见
- **THEN** 默认态 SHALL 使用分层亮色表面、可读深色文字、统一边框（`#D9E3DD`/`#C7D5CD`），并保留精致的 hover 与 active 态

#### Scenario: Accent colors are preserved
- **WHEN** 界面传达成功、积极表现、动作强调、训练上下文、风险或错误
- **THEN** 系统 SHALL 保留绿/蓝/橙/红等强调色关系并适配亮色主题；主品牌绿 SHALL 为深绿 `#23985B`（白字按钮用 `--capture-brand-strong` `#197947`，hover 用 `--capture-brand-primary-hover` `#14683D`），不再使用荧光绿 `#00ff41`

#### Scenario: Report page converges to the unified green family
- **WHEN** 用户打开新版或旧版报告页
- **THEN** 报告页主色 SHALL 收敛到深绿家系，且 6 维度专属色语义保留
- **AND** 热力三段渐变（黄→绿→粉）的绿 SHALL 使用独立可视化绿 `#3AAF6B`，不与品牌装饰色绑定

#### Scenario: Accent and lime stay as accents
- **WHEN** 界面使用 Cyan 或 Lime 强调
- **THEN** Cyan（`#72B8C4`）SHALL 仅用于 AI/技术提示与辅助 icon，不做 Primary CTA；Lime（`#B8DE64`）SHALL 仅作数据高亮/微点缀，占比 < 5%，不做大面积背景、正文或主按钮

### Requirement: Presentation-ready responsive polish
The system SHALL keep localized Chinese text and the brighter theme stable across desktop and mobile presentation viewports.

#### Scenario: User views desktop layout
- **WHEN** the app is viewed on a desktop viewport
- **THEN** Chinese text fits within buttons, navigation, cards, charts, and table columns without incoherent overlap or clipped labels

#### Scenario: User views mobile layout
- **WHEN** the app is viewed on a narrow viewport
- **THEN** navigation chips, CTAs, localized headings, analysis cards, and data tables remain readable without horizontal page scrolling caused by translated text

#### Scenario: User reviews visual-analysis modules
- **WHEN** simulated video, court, timeline, or tooltip overlays require high contrast
- **THEN** the system MAY use localized darker overlay panels inside those modules while the app's overall primary theme remains bright

