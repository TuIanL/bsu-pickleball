## 1. Schema 分层

- [x] 1.1 在 backend tracking/calibration schema 中拆分严格标定点和投影观测点类型，保留现有 JSON 字段形状
- [x] 1.2 将 `ProjectedTrackPoint.court_point` 迁移到投影观测点类型，确保有限数值坐标可序列化
- [x] 1.3 保持 manual/semi-automatic calibration 输入继续使用严格 `x 0..20 ft`、`y 0..44 ft` 校验

## 2. 投影与指标边界处理

- [x] 2.1 更新 player projector 和 player identity 导出逻辑，避免容差内越界投影点触发严格标定点校验
- [x] 2.2 在 analysis pipeline 的 metrics 输入入口集中排除标准球场边界外观测点
- [x] 2.3 确认 tracking 或 player trajectory artifact 仍保留原始投影观测坐标用于诊断

## 3. 回归测试与验证

- [x] 3.1 增加投影观测 schema 测试，覆盖 `y = 44.2195 ft` 可作为 `ProjectedTrackPoint` 序列化
- [x] 3.2 增加标定 schema 测试，覆盖越界标定控制点仍被拒绝
- [x] 3.3 增加 metrics 入口测试，覆盖标准边界外投影观测不会参与距离、速度、热力图或区域指标
- [x] 3.4 运行相关 backend 测试，确认 player tracking、identity、metrics 和 calibration 现有行为未回退
