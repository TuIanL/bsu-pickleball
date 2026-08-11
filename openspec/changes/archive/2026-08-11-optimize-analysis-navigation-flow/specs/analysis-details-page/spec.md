## ADDED Requirements

### Requirement: 分析任务详情页提供来源一致的顶部返回

分析任务状态详情页 SHALL 在页面左上方提供统一的返回任务管理入口。返回地址 SHALL 优先使用显式来源上下文；对于没有显式上下文的 multiview Parent SHALL 返回双摄录制 tab，其他未知来源 SHALL 回退到上传视频任务 tab。

#### Scenario: 双摄 Parent 详情返回

- **WHEN** 用户查看 multiview Parent 的分析详情
- **THEN** 页面左上方 SHALL 显示返回任务管理按钮
- **AND** 点击后 SHALL 返回双摄录制任务 tab

#### Scenario: 普通任务详情返回

- **WHEN** 用户查看没有双摄来源的普通分析任务详情
- **THEN** 页面左上方 SHALL 显示同样结构的返回按钮
- **AND** 点击后 SHALL 返回普通任务管理上下文或上传任务 tab

#### Scenario: 详情页加载失败

- **WHEN** 任务详情加载失败或任务不存在
- **THEN** 错误状态 SHALL 仍提供稳定的返回任务管理入口
- **AND** 返回目标 SHALL 遵循相同的来源回退规则

