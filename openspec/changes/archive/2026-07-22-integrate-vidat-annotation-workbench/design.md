## Context

项目现有 `export_to_vidat.py`、`import_from_vidat.py` 与 `vidat_workbench.py` 已能把时间线转换为 Vidat action 标注并启动本地 Vidat，但导入脚本直接写 SQLite 的 `SessionTimelineEvent`。这种做法没有保存标注版本、没有差异确认，也绕开了 `CodingAction`、FSM 和 `CaptureSegment` 的派生关系；更改一个回合胜者后，比分和比赛结果可能不一致。

Vidat 已作为本地静态发行包安装，适合承担逐帧视频、时段、动作和目标标注。主项目的职责是采集、任务管理、语义化比赛数据、模型分析与报告，不能复制 Vidat 的完整 UI。

## Goals / Non-Goals

**Goals:**

- 让已完成且视频就绪的 CaptureTake 可由一次操作导出并打开 Vidat。
- 让每次导出和回导都有可复现的文件版本、视频/FPS 校验和操作审计。
- 允许用户先审阅结构化差异，再确认把 Vidat 变更应用到比赛数据。
- 将 Vidat 的时间与类别标注转换为可重放的比赛语义动作，并重建比分、事件和片段投影。
- 保留训练可用的原始 Vidat JSON 及语义化快照。

**Non-Goals:**

- 不在 React 前端复刻 Vidat 的逐帧、框选、骨架或 action 编辑 UI。
- 不修改或打包第三方 Vidat 前端。
- 不在本变更训练新模型、定义 COCO/Pose 完整数据集或自动识别比赛事件。
- 不支持多用户并发编辑同一标注包；导入以单机人工复核为目标。

## Decisions

### 1. 标注包是文件化、版本化的交换边界

每个导出创建 `annotation_package` 记录和独立目录，保存 `manifest.json`、Vidat JSON、标签配置及视频的只读引用或软链接。manifest 记录 CaptureTake ID、视频 fingerprint、FPS、导出时间、源时间线 revision 和 schema version。刷新导出创建新版本而不覆写已导入版本。

直接把文件固定写进 Vidat `dist/annotation` 虽然简单，但会在覆盖、多人副本和视频替换时失去可追溯性，因此不采用；打开工作台时再将指定包安全地发布或链接到 Vidat 可访问目录。

### 2. Vidat 只拥有视觉时间标注，项目拥有比赛语义

Vidat action 使用稳定标签 ID 表达 set/game/rally/暂停等范围和 `rally_end` 的 winner、validity 等元数据。主项目将导入动作规范化为 `AnnotationOperation`，再转换为 `CodingAction` 或显式 `correct_score` 锚点。比分不作为每个事件的手工冗余快照，而由既有 ruleset reducer 从回合结果重放。

备选方案是让 Vidat description 成为完整业务数据库；该方案难以结构化编辑、校验和推导后续比分，且不适合 API/报告消费，因此不采用。

### 3. 导入分为解析、预览、确认三个阶段

上传或选择 Vidat JSON 后，服务首先校验 manifest、视频名、FPS、标签 ID、时间范围、配对结构及同层级范围重叠，生成只读 `ImportPlan`。前端展示新增、删除、移动、类型变更、回合胜者变化，以及受影响的后续比分/局/盘摘要。仅确认 API 才在一个事务中创建导入版本、替换该包拥有的语义来源并重放投影。

现有 CLI `--preview` 保留为同一解析器的文本视图；`--apply` 必须要求确认令牌，防止脚本绕开预览。

### 4. 重建以已确认的规范化动作序列为真相

系统为导入动作分配确定性顺序：先按时间，再按层级开始/结束规则，最后按原 action index 破除同一帧并列。应用时生成或替换带 `source=vidat_import` 和 `annotation_package_version_id` 的 CodingAction；随后使用现有 reducer 重放 LiveCodingState，并以重放结果重建 TimelineEvent 与 CaptureSegment。人为 `score_correction` 标签映射为修正锚点，不直接覆写 LiveCodingState。

直接更新 `SessionTimelineEvent` 的方案无法维护 CodingAction 与投影的因果关系，故废弃为导入写入路径。

### 5. 工作台集成优先本地 API，CLI 保持兼容

后端提供列出可导出 CaptureTake、创建/刷新包、获取启动 URL、创建导入预览和确认导入的 REST API。前端在录制任务或片段工作区展示状态化操作。Python CLI 改为调用同一服务层或复用同一纯函数，支持批处理和故障排查；启动器只负责发现本地 Vidat 与打开 URL，不能修改用户任意路径。

## Risks / Trade-offs

- [Vidat description 被人工改坏] → manifest 保存标签/元数据映射；导入校验无法识别的 ID 或字段时只生成阻塞性预览错误，不写库。
- [导入回合后改变大量后续比分] → 预览显示受影响范围和最终状态；确认前不落库，并保存可回退的导入版本。
- [视频替换或 FPS 错误造成时间偏移] → manifest 校验视频 fingerprint、时长和 FPS；不匹配时拒绝确认并要求重新导出。
- [双摄尚未合并] → 仅对存在可播放主视频且合并状态完成的 CaptureTake 启用 Vidat 操作。
- [大视频复制占用磁盘] → 默认软链接，软链接不可用时明确提示用户选择复制；不隐式复制。
- [训练数据版本不可复现] → 保存原始 Vidat JSON、manifest 与确认后的语义快照，不用数据库当前状态替代历史标注。

## Migration Plan

1. 添加标注包及导入审计持久化模型，现有脚本继续只读运行。
2. 将现有导出逻辑抽取为包生成服务，增加 manifest 校验和 CLI/API 测试。
3. 增加导入解析与差异预览，初期只允许 preview，不启用写入。
4. 实现确认导入、动作重放和投影重建后，再把前端确认入口开放给完成的视频任务。
5. 保留原有脚本作为兼容入口，但 `--apply` 切换至确认令牌流程；回滚时关闭确认 API，不删除标注包和审计数据。

## Open Questions

- Vidat 中回合结果采用独立 `rally_end` action，还是在 `rally` 区间 description 中携带 winner；实施前需用一个真实比赛样本验证操作效率。
- 初期是否只支持单路/主机位视频，还是在 Vidat 内将双摄分别标注并以校准偏移合并；本提案默认先支持主机位。
- 是否允许在导入时删除系统原有的非 Vidat 人工 CodingAction；默认仅替换同一标注包来源创建的动作，其他来源在预览中显示冲突。
