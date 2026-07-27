## ADDED Requirements

### Requirement: Vidat 导入后重建片段投影
系统 MUST 在确认 Vidat 导入后，以确认的规范化动作序列重建受影响 CaptureTake 的 set、game 与 rally 片段投影。

#### Scenario: 时间边界修正
- **WHEN** 确认的 Vidat 导入改变一个 rally、game 或 set 的起止时间
- **THEN** 系统 SHALL 更新重建后的对应片段范围
- **AND** SHALL 验证同层片段不重叠且子片段位于父片段范围内
