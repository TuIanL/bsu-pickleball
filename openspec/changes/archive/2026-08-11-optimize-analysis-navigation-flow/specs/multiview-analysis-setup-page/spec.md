## ADDED Requirements

### Requirement: 双摄向导提供一致的业务退出和步骤回退

`MultiViewAnalysisSetupPage` SHALL 在四个阶段提供一致的导航层级：顶部业务退出返回双摄任务管理，步骤 1 和步骤 2 提供上一步，确认阶段提供上一步，步骤 0 只提供退出和下一步。步骤回退 SHALL 不离开当前向导。

#### Scenario: 素材检查退出

- **WHEN** 用户在素材检查阶段点击返回
- **THEN** 页面 SHALL 返回带双摄来源上下文的任务管理页
- **AND** SHALL NOT 导航到 `/capture`

#### Scenario: A 机位标定返回

- **WHEN** 用户在 A 机位标定阶段点击上一步
- **THEN** 页面 SHALL 回到素材检查阶段
- **AND** SHALL 保留已加载的双摄素材状态

#### Scenario: B 机位标定返回

- **WHEN** 用户在 B 机位标定阶段点击上一步
- **THEN** 页面 SHALL 回到 A 机位标定阶段
- **AND** SHALL 保留已保存的 A 机位标定结果

#### Scenario: 确认阶段返回

- **WHEN** 用户在确认阶段点击上一步
- **THEN** 页面 SHALL 回到 B 机位标定阶段
- **AND** SHALL 保留 A/B 标定 id 及朝向选择

### Requirement: 双摄向导允许修正已完成的标定

用户返回 A/B 标定阶段时，向导 SHALL 恢复该机位已保存的点位草稿和 calibration id；用户重新完成标定后 SHALL 用新的结果替换旧结果。向导 SHALL 不允许跳过未完成的前置标定。

#### Scenario: 返回后恢复 A 机位草稿

- **WHEN** 用户完成 A 机位标定、继续到后续阶段、再返回 A 机位
- **THEN** 标定界面 SHALL 恢复已保存的点位草稿
- **AND** 用户 SHALL 可以重新点选四角并提交新的标定结果

#### Scenario: 提交前缺少标定

- **WHEN** A 或 B 机位尚未完成标定
- **THEN** 开始双摄协同分析按钮 SHALL 保持禁用
- **AND** 页面 SHALL 保留在当前向导流程中

### Requirement: 双摄向导关键按钮具有完整交互样式

双摄向导和其标定组件中的退出、上一步、下一步和开始分析按钮 SHALL 使用应用已定义的按钮样式，包含可见边框或填充、hover、focus 和 disabled 状态，不得依赖未定义的 `primary-button` 或 `sport-button` class。

#### Scenario: 下一步按钮可识别

- **WHEN** 用户查看素材检查阶段
- **THEN** 下一步按钮 SHALL 具有与应用一致的可见按钮外观
- **AND** disabled 时 SHALL 明确显示不可用状态

#### Scenario: 提交按钮状态

- **WHEN** 双摄任务正在提交
- **THEN** 开始分析按钮 SHALL 显示提交中状态并禁用重复点击
- **AND** 返回和上一步按钮 SHALL 遵循当前页面定义的退出策略

