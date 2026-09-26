# Shot Landing artifact 与可视化

`shot-landings.v1` 是 `shot-rally-events.v1` 之后的可选事实产物。它只能复用 canonical Shot ID，并严格沿 `ShotEvent.trajectory.segment_ids → reconstructed Segment → end_event_id → Event` 选择首次正式 Bounce；不会以时间最近邻创建或替换 Shot。

永久事实是绝对球场坐标 `landing_x_ft/landing_y_ft`。攻击方视角的 `landing_u/landing_v`、`project12.v1` 标签均为可重算派生值；`paper6` 首版保持 `null`。坐标、区域与状态仅用于描述性分析，不承担司线或裁判判定。

方向优先使用接触时刻前后 250 ms 内 canonical `Player_N` 的冻结轨迹；单摄只读 `player_render_trajectory.v2`，双摄 Parent 只读公开 fused trajectory。证据不足时方向与分区 fail closed，绝不使用落点所在半场反推击球方向。

前端落点页由 selected Job 的 `shot_landings_url` 独立门控，不借用最新任务或球路产物。连续落点和项目十二区共享同一筛选集合与 Shot 选择；界外坐标保留且不 clamp，无坐标 Shot 只进入状态统计和列表。视频回溯保留 `analysisJob` 并以 `timestamp_ms - 1200 ms` 预滚动。

首版 OUT：论文六区边界、双摄逐 Shot 双视图融合、裁判判定、技能评分和自动战术建议。

## 脱敏产物冒烟记录

仓库内脱敏真实分析产物 `backend/data/outputs/job-04692d6f43/` 已用于组合冒烟。测试直接消费其 reconstructed trajectory 与 player render trajectory，并以脱敏 canonical Shot 引用核对：`flight-2 → bounce-2` 保留 `1200 ms` 和界外 `y=-0.513 ft`，方向转换为 `rotate_180`；`flight-6 → bounce-4` 保留 `4700 ms`、界内坐标和 `identity`。这项验证只证明已持久化证据的组合与展示契约，不代表当前环境重新运行了检测模型。

## 验证边界

本次已运行后端相关 pytest、前端落点与工作区测试、TypeScript/Vite production build，以及本次涉及文件的 ESLint，并补充了真实视频隔离短片验收。短片验收只能证明端到端链路能够产出，不替代逐帧人工标注下的召回率、误检率和标定漂移评估。

## 真实双摄修复验收（2026-09-22）

本机已启用实际人物模型，在同一份双摄素材的隔离短片上重新运行 `joint_tracking_v2`。17.75–23.75 秒样本生成 4 名 canonical 球员、710 个球场轨迹点、双视角人物叠加、位置热力图、11 个 canonical Shot、normalized metrics、performance insights 与真实报告；报告累计移动距离约 45.1 ft。此结果证明人物检测、双摄轨迹、指标与报告链路能够产出非空结果，不代表全场识别精度已经人工标注评估。

为覆盖落点链路，另对 32–39 秒片段运行同一流程：生成 4 名球员、837 个球场轨迹点、15 个 Shot，并从正式 `Bounce` 事件得到 1 个可用落点（`shot-009 → flight-12 → bounce-1@cam_1`，球场坐标约 `11.82, 29.53 ft`，派生分区 `T-C`）；两机位均保留原生 image-space 球路，tracking-only 发球层发布 1 个候选并标记为 `partial`。这仍是算法结果而非人工真值。

旧任务 `job-e97318f10c` 的持久化球事件与分段引用可无模型重跑恢复，共组合 834 个 Shot，其中 122 个有弹跳球场坐标、47 个满足当前十二区方向与质量门槛。恢复前 JSON 已按时间戳备份，恢复产物记录源摘要与恢复方法。上述数量是算法候选，不是人工确认的真实击球/落点数量。

骨架按当前产品范围继续显式标记不可用。发球层在无骨架时仅发布 tracking-only 候选；页面不得将其表述为确认发球。历史任务原先没有人物检测，因此人物热力图、运动报告和击球者归属无法从空产物恢复，必须用修复后的推理配置重新计算。
