## ADDED Requirements

### Requirement: Web 能力可用性与准备反馈

模块 API SHALL 在保持 capabilities 数组响应兼容的前提下提供只读 runtime-status，返回是否允许模块提交。来源和模型准备 SHALL 通过显式准备请求执行，模型反馈 SHALL 按 implementation 区分就绪与缺项；环境未启用和准备失败 SHALL 返回稳定的公共错误信息。

#### Scenario: 禁止新增提交但可读旧结果
- **WHEN** modular_analysis_enabled 为 false
- **THEN** runtime-status SHALL 返回不可提交，创建请求 SHALL 拒绝
- **AND** 既有模块清单、产物读取及 legacy 创建 SHALL 保持可用

#### Scenario: 能力目录兼容
- **WHEN** 旧客户端调用 GET /api/analysis/capabilities
- **THEN** 响应 SHALL 仍为能力数组，不把新增运行状态包裹进替代结构

### Requirement: Web 双摄权威来源准备

系统 SHALL 提供按 CaptureTake 准备模块来源的 API，由服务端验证登记的 take、视频、真实 camera_id、view_id、源 PTS 与同步确认，返回 source_ids、公共媒体元数据、参考机位、完整同步快照、revision 和 provenance fingerprint。该入口 MUST NOT 通过场地标定、名册或正式回合切分来准备首批检测能力；MUST NOT 自动确认同步锚点或泄露内部路径。

#### Scenario: 有效双摄准备
- **WHEN** take 有两路已登记视频、权威 PTS 和有效同步确认
- **THEN** 准备 SHALL 返回与真实 camera identity 对齐的两路快照及可用于 Planner 的同步映射
- **AND** 页面无需手工拼装 sync 或重放确认动作

#### Scenario: 缺少同步或来源已改变
- **WHEN** 同步未确认、provenance 失效或一路媒体不属于该 take
- **THEN** API SHALL 返回待准备或不可执行原因，不伪造 source_pts，不静默回退名义 FPS

#### Scenario: 准备包含旧确认迁移
- **WHEN** 已有合法旧同步确认需要迁移才能形成当前快照
- **THEN** 迁移 SHALL 只发生在显式准备路径，后续 preview SHALL 只读取准备结果

### Requirement: Web 双摄绑定校验不破坏预览纯读取

AnalysisRequest SHALL 兼容增加可选 source_binding，携带 take_id、同步 revision 和 provenance fingerprint。Web 双摄 SHALL 使用该绑定；预览及提交 SHALL 通过只读校验确认来源与当前权威同步仍匹配。既有 CLI 无绑定请求 SHALL 保持原 source/sync 校验语义。

#### Scenario: 预览后同步被修改
- **WHEN** Web 预览后 take 的同步版本或来源归属已改变
- **THEN** 提交 SHALL 拒绝过期绑定且不创建 Job，要求重新准备/预览

#### Scenario: 只读验证无隐式迁移
- **WHEN** 对带 take 绑定的请求进行 preview
- **THEN** 系统 MUST NOT 写入同步确认、迁移文件、计划或 Job，也不得解码视频或加载模型
- **AND** 需要写入准备数据时 SHALL 返回准备要求

### Requirement: 提交检查预览的语义指纹

AnalysisJobCreate SHALL 接受可选 expectedPlanHash。提供该字段时，模块提交 MUST 将实际将被持久化的 plan_hash 与其比较；不同 SHALL 返回 HTTP 409 和 plan_preview_stale，且不产生 Job/计划/节点记录。未提供字段的既有调用 SHALL 保持兼容；缓存提示变化 MUST NOT 单独导致语义冲突。

#### Scenario: 配置或模型身份变化
- **WHEN** 模型准备快照或默认有效参数在预览后改变，实际 plan_hash 与 expectedPlanHash 不同
- **THEN** 创建 SHALL 在持久化前被拒绝，不执行任何节点

#### Scenario: 仅缓存可用性变化
- **WHEN** 语义计划相同但其他任务新增或移除了缓存
- **THEN** 提交 SHALL 继续按原语义计划创建/去重，实际缓存使用由 executor 核验

#### Scenario: 旧提交客户端不带预览 hash
- **WHEN** 已有 CLI 或 API 提交合法模块请求但未传 expectedPlanHash
- **THEN** 系统 SHALL 继续通过现有 Planner 与 Worker 合同执行

### Requirement: 模块任务持久化可验证素材归属

模块 Job SHALL 保留从已登记来源验证得到的视频、录制或 take 关联，供 Library 重建历史；前端 return 或显示标题 MUST NOT 作为归属凭据。

#### Scenario: 刷新后可找回录制专项任务
- **WHEN** 单机位或双摄专项创建完成后用户刷新原素材页面
- **THEN** 该 Job SHALL 仍出现在对应素材历史中，且机位及 take 关联不依赖浏览器内存

#### Scenario: 请求伪造其他素材关联
- **WHEN** 请求携带的录制/take 关联与所用已登记视频不一致
- **THEN** 后端 SHALL 拒绝关联请求，不把任务挂到其他素材历史
