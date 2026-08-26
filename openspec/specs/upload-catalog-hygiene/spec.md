# upload-catalog-hygiene Specification

## Purpose

确保 `backend/data/uploads/` 作为生产上传目录，只保留真实用户上传与合法录制登记，不被后端自动化测试的 fixture 污染；并提供安全、可重复、可回滚的清理手段，将历史残留的测试 fixture 与真实资产分离。本 capability 同时约束测试隔离行为，从根上杜绝测试产物再次累积到生产目录。

## Requirements

### Requirement: 安全的 uploads 清理命令
系统 SHALL 提供一个清理命令/脚本，将 `backend/data/uploads/` 中的测试 fixture 与真实用户上传分离。该命令 MUST 以“移动 + 清单”方式执行，**绝不直接删除文件**，并默认 dry-run（仅预览），仅当显式传入应用参数时才执行移动。

#### Scenario: dry-run 默认预览不写盘
- **WHEN** 不带 `--apply` 运行清理命令
- **THEN** 命令只打印将要移出与保留的条目及计数，且 `backend/data/uploads/` 内容不发生任何变更

#### Scenario: 按来源与体积识别 fixture
- **WHEN** 元数据 `source == "upload"` 且其媒体文件缺失或体积小于阈值（默认 512 KB）
- **THEN** 该条目 MUST 被判定为 fixture 候选

#### Scenario: 保留真实与合法资产
- **WHEN** 元数据 `source == "recording"` 或 `source == "sync_recording"`，或 `source == "upload"` 且媒体文件存在且体积不小于阈值
- **THEN** 该条目 MUST 被保留，不被移动

#### Scenario: 应用模式移动到可回收目录并写清单
- **WHEN** 传入 `--apply`
- **THEN** 命令将候选的 `.json` 与同名媒体文件移动到 `<uploads_dir>/.cleanup-trash/<UTC时间戳>/`，并在该目录写入 `manifest.json`（含每条 id、original_filename、media_size、处置结果、移出路径），逐条失败不中断整体

#### Scenario: 幂等重复运行
- **WHEN** 对已经过一次清理的目录再次运行命令
- **THEN** 已移入 `.cleanup-trash` 的文件不再被评估，命令只处理仍残留的 fixture

### Requirement: 后端上传测试不得污染生产 uploads 目录
后端中通过 API（`/api/videos/upload`）上传视频的测试 MUST 在隔离的临时存储中运行，且 MUST 在测试结束后清理其产生的上传元数据与媒体文件，确保 `backend/data/uploads/`（生产目录）不残留任何测试产物。

#### Scenario: 测试会话内全局单例指向隔离存储
- **WHEN** pytest 会话启动并配置隔离环境变量后
- **THEN** 全局 `video_service` 单例的 storage MUST 指向临时目录，且内存缓存 `VIDEOS` 被清空，使经 API 上传的文件写入临时目录而非生产 `uploads` 目录

#### Scenario: 上传用例 teardown 自清理
- **WHEN** 一个通过 `TestClient` 上传视频的测试结束
- **THEN** 该测试上传产生的元数据 JSON 与媒体文件 MUST 被删除（无论落在哪个目录）

#### Scenario: 会话结束临时根被整树清理
- **WHEN** pytest 会话结束
- **THEN** 隔离临时根目录 MUST 被递归删除，测试期间写入的上传产物不残留于生产目录

#### Scenario: 生产目录无测试残渣
- **WHEN** 在隔离修复后完整运行 `test_api_smoke.py`
- **THEN** `backend/data/uploads/` 中由该测试产生的 `*.json` 元数据与媒体文件数量 MUST 为零增长（仅保留修复前已存在的存量）
