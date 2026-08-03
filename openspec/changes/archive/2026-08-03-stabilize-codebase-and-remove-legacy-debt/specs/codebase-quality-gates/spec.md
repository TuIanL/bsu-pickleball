## ADDED Requirements

### Requirement: 前端质量命令可通过

系统 SHALL 保持前端 TypeScript 构建、测试和 Lint 命令可重复执行并通过。

#### Scenario: 前端构建通过

- **WHEN** 在仓库根目录执行 `npm run build`
- **THEN** TypeScript 编译和 Vite production build SHALL 成功退出
- **AND** 不得通过关闭 `strict` 或隐藏类型错误来达成通过

#### Scenario: 前端测试通过

- **WHEN** 执行 `npm test`
- **THEN** 所有现有前端测试 SHALL 通过
- **AND** 路由、录制分析桥接、artifact 状态和降级行为 SHALL 有对应回归测试

#### Scenario: 前端 Lint 通过

- **WHEN** 执行 `npm run lint`
- **THEN** ESLint SHALL 无 error 退出
- **AND** 任何保留 warning SHALL 有局部规则说明，不得通过全局关闭 React hooks 或 TypeScript 规则隐藏问题

### Requirement: 后端测试与本地运行数据隔离

后端测试 SHALL 使用测试专用的临时数据库、存储目录和模型目录，不得依赖仓库默认 `backend/data` 或真实模型资产。

#### Scenario: 录制生命周期测试在空数据库运行

- **WHEN** 单独或全量执行录制生命周期测试
- **THEN** 测试 SHALL 不受默认 SQLite 中历史 `CaptureTake` 记录影响
- **AND** fake session factory 对活跃录制查询 SHALL 返回显式可控的结果

#### Scenario: 模型自动发现测试显式控制资产

- **WHEN** 测试验证模型未配置或模型自动发现
- **THEN** 测试 SHALL 通过临时模型目录显式创建或省略模型文件
- **AND** 结果 SHALL 不随仓库 `models/` 目录当前内容变化

#### Scenario: 测试运行不产生工作区污染

- **WHEN** 执行后端测试
- **THEN** 测试产物 SHALL 写入 pytest 临时目录或明确的测试输出目录
- **AND** 不得改变默认运行数据库中的业务记录

### Requirement: 后端质量命令可通过

系统 SHALL 将后端 pytest 全量通过作为实现完成的必要条件。

#### Scenario: 后端测试通过

- **WHEN** 在 `backend` 目录执行 `python -m pytest -q`
- **THEN** 所有测试 SHALL 通过
- **AND** 失败必须能定位到具体 API、服务或视觉模块，不得由共享历史状态造成随机失败
