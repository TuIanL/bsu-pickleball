## Context

当前系统已经有 Field Session 作为场边采集任务容器，保存 `capture_mode`、`match_format`、`camera_setup`、场地和状态等上下文。RecordingSession 可以可选关联 Field Session，并在 Field Session 内启动录制时继承球场名称和单双打信息。

现有实现有一个重要约束：Field Session 使用 SQLAlchemy/SQLite 持久化，而 RecordingSession 仍使用 `data/recordings/sessions/{session_id}.json` 保存 metadata。因此时间线事件应以 Field Session 为数据库主关系，对 RecordingSession 只保存 `recording_session_id` 字符串引用并通过现有 `session_service` 做存在性和归属校验。

这次 change 的目标是把场边人工操作转化为可查询、可编辑、可供后续分析读取的结构化时间线，而不是实现自动识别算法。

## Goals / Non-Goals

**Goals:**

- 为 Field Session 新增 `SessionTimelineEvent` 数据模型和 REST API。
- 支持人工记录比分、换边、非比赛时间、局/盘/回合边界、备注和自定义标记等事件。
- 保存视频内时间 `timestamp_ms` 和真实时间 `occurred_at`，让事件既能对齐视频，也能对齐现场日志。
- 在前端 Field Session 控制台提供低摩擦的人工打点面板和事件列表。
- 保持当前直接录制入口不受影响。
- 为后续算法事件和人工修正预留 `source=algorithm/corrected`。

**Non-Goals:**

- 不实现自动比分识别、自动换边识别或自动回合切分。
- 不引入双摄 RecordingGroup 或跨摄像头同步模型。
- 不要求分析 pipeline 在本 change 中消费 timeline events。
- 不迁移 RecordingSession 的 JSON metadata 到数据库。
- 不做 soft delete 或完整审计历史。

## Decisions

### 1. 事件强关联 Field Session，弱引用 RecordingSession

`SessionTimelineEvent.field_session_id` 使用数据库关系关联 Field Session；`recording_session_id` 作为 nullable string 保存 RecordingSession 的 `session_id`。

理由：Field Session 已在 SQLite 中，事件也适合放入同一数据库；RecordingSession 目前是文件 metadata，强行建外键会迫使本 change 扩大到录制存储迁移。

替代方案：把 RecordingSession 先迁入数据库，再为事件建立外键。该方案长期更统一，但会把“人工时间线”问题变成录制系统重构，风险和测试面都更大。

### 2. `payload_json` 承载事件扩展数据

事件表只固定保存通用字段：`event_type`、`source`、`timestamp_ms`、`occurred_at`、`label`、`note` 和 `payload_json`。比分、局数、发球方、换边后队伍、备注文本、回合结果等差异化信息进入 `payload_json`。

理由：不同事件的数据形状差异很大，后续还会接入算法事件；使用 JSON 可以减少频繁数据库迁移。

替代方案：为比分、局数、队伍方向等建立一组固定列。该方案查询更强，但第一版字段会快速膨胀，且无法覆盖工程调试和自定义标记。

### 3. 时间戳以 `timestamp_ms` 为分析主轴，`occurred_at` 为对齐辅助

录制进行中打点时，前端优先提交相对当前录制的 `timestamp_ms`；如果未提交且带有有效 `recording_session_id`，后端根据 RecordingSession 的 `started_at` 和当前时间兜底计算。录制结束后的补标必须允许用户显式提交 `timestamp_ms`。

理由：视频分析消费的是视频内时间；真实世界时间只负责多日志或未来多摄对齐。

替代方案：只保存 `occurred_at`，分析时动态换算。该方案会让回放补标和剪辑后的素材对齐变复杂。

### 4. 事件类型全量枚举，UI 首版分模式暴露常用动作

后端枚举保留 `session_note`、`non_play_start/end`、`game_start/end`、`set_start/end`、`rally_start/end`、`score_update/correction`、`side_change`、`timeout_start/end`、`drill_start/end`、`custom_marker`。前端按 `capture_mode` 显示高频按钮：比赛模式以比分、局、换边、非比赛和备注为主；练习模式以练习片段和重点标记为主；工程模式以异常/调试标记为主。

理由：后端契约为后续能力留空间，前端保持场边操作简洁。

替代方案：只定义 UI 当前用到的少量类型。该方案实现更小，但很快会在算法事件或练习模式扩展时再次修改 schema。

### 5. Field Session 删除保护包含时间线事件

如果 Field Session 已有任何 timeline events，即使没有录制，也不能直接删除。

理由：时间线事件就是现场采集资产；误删会丢失后续分析先验。

替代方案：删除 Field Session 时级联删除事件。该方案操作简单，但和“已有录制阻止删除”的现有保护语义不一致。

## Risks / Trade-offs

- [Risk] `recording_session_id` 没有数据库外键，可能引用已删除的 JSON metadata → 创建/更新时通过 `session_service.get_session()` 校验存在性和归属；列表时允许历史事件保留字符串引用。
- [Risk] 前端和后端同时计算时间戳可能产生轻微偏差 → 前端提交值优先，后端兜底只用于缺省场景，并在响应中返回最终 `timestamp_ms`。
- [Risk] `payload_json` 灵活但弱类型，后续分析消费可能遇到字段不一致 → schema 和 UI 对常见事件生成稳定 payload key，测试覆盖比分和备注等主路径。
- [Risk] 事件按钮过多影响场边操作 → UI 只暴露当前模式的常用动作，完整类型通过备注/自定义标记或编辑弹窗补充。
- [Risk] SQLite 表新增对既有部署需要建表 → 应用启动继续使用 `Base.metadata.create_all()` 注册新表；回滚时可停止使用新 route，不影响既有 Field Session 和 RecordingSession。

## Migration Plan

1. 新增 `session_timeline_events` 表模型并注册到数据库初始化。
2. 发布后应用启动自动创建新表，既有 Field Session 和 RecordingSession 数据保持不变。
3. 前端在未选择 Field Session 或直接录制模式下不显示 Field Session 时间线打点能力，保持旧流程。
4. 若需要回滚，移除前端入口和 API route 即可；已创建事件表可暂留，不影响旧功能。

## Open Questions

- Field Session 级事件在没有 `recording_session_id` 时，`timestamp_ms > 0` 是否解释为相对 Field Session `started_at`？本设计允许保存，但 UI 首版主要使用 `timestamp_ms=0` 的任务备注。
- `source=corrected` 是否只表示人工修正算法事件？本设计按此解释；普通人工编辑仍保持 `manual`。
- 后续分析 pipeline 何时开始读取 timeline events，应由单独 change 定义输入契约。
