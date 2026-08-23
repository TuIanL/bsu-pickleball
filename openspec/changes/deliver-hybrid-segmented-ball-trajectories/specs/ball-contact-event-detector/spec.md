## ADDED Requirements

### Requirement: 击球候选检测使用真实时间连续性
系统 SHALL 以 `timestamp_sec`、effective FPS 和 frame stride 判断击球候选前后的连续观测、长缺失与最小事件间隔，MUST NOT 使用固定 `frame_index` 差为 1 作为连续条件。

#### Scenario: 抽帧轨迹中的正常连续点
- **WHEN** 连续处理样本的 source frame index 差等于配置 frame stride 且时间差在容差内
- **THEN** detector SHALL 将其作为连续上下文参与方向和速度突变检测
- **AND** SHALL NOT 将该点当成长缺失后的首次重新锁定

#### Scenario: 真实长时间丢失
- **WHEN** 相邻有效观测的时间差超过配置的 contact context gap
- **THEN** detector SHALL 在缺口两侧停止构造击球候选
- **AND** SHALL 保存基于秒的拒绝诊断

