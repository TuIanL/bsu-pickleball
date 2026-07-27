# Vidat 标注工作台

Vidat 负责视频的逐帧时间标注，项目数据库负责比赛语义、计分、片段和分析结果。不要在 Vidat description 中直接维护派生比分。

注意：Vidat 2.x 的 `actionAnnotationList[].start/end` 使用秒（允许小数），而 `video.frames` 和 `keyframeList` 使用帧号。导出器已按该格式生成；如果旧链接中的动作显示为几千秒，请重新导出一个标注包后再打开。

## 本地配置

默认 Vidat 目录为 `/Users/tuian/Documents/大学/竞赛/大创/匹克球/摄像头录制/tennistest` 。可以用下列环境变量覆盖：

```bash
export PICKLEBALL_VIDAT_DIR=/path/to/tennistest
export PICKLEBALL_VIDAT_DIST=/path/to/tennistest/dist
export PICKLEBALL_VIDAT_URL=http://localhost:8888
```

启动器不会修改 Nginx 配置，也不会默认复制大视频。标注包使用只读软链接；只有明确传入 `--copy-video` 才复制。

## 日常流程

1. 在已完成录制的回放页点击“导出新版本”。每次刷新都创建不可变的新版本。
2. 点击外链图标打开 Vidat，修改 set/game/rally 边界、回合胜者、备注或比分修正锚点。
3. 从 Vidat 保存 annotation JSON，回到回放页选择该文件。
4. 检查新增、删除、移动、类别/胜者/比分锚点变化及最终胜者。有阻塞错误时不能确认。
5. 确认后使用 30 分钟有效的单次令牌写入，并刷新比分、时间线和片段。

CLI 等价命令：

```bash
python scripts/vidat_workbench.py --list
python scripts/export_to_vidat.py <capture_take_id>
python scripts/vidat_workbench.py --package <package_id> --no-launch
python scripts/import_from_vidat.py --package <package_id> --file annotation.json --preview
python scripts/import_from_vidat.py --package <package_id> --file annotation.json --apply --confirmation-token <token>
```

## 失败恢复

- “主机位视频尚未就绪”：先完成分片合并或视频登记；双摄任务在没有 `*_merged.mp4` 时不可导出。
- FPS、视频身份或帧边界不匹配：不要强制导入，从当前 CaptureTake 重新导出新包。
- 同层重叠或父子范围错误：在 Vidat 中调整边界后重新预览。
- 令牌过期、已使用或文件变化：重新选择 JSON 生成预览。失败的确认事务会回滚，原预览保留用于诊断。

## 训练数据工件

每个版本位于 `backend/data/vidat-annotations/<capture_take_id>/vNNN-*`，包含 `manifest.json`、`annotation.json`、`config.json` 和视频引用。确认后，数据库同时保留原始 Vidat JSON、内容哈希、导入审计及规范化语义快照。

后续数据集转换应以 `manifest.json` 锁定视频 fingerprint/FPS，以原始 `annotation.json` 生成动作识别时段，以规范化快照生成回合结果和比分标签。目标检测、姿态或 COCO 转换器必须读取该版本工件，不得用数据库“当前状态”代替历史标注。

## 2026-07-22 真实视频验证

- 双摄已合并：`ct_c0b48c57bbeb` 的主机位 `174_merged.mp4`，1920x1080、60 FPS、532.783 秒。成功生成 v2 包 `vap_3a1c6b6ca687`、发布 Vidat URL、预览并确认导入。
- 单视图链路：上述主机位作为独立标注视频验证，包中仅软链接该视图，不依赖副机位。
- 确认结果：审计 `via_aee222d51619`，生成 2 条 CodingAction、2 条 TimelineEvent、1 个 rally CaptureSegment，原始 JSON、manifest 和语义快照均可独立读取。
- 未合并状态：没有有效主视频的 CaptureTake 被拒绝，单元测试覆盖此路径。
