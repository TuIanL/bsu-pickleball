## ADDED Requirements

### Requirement: 素材历史按同源收拢

素材工作区的历史任务列表 SHALL 只包含与该素材来源等价的任务。后端录制筛选与前端 Library 归属 MUST 使用同一规范化来源状态和身份规则，MUST NOT 各自从原始 metadata 字段推断。

录制素材只可接纳 `sourceStatus = verified_recording` 且规范化 Session、Video、Take/多视角绑定与该素材等价的任务。上传素材只可接纳 `sourceStatus = upload` 且 Video ID 与素材相同的任务。`sourceStatus = unknown` 的历史任务 MUST NOT 被归入任何具体素材历史；它仍可留在一般任务列表中供读取和追溯。

来源等价 MUST NOT 由前端依据文件名、路径、`cameraSlot` 单字段或原始 metadata 的顶层优先/任一匹配逻辑推断。当选中任务的来源与当前素材不等价或未知时，系统 MUST 拒绝把该任务的结果当作本素材的结果展示。

#### Scenario: 异源任务不进入素材历史

- **WHEN** 某任务与其他素材存在关联但来源不等价
- **THEN** 该任务 MUST NOT 出现在当前素材的历史列表中

#### Scenario: 同源任务的多版本

- **WHEN** 同一素材存在多个同源任务版本
- **THEN** 工作区 SHALL 按既有版本选择语义展示
- **AND** 版本切换 MUST NOT 改变来源归属

#### Scenario: 选中任务来源不符

- **WHEN** 用户尝试打开一个来源与当前素材不等价的任务
- **THEN** 系统 MUST 拒绝按本素材展示其结果
- **AND** SHALL 给出可理解的提示，而不是静默展示错误结果

#### Scenario: 冲突的历史任务不归入任一录制

- **WHEN** 历史 Job 的顶层 Session 与 metadata Session 冲突，无法通过服务端重新核验
- **THEN** 后端录制筛选 SHALL 不将该 Job 返回给任一冲突 Session
- **AND** 前端 Library SHALL 将其视为 `unknown`，不在任一录制素材历史中展示
- **AND** 一般任务列表 SHALL 仍可读取该 Job

#### Scenario: 上传素材只接纳明确无录制来源任务

- **WHEN** Library 组装某上传视频的历史任务
- **THEN** 仅 `sourceStatus = upload` 且 `videoId` 匹配的任务 SHALL 归入该素材
- **AND** 缺少快照的旧任务 MUST NOT 因没有 Session 字段而推断为上传任务
