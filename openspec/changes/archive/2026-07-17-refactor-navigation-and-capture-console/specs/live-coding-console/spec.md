## ADDED Requirements

### Requirement: MiniTimeline 等距时间刻度

系统 MUST 使用等距整洁时间刻度代替当前的三点窗口边界标签。

#### Scenario: 刻度计算与渲染

- **WHEN** MiniTimeline 渲染
- **THEN** 时间刻度区域 SHALL 显示多个等距的时间标签
- **AND** 标签值 SHALL 为整洁的时间值（如 `0:00`、`0:30`、`1:00`），而非窗口边界的原始 ms 值
- **AND** 系统 SHALL 按窗口宽度动态选择间隔单位：
  - 窗口 < 30s → 每 5 秒一个刻度
  - 窗口 < 60s → 每 10 秒一个刻度
  - 窗口 < 5min → 每 30 秒一个刻度
  - 窗口 >= 5min → 每 1 分钟一个刻度
- **AND** 每个刻度标签 SHALL 与对应像素位置对齐
- **AND** 刻度线 SHALL 在时间轨道的背景中显示为浅灰竖线

#### Scenario: 刻度与播放头无关

- **WHEN** 播放头移动
- **THEN** 刻度标签 SHALL 不随播放头移动
- **AND** 刻度 SHALL 相对视口窗口保持固定

### Requirement: MiniTimeline 重点标记轨道

系统 MUST 在 MiniTimeline 中新增重点标记独立轨道。

#### Scenario: 重点标记轨道渲染

- **WHEN** 存在 `highlight: true` 的 `add_note` 或 `session_note` 事件
- **THEN** MiniTimeline SHALL 在盘/局/分轨道下方显示第四根轨道
- **AND** 轨道标签 SHALL 为"标记"，使用紫红色（`#8B5CF6`）
- **AND** 每个重点标记 SHALL 以菱形节点显示在轨道中线位置
- **AND** 菱形颜色 SHALL 为 `#8B5CF6`
- **WHEN** 没有重点标记事件
- **THEN** 第四根轨道 SHALL 不渲染

### Requirement: 事件按钮视觉分组

系统 MUST 将事件标注按钮分为三组，使用统一的视觉样式。

#### Scenario: 按钮分组

- **WHEN** LiveCodingPanel 渲染事件按钮
- **THEN** 按钮 SHALL 分为三组，组间有间距分隔：
  - 第一组（层级事件）：盘开始/盘结束、局开始/局结束、分开始/分结束
  - 第二组（比赛状态）：换边、战术暂停、恢复比赛
  - 第三组（辅助事件）：重点标记、备注、撤销
- **AND** 每组 SHALL 使用组标签或视觉分隔

#### Scenario: 按钮样式

- **WHEN** 渲染事件按钮
- **THEN** 按钮 SHALL 使用浅背景 + 彩色边框 + 彩色文字
- **AND** 按钮高度 SHALL 为 34—38px
- **AND** 按钮圆角 SHALL 为 8px
- **AND** 盘相关按钮使用橙色系
- **AND** 局相关按钮使用蓝色系
- **AND** 分相关按钮使用绿色系
- **AND** "撤销"按钮 SHALL 与其他按钮保持额外间距
- **AND** "撤销"按钮 SHALL 使用红色系
