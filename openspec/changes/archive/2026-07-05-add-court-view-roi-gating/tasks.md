## 1. Schema 与存储

- [x] 1.1 定义 court-view/ROI artifact schemas，包含状态、detail、阈值、frame counters、candidate segments、ROI bounds 和诊断计数
- [x] 1.2 扩展 `AnalysisArtifacts` 与 pipeline result，使 raw result 能引用 court-view/ROI artifact URL、路径、状态和说明
- [x] 1.3 在 storage service 中增加 court-view/ROI artifact 的 JSON path 和 API artifact 类型映射

## 2. Detection ROI

- [x] 2.1 实现从标定四角图像点和 source frame dimensions 推导 expanded ROI 的纯函数
- [x] 2.2 为 ROI 推导增加边界裁剪、扩展比例、缺失角点、异常几何和 full-frame fallback 诊断
- [x] 2.3 将 ROI 接入 player detection 路径，选择裁剪推理或全帧推理后过滤，并确保 bbox/footpoint 保持源帧坐标
- [x] 2.4 记录 ROI 外过滤数量、ROI 不可用原因和配置禁用状态

## 3. Court-view Gate

- [x] 3.1 实现 court-view frame scorer，优先使用标定/参考帧进行低成本图像匹配，并在不可用时返回保守状态
- [x] 3.2 实现连续帧状态机，支持开启/结束 candidate segment、短暂抖动容忍、阈值配置和 frame/timestamp 记录
- [x] 3.3 区分 `gated_non_court_view`、`no_detections`、`gate_unavailable` 和 `diagnostic_only` 等诊断原因

## 4. Pipeline 接入

- [x] 4.1 在 `AnalysisPipeline._run_tracking` 逐帧循环中接入 court-view gate 与 ROI 诊断计数
- [x] 4.2 当 gate 明确非球场且跳过启用时，跳过 person detection、tracking update 和 pose estimation，并记录 gated frame
- [x] 4.3 写入 court-view/ROI artifact，并在 pipeline stages 中报告 candidate segment 数量、gated frame 数、ROI 状态和过滤计数
- [x] 4.4 确认 gate/ROI 不可用时现有 tracking、pose、projection、metrics 和 serve-start 路径仍按原行为完成

## 5. API 与前端兼容

- [x] 5.1 暴露 court-view/ROI artifact retrieval endpoint 或复用现有 artifact API 类型分发
- [x] 5.2 确保 job status/raw result 客户端忽略新 artifact 字段时不影响 source video、tracking overlay、pose overlay 和 metrics 展示
- [x] 5.3 在可见 UI 或诊断文案中避免把 court-view candidates 描述为完整 rally、得分回合或战术事件

## 6. 测试与验证

- [x] 6.1 添加 ROI 推导单元测试，覆盖正常四角点、画面边界裁剪、缺失输入和异常几何
- [x] 6.2 添加 court-view 状态机单元测试，覆盖连续开启、连续结束、短暂抖动和视频末尾收尾
- [x] 6.3 添加 pipeline 集成测试，验证 gated frame 不产生 person detection/pose，且 artifact counters 正确
- [x] 6.4 添加降级测试，验证缺少参考帧或 ROI 输入时 pipeline 不失败并输出 skipped/unavailable 诊断
- [x] 6.5 运行后端测试和相关前端类型检查，确认新增 artifact 字段不破坏现有 job/result 消费
