## 1. 后端数据契约与存储

- [x] 1.1 新增发球事件 Pydantic schema，覆盖 artifact 元数据、事件字段、状态枚举、置信度、`timestamp_seconds` 和 `seek_time_seconds` 校验。
- [x] 1.2 扩展 pipeline artifacts schema，加入发球事件 URL、状态和说明字段，保持旧结果 optional 兼容。
- [x] 1.3 扩展 storage service，提供发球事件 artifact JSON 路径。
- [x] 1.4 扩展 artifact API，支持读取发球事件 JSON，并在文件缺失时返回明确 404。

## 2. 发球开始候选检测

- [x] 2.1 新增发球开始检测模块，接收视频元数据、tracking frames、player trajectories 和可选 pose frames 作为输入。
- [x] 2.2 实现 MVP 候选规则：稳定站位后动作/速度突变、候选最小间隔、置信度评分和 reason 输出。
- [x] 2.3 实现降级状态：无输入时 `unavailable`，无候选时 `no_candidates`，低信息量输入时 `partial`。
- [x] 2.4 将发球检测接入 analysis pipeline，在 tracking/pose 输出后生成 artifact 和阶段记录。
- [x] 2.5 确保发球检测失败不会破坏基础结果、tracking overlay、pose overlay 或任务完成状态。

## 3. 前端类型与数据加载

- [x] 3.1 扩展 TypeScript pipeline result 和发球事件 artifact 类型。
- [x] 3.2 在 analysis client 中新增发球事件 artifact 获取函数。
- [x] 3.3 在 job-specific visual analysis 数据加载流程中独立加载发球事件，并维护 loading/available/unavailable/failed 状态。
- [x] 3.4 保持没有发球事件字段的旧任务和 demo 页面行为兼容。

## 4. 播放器 marker 交互

- [x] 4.1 扩展真实视频播放器 props，接收发球事件 artifact、加载状态和状态说明。
- [x] 4.2 在真实视频进度条上渲染发球候选 marker，位置按视频时长计算并限制在有效范围。
- [x] 4.3 为 marker 增加 tooltip 或等效说明，展示“发球候选”、时间、置信度和 reason。
- [x] 4.4 实现点击 marker 跳转到 `seek_time_seconds`，并保持当前 overlay 同步。
- [x] 4.5 显示发球 marker 加载中、不可用、无候选和失败状态，不阻塞播放控制。

## 5. 测试与验证

- [x] 5.1 添加后端 schema 和 detector 单元测试，覆盖 available、partial、no_candidates 和 unavailable。
- [x] 5.2 添加 pipeline/API 测试，验证发球事件 artifact 写入、结果引用、读取和缺失 404。
- [x] 5.3 添加前端数据加载和播放器 marker 逻辑测试，覆盖 marker 渲染、点击 seek 和降级状态。
- [x] 5.4 运行相关后端测试、前端测试和 typecheck/build，记录结果。
- [x] 5.5 用一个真实或 fixture 视频结果手动验证 marker 出现在进度条上，点击后能跳到发球前预卷时刻。
