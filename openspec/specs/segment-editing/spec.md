## ADDED Requirements

### Requirement: Segment 边界修正（唯一边界真相）

系统 MUST 将人工修正与事件推导分开存储。`start_ms`/`end_ms` 为事件推导原始值，`corrected_*` 为人工修正。effective 值通过计算得出，不存数据库。

#### Scenario: effective 值使用 is not None

- **WHEN** 计算 effective_start_ms
- **THEN** SHALL 返回 `corrected_start_ms is not None ? corrected_start_ms : start_ms`
- **AND** SHALL NOT 使用 `or` 短路（避免 `corrected_start_ms=0` 被跳过）

#### Scenario: 恢复原边界

- **WHEN** 用户请求 `POST /api/capture-segments/{id}/reset-boundary-correction`
- **THEN** `corrected_start_ms` SHALL 设置为 null
- **AND** `corrected_end_ms` SHALL 设置为 null
- **AND** `edit_version` SHALL +1

### Requirement: Segment 编辑乐观锁

系统 MUST 使用 `edit_version` 防止并发覆盖。

#### Scenario: 版本匹配

- **WHEN** PATCH 请求携带 `expected_version` 且与当前 `edit_version` 匹配
- **THEN** 更新成功，`edit_version +1`

#### Scenario: 409 冲突

- **WHEN** `expected_version` 不匹配
- **THEN** 返回 409 Conflict

### Requirement: 非破坏式拆分

系统 MUST 在 Rally 拆分时保留原 Segment（标记为 superseded），创建两个新 active Segment。

#### Scenario: 拆分 Rally

- **WHEN** `POST /api/capture-segments/{id}/split` 并提交 `split_ms`
- **AND** segment 为 rally 且 active
- **AND** `split_ms - start_ms > 500ms` 且 `end_ms - split_ms > 500ms`
- **THEN** 原 Rally edit_status SHALL 变为 `superseded`
- **AND** 创建两个新 Rally（R-A、R-B），edit_status = `active`
- **AND** 创建 SegmentEditOperation 记录（operation_type = `split`）

### Requirement: 非破坏式合并

系统 MUST 在 Rally 合并时保留原 Rally（标记为 superseded），创建新合并 Rally。

#### Scenario: 合并相邻 Rally

- **WHEN** `POST /api/capture-segments/merge` 并提交 2 个 segment_id
- **AND** 同为 rally、同一父 game、相邻、间隙 < 500ms
- **AND** 中间无其他 active Rally、无进行中分析任务
- **THEN** 原 Rally edit_status SHALL 变为 `superseded`
- **AND** 创建新的合并 Rally，edit_status = `active`

### Requirement: Segment 归档

系统 MUST 支持 archive/restore 而非硬删除。

#### Scenario: 归档 Segment

- **WHEN** `POST /api/capture-segments/{id}/archive`
- **THEN** `edit_status` SHALL 变为 `archived`

#### Scenario: 恢复归档

- **WHEN** `POST /api/capture-segments/{id}/restore`
- **THEN** `edit_status` SHALL 恢复为 `active`

#### Scenario: 允许硬删除的条件

- **WHEN** Segment 无子 segment、无分析引用、无编辑历史
- **THEN** 允许 `DELETE /api/capture-segments/{id}` 物理删除

### Requirement: 编辑操作审计

系统 MUST 记录所有编辑操作用于追溯。

#### Scenario: 创建编辑操作记录

- **WHEN** 执行拆分/合并/归档/边界修正
- **THEN** 创建 SegmentEditOperation 记录
- **AND** 记录 input_segment_ids 和 output_segment_ids

### Requirement: 层级时间约束

系统 MUST 在编辑时校验时间边界约束。

#### Scenario: 边界在录制范围内

- **WHEN** 修正边界
- **THEN** `0 <= effective_start_ms < effective_end_ms <= capture_take.duration_ms`

#### Scenario: Rally 在父 game 范围内

- **WHEN** 修正 Rally 边界
- **THEN** Rally effective_start SHALL >= 父 game effective_start
- **AND** Rally effective_end SHALL <= 父 game effective_end

#### Scenario: 父片段必须包含子片段

- **WHEN** 修正 game 边界
- **AND** 新的 effective 范围不包含某 active Rally
- **THEN** 拒绝修改，返回 400

#### Scenario: 相邻 Rally 不重叠

- **WHEN** 创建 active Rally
- **THEN** 同一父 game 下，前一 Rally.rally_end <= 当前 Rally.rally_start

### Requirement: Vidat 导入后重建片段投影
系统 MUST 在确认 Vidat 导入后，以确认的规范化动作序列重建受影响 CaptureTake 的 set、game 与 rally 片段投影。

#### Scenario: 时间边界修正
- **WHEN** 确认的 Vidat 导入改变一个 rally、game 或 set 的起止时间
- **THEN** 系统 SHALL 更新重建后的对应片段范围
- **AND** SHALL 验证同层片段不重叠且子片段位于父片段范围内
