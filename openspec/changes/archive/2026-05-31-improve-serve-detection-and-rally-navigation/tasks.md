## 1. 后端覆盖诊断模型

- [x] 1.1 扩展发球事件 schema，新增可选覆盖诊断字段，记录源视频、tracking、pose、trajectory、score series 和候选的时间覆盖摘要
- [x] 1.2 在 `ServeStartDetector` 中汇总评分样本、候选、输入 artifact 的最早/最晚时间和覆盖比例
- [x] 1.3 在分析 pipeline 的 `serve-start-detection` 阶段 counters 中写入覆盖诊断摘要和输入缺口 warning
- [x] 1.4 为旧 artifact 兼容补前端/后端类型默认值，确保缺少覆盖诊断时不会报错

## 2. 发球调试 artifact 完整性

- [x] 2.1 将 rejected 明细上限之外的信息聚合为按时间段和拒绝原因分桶统计
- [x] 2.2 扩展 `serve_debug_candidates.json` 和 `serve_score_series.json` 输出，使其包含评分时域最早/最晚时间、bucket 统计和输入可用状态
- [x] 2.3 增加后端测试覆盖长视频后半段 rejected 仍可通过 bucket 统计复盘
- [x] 2.4 确认 debug artifact 生成失败时仍不影响 `serve_events.json` 和基础分析结果

## 3. Player trajectory 覆盖诊断

- [x] 3.1 在 player trajectory artifact 或 identity diagnostics 中输出每个 `player_id` 的样本数量、最早/最晚时间、状态分布和源 track 历史摘要
- [x] 3.2 记录 tracking 仍存在但 target-court eligibility、primary-player selection 或 identity assignment 未产生 trajectory 样本的时间段摘要
- [x] 3.3 在发球检测消费 player trajectory 时识别 trajectory 提前中断，并把诊断转写到发球事件覆盖摘要
- [x] 3.4 增加后端测试覆盖 tracking 全视频存在但 player trajectory 提前中断的诊断输出

## 4. 发球检测降级能力

- [x] 4.1 当 trajectory 覆盖不足但 tracking overlay 后续仍有检测时，启用保守 tracking/ROI 降级候选生成
- [x] 4.2 当 pose 后续可用但 trajectory 缺失时，允许使用手臂峰值辅助降级候选，但必须标记 `partial` 和真实 source signals
- [x] 4.3 确保降级候选缺少球场坐标时不伪造底线分数，并在 `reason` 中说明缺失信号
- [x] 4.4 增加单元测试覆盖 trajectory 上下文候选、tracking 降级候选、pose 降级候选和降级后无候选四类结果

## 5. 前端发球候选导航条

- [x] 5.1 新增或抽取 `ServeRallyStrip` 组件，接收发球候选、当前播放时间、时长、加载状态和跳转回调
- [x] 5.2 将真实视频发球候选主展示从播放器进度条 marker 迁移到播放器下方横向滚动矩形卡片
- [x] 5.3 每个候选卡片显示序号、发球时间、置信度、检测模式和简短信号摘要，并点击跳转到 `seek_time_seconds`
- [x] 5.4 高亮当前播放时间命中的候选片段，候选多时保持容器宽度与播放器齐平并支持横向平滑滚动
- [x] 5.5 在导航条区域展示 loading、failed、no_candidates、unavailable 和 partial 状态，且不阻塞视频播放或 overlay 层

## 6. 前端类型和测试

- [x] 6.1 更新 TypeScript `ServeEventsArtifact` 类型，加入可选覆盖诊断字段
- [x] 6.2 更新 `resolveServeMarkers` 或新增解析 helper，兼容旧 artifact 并裁剪无效时间
- [x] 6.3 增加前端单元测试覆盖导航条渲染、点击跳转、横向溢出、多候选高亮和旧 artifact 兼容
- [x] 6.4 运行相关 `vitest` 测试，确认现有 marker 解析测试继续通过

## 7. 验证和回归

- [x] 7.1 运行后端发球检测、player identity、API smoke 相关测试
- [x] 7.2 使用本地已有长视频输出或构造 fixture 验证覆盖诊断能指出 score series 只覆盖前段的问题
- [x] 7.3 启动前端开发服务，用真实 job 页面检查播放器、overlay、导航条和状态 rail 不重叠
- [x] 7.4 用桌面和窄屏视口验证导航条宽度、横向滚动、卡片文字和视频控制区布局
