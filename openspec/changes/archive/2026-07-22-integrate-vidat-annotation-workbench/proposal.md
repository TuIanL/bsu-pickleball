## Why

首次真实比赛拍摄产生的关键事件、回合边界和比分结果存在错误，当前主项目的片段管理能力不足以承担逐帧、高频的视频标注。项目已经具备 Vidat 导入导出原型，应将其完善为可靠的日常标注入口，同时确保人工修正不会使后续比分、局结果和分析片段失去一致性。

## What Changes

- 为每个已完成且视频可用的 CaptureTake 建立可追溯的 Vidat 标注包：包含视频引用、匹克球事件标签配置、初始时间线和导出清单。
- 提供一键导出/刷新、打开 Vidat、定位标注文件和导入预览的工作流，自动处理视频选择、FPS 和本地 Vidat 路径，避免用户手工整理文件。
- 将 Vidat 作为视频时间标注层，支持回合、局、盘、暂停、非比赛段及单点事件的增删、类别和起止时间修正。
- 将回导改为“解析与差异预览 -> 用户确认 -> 受控应用”的流程，保存原始 Vidat JSON 和导入记录，禁止未经确认的直接写库。
- 依据导入后的事件语义重建 CodingAction、比分状态、TimelineEvent 和 CaptureSegment；回合结果变化必须自动推导后续比分、局/盘结果和胜者。
- 为训练数据导出保留稳定的 Vidat 原始标注与项目语义化标注快照，供后续动作识别、检测、姿态等数据集转换使用。

## Capabilities

### New Capabilities
- `vidat-annotation-package`: 为 CaptureTake 生成、刷新、保存和校验可复现的 Vidat 视频标注包。
- `vidat-workbench-integration`: 从项目中启动 Vidat，并提供面向本地操作的导出、打开和导入预览入口。
- `vidat-annotation-import`: 校验、预览、确认并审计 Vidat action 标注的回导，同时重建派生的比赛数据。

### Modified Capabilities
- `session-timeline-events`: 导入的人工标注成为具有来源、版本和审计信息的时间线事件来源。
- `segment-editing`: 经确认的 Vidat 时间边界变更必须同步更新或重建局、盘和回合片段。
- `rally-scoring-fsm`: 回放经人工修正的回合结果时，系统必须重算后续比分、局结果和比赛胜者。
- `score-correction`: 从 Vidat 导入的比分锚点必须按既有比分修正规则进入重放，而非直接覆写派生状态。

## Impact

- 后端：新增 Vidat 标注包/导入服务、持久化模型与 REST API；调整 `coding_actions_service` 的可重放语义和比赛状态快照逻辑。
- 工具脚本：完善 `scripts/export_to_vidat.py`、`scripts/import_from_vidat.py` 和 `scripts/vidat_workbench.py`，并保持命令行批处理可用。
- 前端：在已完成录制或片段工作区增加 Vidat 工作台操作、导入差异预览、确认与错误状态。
- 本地依赖：继续使用已安装的 Vidat 静态发行包与 FFprobe；不把 Vidat 前端代码复制进本项目，也不引入云端服务。
