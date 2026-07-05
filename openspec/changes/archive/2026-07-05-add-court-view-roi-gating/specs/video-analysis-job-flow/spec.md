## ADDED Requirements

### Requirement: Court-view/ROI 阶段记录
真实视频分析 pipeline SHALL 在任务阶段记录中暴露 court-view gate 与 detection ROI 的执行状态和摘要。

#### Scenario: Court-view/ROI 阶段完成
- **WHEN** 完成的真实已标定视频分析任务运行了 court-view gate 或 detection ROI
- **THEN** pipeline stages SHALL 包含 court-view/ROI 阶段状态、处理帧计数、候选片段数量、ROI 状态、跳过帧数量和过滤检测数量

#### Scenario: Court-view/ROI 阶段降级
- **WHEN** court-view gate 缺少参考帧或 ROI 缺少标定角点但基础 tracking 仍可运行
- **THEN** pipeline stages SHALL 将对应部分标记为 `skipped`、`partial` 或 `unavailable`，并保持 detection、tracking、pose、projection 和 metrics 阶段按可用输入继续执行

#### Scenario: Court-view/ROI 阶段失败
- **WHEN** court-view/ROI 处理发生可恢复错误
- **THEN** pipeline SHALL 记录失败或 unavailable 诊断，并不得因为该辅助门控失败而伪造成功的 court-view segment

### Requirement: Court-view/ROI artifact 引用
完成的 pipeline raw result SHALL 在 artifacts 中提供 court-view/ROI artifact 的可选引用、状态和说明。

#### Scenario: Artifact 可用
- **WHEN** court-view/ROI artifact 已写入 storage
- **THEN** raw pipeline result artifacts SHALL 包含浏览器可加载的 artifact URL、文件路径、状态和 detail

#### Scenario: Artifact 不可用
- **WHEN** court-view/ROI artifact 因缺少前置条件未生成
- **THEN** raw pipeline result SHALL 暴露不可用状态和原因，而不是要求前端猜测该能力是否运行

#### Scenario: 旧客户端忽略新字段
- **WHEN** 客户端尚未渲染 court-view/ROI artifact
- **THEN** tracking overlay、pose overlay、source video、movement metrics 和现有 job navigation SHALL 继续保持兼容

### Requirement: Court-view 候选不改变报告语义边界
视频分析 job flow SHALL 将 court-view candidates 作为输入质量和导航辅助，而不是完整比赛事件输出。

#### Scenario: 报告需要 rally 语义
- **WHEN** report 或 analysis details 需要完整 rally segmentation、得分、失误、球落点或战术判断
- **THEN** 系统 SHALL 继续标记这些语义为 unavailable，除非未来专门能力提供相应证据

#### Scenario: Serve-start 消费 court-view candidates
- **WHEN** serve-start detector 使用 court-view candidates 作为辅助上下文
- **THEN** 发球 artifact SHALL 仍以发球候选点形式输出，并记录 court-view 只是辅助信号
