## 1. 清理脚本（A：可重复、安全分离 fixture）

- [x] 1.1 新增 `backend/scripts/cleanup_test_uploads.py`：解析 `backend/data/uploads/*.json` 元数据，按 `source == "upload"` 且（媒体缺失或体积 < 阈值）判定 fixture 候选，默认阈值 512 KB（CLI `--threshold` 可覆盖）。
- [x] 1.2 实现保留规则：跳过 `source == "recording"` / `source == "sync_recording"`，以及 `source == "upload"` 且媒体存在且体积 ≥ 阈值的真实上传。
- [x] 1.3 默认 dry-run：打印将要移出/保留的条目与计数，不写盘；仅在 `--apply` 时执行移动。
- [x] 1.4 `--apply` 移动到 `<uploads_dir>/.cleanup-trash/<UTC时间戳>/`，同步移出同名 `.json` 与媒体文件，并在该目录写 `manifest.json`（id、original_filename、media_size、处置、移出路径）；逐条失败不中断。
- [x] 1.5 幂等：已移入 `.cleanup-trash` 的文件不重复评估；脚本可重复运行仅处理残留 fixture。
- [x] 1.6 在脚本头部与 README 注释中标明“仅移动不删除、可回收目录可手动清空”的安全约束与回滚步骤。

## 2. 测试隔离修复（B：治本，杜绝再累积）

- [x] 2.1 在 `backend/tests/conftest.py` 增加 autouse session 级 fixture `_isolate_uploads_singleton`：`config.get_settings.cache_clear()` → `get_settings()` → 原地替换 `app.services.video_service.video_service.storage = StorageService(settings)` → `VIDEOS.clear()`；teardown 再次 `VIDEOS.clear()`。
- [x] 2.2 确认该 fixture 在 `test_api_smoke.py` 通过 `client` 上传前生效（autouse 覆盖整个会话），且 `routes_video` 经由单例对象调用（`.storage` 替换对全部引用生效）。
- [x] 2.3 在 `test_api_smoke.py` 的 API 上传用例上增加 teardown 清理：测试结束后删除其上传的元数据 JSON 与媒体文件（复用 `StorageService.delete_path` 与 `video_service` 已知 id），作为独立保险。
- [x] 2.4 验证 `pytest_unconfigure` 已对临时根做 `shutil.rmtree`，会话结束无残留。

## 3. 验证与收尾

- [x] 3.1 运行 `python backend/scripts/cleanup_test_uploads.py --dry-run`，复核候选移出清单与保留清单（应保留约 15 个 >1MB 真实 mp4 及 recording 登记，移出约 350 个 fixture）。
- [x] 3.2 确认无误后 `--apply`，检查 `.cleanup-trash/<时间戳>/manifest.json` 完整。
- [x] 3.3 重启后端 + 前端，验证 Library 仅显示真实比赛视频，原 300+ .avi 不再出现。
- [x] 3.4 运行 `test_api_smoke.py` 全量，验证 `backend/data/uploads/` 中由该测试新增的 `*.json`/媒体文件数量为零增长。
- [x] 3.5（可选）在 `test_test_isolation.py` 扩展断言，覆盖“上传测试不向生产 uploads 写入”的行为；更新 `openspec/changes/cleanup-test-upload-pollution` 状态至 ready/archive。
