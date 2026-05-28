## 1. 数据模型与配置

- [x] 1.1 扩展发球事件 schema，新增候选片段时间窗、检测模式、上下文状态、signal scores 和 optional debug artifact 引用，同时保持旧 `serve_events.json` 可解析
- [x] 1.2 扩展 pipeline artifact schema，增加发球 score、候选调试 JSON、候选 clips manifest 和 debug overlay 的 optional 路径/URL/状态字段
- [x] 1.3 增加发球时刻检测配置项，包括 `baseline_margin_ft`、发球前静止窗口、发球后验证窗口、最小候选间隔、pose 平滑窗口、debug artifact 开关和 clip 导出上限
- [x] 1.4 为 court unit 处理新增共享 helper，支持 `m`、`ft`、`feet` 及缺失单位的保守降级

## 2. 上下文发球时刻检测器

- [x] 2.1 新增或重构检测器模块，使其接收 tracking、player trajectories、pose frames 和可选源视频帧访问器
- [x] 2.2 实现底线附近过滤，按 `court_unit` 将标准场地长宽和底线 margin 转换到输入坐标单位
- [x] 2.3 实现发球前低速准备窗口判断，并将其作为候选进入评分前的上下文门槛
- [x] 2.4 实现 pose 手腕/肘部速度计算、关键点置信度过滤、短窗口平滑和局部峰值定位
- [x] 2.5 实现无 pose 或低置信 pose 时的 ROI/bbox 局部运动降级信号，并在候选中记录降级检测模式
- [x] 2.6 实现发球后回合激活评分，统计候选后窗口内主要球员持续运动、多人参与和 tracking 连续性
- [x] 2.7 实现候选打分、去重、最小间隔、置信度归一化和 reason/signal breakdown 生成
- [x] 2.8 保留不可用、无候选、partial 和 available 状态分支，确保检测失败不影响基础分析结果

## 3. 调试与导出 artifact

- [x] 3.1 实现候选调试 JSON 写入，记录候选、被拒绝峰值、阈值摘要、court position、检测模式和 signal scores
- [x] 3.2 实现 score 时间序列 CSV 或 JSON 写入，覆盖每个采样时间点和每个候选球员的核心分数
- [x] 3.3 实现候选 clips manifest 和可选短片段导出，按候选时间窗裁剪并限制导出数量
- [x] 3.4 实现可选 debug overlay 生成，显示 bbox、player_id、底线状态、关键点或 ROI 降级信号、峰值和候选区间
- [x] 3.5 确保 debug artifact 生成失败时主 `serve_events.json` 仍可用，并记录局部失败状态

## 4. Pipeline 与 API 集成

- [x] 4.1 在 analysis pipeline 中用上下文检测器替换或包裹当前发球检测阶段，并传入 tracking、trajectory、pose 和源视频元数据
- [x] 4.2 将发球检测阶段 counters 扩展为候选数量、输入信号、检测模式、debug artifact 状态和单位信息
- [x] 4.3 写入新的 optional artifact 文件，并在 pipeline result artifacts 中暴露对应 URL、状态和说明
- [x] 4.4 扩展 artifact route，允许读取发球调试 JSON、score 时间序列、clips manifest 和 debug overlay，同时保持不存在 artifact 时返回明确错误
- [x] 4.5 确认任务删除或输出目录清理时会处理新增发球调试文件

## 5. 前端展示

- [x] 5.1 更新 TypeScript 类型，支持发球候选 signal scores、检测模式、候选片段时间窗和 debug artifact 引用
- [x] 5.2 更新真实视频 marker tooltip 或状态区域，展示发球时刻候选的检测模式、置信度和信号摘要
- [x] 5.3 保持发球事件 artifact 独立加载和失败降级，不让 debug artifact 加载状态阻塞视频、tracking 或 pose overlay
- [x] 5.4 确保 UI 文案使用“发球候选”或“发球时刻候选”，不表达完整回合切分、比分或战术结论
- [x] 5.5 为 debug artifact 提供非阻塞入口或状态说明，供研究/复盘使用

## 6. 测试与验证

- [x] 6.1 添加米制轨迹和英尺轨迹的底线过滤单元测试，覆盖单位缺失的保守降级
- [x] 6.2 添加发球前静止门槛测试，确保连续回合中的普通挥拍峰值不会被高分通过
- [x] 6.3 添加 pose 手腕/肘部峰值定位测试，验证候选 anchor、pre-roll seek 和 signal scores
- [x] 6.4 添加无 pose 降级测试，验证 ROI/bbox 检测模式输出 `partial` 或降级说明
- [x] 6.5 添加发球后回合激活测试，覆盖真实发球、练习挥拍和短回合边界情况
- [x] 6.6 添加 debug artifact 写入和局部失败测试，确保主发球事件 artifact 不被阻塞
- [x] 6.7 更新前端 marker 解析和 tooltip 测试，覆盖新字段、旧 artifact 和视频时长裁剪
- [x] 6.8 使用现有实拍长视频 artifact 做一次人工抽样复盘，记录候选数量、明显误报类型和后续调参建议
