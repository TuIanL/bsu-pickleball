## 1. 后端配置与检测接入

- [x] 1.1 核对 `Settings` 中球模型路径、球检测、弹跳检测、分析叠加视频和位置可视化开关，补齐缺失的默认值、环境变量说明和测试覆盖
- [x] 1.2 将 multi-target/ball detector adapter 接入 `AnalysisPipeline`，确保缺少模型、adapter 或运行时依赖时返回 skipped/unavailable 诊断而不是中断任务
- [x] 1.3 扩展检测记录归一化，使 `player` 与 `ball` 可写入同一 `detections.jsonl` 合同，并保留 unsupported/low-confidence class 诊断
- [x] 1.4 为启用但无候选、部分输入可用、检测失败等路径增加 pipeline stage status、detail 和 counters

## 2. 球轨迹与弹跳 pipeline

- [x] 2.1 在真实分析任务中调用球轨迹引擎，使用 frame timing、视频 metadata、homography 和 detector candidates 生成 raw trajectory samples
- [x] 2.2 接入 trajectory cleaner，输出 `cleaned_ball_trajectory.json`，并保留 filtering、interpolation、coordinate_system 和 coverage metadata
- [x] 2.3 在 `PICKLEBALL_ENABLE_BOUNCE_DETECTION` 启用且 cleaned trajectory 可用时运行弹跳候选检测，输出 `bounce_events.json`
- [x] 2.4 确保球轨迹或弹跳阶段失败时不破坏现有 player tracking、pose、serve、movement 和 source video 输出

## 3. Artifact API 与结果合同

- [x] 3.1 将 `detections`、`ball-trajectory`、`cleaned-ball-trajectory`、`bounce-events` 和可选 `ball-overlay` 的 path/url/status/detail 写入 `AnalysisPipelineResult.artifacts`
- [x] 3.2 确认 artifact API 对已生成 JSON、JSONL 和缺失已知 artifact 分别返回正确响应，并保持旧 artifact 行为兼容
- [x] 3.3 更新 storage/result serialization，保证新增 artifact 字段可选，旧任务结果仍可加载
- [x] 3.4 为真实生成、配置关闭、依赖缺失、无候选和失败路径补充后端单元或集成测试

## 4. 前端工作台与报告展示

- [x] 4.1 扩展可视分析工作台的 layer 状态，使球轨迹、球 overlay 和弹跳候选可独立加载、失败和切换
- [x] 4.2 在真实 job 中仅使用真实球相关 artifact 渲染球层或弹跳 marker，缺失时显示 skipped/unavailable/no-detection/partial/failed 状态
- [x] 4.3 更新报告模块，使其可展示球轨迹覆盖、弹跳候选数量、时间点和复盘入口，同时继续隐藏未实现的击球、回合、比分和战术结论
- [x] 4.4 确保 demo 路由可继续展示示例球路，但真实 job 页面不会把 demo 数据混作上传视频分析结果

## 5. 文档与验证

- [x] 5.1 更新 `models/README.md`、`storage/README.md` 和相关开发说明，将“保持禁用/out of scope/MVP 暂不生成”改为可配置启用与降级说明
- [x] 5.2 运行后端测试，至少覆盖默认关闭和启用球分析的核心路径
- [x] 5.3 运行前端构建或相关测试，验证新增 layer/report 状态不会破坏现有页面
- [x] 5.4 使用 `openspec validate activate-match-analysis-pipeline-capabilities --strict` 验证 change
