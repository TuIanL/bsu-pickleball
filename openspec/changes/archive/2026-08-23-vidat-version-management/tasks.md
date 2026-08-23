# 任务：Vidat 标注包版本管理

## 1. 数据模型与迁移

- [x] 1.1 在 `VidatAnnotationPackage` 增加 `name`、`owner`、`note`、`source_package_id`、`provenance`、`deleted_at` 字段；来源字段校验为同一 CaptureTake，数据库不建立派生外键。
- [x] 1.2 在 `VidatImportAudit` 增加 `result_package_id`，保留现有 `package_id` 作为来源包关联，并为新旧数据定义兼容语义。
- [x] 1.3 在 `LiveCodingState` 增加可空 `active_vidat_package_id`，表示当前 take 的 Vidat 投影来源。
- [x] 1.4 新增 Alembic revision，覆盖上述字段、索引、默认值和 downgrade；同步 `backend/app/database.py` 的本地历史数据库补列逻辑。
- [x] 1.5 为旧数据提供兼容读取：`provenance` 缺失视为 `generated`，名称缺失展示“第 N 版”，`deleted_at` 缺失视为未删除。

## 2. 服务层：派生、删除、元信息对比

- [x] 2.1 实现普通导出元数据参数，支持 `name/owner/note`，默认名称为“第 N 版”，并标记 `provenance=generated`。
- [x] 2.2 实现 `derive_annotation_package()`：验证来源包和同一 take，复制 annotation 与视频 symlink，分配安全的 `version=max+1`，重写 `pickleball_manifest.package_id`、manifest 版本和文件引用，失败时清理孤儿目录。
- [x] 2.3 实现版本号并发保护：对 CaptureTake 加锁或处理唯一约束冲突重试，确保同一 take 不产生重复版本号。
- [x] 2.4 实现 `compare_annotation_packages(a, b)`：返回两侧元信息、统计摘要和事件级 `added/removed/moved/category_changed/winner_changed/score_anchor_changed/changed` 差异；比较只读且限制同一 take。
- [x] 2.5 实现逻辑删除：设置 `deleted_at`，隐藏默认列表并清理 Vidat dist 发布残留，但保留包目录、快照和审计。
- [x] 2.6 实现永久清理：检查审计/预览、当前投影、未删除子派生关系和受控 data root 后，删除目录、发布残留和数据库行；返回具体保护原因。
- [x] 2.7 修改 `confirm_import_preview`：创建新的 `derived` 结果包，保存来源/结果审计关系和规范化快照，来源包保持不变。
- [x] 2.8 修改当前投影应用流程：在同一事务内替换旧 Vidat 投影、保留人工/算法来源、设置 `active_vidat_package_id`，并支持从历史版本重新导入。
- [x] 2.9 保证导入数据库事务和文件系统操作的一致性：失败回滚投影和审计，并清理新建结果包目录。

## 3. 服务层：Vidat 服务停止

- [x] 3.1 在 `vidat_server.py` 增加受控服务状态文件，记录服务标识、master PID、配置路径、URL 和启动时间。
- [x] 3.2 实现服务状态查询：区分未运行、受控运行、未受控端口占用和状态异常，并校验 PID 命令行/配置归属。
- [x] 3.3 修改启动路径：避免重复启动，检测端口冲突，启动成功后写入状态文件并等待 URL 就绪。
- [x] 3.4 实现 `stop_vidat_service()`：只停止归属本系统的 Nginx master，等待 URL 不可用，返回未运行、已停止、未受控或失败状态。
- [x] 3.5 覆盖 PID 文件缺失、PID 复用、端口被其他进程占用和 Nginx 停止超时等错误，不执行无归属的端口级 kill。

## 4. API 路由

- [x] 4.1 扩展 `POST /api/vidat/capture-takes/{take_id}/packages`，接受可选 `name/owner/note` body，并返回完整版本元数据。
- [x] 4.2 新增 `POST /api/vidat/packages/{source_id}/versions`（派生，body：`name/owner/note`，201），校验来源包未删除且属于目标 take。
- [x] 4.3 新增 `PATCH /api/vidat/packages/{id}`（更新 `name/owner/note`，部分更新；不得改变内容列）。
- [x] 4.4 新增 `GET /api/vidat/packages/{a}/compare/{b}`（同一 take 的摘要和事件级差异）。
- [x] 4.5 将 `DELETE /api/vidat/packages/{id}` 定义为逻辑删除，新增 `POST /api/vidat/packages/{id}/purge` 作为受保护的永久清理。
- [x] 4.6 新增 `GET /api/vidat/service/status`、`POST /api/vidat/service/stop`，并保持现有 start 接口返回明确服务状态。
- [x] 4.7 扩展 `PackageResponse`：返回 `name/owner/note/provenance/source_package_id/created_at/imported_at/deleted_at` 和当前投影标识。
- [x] 4.8 调整导入确认响应：返回 `audit_id/source_package_id/result_package_id/active_vidat_package_id/operations`。
- [x] 4.9 为删除保护、跨 take 比较、未受控服务和导入事务失败定义稳定 HTTP 状态和中文错误信息。

## 5. 前端客户端类型与函数

- [x] 5.1 扩展 `VidatPackage` 接口：增加 `name/owner/note/provenance/source_package_id/created_at/imported_at/deleted_at` 和当前投影字段。
- [x] 5.2 增加创建包请求类型，支持导出时提交 `name/owner/note`。
- [x] 5.3 在 `analysisClient.ts` 增加 `deriveVidatPackage`、`updateVidatPackage`、`compareVidatPackages`、`deleteVidatPackage`、`purgeVidatPackage`、`getVidatServiceStatus`、`stopVidatService` 客户端函数。
- [x] 5.4 更新导入确认响应类型，能够选中新生成的结果包并显示来源/结果关系。

## 6. 前端工作台界面

- [x] 6.1 在版本列表和当前版本信息中展示 `name · 第 N 版 · provenance · 状态`，可用时展示负责人、备注、来源、创建/导入时间和当前投影。
- [x] 6.2 为“导出新版本”增加名称/负责人/备注表单，明确这是从 take 事件生成的 `generated` 版本。
- [x] 6.3 新增“从当前版本派生”表单，明确这是复制内容基线的 `derived` 版本。
- [x] 6.4 新增元数据编辑入口，PATCH 成功后刷新，不影响 annotation 内容。
- [x] 6.5 新增版本比较入口：选择两个版本，按差异类型展示事件级变化和两侧摘要。
- [x] 6.6 新增逻辑删除确认，说明审计和快照保留；对永久清理显示二次确认和后端保护原因。
- [x] 6.7 导入确认成功后自动刷新并选中新生成结果包，提示来源版本、结果版本和当前投影已切换。
- [x] 6.8 分开提供“关闭 Vidat 标签页”和“停止 Vidat 服务”；保存 `window.open` 返回的窗口引用，失败时提示手工关闭。
- [x] 6.9 加载服务状态并展示受控运行、未运行、未受控占用和停止失败状态。

## 7. 后端测试

- [x] 7.1 测试普通导出元数据、默认名称和旧包兼容字段。
- [x] 7.2 测试派生包：复制内容、重写 package identity、`provenance=derived`、来源包不变、并发版本号不冲突。
- [x] 7.3 测试元数据 PATCH 仅更新提交字段，禁止修改归档内容。
- [x] 7.4 测试事件级版本比较：摘要完整、差异类型完整、跨 take 被拒绝且不修改投影。
- [x] 7.5 测试逻辑删除：隐藏列表、保留审计/快照、清理 Vidat dist 残留。
- [x] 7.6 测试永久清理：无保护引用时删除目录和数据库行；有审计、预览、当前投影或子派生时返回具体拒绝原因。
- [x] 7.7 测试确认导入：原包 annotation 不变、结果包承载导入内容、双向审计关系正确、当前投影替换且人工/算法数据保留。
- [x] 7.8 测试导入事务失败时数据库、原投影和文件系统均回滚/清理。
- [x] 7.9 测试 Vidat 服务状态、重复启动、受控停止、PID 失联、PID 复用和未受控端口占用。

## 8. API 与前端测试

- [x] 8.1 为创建、派生、PATCH、比较、逻辑删除、purge、导入确认和服务状态 API 增加路由测试。
- [x] 8.2 更新 `VidatWorkbenchPanel.test.tsx`，覆盖导出命名、派生、元数据编辑、比较面板、删除保护、导入结果切换和服务停止提示。
- [x] 8.3 增加窗口引用处理测试：平台打开的窗口尝试关闭，普通手工标签页不误报已关闭。

## 9. CLI 兼容

- [x] 9.1 更新 `scripts/export_to_vidat.py`，支持 `--name/--owner/--note` 并输出版本元数据。
- [x] 9.2 更新 `scripts/import_from_vidat.py`，输出来源包、结果包、当前投影和审计信息。
- [x] 9.3 更新 `scripts/vidat_workbench.py`，支持列出/打开/派生/比较/逻辑删除/purge 和服务状态/停止，并复用服务层。
- [x] 9.4 更新 CLI 回归测试，确保 API 与 CLI 的版本、审计和删除语义一致。

## 10. 真实环境验收

- [x] 10.1 在真实 macOS Homebrew Nginx 环境验证服务状态、启动、停止、重启和端口冲突处理。
- [x] 10.2 使用真实 Vidat JSON 完成“导出 → 打开 → 修改 → 导入 → 比较 → 删除历史版本”的完整验收流程。
