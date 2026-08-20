## ADDED Requirements

### Requirement: 一级导航 Library-first
系统 SHALL 以「比赛库 / 现场采集 / 设备与设置」作为一级主导航；「分析任务」「报告中心」SHALL 退出一级导航，作为比赛库的生命周期与比赛详情的视图存在。

#### Scenario: 主导航展示
- **WHEN** 用户在标准模式查看主导航
- **THEN** 主导航 SHALL 只包含比赛库（→`/library`）、现场采集（→`/capture`）、设备与设置入口
- **AND** 主导航 SHALL NOT 将「分析任务」「报告中心」作为一级项暴露

#### Scenario: 工程层入口
- **WHEN** 需要查看工程任务（Parent/child、Pipeline Stage、错误码）
- **THEN** 用户 SHALL 从「设备与设置 → 工程模式/开发者模式 → 分析任务」进入 Engineering Task Console
- **AND** 普通用户默认不可达工程入口

### Requirement: 训练页不占一级导航
系统 SHALL 保留训练页路由（`/training`）但不作为一级导航项，且不从首页主入口直接引导。

#### Scenario: 训练页不再导航
- **WHEN** 用户查看任意页面主导航
- **THEN** 主导航 SHALL 不包含训练入口

#### Scenario: 训练页直接访问
- **WHEN** 用户直接访问 `/training`
- **THEN** 系统 SHALL 正常渲染训练页内容

### Requirement: 首页工作流入口调整
首页 SHALL 提供面向 Library-first 的主 workflow 入口：进入比赛库与开始现场采集，而非仅一条限制性的单一入口。

#### Scenario: 首页进入比赛库
- **WHEN** 用户加载根路径 `/`
- **THEN** 首页 SHALL 提供进入比赛库的主入口
- **AND** 首页 SHALL 提供开始现场采集的主入口

## REMOVED Requirements

### Requirement: Top navigation for core workflows
**Reason**: 被 Library-first 边导模型取代；极简顶导不再作为 canonical 导航方案
**Migration**: 采用 app-sidebar 重新定义的 Library-first 一级导航（比赛库/现场采集/设备与设置）