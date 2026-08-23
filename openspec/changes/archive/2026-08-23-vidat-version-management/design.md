# 设计：Vidat 标注包版本管理

## Context

当前实现对 `VidatAnnotationPackage` 只有“导出、打开、导入、列出”能力。问题根源是**归档与工作视图混淆**：

- `confirm_import_preview()` 会就地覆盖同一包的 `annotation_json`、`normalized_snapshot_json` 和 `imported_at`，导致旧 annotation 内容丢失。
- `_apply_import_plan()` 将编码动作、分段和时间线写入 take 级表，并按包 ID 删除旧投影；如果导入改为创建新包而不调整投影策略，旧版本投影会与新版本投影叠加。
- 现有预览已经提供 `added/removed/moved/category_changed/winner_changed/score_anchor_changed` 事件差异，但版本比较接口尚未复用这套能力，前端也没有比较入口。

因此本设计把系统拆成两层：**标注包是不可变归档快照；take 级 Vidat 投影是唯一可变的当前工作视图**。导入新包时必须在同一事务内更新两者的关系。

Vidat 本地服务由 `ensure_vidat_service()` 用 `subprocess.Popen(..., start_new_session=True)` 拉起 Nginx master 常驻。仅凭端口或配置执行 `nginx -s stop` 仍有误杀风险，因此需要记录由本系统启动的 PID、配置和 URL，并在停止前校验进程归属。

## Goals / Non-Goals

**Goals:**
- 每个标注包是不可变归档快照；导入会创建新结果版本，原版本内容不被覆盖。
- 支持导出和派生时填写 `name`、`owner`、`note`，并允许后续修改元数据。
- 支持从同一 CaptureTake 的任意版本派生，且派生包具有新的包身份和独立目录。
- 支持两个版本的元信息、统计摘要和事件级差异比较。
- 导入结果成为当前 Vidat 投影；替换旧 Vidat 投影时保留人工和算法来源的数据。
- 支持逻辑删除历史版本，以及在安全条件满足时永久清理。
- 支持 Vidat 服务状态查询、启动、停止，并区分服务和浏览器窗口生命周期。

**Non-Goals:**
- 不做版本间的内容差异可视化逐帧对比。
- 不做多用户权限/角色（仅存 `owner` 字符串，不做鉴权）。
- 不改变人工和算法来源投影的业务语义；本次只补齐 Vidat 投影的替换和当前版本指针。
- 不实现多人同时编辑同一 Vidat 包的实时协同；版本派生是协作边界。

## Decisions

### D1 导入 = 派生新版本（不覆盖归档）
`confirm_import_preview()` 在确认后创建带 `provenance=derived`、`source_package_id=来源包` 的结果包，结果包承载本次导入的 annotation、manifest 和规范化快照；来源包的内容列只读。

导入审计保留预览来源包和结果包两个关系：现有 `VidatImportAudit.package_id` 继续兼容表示来源包，新增 `result_package_id` 表示导入生成的版本。API 同时返回 `source_package_id` 和 `result_package_id`。

- **理由**：归档不可变是版本管理的地基，双向 lineage 才能支持版本比较、审计和删除保护。
- **备选**：保留就地覆盖并依赖审计留痕 → 历史 annotation 仍然丢失，否决。

### D2 建模：元数据、删除状态和当前投影指针
`VidatAnnotationPackage` 增加：

- `name: str | None`：缺省时由序列化层展示“第 N 版”；
- `owner: str | None`；
- `note: str | None`；
- `source_package_id: str | None`：只允许指向同一 CaptureTake 的包，不设置数据库外键，避免派生关系阻止逻辑删除；
- `provenance: str | None`：`generated` 或 `derived`，旧数据缺失时按 `generated` 处理；
- `deleted_at: datetime | None`：逻辑删除时间。

`LiveCodingState` 增加 `active_vidat_package_id`，表示当前 take 的 Vidat 投影来源。它可以是普通导出包，也可以是导入生成的派生包。

- **理由**：元数据和删除状态不改变归档内容；显式当前指针可以避免用“最新创建时间”猜测当前投影。
- **备选**：只按 `imported_at` 推断当前包 → 分支导入和并发操作下无法可靠表达当前投影，否决。

### D3 派生 = 新身份 + 新目录 + 可复用视频引用
`derive_annotation_package()` 必须验证来源包存在、未被逻辑删除且属于目标 CaptureTake，然后在 `vidat-annotations/<take>/vNNN-*` 下创建新目录。视频复用现有 symlink 机制，不复制大文件。

复制 annotation 时必须重写 `pickleball_manifest.package_id`、manifest 的 `package_id/version`、包目录引用和相关文件名；不能直接保留来源包 ID，否则 `parse_vidat_annotation()` 会拒绝派生包。`normalized_snapshot_json` 在新包尚未导入时置空，导入确认后再写入。

版本号使用同一 CaptureTake 的唯一约束，并通过 take 行锁或唯一冲突重试解决并发导出；数据库提交失败时清理新建目录，避免产生孤儿文件。

### D4 版本比较 = 摘要 + 事件级 diff
`compare_annotation_packages(a, b)` 只允许比较同一 CaptureTake 且未永久清理的两个包，返回：

- 两侧的 `version/name/provenance/source_package_id/created_at/imported_at/deleted_at`；
- 两侧的操作数、编码动作数、最终比分和最终胜者；没有规范化快照时从 annotation 解析，无法计算时返回 `null`；
- 复用现有预览 diff 的稳定事件 ID 和分类，返回 `added/removed/moved/category_changed/winner_changed/score_anchor_changed/changed` 等事件级差异。

比较是只读操作，不修改当前投影，也不把某一侧自动设为基线。

- **理由**：满足用户“查看版本区别”的核心需求，并复用已有校验和 diff 语义，避免产生两套差异定义。
- **备选**：只比较数量和比分 → 无法定位具体标注修改，否决。

### D5 删除 = 逻辑删除优先，永久清理受保护
普通 `DELETE /packages/{id}` 执行逻辑删除：设置 `deleted_at`、从默认列表隐藏、清理该包在 Vidat dist 中的发布文件，但保留数据库快照和导入审计。当前投影包、预览来源包、审计涉及的包和仍有子派生包的包不能被永久清理。

永久清理使用显式 `purge` 操作，仅当包不存在审计/预览引用、不是当前投影、没有未删除子派生包时，才校验 `package_dir` 位于受控 data root 下并删除目录、发布残留和数据库行。逻辑删除的包不允许重新打开或导入，但允许在“显示已删除版本”视图中查看 lineage 和审计信息。

- **理由**：满足用户清理历史版本的需求，同时不破坏训练留存和导入审计。
- **备选**：所有删除都物理删行 → 导入过的历史版本几乎都无法安全删除，且会破坏审计外键，否决。

### D6 Vidat 服务 = 受控进程生命周期
启动时写入 data root 下的服务状态文件，记录 PID、配置路径、URL、启动时间和服务标识；状态查询同时检查 PID 存活、命令行/配置归属和 URL 响应。若端口已被未受控进程占用，系统不得把它当成可停止的 Vidat 服务。

停止时只终止状态文件确认属于本系统的 Nginx master，并等待 URL 不可用后返回；未运行、已失联、停止失败都返回可区分的状态。`nginx -s stop` 作为受控配置下的优雅停止手段，不能仅凭固定端口执行。

浏览器窗口引用由前端保存：如果窗口由平台脚本打开，关闭按钮可尝试关闭该窗口；服务停止按钮只停止 Nginx，不承诺能关闭用户手工打开的标签页。

### D7 API 与前端形态
- `POST /capture-takes/{take_id}/packages`：可选 JSON body `name/owner/note`，普通导出。
- `POST /packages/{source_id}/versions`：派生，body 为 `name/owner/note`。
- `PATCH /packages/{id}`：部分更新元数据。
- `GET /packages/{a}/compare/{b}`：返回摘要和事件级差异。
- `DELETE /packages/{id}`：逻辑删除；`POST /packages/{id}/purge`：条件永久清理。
- `GET /service/status`、`POST /service/start`、`POST /service/stop`：服务生命周期。
- 导入确认返回 `audit_id/source_package_id/result_package_id/active_vidat_package_id/operations`。
- `analysisClient.ts` 提供对应类型和函数；`VidatWorkbenchPanel` 提供导出元数据表单、派生、编辑、比较、删除/清理、导入结果切换及服务/窗口状态。

## Risks / Trade-offs

- **[R1] 导入后旧投影叠加** → 在同一事务中根据 `active_vidat_package_id` 删除旧 Vidat 来源投影，只保留人工/算法来源，并设置新的当前包指针；失败则整体回滚。
- **[R2] 派生包身份残留来源 ID** → 统一由服务层重写 manifest、`pickleball_manifest` 和视频/annotation 引用，并增加解析回读测试。
- **[R3] 删除导致审计断链** → 默认逻辑删除；永久清理必须检查审计、预览、当前投影和子派生关系，并保留明确拒绝原因。
- **[R4] 文件系统与数据库事务不一致** → 先创建受控临时目录，数据库提交失败时清理；永久清理先记录逻辑删除状态，再执行文件清理并可重试。
- **[R5] 版本号并发冲突** → 对 CaptureTake 加锁或在唯一约束冲突后重新分配版本，测试并发导出。
- **[R6] Nginx PID 被复用或端口被其他服务占用** → 状态文件保存服务标识和配置，停止前验证 PID 命令行/配置归属；未受控端口只报告冲突，不执行停止。
- **[R7] 旧数据库和旧包缺少新字段** → 增加 Alembic revision 与 `init_db()` 补列逻辑；序列化层对旧数据提供 `generated` 和默认名称兼容。
- **[R8] 事件级比较数据量过大** → 首版限制为同一 take 的两个包并返回结构化差异；UI 先按差异类型分组，后续再增加分页或逐帧预览。

## Migration Plan

1. 新增 Alembic revision：为 `vidat_annotation_packages` 增加元数据和 `deleted_at`，为 `vidat_import_audits` 增加 `result_package_id`，为 `live_coding_states` 增加 `active_vidat_package_id`；同步 `init_db()` 兼容补列和旧数据默认值。
2. 实现身份安全的派生、事件级比较、逻辑删除/永久清理、发布残留清理和版本号并发保护。
3. 修改 `confirm_import_preview`：生成结果包、保存双向审计关系、替换当前 Vidat 投影，并在事务失败时回滚数据库和文件。
4. 新增/调整 REST API、响应模型和错误状态；创建包接口支持元数据，比较使用只读 GET，删除区分逻辑删除与 purge。
5. 升级前端客户端和工作台，加入导出/派生表单、版本比较面板、删除确认、导入结果切换、服务状态和窗口处理。
6. 同步更新三个 CLI 脚本与 API 的参数和返回语义。
7. 完成后端、API、前端和服务生命周期测试，再在真实 macOS Nginx 环境验证启动、状态、停止和端口冲突。

## Open Questions

- 是否需要为逻辑删除增加恢复入口？首版可以只保留“显示已删除版本”查询，恢复能力作为后续增强。
- `active_vidat_package_id` 是否放在 `LiveCodingState` 还是单独的 take 投影表？首版放在 `LiveCodingState`，若现有迁移约束不适配再拆表。
- macOS Homebrew Nginx 的实际 PID/配置归属检测方式需在真实环境实测；未验证前不允许实现无标识的兜底 kill。
