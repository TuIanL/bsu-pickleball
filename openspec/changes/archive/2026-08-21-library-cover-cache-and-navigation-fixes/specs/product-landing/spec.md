## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: 上传工作流返回比赛库

`/upload` 上传分析工作流页面 SHALL 提供返回比赛库的出口，便于用户不想继续上传时回到比赛库。

#### Scenario: 上传页返回比赛库
- **WHEN** 用户从比赛库点击「上传视频」进入 `/upload`，随后想返回
- **THEN** 页面顶部 SHALL 提供「返回比赛库」入口，点击后 `onNavigate("/library")`