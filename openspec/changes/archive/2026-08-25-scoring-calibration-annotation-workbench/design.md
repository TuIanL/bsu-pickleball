## Context

现有系统已经具备 CaptureTake、比赛视频、盘/局/回合片段、时间轴事件和逐帧视频播放能力。[SegmentManagerPage](/Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/SegmentManagerPage.tsx) 可以加载 `take.video_ids`、回合片段和时间轴事件，[SegmentVideoPlayer](/Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/components/SegmentVideoPlayer.tsx) 支持播放、定位和逐帧前进后退。

但现有 `CaptureSegment` 是比赛层级的区间模型，`SessionTimelineEvent` 是比分、换边、暂停等稀疏事件模型，二者都不适合承载高频逐球标注。当前 `shot-rally-events.v1` 也保留了大量未知字段，算法候选不能直接视为人工真值。PB Vision 导出的 JSON 和 Excel 主要是聚合统计，不能替代逐球证据。

因此，本 change 需要新增一个独立的、可版本化的评分校准标注层，同时尽可能复用现有视频和时间轴基础设施。

## Goals / Non-Goals

**Goals:**

- 提供基于 CaptureTake 的逐球/击球机会人工确认工作流。
- 支持第一批评分候选指标所需的发球、接发、入界结果和可观察落点区域标签。
- 清晰区分人工标签、算法候选、人工接受/修正/拒绝决定及证据时间窗。
- 将编辑中的标注保存为版本化标注包，并在审核锁定后导出 Gold Set。
- 输出覆盖率、未知率、冲突和证据完整性等质量摘要，为后续指标和评分校准提供输入。
- 保持现有片段、时间轴、Vidat 和算法产物兼容，不改变其既有语义。

**Non-Goals:**

- 不在本 change 中实现六维技能分数、Overall 分数或跨指标加权模型。
- 不复刻 PB Vision 的专有 `quality` 分数或页面交互。
- 不在本 change 中训练、部署或自动选择机器学习模型。
- 不要求继续从 PB Vision 导出数据；PB Vision 文件只能作为可选外部对照。
- 不把逐球标注改造成新的 `SessionTimelineEvent` 类型，也不覆盖算法生成的 canonical shot/rally artifact。
- 不在第一版实现精确的数值落点测量、厨房区到达或移动恢复标签；第一版落点使用可审计的区域/可观察性标签。

## Decisions

### 1. 新增独立工作台页面，复用现有播放器和回合上下文

工作台以一个 `CaptureTake` 为入口，复用现有视频源、机位切换、回合片段和播放头。页面增加逐球标注队列和标注面板，但不把 `SegmentManagerPage` 改造成逐球编辑器。

选择独立页面，是因为片段管理关注区间层级和边界编辑，而评分校准关注密集事件、快速确认和证据审计。复用 `SegmentVideoPlayer` 和时间轴基础能力可以减少视频同步与逐帧控制的重复实现。

备选方案是直接扩展 `SegmentManagerPage`；该方案初期改动少，但会把两套不同的编辑语义、保存状态和操作密度混在一个页面中，后续难以维护。

### 2. 使用 `scoring-calibration-annotation.v1`，而不是复用普通时间轴事件或 Vidat action schema

标注包采用独立版本化契约，至少包含：

- `package_id`、`schema_version`、`capture_take_id`；
- 视频/机位引用、CaptureTake 和回合片段版本引用；
- 算法候选产物引用及其版本或 hash；
- 标注包状态：`draft`、`reviewed`、`locked`；
- 标注条目、修订来源、创建者和时间戳；
- Gold Set 质量摘要。

标注条目以一次击球或一次击球机会为单位，保存证据时间窗、所属回合（允许暂时为空）、击球人、阶段、机会状态、结果、落点可观察性、落点区域、置信度和备注。

编辑态使用数据库实体支持单条保存和并发控制，标注包锁定时生成稳定的规范化 JSON artifact。锁定后的内容不可原地覆盖，修正必须产生新的 revision；这样既方便工作台交互，也保证后续评估可重放。

备选方案是只保存一个本地 JSON 文件；该方案适合一次性实验，但不利于草稿保存、多人复核、并发冲突和与 CaptureTake 权威版本关联。

### 3. 用机会状态表达分母，不用缺失值推断失败

第一版使用显式状态：

- `opportunity_status`：`eligible`、`not_applicable`、`unobservable`；
- `outcome`：`in_play`、`net`、`out`、`unknown`；
- `landing_status`：`measured`、`not_applicable`、`unobservable`；
- `landing_zone`：`short`、`middle`、`deep`、`unknown`。

例如，发球下网可以是 `eligible + net`；有效发球后没有清晰看到接发，可以是 `unobservable`；发球本身无效时，接发机会应是 `not_applicable`，不能进入接发分母。落点只有在 `landing_status=measured` 时才进入落点指标。

备选方案是用 `null` 或 `0` 表示所有未观测情况；这会把不可见、未发生和失败混为一谈，导致分母错误，故不采用。

### 4. 算法候选与人工真值双轨保存

工作台可以展示现有算法的 serve/shot/rally 候选，帮助标注者定位视频，但每条候选必须保留独立的人工决定：`accepted`、`corrected`、`rejected` 或 `unreviewed`。人工新建的事件也必须标记为 `manual`，不能伪装成算法结果。

Gold Set 只读取已审核或锁定版本中的人工决定，不读取未复核候选。这样可以比较算法与人工真值，而不是把算法输出再次当作训练标签。

### 5. 先做可解释的人工校准，不在工作台内计算正式评分

工作台只产出结构化事实和质量摘要，不直接生成六维分数或总分。后续指标层可以根据锁定的 Gold Set 计算发球入界率、接发入界率和有效落点覆盖情况；`performance-score.v1` 再独立决定哪些指标具备评分资格。

这样可以把“视频事实是否正确”“指标如何计算”和“指标如何映射为评分”分成三个可独立验证的层次。

### 6. 锁定前执行结构和语义校验

保存单条标注时允许草稿状态，但锁定前必须校验：证据时间窗在视频范围内、时间顺序合法、必需字段完整、结果与机会状态一致、落点字段与可观察性一致、同一回合不存在明显重复的发球机会。无法自动判断的疑点以 warning 和质量摘要呈现，不强行猜测。

### 7. 采用可复用的高密度标注交互

页面采用“视频 + 时间轴/候选列表 + 标注面板 + 待处理队列”布局。应支持从候选跳转到证据窗口、逐帧微调、保存后进入下一条、筛选未标注/不确定条目。键盘快捷键可以作为实现手段，但不能改变数据语义。

## Risks / Trade-offs

- **视频尚未注册为 CaptureTake** → 工作台无法直接使用 PB Vision 分享链接；上线前需要让用户上传或注册自己的原始比赛视频，并在无视频时提供明确的引导状态。
- **落点在单摄或遮挡下不可见** → 第一版使用 `unobservable` 和区域标签，不把无法观察的落点纳入分母；数值深度留待后续多视角/场地标定能力成熟后增加。
- **人工标注耗时较高** → 提供候选跳转、逐帧控制、批量队列和快捷操作，但不牺牲每条标签的证据和来源记录。
- **算法候选与人工事件无法一一对应** → 使用稳定的候选引用、时间窗和人工接受/修正/拒绝状态；无法匹配时允许人工新建或标记未匹配。
- **单个标注者偏差进入 Gold Set** → 第一版支持 reviewed/locked 生命周期和质量摘要；后续可在不改变 v1 语义的情况下增加第二标注者和一致性统计。
- **范围扩张到六维评分或机器学习** → 在 spec 和任务中明确本 change 只负责标注与 Gold Set，不在实现阶段顺带加入正式评分模型。
- **数据库编辑态与规范化 artifact 不一致** → 锁定操作必须在同一事务/受控流程中完成校验、生成 artifact 和记录 revision；失败时保留 draft，不产生半锁定包。

## Migration Plan

1. 以新增数据库表、API 和前端路由的方式部署，不修改既有 CaptureSegment、SessionTimelineEvent 和算法 artifact 的字段语义。
2. 为已有 CaptureTake 提供按需创建 draft 标注包的入口；没有视频或没有可用回合时只展示阻塞原因，不生成虚假标注。
3. 先使用单摄本地视频和人工创建/确认的发球、接发事件验证完整闭环，再接入现有算法候选。
4. 只有通过校验并显式锁定的标注包才可导出 Gold Set；现有指标和报告流程在没有 Gold Set 时保持原行为。
5. 若工作台出现问题，可隐藏入口或停用新 API；已保存的 draft/locked 标注包保留，不回滚或删除既有视频、片段和分析产物。

## Open Questions

- 当前第一批实验视频是否已经注册为 CaptureTake；如果没有，需要复用哪条上传/导入入口。
- 第一版落点是否只使用 `short/middle/deep`，还是同时允许标注者在已标定球场上点击一个近似位置；默认建议先使用区域标签。
- 第一版是否只配置一个标注者，还是马上安排第二人进行复核；默认建议先支持 `reviewed/locked`，暂不把双人一致性作为上线门槛。
- 是否需要把现有 PB Vision JSON/Excel 导入为外部 reference；默认建议不阻塞工作台，后续单独增加对照导入。
