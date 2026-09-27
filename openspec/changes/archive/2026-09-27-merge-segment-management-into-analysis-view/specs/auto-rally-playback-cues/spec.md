# auto-rally-playback-cues Delta

## MODIFIED Requirements

### Requirement: 回放提示按数据可选启用

回放提示能力 SHALL 以可选数据启用的方式实现，未提供自动回合数据的调用方 MUST NOT 观察到任何渲染或交互变化。

#### Scenario: 未传入自动回合数据

- **WHEN** 调用方不传入当前自动回合与自动回合区间
- **THEN** 播放器 SHALL NOT 渲染中央叠加层
- **AND** 进度条 SHALL NOT 附加区间配色样式，SHALL 保持其既有上色外观
- **AND** 其余 DOM 结构与交互行为 SHALL 与启用前一致

#### Scenario: 其它调用点不受影响

- **WHEN** 其它页面以不传自动回合数据的方式使用同一播放器组件
- **THEN** 这些页面的渲染与交互 SHALL 保持不变

#### Scenario: 保持只读回放约束

- **WHEN** 回放提示与区间配色生效
- **THEN** 页面 SHALL NOT 发送 Segment PATCH、边界复核决定或 AnalysisBatch 创建请求
- **AND** SHALL NOT 用本地状态修改任何 `CaptureSegment` 边界
