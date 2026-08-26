## Why

后端 `backend/tests/test_api_smoke.py` 通过真实 `/api/videos/upload` 接口上传合成 fixture 视频（96×96、3–40 帧的 MJPG 伪视频，或 `b"not-a-real-video"` 占位字节），这些文件写到了**生产数据目录** `backend/data/uploads/` 而非隔离的临时目录。结果是 `video_service.list_videos()` 把全部 `*.json` 元数据当作普通上传视频暴露给 `GET /api/videos`，前端 Library（`buildLibraryItems` → `listVideosCatalog`）于是把这些测试残渣当成“比赛视频”显示。当前 `backend/data/uploads/` 下约有 **300 个 .avi + 243 个微型 .mp4**（共约 350 个测试 fixture，远低于真实视频体积），它们点进去没有任何可播放的真实视频，严重污染用户视角的比赛库。问题已确认根因：测试隔离机制未对“通过 API 上传”的用例生效，且测试不清理自身产物，导致污染持续累积。

## What Changes

- **A. 一次性清理（治标）**：提供一个安全（废纸篓式、可验证）的清理命令/脚本，扫描 `backend/data/uploads/`，把测试 fixture 与真实用户上传分离——将疑似 fixture（来源为 `upload` 且媒体文件缺失或体积过小）移入本地回收目录并生成清单，**绝不 `rm` 直接删除**；保留所有真实用户视频与 `source=recording/sync_recording` 的合法登记。
- **B. 修复测试隔离（治本）**：在 pytest 会话内，保证“通过 API 上传视频”的测试不再写入生产 `uploads` 目录；无论隔离环境变量是否生效，测试都在 teardown 阶段删除其上传的元数据 JSON 与媒体文件，杜绝污染累积。
- **C（本次不做）**：不在 `video_service.list_videos()` 或 `libraryAdapter` 层做“过滤过小/非真实来源视频”的兜底逻辑，留待后续单独评估。

## Capabilities

### New Capabilities
- `upload-catalog-hygiene`：提供可重复、安全（废纸篓式 + 清单）的清理机制，把 `backend/data/uploads` 中的测试 fixture 与真实上传区分开；并固化“后端 API 上传测试不得污染生产 uploads 目录、且必须自清理”的约束。

### Modified Capabilities
（无 — 本次不改动 Library 投影契约或前端展示逻辑，C 已明确延后。）

## Impact

- 后端：`backend/tests/conftest.py`（隔离加固）、`backend/tests/test_api_smoke.py`（上传用例 teardown 清理）；新增一次性清理脚本（如 `backend/scripts/cleanup_test_uploads.py`）。
- 数据：`backend/data/uploads/` 本地运行时数据（已被 `.gitignore` 忽略，清理不影响 git 跟踪文件）。
- 前端：无代码改动（库表现由后端 catalog 自然净化）。
- 风险：清理脚本只移动、不删除，并输出保留/移出的清单，用户可在验证后手动清空回收目录。
