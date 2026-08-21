# global-design-token-system

## ADDED Requirements

### Requirement: 全局设计 Token 层
系统 SHALL 在 `:root` 定义一套全局 CSS 设计 Token，作为当前主产品壳层（Library / Workspace / Capture / Sidebar / PB Vision Report）的唯一颜色来源；Token 命名 SHALL 沿用 `--capture-*` 前缀，且每个 Token SHALL 只保留一份权威定义（原位升级，不重复定义）。

#### Scenario: Token 定义存在且可全局解析
- **WHEN** 任意页面渲染并读取 `:root` 变量
- **THEN** 系统 SHALL 提供底色层级 Token（canvas `--capture-surface-page: #F1F5F3`、soft `--capture-surface-soft: #F7FAF8`、card `--capture-surface-card: #FFFFFF`）、边框 Token（default `#D9E3DD`、strong `#C7D5CD`）、品牌绿 Token（primary `#23985B`、strong `#197947`、hover `#14683D`、soft `#DDF1E5`）、文字三级 Token（`#182B24`/`#64736C`/`#8F9D96`）、侧边栏 Token（`--capture-sidebar-bg: #FAFCFB`、`--capture-nav-active-bg: #E6F3EA`、`--capture-nav-active-text: #1B824C`）

#### Scenario: 播放器外框统一
- **WHEN** 视频播放器或工作台渲染
- **THEN** 播放器外框 SHALL 使用 `--capture-surface-video: #24302B`，而非纯黑或白纸背景

#### Scenario: 无同名重复定义
- **WHEN** 实施迁移
- **THEN** `:root` 中每个 `--capture-*` Token SHALL 只有一份权威定义，旧定义直接原位改值 + 追加缺失 Token，禁止先新增同名变量再保留旧定义

### Requirement: 状态色板统一
系统 SHALL 使用按业务语义命名的 status token 表达分析/录制生命周期状态，状态语义沿用：待处理、正在分析、分析完成、待合并、失败、技术/AI；每个状态 SHALL 同时提供前景色与 Badge 浅底色（soft）两组 Token，且前景色与浅底对比度 SHALL ≥ ~4.5:1（适配 10~12px Badge 小字号）。

#### Scenario: 状态使用统一 token
- **WHEN** 比赛库卡片或任何页面展示状态 Badge
- **THEN** 系统 SHALL 使用对应 status token（pending `#475569`、processing `#8A570E`、success `#176B3C`、merge `#9A5300`、failed `#B42318`、AI `#2F6F7B`）及其 soft 浅底（`#EEF2F6`/`#FFF3DC`/`#E5F4EA`/`#FFF0DA`/`#FDE8E7`/`#E8F4F6`），而非散落硬编码 hex

#### Scenario: 功能语义色保留原值
- **WHEN** capture 时间线或录制状态渲染
- **THEN** 时间线盘/局/分/playhead、录制红等功能语义色 SHALL 保持原值，不因全局 Token 迁移而校准

### Requirement: 报告页收敛到深绿家系
报告页 `.pb-vision-theme` 的主色 SHALL 由荧光绿 `#00ff41` 收敛到全局品牌绿 `#23985B`；`--pb-*` SHALL 保留为 compatibility aliases 引用全局 Token；6 维度色与热力三段渐变（黄→绿→粉）语义 SHALL 保留。

#### Scenario: 报告页主色迁移
- **WHEN** 用户打开新版报告页（PB Vision 布局）
- **THEN** 主按钮、选中态、进度条、关键数字 SHALL 使用 `#23985B`（或 `--capture-brand-primary`），不再出现荧光绿 `#00ff41`

#### Scenario: 维度与热力语义保留
- **WHEN** 报告页展示 6 维度技能或场地热力图
- **THEN** 6 维度专属色与浅底 SHALL 保持原值；热力三段黄→绿→粉的绿 SHALL 使用独立可视化绿 `#3AAF6B`（`--pb-heat-mid`），不与品牌装饰色绑定

#### Scenario: `--pb-*` 兼容别名保留
- **WHEN** 迁移后仍存在 `var(--pb-*)` 引用
- **THEN** 系统 SHALL 保留 `--pb-primary`/`--pb-primary-dark`/`--pb-primary-soft` 等 aliases 引用全局 Token，删除的仅为荧光绿 literal 与旧注释

#### Scenario: 新旧两版报告家族一致
- **WHEN** 用户通过「切换旧版（Legacy）」打开旧版报告
- **THEN** 旧版报告的深绿风格 SHALL 与新版收敛到同一绿色家族，不出现荧光绿

### Requirement: 库/工作台/侧边栏去硬编码
比赛库、Workspace、侧边栏及比赛库卡片的颜色 SHALL 引用全局 Token，不再使用散落硬编码 hex。

#### Scenario: 库/工作台底色层级
- **WHEN** 用户打开比赛库或素材工作台
- **THEN** 页面最外层使用 canvas 背景、Workspace 内容区/筛选栏使用 surface-soft、卡片使用 surface-card，形成三层底色层级而非纯白

#### Scenario: 侧边栏与卡片用 Token
- **WHEN** 侧边栏或比赛库卡片渲染
- **THEN** 边框、文字、状态 Badge SHALL 使用全局 Token 对应值
- **AND** 选中导航项 SHALL 采用「左侧 3px 强调条 `--capture-brand-primary`（#23985B）+ 浅绿底 `--capture-nav-active-bg`（#E6F3EA）+ 深绿字 `--capture-nav-active-text`（#1B824C）」，而非整块浅绿按钮

#### Scenario: 状态 tone 按业务语义
- **WHEN** 比赛库卡片渲染状态 Badge
- **THEN** 状态类型 SHALL 使用业务语义 `pending / processing / success / merge / failed / ai`，UI 不依赖颜色名决定配色

#### Scenario: 卡片占位克制化
- **WHEN** 比赛库卡片没有真实缩略图/封面
- **THEN** 占位区 SHALL 使用中性灰渐变（`#E7EEEB → #DCE7E2`）叠加轻球场线纹理，品牌绿 SHALL 仅保留在状态 Badge、Tab 下划线、主按钮、活跃导航与关键数字

### Requirement: 视觉层级与辅助色纪律
系统 SHALL 维持稳定的全局视觉占比与辅助色使用边界，防止色彩体系重新发散。

#### Scenario: 全局视觉占比固定
- **WHEN** 主产品壳层渲染
- **THEN** 视觉占比 SHALL 大致保持：70% 雾灰绿/云白底色、20% 深文字/中性边框、7% 青瓷主绿、2% 状态色、1% Cyan/Lime 点缀

#### Scenario: Accent 与 Lime 使用边界
- **WHEN** 使用 `--capture-accent`（#72B8C4）或 `--capture-lime`（#B8DE64）
- **THEN** accent SHALL 仅用于 AI/双摄/技术提示与辅助 icon，不得作为 Primary CTA；lime SHALL 仅作数据高亮/运动感微点缀，全屏占比 `< 5%`，不得用作大面积背景、正文文字或主按钮

#### Scenario: 主绿分级
- **WHEN** 使用品牌绿
- **THEN** `--capture-brand-primary`（#23985B）用于品牌标识/图标/Tab underline/大色块，`--capture-brand-strong`（#197947）用于白字主按钮/较小绿色文字，`--capture-brand-primary-hover`（#14683D）用于 hover/pressed

### Requirement: 清理无用颜色方案代码
系统 SHALL 删除当前主产品壳层不再使用的颜色方案定义，同时保留 `--pb-*` compatibility aliases 与 `src/styles/app.css` 兼容样式域。

#### Scenario: 死代码删除
- **WHEN** 迁移完成
- **THEN** 系统 SHALL 删除 `:root` 中 0 使用的通用色（`--surface-0..4`、`--action-green`、`--glow-green`、`--pickle-lime`、`--court-blue`、`--warning-orange`、`--error-red` 等）以及荧光绿 literal（`#00ff41 / #00cc33 / #e6ffe9`）与旧注释

#### Scenario: `--pb-*` 别名保留
- **WHEN** 清理荧光绿
- **THEN** `--pb-primary`/`--pb-primary-dark`/`--pb-primary-soft` 等 aliases SHALL 保留并引用全局 Token，不因清理而删除（否则现有 `var(--pb-*)` 引用会断裂）

#### Scenario: 老落地页风格保留
- **WHEN** 全站清理颜色代码
- **THEN** `src/styles/app.css` 及其在用的落地页/训练/硬件/旧版报告样式 SHALL 保持不变，作为兼容样式域保留，不纳入删除范围
