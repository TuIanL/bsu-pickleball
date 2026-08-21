# product-landing Specification

## Purpose
TBD - created by syncing change redesign-product-entry-and-capture-console.

## Requirements
### Requirement: 双工作流入口首页

系统 SHALL 提供一个产品首页，中央放置主工作流入口按钮，下方放置能力介绍卡片（纯展示、不跳转）。

#### Scenario: 用户首次进入系统
- **WHEN** 用户加载应用根路径 `/`
- **THEN** 系统展示 Hero 区（产品标语 + 描述文字）
- **AND** 页面中央展示「进入开始使用」主导入口
- **AND** 页面下方展示三个能力介绍卡片（视频上传分析 / 球场现场采集 / 训练结果沉淀），卡片为纯展示无跳转

#### Scenario: 用户点击进入开始使用
- **WHEN** 用户在首页点击「进入开始使用」按钮
- **THEN** 系统导航到 `/library`（比赛库 / 视频库）
- **AND** SHALL NOT 导航到 `/capture`（现场采集）

### Requirement: 上传工作流返回比赛库

`/upload` 上传分析工作流页面 SHALL 提供返回比赛库的出口，便于用户不想继续上传时回到比赛库。

#### Scenario: 上传页返回比赛库
- **WHEN** 用户从比赛库点击「上传视频」进入 `/upload`，随后想返回
- **THEN** 页面顶部 SHALL 提供「返回比赛库」入口，点击后 `onNavigate("/library")`

### Requirement: 首页顶部无导航 Tab

系统 SHALL 在首页不展示任何页面跳转标签，只保留 Logo + 产品名（左）和辅助入口（右）。

#### Scenario: 用户查看首页导航
- **WHEN** 用户在首页 `/`
- **THEN** 顶部导航栏左侧显示「拍动视析 Logo + 产品名」
- **AND** 顶部导航栏右侧显示「任务历史」和「帮助」等辅助入口
- **AND** 不显示「总览 / 视频分析 / 球场采集 / 训练」等一级 tab

#### Scenario: 用户从首页导航到任务历史
- **WHEN** 用户点击导航栏右上角「任务历史」
- **THEN** 系统导航到 `/analysis/tasks` 任务历史页面

### Requirement: 首页能力卡片纯展示

系统 SHALL 在首页下方展示三个能力介绍卡片，仅作产品介绍不提供跳转。

#### Scenario: 用户查看能力卡片
- **WHEN** 用户滚动到首页卡片区
- **THEN** 系统展示「视频上传分析」「球场现场采集」「训练结果沉淀」三张卡片
- **AND** 每张卡片包含标题、描述文字和图标
- **AND** 卡片不包含跳转按钮或链接
