## Context

`backend/data/uploads/` 是生产上传视频目录，前端 Library 通过 `GET /api/videos`（`video_service.list_videos()` 枚举全部 `*.json` 元数据）把其中的视频当作“比赛素材”展示。`backend/tests/test_api_smoke.py` 用 `client = TestClient(app)` 直接 POST 合成 fixture 到 `/api/videos/upload`，这些 fixture 落到了生产目录而非隔离临时目录。现状数据：

- 约 **300 个 .avi**（全部 < 50 KB，96×96 合成帧或占位符）
- 约 **243 个微型 .mp4**（< 10 KB，部分为 `b"not-a-real-video"` 16 字节）
- 仅约 **15 个 .mp4 > 1 MB** 和其余 `source=recording` 登记是真实/合法资产

隔离机制 `conftest.py:pytest_configure` 本会通过 `PICKLEBALL_UPLOADS_DIR` 环境变量把目录指向临时路径（`config.py:294` 确实读取该变量），但“通过 API 上传”的用例仍污染了生产目录——根因是模块级全局单例 `video_service`（`video_service.py` 末尾 `video_service = VideoService()`）在 `routes_video.py` 导入时即被绑定，其 `storage` 指向的内存/磁盘目录在测试期间未随隔离环境切换，且上传用例不清理自身产物，导致累积。

## Goals / Non-Goals

**Goals:**
- A：安全、可重复、可验证地分离并移出（非删除）测试 fixture，净化生产 catalog，不影响真实用户视频与合法录制登记。
- B：固化约束——后端 API 上传测试不污染生产 `uploads` 目录，且自清理，杜绝再累积。

**Non-Goals:**
- C（前端/后端 catalog 层过滤过小/非真实来源视频的兜底逻辑）按用户决定本次不做。
- 不改动 Library 投影契约 (`library-item-projection`)、不改动前端展示逻辑。
- 不删除任何文件（仅移动到回收目录，由用户后续手动清空）。

## Decisions

### 决策 1：清理脚本以“移动 + 清单”方式分离 fixture（A）

新增 `backend/scripts/cleanup_test_uploads.py`，逻辑：

1. 解析 `backend/data/uploads/` 下所有 `*.json` 元数据。
2. 判定候选 fixture 的两条规则（满足任一即判为 fixture）：
   - `source == "upload"` 且媒体文件**缺失**（`path` 指向文件不存在）；
   - `source == "upload"` 且媒体文件体积 **< THRESHOLD**（默认 `512 KB`，CLI 可覆盖）。
3. **保留**以下，绝不移动：
   - `source == "recording"` 或 `source == "sync_recording"` 的合法登记（真实录制媒体在别处）；
   - `source == "upload"` 且媒体文件存在且体积 ≥ THRESHOLD 的真实用户上传。
4. 默认 **dry-run**：只打印将要移出 / 保留的条目与计数，不写盘。
5. `--apply` 才执行：把候选的 `.json` + 同名媒体文件移动到 `<uploads_dir>/.cleanup-trash/<UTC时间戳>/`，并在该目录写入 `manifest.json`（含每条的 id、original_filename、media_size、处置=removed/kept、移出路径）。移动用 `shutil.move`，失败逐条报告不中断。
6. 幂等：已移入 `.cleanup-trash` 的文件不再参与评估；重复运行只处理残留 fixture。

**为何移动而非删除**：符合项目“废纸篓式”安全偏好；`uploads` 已被 `.gitignore` 忽略，仅本地运行时数据，用户可在验证 `manifest.json` 后手动清空回收目录。阈值 512 KB 远高于真实比赛视频（MB 级）且远高于最大 fixture（~25 KB），精确分离、零误删风险。

### 决策 2：强制全局单例在测试会话内使用隔离存储（B-主）

在 `conftest.py` 增加 **autouse session 级 fixture** `_isolate_uploads_singleton`：

1. `config.get_settings.cache_clear()` —— 清除可能被提前缓存的设置；
2. `settings = config.get_settings()` —— 此时 `PICKLEBALL_*` 已由 `pytest_configure` 设为临时路径；
3. `app.services.video_service.video_service.storage = StorageService(settings)` —— **原地替换**单例的 storage（而非重绑模块变量，避免漏掉 `routes_video` 等已绑定引用）；
4. `app.services.video_service.VIDEOS.clear()` —— 清空内存缓存，强制走隔离磁盘目录。
5. yield；teardown 再次 `VIDEOS.clear()`。

效果：所有经 `video_service.save_upload` 的写入（含 `TestClient` 上传）都落到临时目录，会话结束由 `pytest_unconfigure` 的 `shutil.rmtree(temp_root)` 整树清理，**从根上不再累积**。

### 决策 3：上传用例 teardown 自清理（B-防御）

在 `test_api_smoke.py` 已通过 `client` 上传视频的用例上套用 `teardown` 清理：测试结束后删除其上传产生的元数据 JSON 与媒体文件（无论落在何目录）。这是与决策 2 正交的保险——即使将来单例隔离因重构失效，上传用例也不再污染。清理函数复用 `StorageService.delete_path` 与 `video_service` 已知 id。

### 备选方案（已否决）

- **仅在前端 `listVideosCatalog` 过滤**：即方案 C，被用户明确延后；且只隐藏不根治，测试库会继续膨胀。
- **重绑 `app.services.video_service.video_service` 模块变量**：会因 `routes_video` 等在导入时固定引用旧对象而漏网，不如“原地替换 `.storage`”稳妥。
- **清理脚本直接 `rm`**：违背安全偏好，一旦阈值误判即不可逆丢失真实视频。

## Risks / Trade-offs

- [Risk] 真实用户上传了极小视频（< 512 KB）→ 被误判为 fixture 移出。→ Mitigation：dry-run 先预览清单；阈值可调；真实比赛视频几乎必 > 1 MB，误判概率极低；移出到回收目录可随时还原。
- [Risk] 决策 2 仍可能因 `get_settings` 早期缓存时序问题未完全覆盖 → Mitigation：决策 3 的 teardown 自清理作为独立保险，双重保障。
- [Risk] 移动后若 Library 仍展示旧项 → Mitigation：刷新 `video_service.VIDEOS` 与重启后端即可；回收目录内容不影响 catalog（已从 uploads 主目录移出）。

## Migration Plan

1. 实施 B（conftest 隔离 fixture + test_api_smoke teardown）并跑测试，确认不再向 `backend/data/uploads` 写入。
2. 运行 `python backend/scripts/cleanup_test_uploads.py --dry-run` 复核候选清单与保留清单。
3. 确认无误后 `--apply` 移动；检查生成的 `manifest.json`。
4. 重启后端 + 前端，验证 Library 仅剩真实比赛视频。
5. 用户手动清空 `.cleanup-trash/<时间戳>/`（可选）。
6. Rollback：若误移，从 `manifest.json` 列出的 `removed_path` 将文件移回 `backend/data/uploads/`（保留原 `.json` 与媒体同名即可）。

## Open Questions

- 真实用户上传的最小合理体积阈值是否需要按项目约定固化（如 512 KB）还是放宽到 256 KB？默认 512 KB，待用户确认。
- 是否将“测试不得污染生产数据目录”写入 CI 检查（`test_test_isolation.py` 已断言路径非生产目录，可扩展覆盖 uploads 写入行为）？本次先以 conftest + teardown 实现，CI 断言增强可作为后续小步。
