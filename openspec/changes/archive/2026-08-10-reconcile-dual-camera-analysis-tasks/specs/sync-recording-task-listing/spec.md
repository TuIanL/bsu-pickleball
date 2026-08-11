## MODIFIED Requirements

### Requirement: 双摄录制卡片

系统 SHALL 用 `SyncRecordingTaskCard` 组件渲染每条双摄录制会话，全文不使用“主机位/副机位”称谓。卡片 SHALL 将录制资产状态与分析任务状态分区展示；分析任务 SHALL 按双摄协同 Parent、A 机位单摄、B 机位单摄分组，并对每组展示最新任务与可展开的历史任务。

#### Scenario: 展示录制摘要

- **WHEN** 系统渲染一条双摄录制会话卡片
- **THEN** 卡片展示底线机位 A 视频和底线机位 B 视频信息
- **AND** 卡片展示录制时长、分段数量和总重启次数
- **AND** 每条会话展示状态标签（completed / failed / canceled）
- **AND** 每条会话展示待合并、合并中、已完成或失败的合并状态

#### Scenario: 待合并任务展示合并按钮

- **WHEN** 双摄任务已停止且合并状态为待合并或失败
- **THEN** 卡片 MUST 展示“合并视频”或“重新合并”按钮
- **AND** 点击按钮 MUST 提交该任务的双路合并操作

#### Scenario: 合并中禁止重复提交

- **WHEN** 双摄任务合并状态为合并中
- **THEN** 卡片 MUST 展示处理中状态
- **AND** 合并按钮 MUST 禁止重复提交
- **AND** 卡片 MUST 不提供播放或分析入口

#### Scenario: 展示默认分析入口

- **WHEN** 双摄录制会话的两路合并均成功且 `default_analysis_video_id` 存在
- **THEN** 卡片提供创建分析任务入口
- **AND** 点击后跳转到录制分析桥接页面或已有分析详情页面

#### Scenario: 分析不可用

- **WHEN** 双摄录制会话尚未完成两路合并
- **THEN** 卡片展示待合并或失败原因
- **AND** 卡片 MUST 不展示可播放视频和分析入口

#### Scenario: 分析任务按类型分区

- **WHEN** 双摄录制会话存在公开分析任务
- **THEN** 卡片 SHALL 分别展示双摄协同、A 机位和 B 机位任务区域
- **AND** 每个区域 SHALL 默认展示最近更新任务
- **AND** internal child SHALL NOT 作为独立任务区域展示

#### Scenario: 历史任务可展开

- **WHEN** 任一任务区域存在多个公开任务
- **THEN** 卡片 SHALL 展示历史任务数量和展开控制
- **AND** 展开后 SHALL 显示每个历史任务的状态、时间和具体操作

#### Scenario: 操作作用于明确任务

- **WHEN** 用户点击某个当前或历史分析任务的操作
- **THEN** 操作 SHALL 使用该任务对应的 job id
- **AND** SHALL 不因同组存在其他任务而作用于错误任务
