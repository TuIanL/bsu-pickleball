## 1. Reference 诊断模型

- [x] 1.1 在 `courtvision_calibration_engine` 中新增 reference line support 评分逻辑，基于自动标定 keypoints 将标准球场线投影回图像并计算 mask 支持度
- [x] 1.2 定义 structured diagnostics 数据模型，覆盖 reference score、coverage、supported line 数量、容忍阈值和组合 confidence breakdown
- [x] 1.3 明确组合 confidence 与 reject 门槛规则，并让 reference 低支持度能够成为显式 rejection reason

## 2. 自动标定服务接入

- [x] 2.1 扩展 `AutomaticCalibrationResponse` 相关 schema，增加 optional 的 reference diagnostics 与 confidence breakdown 字段
- [x] 2.2 在 `AutomaticCalibrationService.suggest()` 中接入 reference 评分、组合 confidence 和新的 available/rejected 判定逻辑
- [x] 2.3 更新自动标定 preview 生成逻辑，使预览图包含 projected court lines 和 reference support 摘要

## 3. 前端诊断展示与兼容

- [x] 3.1 更新自动标定响应的前端类型和客户端适配，使新增 diagnostics 字段可被安全读取
- [x] 3.2 在上传/标定工作流中展示 final confidence、reference 解释、主要 rejection reason 和增强后的 preview 文案
- [x] 3.3 保持旧响应兼容：当新增 diagnostics 缺失时，界面继续使用现有字段稳定降级

## 4. 验证

- [x] 4.1 为 reference line support 和组合 confidence 逻辑补充后端单元测试或针对性诊断测试
- [ ] 4.2 验证自动标定 `available`、`rejected`、`unavailable` 三类结果的响应字段与 preview 输出（**需真实视频 + 运行后端服务**）
- [ ] 4.3 手工检查上传流程中的自动标定展示，确认用户可以基于增强诊断做接受、修正或回退手工标定决策（**需启动前后端服务**）
