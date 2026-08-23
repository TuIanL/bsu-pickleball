# 提案：Vidat 标注包版本管理

## Why

当前 Vidat 标注包可以不断导出和导入，但缺少可协作的版本生命周期：用户无法用名称、负责人和备注区分分工版本，也无法看到两个版本具体改了哪些事件或安全清理历史版本。更严重的是，当前导入会就地覆盖包内容，而实时投影仍按旧包 ID 管理，无法同时保证历史归档和当前比赛视图的一致性。

同时，打开 Vidat 会启动由 Nginx 托管的本地静态服务；现有系统没有服务状态、停止和窗口生命周期管理，导致用户关闭页面后本地服务仍可能占用端口。

## What Changes

- **BREAKING：导入产生新版本**：确认导入不再覆盖来源包，而是创建不可变的 `derived` 结果版本；来源包的 annotation、manifest、规范化快照和审计内容保持可追溯。
- **版本身份与元数据**：标注包增加自定义 `name`、`owner`、`note`，同时记录 `source_package_id`、`provenance`、删除状态；普通导出和派生导出都支持自定义元数据，缺省名称为“第 N 版”。
- **派生与分工**：支持从任意同一 CaptureTake 的版本派生新包，重写包身份字段和目录引用，确保派生包可以独立导入和继续编辑。
- **详细版本比较**：比较两个版本时同时返回元信息、统计摘要和事件级差异，包括新增、删除、移动、事件类型、胜者及比分锚点变化；比较结果在前端可查看。
- **当前 Vidat 投影**：导入结果成为 CaptureTake 的当前 Vidat 投影；应用新结果前替换旧的 Vidat 投影，但保留人工和算法来源的数据。
- **删除策略**：普通“删除”采用逻辑删除，隐藏版本但保留审计和快照；只有未被审计、未被当前投影或派生关系保护的版本才允许永久清理文件和数据库记录。
- **导出和导入体验**：工作台支持导出命名、负责人/备注编辑、从当前版本派生、版本比较、删除/清理，并在导入完成后自动选中新生成版本。
- **Vidat 服务生命周期**：增加服务状态查询、启动、停止和进程归属校验；停止服务与关闭由平台打开的浏览器窗口分开处理，避免把“标签页仍在”误认为“后台服务仍在运行”。
- **CLI 同步**：现有 Vidat 导出、导入和工作台脚本同步支持元数据、派生、比较、删除/清理和服务停止语义。

## Capabilities

### New Capabilities

- `vidat-service-control`：本地 Vidat 静态服务（Nginx）的启停控制与状态查询。

### Modified Capabilities

- `vidat-annotation-package`：增加版本元数据、派生来源、逻辑删除/永久清理和事件级版本比较；明确删除不破坏审计留存。
- `vidat-annotation-import`：`confirm_import` 由就地覆盖改为创建结果版本，并原子更新当前 Vidat 投影与审计关系。
- `vidat-workbench-integration`：工作台新增命名、派生、元数据编辑、详细比较、删除/清理、导入结果切换和 Vidat 服务生命周期入口；CLI 管理能力继续保持。

## Impact

- **数据模型与迁移**：扩展 `VidatAnnotationPackage` 元数据和 `deleted_at`；为 `VidatImportAudit` 增加结果包关联；为实时状态增加当前 Vidat 投影指针；新增 Alembic 迁移并同步本地 `init_db()` 兼容迁移。
- **服务层**：修改 `backend/app/services/vidat_annotation_service.py`，实现身份安全的派生、事件级比较、逻辑删除/永久清理、导入结果包和当前投影替换；修改 `backend/app/services/vidat_server.py`，维护受控 Nginx PID/状态文件。
- **API**：扩展创建包请求；新增派生、元数据 PATCH、详细比较、逻辑删除/永久清理和服务状态/停止接口；调整导入确认响应，返回来源包、结果包和当前投影信息。
- **前端**：扩展 `src/services/analysisClient.ts` 类型和客户端；升级 `src/components/capture/VidatWorkbenchPanel.tsx` 的版本管理、比较面板、表单、确认提示和窗口/服务状态处理。
- **CLI**：更新 `scripts/export_to_vidat.py`、`scripts/import_from_vidat.py`、`scripts/vidat_workbench.py`，保持 API 与 CLI 的版本语义一致。
- **测试与兼容**：覆盖旧包默认元数据、派生身份、导入不覆盖、当前投影替换、详细比较、删除保护、Nginx 进程归属、API 和前端交互；旧数据库记录默认视为 `generated` 且未删除。
