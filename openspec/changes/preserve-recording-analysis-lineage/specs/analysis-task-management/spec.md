## ADDED Requirements

### Requirement: 来源不可证的历史任务保持可读

系统 SHALL 保证来源不可证明或缺失来源的历史分析任务继续可读、可追溯、可删除。

任务列表 MUST NOT 因来源字段缺失而隐藏、报错或改变既有分组。系统 MUST NOT 用推断、回填或改写的方式为历史任务补造来源。

任务的来源展示 SHALL 区分「已核实来源」「来源未知」「无来源（普通上传）」三种状态；无法确定时 MUST 显示为未知，而不是猜测为某一录制。
公共任务摘要 MUST 提供安全投影 `sourceStatus`，取值为 `verified_recording`、`upload` 或 `unknown`。完整 `sourceSnapshot` MUST NOT 出现在任何 HTTP 响应。缺少快照的历史任务默认 `unknown`；只有服务端明确记录的普通上传才为 `upload`。

#### Scenario: 历史任务缺少来源字段

- **WHEN** 任务列表加载包含缺失来源字段的历史任务
- **THEN** 列表 SHALL 正常渲染文件、状态与时间
- **AND** SHALL 隐藏来源专属控件而不是抛出异常

#### Scenario: 不回填历史来源

- **WHEN** 系统读取到来源未知的历史任务
- **THEN** MUST NOT 为其写入或推断来源
- **AND** 该任务 MUST NOT 被声明了录制来源的新请求复用

#### Scenario: 三种来源状态可区分

- **WHEN** 任务分别具有已核实来源、未知来源、无来源（普通上传）
- **THEN** 界面 SHALL 能区分这三种状态
- **AND** MUST NOT 把未知显示为某个具体录制

#### Scenario: 安全来源状态投影

- **WHEN** 客户端读取含已核实录制、明确普通上传或来源不可证任务的公开摘要
- **THEN** 摘要 SHALL 分别提供 `verified_recording`、`upload` 或 `unknown`
- **AND** MUST NOT 返回完整 `sourceSnapshot`、绝对路径或可信存储根

#### Scenario: 缺少来源快照的历史任务默认为未知

- **WHEN** 历史 Job 没有 `sourceSnapshot` 且无法重新核验其来源声明
- **THEN** 摘要 SHALL 返回 `sourceStatus = unknown`
- **AND** MUST NOT 将其转换为 `upload` 或某一录制来源
