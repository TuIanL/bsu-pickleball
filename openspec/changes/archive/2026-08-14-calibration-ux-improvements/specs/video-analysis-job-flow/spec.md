## ADDED Requirements

### Requirement: 阶段 stepper 隐藏可见滚动条

任务状态页的水平阶段胶囊 stepper SHALL 保持横向可滚动与自动聚焦当前阶段的能力，但 SHALL NOT 显示可见的横向滚动条。

#### Scenario: 阶段 stepper 不显示滚动条

- **WHEN** 用户查看含多个分析阶段的非终态任务
- **THEN** 阶段以单行横向可滚动的胶囊呈现
- **AND** 不显示可见的横向滚动条

#### Scenario: 当前阶段仍自动聚焦

- **WHEN** 当前运行阶段不在可视区内
- **THEN** 系统仍自动将该阶段滚动到可视区
- **AND** 用户仍可通过触摸、触控板或拖动横向滑动浏览各阶段
