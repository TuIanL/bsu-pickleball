# vidat-annotation-import Specification

## Purpose

定义 Vidat 标注导入的格式校验、时间校验、差异预览、确认令牌和过期保护规则，确保导入行为可审计并且不会覆盖未经确认的历史数据。
## Requirements
### Requirement: 导入格式与时间校验
系统 MUST 在创建导入预览时校验 Vidat JSON 与标注包 manifest 的身份、视频、FPS、标签和时间边界。

#### Scenario: 文件与包匹配
- **WHEN** 用户提交属于某标注包的 Vidat annotation JSON
- **THEN** 系统 SHALL 验证 CaptureTake ID、视频 fingerprint 或视频标识、FPS 和标签 ID
- **AND** 校验通过后 SHALL 生成导入预览而不修改比赛数据

#### Scenario: 不匹配文件
- **WHEN** JSON 的视频标识、FPS 或标签映射与标注包 manifest 不兼容
- **THEN** 系统 SHALL 将预览标记为不可确认
- **AND** SHALL 返回具体的不匹配原因

### Requirement: 结构化导入差异预览
系统 SHALL 将 Vidat action 标注转换为新增、删除、移动、类型变更、回合结果变更和比分锚点变更，并展示受影响的比赛状态摘要。

#### Scenario: 回合胜者改变
- **WHEN** 导入内容把一个有效回合的胜者由 A 改为 B
- **THEN** 预览 SHALL 标记该回合结果变更
- **AND** SHALL 展示从该回合起至比赛结束的受影响比分、局/盘和最终胜者摘要

### Requirement: 确认令牌保护的导入
系统 MUST 仅在用户使用未过期且对应预览内容的确认令牌时应用 Vidat 导入；确认时 SHALL 派生一个不可变的结果包，而不是覆盖来源归档包。

#### Scenario: 确认有效预览
- **WHEN** 用户确认一个无阻塞错误的导入预览
- **THEN** 系统 SHALL 在单一事务中创建结果包、保存来源/结果包审计、规范化快照与重放结果
- **AND** 结果包 SHALL 承载本次导入内容并标记为 `provenance=derived`
- **AND** 来源标注包版本的 annotation、manifest、规范化快照和导入时间 SHALL 保持不变
- **AND** 系统 SHALL 替换当前 Vidat 投影，保留人工和算法来源的数据
- **AND** 系统 SHALL 设置 `active_vidat_package_id` 为结果包 ID，并返回来源包、结果包和新的比赛状态

#### Scenario: 预览过期或已变化
- **WHEN** 用户确认的令牌过期、已使用或与提交 JSON 不一致
- **THEN** 系统 SHALL 拒绝写入
- **AND** SHALL 要求重新生成预览

#### Scenario: 应用失败时保持原状
- **WHEN** 结果包创建、审计保存或实时投影重放任一步骤失败
- **THEN** 系统 SHALL 回滚数据库事务
- **AND** SHALL 清理本次创建的包目录
- **AND** SHALL 保持来源包和原当前 Vidat 投影不变

### Requirement: 导入结果投影唯一性
系统 SHALL 保证一个 CaptureTake 同时只有一个当前 Vidat 投影来源。

#### Scenario: 新结果替换旧 Vidat 投影
- **WHEN** 用户确认一个新的导入结果包
- **THEN** 系统 SHALL 删除或失活旧结果包产生的 Vidat 编码动作、分段和时间线投影
- **AND** SHALL 保留人工和算法来源的动作、分段和事件
- **AND** SHALL 将新结果包的投影关联到其 `result_package_id`

#### Scenario: 从历史版本重新导入
- **WHEN** 用户选择历史版本进行预览并确认导入
- **THEN** 系统 SHALL 从该历史版本派生新的结果包
- **AND** SHALL 以新的结果包作为当前 Vidat 投影
- **AND** SHALL 不修改历史版本及其原有审计记录

