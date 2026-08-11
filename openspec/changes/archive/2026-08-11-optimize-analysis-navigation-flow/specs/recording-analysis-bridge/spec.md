## ADDED Requirements

### Requirement: 录制分析入口区分双摄主流程和单摄工程流程

从双摄录制进入的主分析流程 SHALL 使用双摄任务上下文；A/B 单摄分析入口 SHALL 继续作为次级工程入口，并在返回任务管理时恢复其实际录制来源，不得默认伪装为上传视频任务。

#### Scenario: 双摄创建页退出

- **WHEN** 用户从双摄录制卡片进入 `MultiViewAnalysisSetupPage` 并点击退出
- **THEN** 页面 SHALL 返回双摄任务管理上下文
- **AND** SHALL NOT 返回单摄录制分析页或视频采集页

#### Scenario: 单摄工程入口返回

- **WHEN** 用户通过 A/B 单摄工程入口创建或查看分析任务
- **THEN** 页面 SHALL 保留普通录制来源及 session/camera slot 上下文
- **AND** 返回任务管理时 SHALL 进入录制视频任务视图

#### Scenario: 创建失败重试

- **WHEN** 录制分析创建失败
- **THEN** 页面 SHALL 提供留在当前创建流程重试或返回原录制任务的操作
- **AND** SHALL 不把用户送到无关的上传视频创建页

