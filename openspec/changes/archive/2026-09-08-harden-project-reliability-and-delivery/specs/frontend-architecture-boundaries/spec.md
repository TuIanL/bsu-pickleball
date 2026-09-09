## ADDED Requirements

### Requirement: 重型页面按需加载

系统 SHALL 将分析、采集、复核、报告和 3D 工作台按消费边界动态加载，保留现有路由、查询参数、历史和状态降级契约；共享模块不得使未访问工作台重新进入首屏静态依赖。

#### Scenario: 冷启动落地页
- **WHEN** 用户首次打开 landing
- **THEN** 应用 SHALL 不请求未访问工作台和 3D 模块，初始 JS gzip 总量 SHALL 满足交付预算

#### Scenario: 刷新工作台深链
- **WHEN** 用户刷新含 job/take/return/search 的工作台 URL
- **THEN** 应用 SHALL 显示加载状态并恢复正确页面及参数，不改变导航历史语义

#### Scenario: Chunk 加载失败
- **WHEN** 页面 chunk 下载失败
- **THEN** 应用 SHALL 提供明确错误和重试或刷新操作，不出现永久空白页，URL 上下文 SHALL 保留
