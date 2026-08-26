# scoring-calibration-annotation-workbench Specification

## Purpose
TBD - created by archiving change scoring-calibration-annotation-workbench. Update Purpose after archive.
## Requirements
### Requirement: Workbench SHALL be bound to a registered CaptureTake

评分校准工作台 MUST 以一个 `CaptureTake` 为工作范围，加载其可用视频、机位信息、有效回合片段和可用的算法候选。工作台 MUST 保留这些来源的引用，不得把外部 PB Vision 分享链接当作系统内视频源。

#### Scenario: CaptureTake has a playable video

- **WHEN** 用户打开一个包含有效 `video_ids` 的 CaptureTake
- **THEN** 系统 SHALL 展示对应视频、可用机位切换、回合上下文和标注队列

#### Scenario: CaptureTake has no playable video

- **WHEN** 用户打开一个没有可用视频源的 CaptureTake
- **THEN** 系统 SHALL 展示明确的阻塞原因和上传/注册视频的引导，并 SHALL 禁止创建可锁定的人工标注

### Requirement: Workbench SHALL support evidence-focused video review

工作台 MUST 支持播放、暂停、时间轴定位、逐帧前进和逐帧后退。每条标注 MUST 能保存相对于视频起点的证据时间窗，并在回看标注时跳转到该时间窗。

#### Scenario: Annotator adjusts an event boundary

- **WHEN** 标注者在视频中逐帧调整击球时间和证据窗口
- **THEN** 系统 SHALL 保存调整后的时间值，并 SHALL 保留所属 `video_id` 或机位来源

#### Scenario: Annotator reviews an existing annotation

- **WHEN** 标注者从队列或时间轴打开一条已有标注
- **THEN** 系统 SHALL 将视频定位到该标注的证据窗口，并 SHALL 显示其人工决定、算法候选和备注

### Requirement: Workbench SHALL capture score-relevant shot facts

工作台 MUST 允许以一次击球或一次击球机会为单位保存以下信息：证据时间窗、可选回合引用、击球人、击球阶段、机会状态、结果、落点可观察性、落点区域、置信度和备注。第一版至少支持 `serve`、`return`、`other`、`unknown` 阶段，`in_play`、`net`、`out`、`unknown` 结果，以及 `short`、`middle`、`deep`、`unknown` 落点区域。

#### Scenario: Annotator records a valid serve

- **WHEN** 标注者将一条击球标记为 `stage=serve`、`opportunity_status=eligible`、`outcome=in_play`，并选择可观察落点区域
- **THEN** 系统 SHALL 保存该条发球事实，并 SHALL 允许后续发球入界率和有效发球落点指标引用它

#### Scenario: Annotator records an unobservable return

- **WHEN** 有效发球后接发过程被遮挡或无法确认
- **THEN** 标注者 SHALL 能将该接发标记为 `opportunity_status=unobservable`，系统 SHALL 不把它当作接发失败

#### Scenario: Annotator records a non-applicable return

- **WHEN** 发球已经下网或出界且不存在可计入的接发机会
- **THEN** 标注者 SHALL 能将接发机会标记为 `opportunity_status=not_applicable`，系统 SHALL 不将其计入接发分母

### Requirement: Result and landing semantics SHALL be explicit

系统 MUST 将 `unobservable`、`not_applicable`、`unknown` 和失败结果区分保存。落点区域只有在 `landing_status=measured` 时才能作为落点指标输入；下网、出界或不可观察的击球不得通过默认值自动获得落点。

#### Scenario: Net or out shot has no measured landing

- **WHEN** 标注者将击球结果标记为 `net` 或 `out`
- **THEN** 系统 SHALL 将落点标记为 `not_applicable` 或要求标记为不可测，并 SHALL 拒绝把该落点作为有效落点样本

#### Scenario: Annotator cannot determine the result

- **WHEN** 视频证据不足以判断击球结果
- **THEN** 系统 SHALL 允许保存 `outcome=unknown` 或 `opportunity_status=unobservable`，并 SHALL 在质量摘要中计入未知项

### Requirement: Algorithm candidates and human decisions SHALL remain separate

当存在算法候选时，系统 MUST 展示候选来源、时间和置信度，并 MUST 为候选保存独立的人工决定状态：`accepted`、`corrected`、`rejected` 或 `unreviewed`。算法候选 MUST NOT 自动成为 Gold Set。

#### Scenario: Annotator accepts an algorithm candidate

- **WHEN** 标注者确认算法候选的时间和语义均正确
- **THEN** 系统 SHALL 保存候选引用及 `accepted` 决定，并 SHALL 将最终人工事实写入当前标注 revision

#### Scenario: Annotator corrects an algorithm candidate

- **WHEN** 标注者修改候选的时间、阶段、结果或击球人
- **THEN** 系统 SHALL 保留原始候选，并 SHALL 保存 `corrected` 决定和修改后的人工事实

#### Scenario: Annotator creates an event missing from candidates

- **WHEN** 视频中存在算法未产生候选的可观察击球
- **THEN** 系统 SHALL 允许标注者创建来源为 `manual` 的新条目，并 SHALL 将其纳入后续 Gold Set

### Requirement: Annotation packages SHALL be versioned and traceable

系统 MUST 提供版本化的 `scoring-calibration-annotation.v1` 标注包。标注包 MUST 关联 CaptureTake、视频/机位、回合片段版本、算法候选产物版本或 hash、标注者、revision、状态和创建/更新时间。状态至少包含 `draft`、`reviewed` 和 `locked`。

#### Scenario: Annotator saves a draft

- **WHEN** 标注者保存部分完成的标注
- **THEN** 系统 SHALL 持久化当前 draft，并 SHALL 允许后续继续编辑，不要求未完成条目立即进入 Gold Set

#### Scenario: Annotator locks a package

- **WHEN** 标注包通过锁定前校验且标注者显式确认锁定
- **THEN** 系统 SHALL 生成可重放的规范化 Gold Set artifact，并 SHALL 将该 revision 标记为 `locked`

#### Scenario: User corrects a locked package

- **WHEN** 用户需要修改已锁定的标注包
- **THEN** 系统 SHALL 保留原 locked revision，并 SHALL 创建新的 draft revision，不得原地覆盖历史 Gold Set

### Requirement: System SHALL validate annotations before locking

锁定操作 MUST 校验证据时间窗位于视频有效范围内、开始时间不晚于结束时间、必需字段完整、机会状态与结果组合合法、落点状态与落点区域组合合法，并 SHALL 检查同一回合内明显重复的发球机会。无法自动确定的语义疑点 MUST 以 warning 或质量摘要呈现，不得被系统静默猜测。

#### Scenario: Annotation has an invalid evidence window

- **WHEN** 标注的时间窗超出视频范围或结束时间早于开始时间
- **THEN** 系统 SHALL 拒绝锁定，并 SHALL 返回可定位到具体标注的校验错误

#### Scenario: Annotation has an inconsistent landing value

- **WHEN** 标注将落点区域设置为 `deep` 但落点状态为 `not_applicable` 或击球结果为 `net`
- **THEN** 系统 SHALL 拒绝该条标注进入 locked revision，并 SHALL 要求修正或明确标记为不可测

### Requirement: Workbench SHALL provide a review queue and quality summary

工作台 MUST 提供未标注、未复核、不确定和存在校验 warning 的队列筛选。标注包 MUST 计算至少包含总条目数、已确认条目数、未知/不可观察条目数、未匹配候选数、冲突数和证据完整率的质量摘要。

#### Scenario: Annotator filters uncertain items

- **WHEN** 标注者选择“不确定”或“待复核”筛选条件
- **THEN** 系统 SHALL 只展示对应条目，并 SHALL 支持从队列直接进入其证据窗口

#### Scenario: Package has unresolved quality issues

- **WHEN** 标注包仍存在必需字段缺失或锁定阻塞错误
- **THEN** 系统 SHALL 展示阻塞原因和质量摘要，并 SHALL 禁止将其声明为 locked Gold Set

### Requirement: Locked Gold Set SHALL expose facts without formal skill scores

系统只可以从 `locked` 标注包导出结构化人工事实和质量摘要。该导出 MUST 可供后续指标校验使用，但本能力 MUST NOT 生成六维技能分数、Overall 分数、PB Vision 专有 quality 分数或机器学习模型输出。

#### Scenario: Downstream metric evaluator reads a locked package

- **WHEN** 后续指标校验请求一个已锁定标注包
- **THEN** 系统 SHALL 返回带 schema version、revision、provenance 和质量摘要的人工事实，并 SHALL 不附带未经独立定义的正式技能评分

#### Scenario: Downstream evaluator requests a draft package

- **WHEN** 后续指标校验请求一个仍为 `draft` 或存在锁定错误的标注包
- **THEN** 系统 SHALL 返回不可作为 Gold Set 使用的状态和原因，并 SHALL 不将其用于评分校准
