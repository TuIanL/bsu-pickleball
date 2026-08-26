## Context

当前工作台已经能在 CaptureTake 上保存逐球事实，但页面默认面对完整比赛视频，并要求用户在详细表单中逐项填写。真实验收时，已有 CaptureTake 的时间轴包含 38 个回合，而页面显示“候选 0”，原因是候选适配器只读取当前进程内的 `mock_analysis.JOBS`，没有扫描录制目录中已经保存的分析产物。

本 change 需要降低第一批校准的人工成本，同时保持 `scoring-calibration-annotation.v1` 的事实语义和 Gold Set 生命周期不变。用户只需要抽样查看少量回合并快速确认发球、接发和不可观察情况；详细字段仍然保留，但不应阻塞最小校准流程。

## Goals / Non-Goals

**Goals:**

- 将标注入口从“完整视频逐球编辑”转为“回合抽样校准队列”。
- 默认从有效 rally 片段中均匀抽取 12 个回合，并允许切换到全部回合。
- 从 CaptureTake 的 `session_dir/analysis/job-*` 中发现已落盘的候选事件，按视频 ID 过滤并保留 job/artifact provenance。
- 提供发球入界、发球失败、接发入界、接发不可观察和跳过等快捷决定。
- 自动填充回合、机位、证据时间窗和最小字段；高级字段继续可编辑。
- 展示处理进度，支持保存后自动进入下一个抽样回合。

**Non-Goals:**

- 不把算法候选直接视为人工真值。
- 不在本 change 中训练击球识别模型或生成六维评分、Overall 分数。
- 不删除现有详细标注表单、候选复核、Gold Set 锁定和 revision 能力。
- 不修改 `CaptureSegment`、原始视频或已有分析 artifact。

## Decisions

### 1. 以 rally 片段作为抽样单位

抽样队列从当前 CaptureTake 的未 superseded `rally` 片段生成，默认按时间均匀取 12 个样本，并保存样本相对原始片段的引用。这样用户看到的是短回合窗口，而不是一条 11 分钟的视频；需要全量复核时仍可选择“全部回合”。

备选方案是按固定秒数切窗，但固定切窗可能把回合截断，也无法直接关联已有的回合上下文，因此不采用。

### 2. 快捷决定复用现有 annotation API

快捷按钮只负责把最小事实转换为现有 `AnnotationUpsertRequest`：阶段、机会状态、结果、落点可观察性、事件时间、证据窗口和回合引用。保存仍经过现有校验和 revision 语义，不新增第二套事实表。

快捷决定的默认值为：发球/接发阶段由按钮确定，`eligible` 配合 `in_play/net/out`，不可观察接发使用 `unobservable + unknown + unobservable + unknown`。击球人、区域、置信度和备注进入高级表单，可在需要时补充。

### 3. 从 CaptureTake 存储目录发现候选

候选适配器首先读取 CaptureTake 的 `session_dir`，扫描有限深度的 `analysis/job-*/serve_events.json`、`serve_debug_candidates.json` 和可用的 shot/rally 事件文件；只接受候选 payload 中的 `video_id` 与 CaptureTake 的 registered `video_ids` 匹配的 artifact。每条候选携带 job ID、artifact 文件名、检测器版本、置信度和覆盖诊断。

适配器继续兼容当前内存任务 registry，但不要求后端重启后任务仍存在于内存。没有候选时，页面展示“没有可读取的落盘候选及原因”，并允许人工快捷标注。

### 4. 详细表单作为高级信息

快速模式默认显示回合视频、候选、快捷按钮和进度；现有详细表单放入“补充字段”折叠区。用户可以从时间线或队列打开完整编辑，且高级编辑修改后仍通过原有保存、校验和锁定流程。

## Risks / Trade-offs

- **候选文件覆盖不完整** → 展示 artifact coverage/warning，候选只作定位建议；没有候选的回合仍可手动处理。
- **均匀抽样遗漏特殊情况** → 提供“全部回合”和手动加入回合入口，后续可增加按 warning/不确定性过采样。
- **快捷默认值被误用** → 快捷按钮使用明确中文语义，保存后在队列中显示结果；不可观察永远保存为 unknown，不推断为失败。
- **外置磁盘不可用** → 候选区域显示存储不可读原因，不影响本地人工标注工作台加载和 draft 保存。

## Migration Plan

1. 不新增数据库表，不改变既有标注包和 Gold Set schema。
2. 增加候选落盘扫描和抽样队列读取逻辑，旧的内存候选适配作为兼容路径保留。
3. 前端默认进入抽样快速模式，详细编辑仍可展开；旧 revision 数据继续按原方式加载。
4. 通过真实 CaptureTake 验收后，继续使用原有 reviewed/locked 流程；若快速模式出现问题，可退回详细模式，不影响已保存数据。

## Open Questions

- 首批校准默认抽样数暂定为 12；如果第一轮证据仍不足，再扩大到 20 或切换全部回合。
- 接发候选如果暂时没有可靠的算法事件，第一版由回合窗口加快捷人工事实承载，不把不完整候选伪装成自动识别结果。
