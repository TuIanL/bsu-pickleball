## MODIFIED Requirements

### Requirement: 双摄停止后合并两路 MP4

双摄正常停止时，系统 MUST 先完成两路 TS 分段的安全收尾、CaptureTake 终态化和任务元数据持久化，且 MUST NOT 在停止请求中自动执行 MP4 合并。系统 MUST 允许用户通过任务管理中的一个任务级操作，异步为 cam_1 和 cam_2 分别合并有效 Fragment，并在两路都成功后登记视频。

#### Scenario: 双摄正常停止不自动合并

- **WHEN** 双摄录制正常停止
- **THEN** 系统 MUST 停止两路录制进程并保存有效 TS 分段
- **AND** 系统 MUST 持久化双摄会话和 CaptureTake 的终态信息
- **AND** 停止 API MUST NOT 调用 MP4 合并或 Video 登记流程
- **AND** 双摄任务 MUST 进入"待合并"状态

#### Scenario: 用户显式触发双路合并

- **WHEN** 用户在任务管理中对一个已停止的双摄任务点击"合并视频"
- **THEN** 系统 MUST 异步提交该任务的合并操作
- **AND** 系统 MUST 为 cam_1 和 cam_2 分别合并有效 Fragment
- **AND** 系统 MUST 持久化合并中的状态和每路处理结果
- **AND** 两路均成功后 cam_1 MUST 登记为 `default_analysis_video_id`

#### Scenario: 合并前任务不可用作视频

- **WHEN** 双摄任务尚未完成两路 MP4 合并
- **THEN** 系统 MUST NOT 提供可用的播放视频 ID
- **AND** 系统 MUST NOT 允许基于该任务创建视频分析任务

#### Scenario: 任一路合并失败

- **WHEN** cam_1 或 cam_2 合并、校验或登记失败
- **THEN** 系统 MUST 保留两路原始 TS 分段
- **AND** 任务总体状态 MUST 为失败或可重试状态
- **AND** 系统 MUST 保存可展示的失败原因
- **AND** 用户 MUST 能再次触发合并
