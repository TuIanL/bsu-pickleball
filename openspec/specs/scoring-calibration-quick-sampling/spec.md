# scoring-calibration-quick-sampling Specification

## Purpose
TBD - created by archiving change scoring-calibration-quick-sampling. Update Purpose after archive.
## Requirements
### Requirement: Workbench SHALL provide a rally sampling queue

工作台 MUST 以 CaptureTake 的有效 `rally` 片段作为快速校准队列，并默认均匀抽取有限数量的回合样本。用户 MUST 能查看当前样本进度，并能切换为全部回合或手动进入任意回合；系统不得默认要求用户从完整比赛视频的 0 秒开始逐球浏览。

#### Scenario: Open quick calibration for a take with many rallies

- **WHEN** 用户打开包含多个有效 rally 片段的 CaptureTake
- **THEN** 系统 SHALL 默认创建有限抽样队列，显示样本总数、当前序号和回合起止时间，并将播放器定位到当前回合窗口

#### Scenario: User chooses all rallies

- **WHEN** 用户将队列范围切换为“全部回合”
- **THEN** 系统 SHALL 展示所有未 superseded 的 rally 片段，并 SHALL 保留同样的保存、筛选和自动下一条语义

### Requirement: System SHALL discover persisted algorithm candidates

系统 MUST 能从 CaptureTake 关联的本地分析目录读取已保存的候选 artifact，至少支持发球候选文件，并 MUST 按 CaptureTake 的 registered `video_ids` 过滤来源。候选 MUST 展示来源 job、artifact 类型、时间和置信度，不能因后端进程重启而只剩内存候选。

#### Scenario: Take has persisted serve candidates

- **WHEN** CaptureTake 的 `session_dir/analysis/job-*` 下存在与其视频 ID 匹配的发球候选 artifact
- **THEN** 工作台 SHALL 在对应回合附近显示候选，并 SHALL 保留 job/artifact provenance 和 coverage warning

#### Scenario: Candidate storage is unavailable

- **WHEN** 外置分析目录不存在、不可读或没有与当前视频匹配的候选
- **THEN** 工作台 SHALL 明确显示候选不可用原因，并 SHALL 允许用户继续使用人工快捷标注

### Requirement: Workbench SHALL support minimum-fact quick decisions

工作台 MUST 提供不打开详细表单即可保存最小评分事实的快捷操作，至少包括“发球入界”“发球失败”“接发入界”“接发不可观察”和“跳过”。快捷操作 MUST 自动填充阶段、机会状态、结果、落点可观察性、当前回合和证据时间窗，并 MUST 复用现有标注 API 和锁定前校验。

#### Scenario: Quick-confirm an in-play serve

- **WHEN** 用户在当前回合点击“发球入界”
- **THEN** 系统 SHALL 创建或更新 `stage=serve`、`opportunity_status=eligible`、`outcome=in_play` 的人工事实，自动关联当前 rally 和证据时间窗，并反馈保存成功

#### Scenario: Mark an unobservable return

- **WHEN** 用户在当前回合点击“接发不可观察”
- **THEN** 系统 SHALL 保存 `stage=return`、`opportunity_status=unobservable`、`outcome=unknown`、`landing_status=unobservable`、`landing_zone=unknown`，且不得将其当作接发失败

#### Scenario: Skip a rally

- **WHEN** 用户点击“跳过”
- **THEN** 系统 SHALL 将当前回合标记为本次抽样不处理并进入下一条，但不得创建虚假的人工事实或改变 Gold Set 内容

### Requirement: Advanced annotation fields SHALL be optional in quick mode

快速模式 MUST 将击球人、落点区域、置信度和备注作为可选的高级信息，不得阻塞最小发球/接发事实的保存；用户 MUST 能展开详细表单，对已保存事实进行补充和修正。

#### Scenario: Save minimum fact without advanced fields

- **WHEN** 用户只通过快捷按钮确认发球或接发，未填写击球人、落点区域和备注
- **THEN** 系统 SHALL 允许保存合法人工事实，并 SHALL 在队列中显示其待补充状态而不是报必填错误

#### Scenario: User opens advanced editing

- **WHEN** 用户从快速队列或时间线打开“补充字段”
- **THEN** 系统 SHALL 展开现有详细表单，并 SHALL 允许编辑后通过原有 update/validation/revision 语义保存

### Requirement: Quick calibration SHALL show progress and preserve Gold Set boundaries

系统 MUST 显示抽样队列的已处理、待处理和跳过数量，并支持保存后自动进入下一条。快捷模式 MUST 不绕过 draft/reviewed/locked 生命周期；只有 locked revision 才能作为 Gold Set。

#### Scenario: Save and advance

- **WHEN** 用户保存当前快速事实并选择“下一条”
- **THEN** 系统 SHALL 更新进度、定位下一个待处理回合，并 SHALL 不重复创建当前事实

#### Scenario: Lock quick-mode annotations

- **WHEN** 用户完成抽样并锁定标注包
- **THEN** 系统 SHALL 使用与详细模式相同的锁定校验和 Gold Set artifact，且 SHALL 保留快捷事实的 provenance
