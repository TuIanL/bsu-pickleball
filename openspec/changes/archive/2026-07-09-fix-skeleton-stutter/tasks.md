## 1. 后端：新增任务级门控参数覆盖

- [x] 1.1 在 `PickleballSettings` 中增加 `court_view_match_threshold` 字段（已存在 L130，检查是否需要拆分出任务级覆盖）
- [x] 1.2 在分析任务请求 schema 中增加可选字段 `court_view_match_threshold: float | None`，传入 `run_pipeline` 覆盖默认配置
- [x] 1.3 在 `analysis_pipeline.py` 中读取该覆盖值，初始化 court_view_scorer 时传入替代默认阈值
- [x] 1.4 在 `court_view_roi.json` 的 `thresholds` 中记录实际使用的 match_threshold（含覆盖来源）
- [x] 1.5 高剔除率预警：当 `non_court_view_frame_count / processed_frame_count > 0.9` 时，在 artifact detail 中加入诊断提示

## 2. 前端：骨架空洞淡出机制

- [x] 2.1 在 `videoOverlayPlayback.ts` 中新增 `MAX_POSE_GAP_SECONDS` 常量（默认 0.5s），检测 `findFrameWindow` 返回的窗口跨度是否超过该阈值
- [x] 2.2 修改 `resolvePoseFrame` 返回值类型，支持 `null` / 标记字段表示"骨架应隐藏"
- [x] 2.3 在渲染侧（视频叠加播放组件）根据隐藏标记执行 CSS opacity 过渡（渐入/淡出，duration 0.3s）
- [x] 2.4 确保淡出/淡入不破坏检测框等其他叠加元素的渲染（检测框走不同路径，不受此影响）

## 3. 验证

- [x] 3.1 用 job-4879e5beb4 的视频 + 关门控（`enable_court_view_gate=false`）重跑，确认骨架覆盖率回归正常
- [x] 3.2 用 job-4879e5beb4 的视频 + 调低阈值（`court_view_match_threshold=0.5`）重跑，对比骨架覆盖率和质量
- [x] 3.3 手动测试前端：在空洞区间骨架是否正确淡出，回到有数据区间是否淡入
